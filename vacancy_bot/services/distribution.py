"""
Сервис рассылки вакансий пользователям.
Реализует anti-flood, rate limiting и форматирование.
"""

import asyncio
import logging
import re
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config, CATEGORIES, get_moderation_chat_id, moderation_enabled
from database import db
from parser.filter.text_cleaner import remove_telegra_links

logger = logging.getLogger(__name__)


class VacancyDistributor:
    """
    Сервис рассылки вакансий.
    Отправляет вакансии пользователям по их категориям.
    """
    
    def __init__(self, bot: Bot, parser=None):
        self.bot = bot
        self.parser = parser  # Telethon parser для загрузки фото
        self._is_running = False
    
    def _clean_hashtags(self, text: str) -> str:
        """Удаляет хэштеги, сохраняя переносы строк."""
        text = re.sub(r"#\w+", "", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _normalize_username(self, value: str) -> str:
        return value.lower().lstrip("@").strip()

    def _is_channel_contact(self, contact: str, source: Optional[str]) -> bool:
        """Контакт совпадает с каналом-источником — не использовать."""
        if not contact or not source:
            return False
        if not contact.startswith("@"):
            return False
        contact_user = self._normalize_username(contact)
        source_user = self._normalize_username(source.replace("https://t.me/", ""))
        if not contact_user or not source_user:
            return False
        return contact_user == source_user

    def _extract_contact(self, text: str, exclude_source: Optional[str] = None) -> Optional[str]:
        """
        Извлекает контакт из текста вакансии.
        Приоритет: @username > телефоны > email.
        
        Args:
            text: Текст вакансии
            
        Returns:
            Контакт в формате @username (предпочтительно), телефон или email
        """
        # Сначала ищем контакт в формате "Контакты для отклика: @username" или "Контакты: @username"
        contact_line_match = re.search(
            r'(?:контакт[ы]?\s+для\s+отклика|контакт[ы]?|связь|написать|писать|писать\s+в|отклик|откликаться)[:]\s*(@[\w]+)',
            text,
            re.IGNORECASE
        )
        if contact_line_match:
            username = contact_line_match.group(1)
            username_lower = username.lower()
            if not any(skip in username_lower for skip in ['bot', 'admin', 'support', 'help', 'vakansii']):
                if not self._is_channel_contact(username, exclude_source):
                    return username
        
        # Ищем секцию "Контакты:" и извлекаем все контакты оттуда
        contacts_section_match = re.search(
            r'контакт[ы]?[:]\s*([^\n]+(?:\n[^\n]+)*?)(?=\n\n|\n[А-Я]|\n[а-я]|\n[A-Z]|\n[a-z]|$)',
            text,
            re.IGNORECASE | re.MULTILINE
        )
        if contacts_section_match:
            contacts_section = contacts_section_match.group(1)
            
            # Ищем @username в секции контактов
            telegram_in_section = re.findall(r'@[\w]+', contacts_section)
            for match in telegram_in_section:
                username = match.lower()
                if not any(skip in username for skip in ['bot', 'admin', 'support', 'help', 'vakansii']):
                    if not self._is_channel_contact(match, exclude_source):
                        return match
            
            # Ищем телефон в секции контактов (приоритет перед email)
            phone_in_section = re.search(
                r'\+?\d{1,3}[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
                contacts_section
            )
            if phone_in_section:
                phone = phone_in_section.group(0).strip()
                # Очищаем от лишних символов, но сохраняем формат
                phone = re.sub(r'[\s\-\(\)]+', '', phone)
                if phone.startswith('8') and len(phone) == 11:
                    phone = '+7' + phone[1:]
                elif not phone.startswith('+') and len(phone) == 10:
                    phone = '+7' + phone
                elif not phone.startswith('+') and len(phone) == 11 and phone.startswith('7'):
                    phone = '+' + phone
                return phone
            
            # Ищем email в секции контактов
            email_in_section = re.search(
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                contacts_section
            )
            if email_in_section:
                return email_in_section.group(0)
        
        # Ищем @username (Telegram) по всему тексту - приоритет
        # Исключаем ботов и служебные аккаунты
        telegram_matches = re.findall(r'@[\w]+', text)
        for match in telegram_matches:
            username = match.lower()
            if not any(skip in username for skip in ['bot', 'admin', 'support', 'help', 'vakansii']):
                if not self._is_channel_contact(match, exclude_source):
                    return match

        for match in telegram_matches:
            if 'vakansii' not in match.lower() and not self._is_channel_contact(match, exclude_source):
                return match
        
        # Ищем телефоны по всему тексту (формат +7, 8, или без кода)
        phone_patterns = [
            r'\+7[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # +7XXXXXXXXXX
            r'8[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # 8XXXXXXXXXX
            r'\+?\d{1,3}[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # Общий паттерн
        ]
        for pattern in phone_patterns:
            phone_match = re.search(pattern, text)
            if phone_match:
                phone = phone_match.group(0).strip()
                # Очищаем от лишних символов
                phone = re.sub(r'[\s\-\(\)]+', '', phone)
                if phone.startswith('8') and len(phone) == 11:
                    phone = '+7' + phone[1:]
                elif not phone.startswith('+') and len(phone) == 10:
                    phone = '+7' + phone
                elif not phone.startswith('+') and len(phone) == 11 and phone.startswith('7'):
                    phone = '+' + phone
                return phone
        
        # Ищем email по всему тексту
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        if email_match:
            return email_match.group(0)
        
        return None
    
    def _smart_truncate(self, text: str, max_length: int) -> str:
        """
        Умное сокращение текста с учетом границ предложений, слов и списков.
        Не обрезает посередине слова, предложения или пункта списка.
        
        Args:
            text: Исходный текст
            max_length: Максимальная длина (включая "...")
            
        Returns:
            Сокращенный текст с "..." в конце (если был обрезан)
        """
        if not text:
            return text
        
        # Если текст короче или равен лимиту, возвращаем как есть
        if len(text) <= max_length:
            return text
        
        # Сначала пытаемся обрезать по пунктам списка (дефисы, маркеры)
        # Это важно для вакансий с обязанностями в виде списка
        list_item_patterns = [
            r'\n\s*[-•*]\s+',  # Дефис, точка, звездочка с новой строки
            r'\n\s*\d+[\.\)]\s+',  # Нумерованный список
            r'\n\s*[а-яА-Я]\)\s+',  # Буквенный список (а), б), в)...
        ]
        
        for pattern in list_item_patterns:
            matches = list(re.finditer(pattern, text))
            if matches:
                # Ищем последний пункт списка, который помещается в лимит
                for match in reversed(matches):
                    # Берем текст до начала этого пункта
                    end_pos = match.start()
                    if end_pos + 3 <= max_length:  # +3 для "..."
                        result = text[:end_pos].rstrip()
                        # Убираем последний неполный пункт если он есть
                        if result and result[-1] not in '.\n':
                            # Ищем последний полный пункт
                            last_item_match = re.search(r'\n\s*[-•*]\s+[^\n]+$', result, re.MULTILINE)
                            if last_item_match:
                                result = result[:last_item_match.start()].rstrip()
                        if len(result) + 3 <= max_length:
                            return result + "..."
        
        # Пытаемся обрезать по границе предложения (точка, восклицательный, вопросительный)
        # Ищем последнее предложение, которое помещается в лимит
        sentence_end_pattern = r'[.!?]\s+'
        matches = list(re.finditer(sentence_end_pattern, text))
        
        if matches:
            # Ищем последнее предложение, которое помещается
            for i, match in enumerate(reversed(matches)):
                # Берем текст до конца этого предложения (включая разделитель)
                end_pos = match.end()
                if end_pos + 3 <= max_length:  # +3 для "..."
                    result = text[:end_pos].rstrip()
                    if len(result) + 3 <= max_length:
                        return result + "..."
            
            # Если ни одно полное предложение не поместилось, берем первое предложение
            first_match = matches[0]
            if first_match.start() + 3 <= max_length:
                result = text[:first_match.start()].rstrip()
                if len(result) + 3 <= max_length:
                    return result + "..."
        
        # Если не получилось обрезать по предложениям, обрезаем по словам
        words = text.split()
        result = ""
        for word in words:
            # Проверяем, поместится ли слово + пробел + "..." в лимит
            separator = " " if result else ""
            test_result = result + separator + word
            if len(test_result) + 3 <= max_length:  # +3 для "..."
                result = test_result
            else:
                break
        
        # Если нашли хотя бы одно слово, добавляем "..."
        if result:
            return result.rstrip() + "..."
        
        # Если ничего не получилось, обрезаем жестко, но хотя бы по границе символа
        # (не обрезаем посередине многострочного символа)
        truncated = text[:max_length - 3]
        # Убираем неполные символы в конце (для UTF-8 и знаков препинания)
        while truncated and not truncated[-1].isalnum() and truncated[-1] not in ' .,!?;:\n-':
            truncated = truncated[:-1]
        return truncated + "..."
    
    def _trim_vacancy_text(self, text: str, contact: Optional[str] = None) -> str:
        """
        Умное сокращение текста вакансии до MAX_VACANCY_LENGTH символов.
        
        Приоритет сохранения:
        1. Должность / кто требуется
        2. Ключевые требования (кратко)
        3. Формат и оплата (если есть)
        4. Контакт для отклика (обязательно)
        
        Что удаляется:
        - Длинные вступления и "вода"
        - Повторяющиеся формулировки
        - Подробные описания условий
        - Второстепенные требования
        - Декоративные фразы
        
        Args:
            text: Исходный текст вакансии
            contact: Контакт для связи (если уже извлечен)
            
        Returns:
            Сокращенный текст вакансии (≤ MAX_VACANCY_LENGTH символов)
        """
        if not text:
            return text
        
        # Извлекаем контакт если не передан
        if not contact:
            contact = self._extract_contact(text)
        
        # Если контакта нет - возвращаем исходный текст (будет отклонен позже)
        if not contact:
            logger.warning("⚠️ Вакансия без контакта, сокращение пропущено")
            return text
        
        # Очищаем текст от HTML тегов для обработки (сохраним их позже если нужно)
        text_clean = re.sub(r'<[^>]+>', '', text)
        
        # Удаляем длинные URL (особенно hooks.pro и другие служебные ссылки)
        # Они занимают много места и не несут полезной информации для пользователя
        # ВАЖНО: удаляем URL только если они на отдельной строке или в начале/конце строки
        url_patterns = [
            r'https?://hooks\.pro/[^\s\n]+',  # Ссылки на hooks.pro
            r'https?://[^\s\n]{50,}',  # Любые URL длиннее 50 символов
        ]
        for pattern in url_patterns:
            # Удаляем URL только если они на отдельной строке или в начале/конце
            text_clean = re.sub(rf'^\s*{pattern}\s*$', '', text_clean, flags=re.IGNORECASE | re.MULTILINE)
            text_clean = re.sub(rf'^\s*{pattern}\s+', '', text_clean, flags=re.IGNORECASE | re.MULTILINE)
            text_clean = re.sub(rf'\s+{pattern}\s*$', '', text_clean, flags=re.IGNORECASE | re.MULTILINE)
            # Также удаляем URL в середине строки, но только очень длинные
            text_clean = re.sub(rf'\s+{pattern}\s+', ' ', text_clean, flags=re.IGNORECASE)
        
        # Удаляем декоративные фразы и "воду"
        water_phrases = [
            r'добро\s+пожаловать\s*[!.]?',
            r'привет\s*[!.]?',
            r'здравствуйте\s*[!.]?',
            r'уважаемые\s+коллеги\s*[!.]?',
            r'дорогие\s+друзья\s*[!.]?',
            r'спешим\s+сообщить\s*[!.]?',
            r'рады\s+предложить\s*[!.]?',
            r'обращаемся\s+к\s+вам\s*[!.]?',
            r'хотим\s+найти\s*[!.]?',
            r'ищем\s+активных\s+и\s+ответственных\s*[!.]?',
            r'компания\s+с\s+многолетним\s+опытом\s*[!.]?',
            r'динамично\s+развивающаяся\s+компания\s*[!.]?',
        ]
        for phrase in water_phrases:
            text_clean = re.sub(phrase, '', text_clean, flags=re.IGNORECASE)
        
        # Удаляем множественные пробелы и переносы строк после удаления URL
        # НО сохраняем структуру текста (не заменяем все пробелы на один)
        text_clean = re.sub(r'[ \t]+', ' ', text_clean)  # Множественные пробелы/табы в одну строку
        text_clean = re.sub(r'\n\s*\n\s*\n+', '\n\n', text_clean)  # Множественные пустые строки
        text_clean = text_clean.strip()
        
        # Извлекаем ключевые части
        parts = {
            'position': None,  # Должность
            'description': None,  # Описание задач/обязанностей
            'requirements': [],  # Требования
            'conditions': None,  # Условия/формат
            'payment': None,  # Оплата
            'contact': contact,  # Контакт
        }
        
        text_lower = text_clean.lower()
        lines = [line.strip() for line in text_clean.split('\n') if line.strip()]
        
        # Паттерны для извлечения информации
        position_patterns = [
            r'(?:ищем|нужен|требуется|ищется|вакансия|на\s+позицию|на\s+должность)[:]\s*(.+?)(?:\.|$|требования|условия|оплата)',
            r'(?:должность|позиция|роль)[:]\s*(.+?)(?:\.|$|требования|условия|оплата)',
        ]
        
        for pattern in position_patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                parts['position'] = match.group(1).strip()
                break
        
        # Если не нашли через паттерн, берем первую строку как должность
        if not parts['position'] and lines:
            first_line = lines[0]
            # Проверяем что это не просто приветствие
            if not re.search(r'^(привет|здравствуйте|добро пожаловать|уважаемые|дорогие)', first_line, re.IGNORECASE):
                # Берем первую строку, но умно обрезаем если нужно
                if len(first_line) > 100:
                    parts['position'] = self._smart_truncate(first_line, 97)  # -3 для "..."
                else:
                    parts['position'] = first_line
        
        # Извлекаем описание задач/обязанностей
        description_patterns = [
            r'(?:нужно|требуется|необходимо|задачи|обязанности|работа)[:]\s*(.+?)(?:\.|$|требования|условия|оплата|контакт)',
            r'(?:помогать|заниматься|работать|делать)[:]\s*(.+?)(?:\.|$|требования|условия|оплата|контакт)',
            r'(?:ищем|нужен|требуется)[:]\s*(.+?)(?:\.|$|требования|условия|оплата|контакт)',
        ]
        for pattern in description_patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE | re.DOTALL)
            if match:
                desc_text = match.group(1).strip()
                # Убираем контакты из описания
                desc_text = re.sub(r'@[\w]+', '', desc_text)
                desc_text = re.sub(r'\+?\d{1,3}[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', '', desc_text)
                desc_text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', desc_text)
                desc_text = desc_text.strip()
                if desc_text and len(desc_text) > 15:  # Минимум 15 символов
                    parts['description'] = desc_text
                    break
        
        # Если не нашли описание через паттерн, берем текст после должности как описание
        # ВАЖНО: сохраняем структуру списков (дефисы, маркеры)
        if not parts['description'] and text_clean:
            # Ищем текст после должности, сохраняя структуру (включая списки)
            # Берем все строки до "Контакты", "Требования" и т.д.
            desc_lines = []
            text_lines = text_clean.split('\n')
            skip_first = True  # Пропускаем первую строку (должность)
            
            for line in text_lines:
                line = line.strip()
                if not line:
                    continue
                
                # Пропускаем первую строку если она должность
                if skip_first:
                    skip_first = False
                    continue
                
                # Останавливаемся на ключевых словах
                if re.search(r'^(требования|условия|оплата|контакт|связь|формат|график|зп|зарплат|контакты|мы\s+предлагаем)', line, re.IGNORECASE):
                    break
                
                # Пропускаем строки, которые являются только контактами
                if re.match(r'^[@\+]|^[0-9\+\-\(\)\s]+$|^[a-zA-Z0-9._%+-]+@', line):
                    continue
                
                # Сохраняем строку (включая списки с дефисами)
                if len(line) > 5:
                    desc_lines.append(line)
            
            if desc_lines:
                # Сохраняем структуру списков - объединяем через \n, а не пробел
                desc_text = '\n'.join(desc_lines)
                # Убираем контакты из описания, но сохраняем структуру
                desc_text = re.sub(r'@[\w]+', '', desc_text)
                desc_text = re.sub(r'\+?\d{1,3}[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', '', desc_text)
                desc_text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', desc_text)
                # Убираем множественные пустые строки, но сохраняем одну
                desc_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', desc_text)
                desc_text = desc_text.strip()
                if desc_text and len(desc_text) > 15:
                    parts['description'] = desc_text
        
        # Если все еще не нашли описание, берем весь текст между должностью и контактами/требованиями
        if not parts['description'] and text_clean:
            # Ищем текст между должностью и следующими ключевыми словами
            # Берем текст до первого вхождения "Контакты", "Требования", "Условия" и т.д.
            desc_match = re.search(
                r'(?:(?:ищем|нужен|требуется|ищется|вакансия|на\s+позицию)[:]\s*)?(.+?)(?=\n*(?:контакт|требования|условия|оплата|формат|график|зп|зарплат)[:])',
                text_clean,
                re.IGNORECASE | re.DOTALL
            )
            if desc_match:
                desc_text = desc_match.group(1).strip()
                # Убираем должность если она в начале
                desc_text = re.sub(r'^(?:ищем|нужен|требуется|ищется|вакансия|на\s+позицию)[:]\s*', '', desc_text, flags=re.IGNORECASE)
                # Убираем контакты
                desc_text = re.sub(r'@[\w]+', '', desc_text)
                desc_text = re.sub(r'\+?\d{1,3}[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', '', desc_text)
                desc_text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', desc_text)
                desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                # Берем первые 200 символов
                if desc_text and len(desc_text) > 15:
                    parts['description'] = desc_text[:200]
        
        # Если все еще нет описания, берем весь текст до контактов (кроме должности)
        if not parts['description'] and text_clean:
            # Разбиваем на строки и берем все до "Контакты"
            all_lines = text_clean.split('\n')
            desc_lines = []
            for line in all_lines[1:]:  # Пропускаем первую строку (должность)
                line = line.strip()
                if re.match(r'^(контакт|требования|условия|оплата|формат|график|зп|зарплат)', line, re.IGNORECASE):
                    break
                if line and len(line) > 10:
                    # Пропускаем контакты
                    if not re.match(r'^[@\+]|^[0-9\+\-\(\)\s]+$|@|^[a-zA-Z0-9._%+-]+@', line):
                        desc_lines.append(line)
            if desc_lines:
                desc_text = ' '.join(desc_lines)
                desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                if desc_text and len(desc_text) > 15:
                    parts['description'] = desc_text[:200]
        
        # Извлекаем требования
        req_section = False
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['требования', 'требуется', 'нужно']):
                req_section = True
                continue
            if req_section:
                if any(keyword in line_lower for keyword in ['условия', 'оплата', 'контакт', 'связь']):
                    req_section = False
                    break
                if line and len(line) > 5:
                    parts['requirements'].append(line)
        
        # Если не нашли секцию требований, ищем ключевые слова в тексте
        if not parts['requirements']:
            req_keywords_pattern = r'(?:опыт|знание|умение|навык|уверенное\s+владение|знание\s+язык|знание\s+программ)[:]\s*(.+?)(?:\.|$|,|;|\n)'
            req_matches = re.findall(req_keywords_pattern, text_clean, re.IGNORECASE)
            parts['requirements'] = [m.strip() for m in req_matches[:5]]  # Максимум 5 требований
        
        # Извлекаем условия/формат работы
        conditions_patterns = [
            r'(?:условия|формат\s+работы|график|режим)[:]\s*(.+?)(?:\.|$|оплата|контакт)',
            r'(?:удаленн|remote|офис|гибрид|full.?time|part.?time|полная\s+занятость|частичная)[^\n]*',
        ]
        for pattern in conditions_patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                parts['conditions'] = match.group(1).strip() if match.groups() else match.group(0).strip()
                break
        
        # Извлекаем оплату
        payment_patterns = [
            r'(?:оплат[ае]|зарплат[ае]|ставк[ае]|доход|гонорар)[:]\s*(.+?)(?:\.|$|контакт|руб|€|\$|usd)',
            r'(?:от|до|от\s+\d+.*?до\s+\d+)[\s\d\.,]+(?:руб|€|\$|usd|eur)',
            r'\d+[\s\d\.,]+(?:руб|€|\$|usd|eur|доллар|евро)',
        ]
        for pattern in payment_patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                parts['payment'] = match.group(1).strip() if match.groups() else match.group(0).strip()
                break
        
        # Формируем краткую версию
        result_parts = []
        
        # 1. Должность (обязательно)
        if parts['position']:
            position_text = parts['position']
            # Сокращаем если слишком длинная (умно, по границам слов)
            if len(position_text) > 80:
                position_text = self._smart_truncate(position_text, 77)
            result_parts.append(position_text)
        
        # 2. Описание задач/обязанностей (важно для понимания вакансии)
        # ВАЖНО: описание должно быть всегда, даже если короткое
        if parts['description']:
            description_text = parts['description']
            # Сокращаем описание до 250 символов (увеличено для сохранения списков обязанностей)
            # Умная обрезка сохранит структуру списков
            if len(description_text) > 250:
                description_text = self._smart_truncate(description_text, 247)  # -3 для "..."
            result_parts.append(description_text)
        elif not parts['description'] and text_clean:
            # Если описание не найдено, берем текст между должностью и контактами
            # Это последняя попытка найти хоть какое-то описание
            desc_text = text_clean
            # Убираем должность если она в начале
            if parts['position']:
                desc_text = desc_text.replace(parts['position'], '', 1)
            # Убираем контакты
            if contact:
                desc_text = desc_text.replace(contact, '')
            desc_text = re.sub(r'@[\w]+', '', desc_text)
            desc_text = re.sub(r'\+?\d{1,3}[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', '', desc_text)
            desc_text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', desc_text)
            # Убираем ключевые слова
            desc_text = re.sub(r'(?:требования|условия|оплата|контакт|связь|формат|график|зп|зарплат)[:]\s*[^\n]*', '', desc_text, flags=re.IGNORECASE)
            desc_text = re.sub(r'\s+', ' ', desc_text).strip()
            if desc_text and len(desc_text) > 20:
                if len(desc_text) > 200:
                    desc_text = self._smart_truncate(desc_text, 197)
                result_parts.append(desc_text)
        
        # 3. Требования (кратко, только ключевые)
        if parts['requirements']:
            req_text = 'Требования: '
            req_items = []
            for req in parts['requirements'][:3]:  # Максимум 3 требования
                # Сокращаем каждое требование до 50 символов (умно, по границам слов)
                if len(req) > 50:
                    req_short = self._smart_truncate(req, 47)  # -3 для "..."
                else:
                    req_short = req
                req_items.append(req_short)
            
            req_text += ', '.join(req_items)
            result_parts.append(req_text)
        
        # 4. Условия/формат (если есть место)
        if parts['conditions']:
            conditions_text = f"Условия: {self._smart_truncate(parts['conditions'], 57)}"  # -3 для "..."
            result_parts.append(conditions_text)
        
        # 5. Оплата (если есть место)
        if parts['payment']:
            payment_text = f"Оплата: {self._smart_truncate(parts['payment'], 57)}"  # -3 для "..."
            result_parts.append(payment_text)
        
        # Объединяем части
        result = '\n'.join(result_parts)
        
        # НЕ добавляем контакт здесь - он будет добавлен в format_vacancy
        # Это нужно только для проверки длины
        contact_text = f"Контакты: {contact}"
        
        # Проверяем длину
        contact_text = f"\n\n<b>Контакты для отклика:</b> {contact}"
        total_length = len(result) + len(contact_text)
        
        if total_length > MAX_VACANCY_LENGTH:
            # Нужно еще сократить
            # Резервируем место для контакта и разделителей
            available_length = MAX_VACANCY_LENGTH - len(contact_text) - 20  # -20 для запаса и разделителей
            
            # Приоритет сохранения:
            # 1. Должность (обязательно, но можно сократить)
            # 2. Описание (важно, но можно сократить)
            # 3. Требования (можно сократить или убрать)
            # 4. Условия и оплата (можно сократить или убрать)
            
            new_result_parts = []
            
            # 1. Должность (обязательно, но сокращаем если нужно)
            if result_parts:
                position = result_parts[0]
                max_position_length = min(80, available_length // 3)  # До 1/3 доступного места
                if len(position) > max_position_length:
                    position = self._smart_truncate(position, max_position_length - 3)
                new_result_parts.append(position)
                available_length -= len(position) + 1  # +1 для \n
            
            # 2. Описание (важно, стараемся сохранить максимально)
            if len(result_parts) > 1 and parts['description']:
                description = result_parts[1]
                # Выделяем больше места для описания (до 60% оставшегося места)
                max_description_length = min(200, int(available_length * 0.6))
                if len(description) > max_description_length:
                    description = self._smart_truncate(description, max_description_length - 3)
                if available_length > len(description) + 1:
                    new_result_parts.append(description)
                    available_length -= len(description) + 1
            
            # 3. Требования (сокращаем или убираем)
            if len(result_parts) > 2 and parts['requirements']:
                req_text = result_parts[2]
                max_req_length = min(100, available_length)
                if len(req_text) > max_req_length:
                    # Сокращаем требования более агрессивно
                    req_text = self._smart_truncate(req_text, max_req_length - 3)
                if available_length > len(req_text) + 1:
                    new_result_parts.append(req_text)
                    available_length -= len(req_text) + 1
            
            # 4. Условия и оплата (только если есть место)
            for i in range(3, len(result_parts)):
                part = result_parts[i]
                if available_length > len(part) + 1:
                    new_result_parts.append(part)
                    available_length -= len(part) + 1
                else:
                    break
            
            result = '\n'.join(new_result_parts)
            total_length = len(result) + len(contact_text)
            
            # Если все еще длинно, агрессивно сокращаем описание и должность
            if total_length > MAX_VACANCY_LENGTH and new_result_parts:
                # Сокращаем описание если есть
                if len(new_result_parts) > 1:
                    max_desc_length = MAX_VACANCY_LENGTH - len(contact_text) - len(new_result_parts[0]) - 30
                    if max_desc_length > 20:
                        new_result_parts[1] = self._smart_truncate(new_result_parts[1], max_desc_length - 3)
                
                # Если все еще длинно, сокращаем должность
                result = '\n'.join(new_result_parts)
                total_length = len(result) + len(contact_text)
                if total_length > MAX_VACANCY_LENGTH and new_result_parts:
                    max_position_length = MAX_VACANCY_LENGTH - len(contact_text) - 30
                    if max_position_length > 20:
                        new_result_parts[0] = self._smart_truncate(new_result_parts[0], max_position_length - 3)
                        result = '\n'.join(new_result_parts)
        
        # НЕ добавляем контакт в результат - он будет добавлен в format_vacancy
        # Возвращаем только текст без контакта
        # Убираем контакт из результата если он там есть
        final_result = result.strip()
        if contact and contact in final_result:
            # Удаляем строки с контактом
            contact_patterns = [
                rf'(?:контакт[ы]?\s+для\s+отклика|контакт[ы]?)[:]\s*{re.escape(contact)}',
                rf'{re.escape(contact)}\s*$',
            ]
            for pattern in contact_patterns:
                final_result = re.sub(pattern, '', final_result, flags=re.IGNORECASE | re.MULTILINE)
            final_result = re.sub(r'\n\s*\n+', '\n', final_result).strip()
        
        if not final_result:
            final_result = "Вакансия"
        
        # Финальная проверка длины (без учета контакта, он добавится отдельно)
        # Оставляем запас для контакта (примерно 50 символов для "Контакты для отклика: @username")
        contact_text_length = len(f"\n\n<b>Контакты для отклика:</b> {contact}")
        max_text_length = MAX_VACANCY_LENGTH - contact_text_length - 10  # -10 для запаса
        if len(final_result) > max_text_length:
            # Умное сокращение - обрезаем по границам предложений и слов
            final_result = self._smart_truncate(final_result, max_text_length)
        
        # Логируем если было сокращение
        original_length = len(text)
        final_length = len(final_result)
        
        # Проверяем, что результат не пустой и имеет описание
        if not parts.get('description') and final_result:
            logger.warning(f"⚠️ Вакансия без описания после обработки (должность: {parts.get('position', 'нет')})")
        
        if final_length < original_length:
            logger.info(
                f"✂️ Текст вакансии сокращен: {original_length} → {final_length} символов "
                f"(сокращено на {original_length - final_length}), "
                f"части: должность={bool(parts.get('position'))}, "
                f"описание={bool(parts.get('description'))}, "
                f"требования={len(parts.get('requirements', []))}, "
                f"условия={bool(parts.get('conditions'))}, "
                f"оплата={bool(parts.get('payment'))}"
            )
        
        return final_result
    
    def _generate_hashtags(self, text: str, category_id: str) -> str:
        """
        Генерирует хэштеги для вакансии на основе текста и категории.
        
        Хэштеги по:
        - профессии (из текста)
        - специализации (из категории)
        - формату работы (remote, full-time и т.д.)
        - языку/стеху (если указано)
        
        Args:
            text: Текст вакансии
            category_id: ID категории
            
        Returns:
            Строка с хэштегами через пробел
        """
        text_lower = text.lower()
        hashtags = []
        
        # Хэштеги по категории/специализации (базовые)
        category_data = CATEGORIES.get(category_id, CATEGORIES["other"])
        category_hashtags = category_data.get("hashtag", "").split()
        hashtags.extend(category_hashtags)
        
        # Определяем профессию из текста (более детально)
        profession_patterns = [
            (r'\bбухгалтер\w*\b', ["#бухгалтер", "#accounting", "#finance"]),
            (r'\baccountant\b', ["#accountant", "#accounting", "#finance"]),
            (r'\bразработчик\w*\b', ["#разработчик", "#developer"]),
            (r'\bdeveloper\b', ["#developer"]),
            (r'\bпрограммист\w*\b', ["#программист", "#programmer"]),
            (r'\bprogrammer\b', ["#programmer"]),
            (r'\bдизайнер\w*\b', ["#дизайнер", "#designer"]),
            (r'\bdesigner\b', ["#designer"]),
            (r'\bмаркетолог\w*\b', ["#маркетолог", "#marketer"]),
            (r'\bmarketer\b', ["#marketer"]),
            (r'\bкопирайтер\w*\b', ["#копирайтер", "#copywriter"]),
            (r'\bcopywriter\b', ["#copywriter"]),
            (r'\bменеджер\w*\b', ["#менеджер", "#manager"]),
            (r'\bmanager\b', ["#manager"]),
            (r'\bаналитик\w*\b', ["#аналитик", "#analyst"]),
            (r'\banalyst\b', ["#analyst"]),
            (r'\bтестировщик\w*\b', ["#тестировщик", "#qa", "#tester"]),
            (r'\bqa\b', ["#qa", "#tester"]),
            (r'\bdevops\b', ["#devops"]),
            (r'\bsmm\b', ["#smm"]),
            (r'\bseo\b', ["#seo"]),
        ]
        
        for pattern, tags in profession_patterns:
            if re.search(pattern, text_lower):
                hashtags.extend(tags)
                break  # Берем первую найденную профессию
        
        # Определяем формат работы
        if re.search(r'\b(удаленн|remote|фриланс|freelance|удалённ)\b', text_lower):
            hashtags.append("#remote")
        if re.search(r'\bfull.?time\b', text_lower):
            hashtags.append("#fulltime")
        if re.search(r'\bpart.?time\b', text_lower):
            hashtags.append("#parttime")
        if re.search(r'\bпроект\b', text_lower):
            hashtags.append("#project")
        
        # Определяем язык/стек (технологии)
        tech_patterns = [
            (r'\bpython\b', ["#python"]),
            (r'\bjavascript\b|\bjs\b', ["#javascript", "#js"]),
            (r'\bjava\b', ["#java"]),
            (r'\bphp\b', ["#php"]),
            (r'\bgolang\b|\bgo\b', ["#golang", "#go"]),
            (r'\brust\b', ["#rust"]),
            (r'\bc\+\+\b', ["#cpp"]),
            (r'\bc#\b', ["#csharp"]),
            (r'\breact\b', ["#react"]),
            (r'\bvue\b', ["#vue"]),
            (r'\bangular\b', ["#angular"]),
            (r'\bdjango\b', ["#django"]),
            (r'\bfastapi\b', ["#fastapi"]),
            (r'\blaravel\b', ["#laravel"]),
            (r'\bnode\b', ["#nodejs"]),
            (r'\bfigma\b', ["#figma"]),
            (r'\bphotoshop\b', ["#photoshop"]),
        ]
        
        for pattern, tags in tech_patterns:
            if re.search(pattern, text_lower):
                hashtags.extend(tags)
        
        # Определяем языки (иностранные)
        language_patterns = [
            (r'\bнемецк\w+\s+язык\b|\bgerman\b', ["#немецкийязык"]),
            (r'\bанглийск\w+\s+язык\b|\benglish\b', ["#english"]),
            (r'\bфранцузск\w+\s+язык\b|\bfrench\b', ["#французскийязык"]),
            (r'\bиспанск\w+\s+язык\b|\bspanish\b', ["#испанскийязык"]),
        ]
        
        for pattern, tags in language_patterns:
            if re.search(pattern, text_lower):
                hashtags.extend(tags)
        
        # Убираем дубликаты и пустые, сохраняя порядок
        seen = set()
        unique_hashtags = []
        for tag in hashtags:
            if tag and tag not in seen:
                seen.add(tag)
                unique_hashtags.append(tag)
        
        return " ".join(unique_hashtags) if unique_hashtags else "#freelance"
    
    def _format_text_as_quote(self, text: str) -> str:
        """
        Форматирует текст вакансии как цитату с HTML форматированием.
        Использует <blockquote> для обертки и выделяет важные части жирным/курсивом.
        Убирает мусорные повторы и разговорные фразы.
        
        Args:
            text: Исходный текст
            
        Returns:
            Текст в формате HTML цитаты
        """
        # Убираем мусорные фразы
        garbage_phrases = [
            r'пишите\s+в\s+лс',
            r'напишите\s+в\s+лс',
            r'в\s+личные\s+сообщения',
            r'детали\s+в\s+лс',
            r'в\s+пм',
            r'в\s+личку',
            r'подробнее\s+в\s+лс',
            r'контакт[ы]?\s*[:]\s*$',  # Пустые строки "Контакты:"
        ]
        
        for phrase in garbage_phrases:
            text = re.sub(phrase, '', text, flags=re.IGNORECASE)
        
        # Убираем множественные пробелы (но сохраняем переносы строк)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Убираем множественные пустые строки
        
        # Убираем пустые строки в начале и конце
        text = text.strip()
        
        # Улучшаем форматирование списков (маркеры -, •, *)
        # Заменяем маркеры на более аккуратные
        text = re.sub(r'^[\s]*[-•*]\s+', '', text, flags=re.MULTILINE)
        
        # Убираем лишние пробелы после двоеточий
        text = re.sub(r':\s+', ': ', text)
        
        # Убираем множественные точки и восклицательные знаки
        text = re.sub(r'\.{3,}', '...', text)
        text = re.sub(r'!{2,}', '!', text)
        
        # Выделяем важные секции жирным (ПЕРЕД разбиением на строки)
        # Но только если они еще не отформатированы HTML тегами
        # Проверяем что слово не находится внутри <b>...</b> или <i>...</i>
        section_patterns = [
            (r'(?i)(?<!<b>)(?<!<i>)\b(задачи?[:]?)\b(?!</b>)(?!</i>)', r'<b>\1</b>'),
            (r'(?i)(?<!<b>)(?<!<i>)\b(требования?[:]?)\b(?!</b>)(?!</i>)', r'<b>\1</b>'),
            (r'(?i)(?<!<b>)(?<!<i>)\b(условия?[:]?)\b(?!</b>)(?!</i>)', r'<b>\1</b>'),
            (r'(?i)(?<!<b>)(?<!<i>)\b(оплат[ае]?[:]?)\b(?!</b>)(?!</i>)', r'<b>\1</b>'),
            (r'(?i)(?<!<b>)(?<!<i>)\b(контакт[ы]?[:]?)\b(?!</b>)(?!</i>)', r'<b>\1</b>'),
            (r'(?i)(?<!<b>)(?<!<i>)\b(обязанности?[:]?)\b(?!</b>)(?!</i>)', r'<b>\1</b>'),
            (r'(?i)(?<!<b>)(?<!<i>)\b(ответственность[:]?)\b(?!</b>)(?!</i>)', r'<b>\1</b>'),
            (r'(?i)(?<!<b>)(?<!<i>)\b(график[:]?)\b(?!</b>)(?!</i>)', r'<b>\1</b>'),
            (r'(?i)(?<!<b>)(?<!<i>)\b(формат\s+работы?[:]?)\b(?!</b>)(?!</i>)', r'<b>\1</b>'),
        ]
        
        for pattern, replacement in section_patterns:
            text = re.sub(pattern, replacement, text)
        
        # Выделяем важные слова курсивом (профессии, технологии)
        important_words = [
            (r'\b(удаленн[аяо]?|remote|фриланс|freelance)\b', r'<i>\1</i>'),
            (r'\b(full.?time|part.?time|полная\s+занятость|частичная\s+занятость)\b', r'<i>\1</i>'),
        ]
        
        for pattern, replacement in important_words:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Разбиваем на строки
        lines = text.split('\n')
        
        # Оборачиваем каждую непустую строку (без символов >)
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line:
                # Убираем лишние повторы в начале строки
                line = re.sub(r'^[>•\-\*]\s*', '', line)
                # Экранируем HTML спецсимволы, но сохраняем наши HTML теги
                # Сначала заменяем наши теги на плейсхолдеры
                placeholders = {}
                tag_counter = 0
                for match in re.finditer(r'<(/?)(b|i|u|code|pre|a)([^>]*)>', line):
                    placeholder = f"__TAG_{tag_counter}__"
                    placeholders[placeholder] = match.group(0)
                    line = line.replace(match.group(0), placeholder)
                    tag_counter += 1
                
                # Экранируем оставшиеся HTML спецсимволы
                line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                
                # Восстанавливаем наши теги
                for placeholder, tag in placeholders.items():
                    line = line.replace(placeholder, tag)
                
                formatted_lines.append(line)
            else:
                formatted_lines.append("")
        
        # Убираем множественные пустые строки
        result_lines = []
        prev_empty = False
        for line in formatted_lines:
            if not line:
                if not prev_empty:
                    result_lines.append("")
                prev_empty = True
            else:
                result_lines.append(line)
                prev_empty = False
        
        # Оборачиваем весь текст в <blockquote> для Telegram HTML (без символов >)
        quoted_text = "\n".join(result_lines)
        # Если текст пустой, возвращаем пустой blockquote
        if not quoted_text.strip():
            return "<blockquote></blockquote>"
        
        # Гарантируем, что возвращаем корректный blockquote с закрывающим тегом
        result = f"<blockquote>{quoted_text}</blockquote>"
        
        # Проверяем, что открывающий и закрывающий теги присутствуют
        if result.count('<blockquote>') != result.count('</blockquote>'):
            logger.error(f"Некорректное количество тегов blockquote в результате _format_text_as_quote")
            # Исправляем: удаляем все теги и создаем заново
            content = re.sub(r'</?blockquote>', '', result)
            result = f"<blockquote>{content.strip()}</blockquote>"
        
        return result
    
    @staticmethod
    def _sanitize_html(text: str) -> str:
        """Исправляет незакрытые/неправильно вложенные HTML-теги.
        
        Telegram требует строгую вложенность тегов.
        Этот метод гарантирует, что все открытые теги закрыты
        в правильном порядке (LIFO).
        """
        allowed_tags = {'b', 'i', 'u', 'code', 'pre', 'blockquote', 'a', 's'}
        tag_pattern = re.compile(r'<(/?)(\w+)([^>]*)>')
        
        stack = []  # стек открытых тегов
        result = []
        last_end = 0
        
        for match in tag_pattern.finditer(text):
            is_closing = match.group(1) == '/'
            tag_name = match.group(2).lower()
            
            if tag_name not in allowed_tags:
                continue
            
            result.append(text[last_end:match.start()])
            
            if not is_closing:
                # Открывающий тег
                result.append(match.group(0))
                stack.append(tag_name)
            else:
                # Закрывающий тег
                if tag_name in stack:
                    # Закрываем все теги до нужного (восстанавливаем порядок)
                    tags_to_reopen = []
                    while stack and stack[-1] != tag_name:
                        popped = stack.pop()
                        result.append(f'</{popped}>')
                        tags_to_reopen.append(popped)
                    if stack:
                        stack.pop()
                        result.append(match.group(0))
                    # Переоткрываем вложенные теги
                    for t in reversed(tags_to_reopen):
                        result.append(f'<{t}>')
                        stack.append(t)
                # Если тег не был открыт — просто пропускаем закрывающий
            
            last_end = match.end()
        
        result.append(text[last_end:])
        
        # Закрываем все оставшиеся открытые теги
        while stack:
            result.append(f'</{stack.pop()}>')
        
        return ''.join(result)
    
    def format_vacancy(self, vacancy: Dict) -> str:
        """
        Форматирование вакансии для отправки в новом стандарте FreelanceHub.
        
        Формат:
        🆕 Новая вакансия
        Направление: <emoji + категория>
        
        > Текст вакансии в цитате
        > Контакты для отклика: @username
        
        #хэштеги
        
        Args:
            vacancy: Словарь с данными вакансии
            
        Returns:
            Отформатированный текст сообщения
        """
        category_id = vacancy.get("category", "other")
        category_data = CATEGORIES.get(category_id, CATEGORIES["other"])
        
        source = vacancy.get("source", "")

        text = (vacancy.get("text") or vacancy.get("original_text") or "").strip()
        if not text:
            return ""

        text = remove_telegra_links(text)

        # Удаляем ссылки на фото/изображения (включая с открывающей скобкой)
        text = re.sub(
            r'[(\[]*https?://\S+?\.(?:jpg|jpeg|png|webp|gif|bmp|svg|tiff)(?:\?\S*)?[)\]]*',
            '', text, flags=re.IGNORECASE,
        )
        # Удаляем ссылки на хостинги изображений (teletype, telegraph, imgur и др.)
        text = re.sub(
            r'[(\[]*https?://(?:i\.)?(?:imgur\.com|ibb\.co|postimg\.cc|imgbb\.com|imageban\.ru|'
            r'pic\.re|prnt\.sc|prntscr\.com|joxi\.ru|gyazo\.com|'
            r'img\d*\.teletype\.in|teletype\.in/files|'
            r'telegraph\.controller\.bot|telegraph\.[\w.]+/files|'
            r'sun\d*-\d+\.userapi\.com|pp\.userapi\.com|vk\.com/photo|'
            r'disk\.yandex\.\w+/\S+|drive\.google\.com/\S+/d/)\S*[)\]]*',
            '', text, flags=re.IGNORECASE,
        )
        # Markdown-ссылки на изображения [Текст](image_url) → сохраняем "Текст"
        text = re.sub(
            r'\[([^\]]+)\]\(https?://\S+?\.(?:jpg|jpeg|png|webp|gif)\S*\)',
            r'\1', text, flags=re.IGNORECASE,
        )
        # Markdown-ссылки с текстом на хостинги/telegraph [Текст](url) → сохраняем "Текст"
        text = re.sub(
            r'\[([^\]]+)\]\(https?://(?:telegraph\.\S+|img\d*\.teletype\.\S+|teletype\.in/files)\S*\)',
            r'\1', text, flags=re.IGNORECASE,
        )
        # Пустые markdown-ссылки [](url) → удаляем целиком
        text = re.sub(
            r'\[\]\(https?://\S+?\)',
            '', text, flags=re.IGNORECASE,
        )
        # Убираем оставшиеся пустые скобки []
        text = re.sub(r'\[\s*\]', '', text)

        # Удаляем декоративные разделители (➖➖➖, ━━━, ═══, ——— и т.д.)
        text = re.sub(r'[➖━═—–\-]{3,}', '', text)

        # Удаляем рекламные/спонсорские футеры
        ad_footer_patterns = [
            r'📢?\s*разместить\s+(?:рекламу|вакансию)[^\n]*',
            r'\[?разместить\s+(?:рекламу|вакансию)[^\n]*',
            r'при\s+поддержк[ие]\s+[^\n]*',
            r'реклама\s+в\s+канал[ае][^\n]*',
            r'по\s+вопросам\s+рекламы[^\n]*',
            r'(?:наш|наши)\s+(?:канал[ы]?|чат|бот)[^\n]*подпис[^\n]*',
            r'подписывайтесь\s+на\s+(?:наш|канал)[^\n]*',
        ]
        for pattern in ad_footer_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Очищаем пустые строки, оставшиеся после удаления
        text = re.sub(r'[ \t]+\n', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        if source:
            source_user = self._normalize_username(source.replace("https://t.me/", ""))
            if source_user:
                text = re.sub(
                    rf"(?i)\n*контакт[ы]?(?:\s+для\s+отклика)?[:]\s*@{re.escape(source_user)}\s*",
                    "",
                    text,
                ).strip()

        text = self._clean_hashtags(text)
        contact = self._extract_contact(text, exclude_source=source)

        # Вакансии без контакта для отклика — не отправляем
        if not contact:
            logger.info(
                "⛔ Вакансия %s пропущена: нет контакта для отклика",
                vacancy.get("id", "?"),
            )
            return ""

        quoted_text = self._format_text_as_quote(text)
        if not quoted_text or quoted_text == "<blockquote></blockquote>":
            quoted_text = f"<blockquote>{text}</blockquote>"

        if contact and contact not in text:
            blockquote_match = re.match(r"<blockquote>(.*?)</blockquote>", quoted_text, re.DOTALL)
            if blockquote_match:
                content = blockquote_match.group(1).strip()
                content += f"\n\n<b>Контакты для отклика:</b> {contact}"
                quoted_text = f"<blockquote>{content}</blockquote>"
        
        # Генерируем хэштеги
        hashtags = self._generate_hashtags(text, category_id)
        
        # Формируем финальное сообщение
        header = (
            "🆕 Новая вакансия\n"
            f"Направление: {category_data['name']}\n\n"
        )
        
        footer = f"\n\n{hashtags}"
        
        message = f"{header}{quoted_text}{footer}"
        
        # Санитизация HTML — гарантируем корректную вложенность тегов
        message = self._sanitize_html(message)
        
        return message.strip()

    async def _send_html_messages(self, tg_id: int, message_text: str) -> None:
        """Отправить длинный HTML-текст частями без обрезки."""
        max_len = 4096
        if len(message_text) <= max_len:
            await self.bot.send_message(
                chat_id=tg_id,
                text=message_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return

        parts = message_text.split("\n\n")
        chunk = ""
        for part in parts:
            candidate = f"{chunk}\n\n{part}".strip() if chunk else part
            if len(candidate) <= max_len:
                chunk = candidate
                continue
            if chunk:
                await self.bot.send_message(
                    chat_id=tg_id,
                    text=chunk,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            if len(part) <= max_len:
                chunk = part
            else:
                for i in range(0, len(part), max_len):
                    await self.bot.send_message(
                        chat_id=tg_id,
                        text=part[i:i + max_len],
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                chunk = ""
        if chunk:
            await self.bot.send_message(
                chat_id=tg_id,
                text=chunk,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    
    async def send_vacancy_to_user(
        self, 
        user: Dict, 
        vacancy: Dict
    ) -> bool:
        """
        Отправить вакансию одному пользователю.
        
        Args:
            user: Данные пользователя из БД
            vacancy: Данные вакансии
            
        Returns:
            True если отправлено успешно
        """
        user_id = user["id"]  # ID в нашей БД
        tg_id = user["tg_id"]  # Telegram ID
        vacancy_id = vacancy["id"]
        
        try:
            # Проверяем rate limit
            if not await db.can_send_to_user(user_id):
                logger.debug(f"Rate limit для пользователя {tg_id}")
                return False
            
            # Проверяем не отправляли ли уже
            if await db.was_vacancy_sent_to_user(user_id, vacancy_id):
                logger.debug(f"Вакансия {vacancy_id} уже отправлена {tg_id}")
                return False
            
            logger.debug(f"Отправка вакансии {vacancy_id} пользователю {tg_id}")
            
            # Форматируем и отправляем
            message_text = self.format_vacancy(vacancy)

            if not message_text or len(message_text.strip()) < 10:
                raw = (vacancy.get("text") or vacancy.get("original_text") or "").strip()
                if len(raw) >= 10:
                    # Добавляем заголовок к сырому тексту
                    category_id = vacancy.get("category", "other")
                    category_data = CATEGORIES.get(category_id, CATEGORIES["other"])
                    message_text = (
                        "🆕 Новая вакансия\n"
                        f"Направление: {category_data['name']}\n\n"
                        f"<blockquote>{raw}</blockquote>"
                    )
                else:
                    logger.warning(f"Пустой текст вакансии {vacancy_id}")
                    return False

            await self._send_with_default_photo(tg_id, message_text)
            
            # Записываем в БД
            await db.record_sent_vacancy(user_id, vacancy_id)
            await db.record_send_log(user_id)
            logger.debug(f"✅ Вакансия {vacancy_id} отправлена пользователю {tg_id}")
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            error_type = type(e).__name__
            
            # Детальное логирование ошибки
            logger.error(
                f"❌ Ошибка отправки вакансии {vacancy_id} пользователю {tg_id}: "
                f"{error_type}: {str(e)[:200]}"
            )
            
            # Пользователь заблокировал бота или не начал диалог
            if "blocked" in error_msg or "deactivated" in error_msg or "can't initiate" in error_msg:
                logger.info(f"Пользователь {tg_id} заблокировал бота или не начал диалог")
                # Деактивируем пользователя
                await db.deactivate_user(tg_id)
                
            elif "chat not found" in error_msg or "forbidden" in error_msg:
                logger.info(f"Чат не найден или запрещен для {tg_id}")
                
            elif "message is too long" in error_msg or "caption is too long" in error_msg:
                logger.warning(f"Сообщение слишком длинное для {tg_id}, отправляем частями")
                try:
                    await self._send_html_messages(tg_id, message_text)
                    await db.record_sent_vacancy(user_id, vacancy_id)
                    await db.record_send_log(user_id)
                    return True
                except Exception as e2:
                    logger.error(f"Ошибка отправки частями {vacancy_id} -> {tg_id}: {e2}")
            else:
                logger.error(f"Ошибка отправки вакансии {vacancy_id} -> {tg_id}: {e}")
                logger.error(f"Тип ошибки: {type(e).__name__}, Сообщение: {str(e)[:200]}")
            
            return False
    
    async def distribute_vacancy(self, vacancy: Dict) -> int:
        """
        Разослать одну вакансию всем подходящим пользователям.
        
        Args:
            vacancy: Данные вакансии
            
        Returns:
            Количество успешных отправок
        """
        category = vacancy.get("category", "other")
        vacancy_id = vacancy["id"]
        
        # Получаем пользователей с этой категорией
        users = await db.get_users_by_category(category)
        
        if not users:
            logger.info(f"Нет пользователей для категории {category}")
            await db.mark_vacancy_sent(vacancy_id)
            return 0
        
        logger.info(
            f"Рассылка вакансии {vacancy_id} ({category}): "
            f"{len(users)} потенциальных получателей"
        )
        
        success_count = 0
        skipped_no_subscription = 0

        for user in users:
            if not await db.has_active_subscription(user["tg_id"]):
                skipped_no_subscription += 1
                logger.debug(
                    "Пропуск вакансии %s: нет подписки у %s",
                    vacancy_id,
                    user["tg_id"],
                )
                continue

            success = await self.send_vacancy_to_user(user, vacancy)
            if success:
                success_count += 1

            await asyncio.sleep(config.rate_limit.min_delay_seconds)

        if skipped_no_subscription:
            logger.info(
                "Вакансия %s: пропущено %s пользователей без подписки",
                vacancy_id,
                skipped_no_subscription,
            )

        eligible_users = len(users) - skipped_no_subscription

        logger.info(
            f"📊 Вакансия {vacancy_id}: отправлено {success_count} из {len(users)}"
        )
        
        # Помечаем вакансию отправленной:
        # - если хотя бы 1 отправка прошла
        # - или если нет пользователей с подпиской (нет смысла повторять)
        if success_count > 0 or eligible_users == 0:
            await db.mark_vacancy_sent(vacancy_id)
            logger.info(
                f"Вакансия {vacancy_id} разослана: "
                f"{success_count}/{len(users)} успешно"
            )
        else:
            logger.warning(
                f"⚠️ Вакансия {vacancy_id}: 0 отправок из {eligible_users} "
                f"подписчиков — НЕ помечена как отправленная, будет повторена"
            )
        
        return success_count

    def _moderation_keyboard(self, vacancy_id: int):
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Принять",
                callback_data=f"vac_mod:approve:{vacancy_id}",
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"vac_mod:reject:{vacancy_id}",
            ),
        )
        return builder.as_markup()

    def _format_moderation_preview(self, vacancy: Dict) -> str:
        category_id = vacancy.get("category", "other")
        cat = CATEGORIES.get(category_id, CATEGORIES["other"])
        raw = (vacancy.get("text") or vacancy.get("original_text") or "").strip()
        raw = remove_telegra_links(raw)
        # Удаляем все HTML-теги из исходного текста — они часто сломаны
        raw = re.sub(r'<[^>]+>', '', raw)
        if len(raw) > 3500:
            raw = raw[:3500] + "..."
        result = (
            f"📥 <b>Модерация вакансии</b> #{vacancy['id']}\n"
            f"Источник: {vacancy.get('source', '?')}\n"
            f"Категория: {cat['name']}\n"
            f"Quality: {vacancy.get('quality_score', 0)}\n\n"
            f"{raw}"
        )
        return self._sanitize_html(result)

    async def send_pending_to_moderation(self) -> int:
        """Отправить новые вакансии в чат модерации."""
        if not moderation_enabled():
            return 0

        chat_id = get_moderation_chat_id()
        if not chat_id:
            return 0

        pending = await db.get_vacancies_pending_moderation(limit=30)
        sent = 0

        for vacancy in pending:
            try:
                preview = self._format_moderation_preview(vacancy)
                markup = self._moderation_keyboard(vacancy["id"])
                default_photo = await db.get_default_photo()

                if default_photo:
                    await self.bot.send_photo(chat_id=chat_id, photo=default_photo)

                msg = await self.bot.send_message(
                    chat_id=chat_id,
                    text=preview,
                    parse_mode="HTML",
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
                await db.set_vacancy_moderation_status(
                    vacancy["id"],
                    "pending",
                    moderation_chat_message_id=msg.message_id,
                )
                sent += 1
            except Exception as e:
                logger.error(
                    "Ошибка отправки вакансии %s в модерацию: %s",
                    vacancy.get("id"),
                    e,
                )

        if sent:
            logger.info("📥 Отправлено в модерацию: %s вакансий", sent)
        return sent
    
    async def distribute_all_pending(self) -> tuple:
        """
        Разослать все неотправленные вакансии.
        
        Returns:
            Tuple (количество вакансий, общее количество отправок)
        """
        if self._is_running:
            logger.warning("Рассылка уже запущена")
            return 0, 0
        
        self._is_running = True
        
        try:
            vacancies = await db.get_unsent_vacancies(limit=50)
            
            if not vacancies:
                logger.info("Нет вакансий для рассылки")
                return 0, 0
            
            total_vacancies = 0
            total_sends = 0
            
            for vacancy in vacancies:
                sends = await self.distribute_vacancy(vacancy)
                total_vacancies += 1
                total_sends += sends
                
                # Пауза между вакансиями
                await asyncio.sleep(2)
            
            logger.info(
                f"📬 Рассылка завершена: {total_vacancies} вакансий, "
                f"{total_sends} отправок"
            )
            
            return total_vacancies, total_sends
            
        finally:
            self._is_running = False
    
    async def send_approved_user_vacancy(self, vacancy: Dict) -> int:
        """
        Разослать одобренную пользовательскую вакансию.
        
        Args:
            vacancy: Данные из таблицы user_vacancies
            
        Returns:
            Количество успешных отправок
        """
        category = vacancy.get("category", "other")
        category_data = CATEGORIES.get(category, CATEGORIES["other"])
        vacancy_id = vacancy["id"]
        
        # Форматируем в стиле основных вакансий (HTML)
        text = vacancy.get("text", "").strip()
        contact = vacancy.get("contact", "")
        author = f"@{vacancy.get('username')}" if vacancy.get("username") else "пользователь"
        
        message_text = (
            "🔥 Новая вакансия\n"
            f"Направление: {category_data['name']}\n\n"
            f"<blockquote>{text}\n\n"
            f"<b>Контакт:</b> {contact}</blockquote>\n\n"
            f"{category_data.get('hashtag', '#vacancy')}"
        )
        message_text = self._sanitize_html(message_text)
        
        # Получаем подписчиков
        users = await db.get_users_by_category(category)
        if not users:
            logger.info(f"Нет пользователей для user_vacancy {vacancy_id}")
            await db.mark_user_vacancy_sent(vacancy_id)
            return 0
        
        success_count = 0
        
        for user in users:
            # Не отправляем автору
            if user["tg_id"] == vacancy.get("tg_id"):
                continue
            
            # Проверяем подписку
            if not await db.has_active_subscription(user["tg_id"]):
                continue
            
            try:
                await self._send_with_default_photo(user["tg_id"], message_text)
                await db.record_send_log(user["id"])
                success_count += 1
            except Exception as e:
                error_msg = str(e).lower()
                if "blocked" in error_msg or "can't initiate" in error_msg or "forbidden" in error_msg:
                    await db.deactivate_user(user["tg_id"])
                logger.warning(f"Ошибка отправки user_vacancy {user['tg_id']}: {e}")
            
            await asyncio.sleep(config.rate_limit.min_delay_seconds)
        
        # Помечаем как разосланную
        await db.mark_user_vacancy_sent(vacancy_id)
        logger.info(
            f"📬 User vacancy {vacancy_id}: отправлено {success_count} подписчикам"
        )
        
        return success_count
    
    async def distribute_user_vacancies(self) -> int:
        """Разослать все одобренные пользовательские вакансии."""
        vacancies = await db.get_approved_user_vacancies(limit=10)
        if not vacancies:
            return 0
        
        total = 0
        for vacancy in vacancies:
            sends = await self.send_approved_user_vacancy(vacancy)
            total += sends
            await asyncio.sleep(2)
        
        logger.info(f"📬 User vacancies: {len(vacancies)} вакансий, {total} отправок")
        return total
    
    async def _download_photo_from_telethon(self, source_id: str, message_id: int) -> Optional[str]:
        """Загрузить фото из Telegram через Telethon и получить file_id от бота"""
        if not self.parser or not self.parser.is_authorized or not self.parser.client:
            logger.warning("Telethon не доступен для загрузки фото")
            return None
        
        try:
            logger.debug(f"Загрузка фото из {source_id}, message_id={message_id}")
            
            # Получаем сообщение через Telethon
            entity = await self.parser.client.get_entity(source_id)
            message = await self.parser.client.get_messages(entity, ids=message_id)
            
            if not message:
                logger.warning(f"Сообщение {message_id} не найдено в {source_id}")
                return None
            
            if not message.media:
                logger.warning(f"В сообщении {message_id} нет медиа")
                return None
            
            logger.debug(f"Медиа найдено в сообщении {message_id}")
            
            # Скачиваем фото во временный файл
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                photo_path = tmp_file.name
            
            try:
                logger.debug(f"Скачивание медиа из сообщения {message_id}")
                photo_path = await self.parser.client.download_media(
                    message.media, 
                    file=photo_path
                )
                
                if not photo_path:
                    logger.warning(f"Не удалось скачать медиа из сообщения {message_id}")
                    return None
                
                if not os.path.exists(photo_path):
                    logger.warning(f"Файл не существует после скачивания: {photo_path}")
                    return None
                
                logger.debug(f"Медиа скачано: {photo_path}, размер: {os.path.getsize(photo_path)} bytes")
                
                # Отправляем фото боту чтобы получить file_id
                # Используем путь к файлу напрямую, а не BufferedReader
                admin_id = config.admin.ids[0] if config.admin.ids else None
                if not admin_id:
                    logger.warning("Нет админа для получения file_id фото")
                    try:
                        os.remove(photo_path)
                    except:
                        pass
                    return None
                
                try:
                    # Открываем файл как InputFile для aiogram
                    from aiogram.types import FSInputFile
                    photo_file = FSInputFile(photo_path)
                    
                    logger.debug(f"Отправка фото админу {admin_id} для получения file_id")
                    sent_message = await self.bot.send_photo(
                        chat_id=admin_id,
                        photo=photo_file
                    )
                    
                    if not sent_message.photo:
                        logger.warning("Фото не получено в ответе от бота")
                        try:
                            os.remove(photo_path)
                        except:
                            pass
                        return None
                    
                    file_id = sent_message.photo[-1].file_id
                    logger.info(f"✅ File_id получен: {file_id[:20]}...")
                    
                    # Удаляем служебное сообщение админу (чтобы не было видно пользователю)
                    try:
                        await self.bot.delete_message(
                            chat_id=admin_id,
                            message_id=sent_message.message_id
                        )
                        logger.debug("Служебное сообщение админу удалено")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить служебное сообщение: {e}")
                    
                    # Удаляем временный файл
                    try:
                        os.remove(photo_path)
                    except:
                        pass
                    
                    return file_id
                except Exception as e:
                    logger.error(f"Ошибка отправки фото боту: {e}")
                    logger.error(f"Тип ошибки: {type(e).__name__}, Детали: {str(e)[:300]}")
                    # Удаляем временный файл при ошибке
                    try:
                        os.remove(photo_path)
                    except:
                        pass
                    return None
            except Exception as e:
                # Удаляем временный файл при ошибке
                try:
                    if os.path.exists(photo_path):
                        os.remove(photo_path)
                except:
                    pass
                raise e
            
            return None
        except Exception as e:
            logger.error(f"Ошибка загрузки фото через Telethon: {e}")
            return None
    
    async def _send_with_default_photo(self, tg_id: int, message_text: str):
        """Отправляет дефолтное фото с текстом в одном сообщении (caption).

        Telegram ограничивает caption до 1024 символов.
        Если текст длиннее — фото + текст отдельными сообщениями.
        При ошибке парсинга HTML — повторяет без HTML.
        """
        default_photo_id = await db.get_default_photo()

        if default_photo_id:
            if len(message_text) <= 1024:
                # Фото + текст одним сообщением
                try:
                    await self.bot.send_photo(
                        chat_id=tg_id,
                        photo=default_photo_id,
                        caption=message_text,
                        parse_mode="HTML",
                    )
                    return
                except Exception as e:
                    error_msg = str(e).lower()
                    if "parse entities" in error_msg or "can't parse" in error_msg:
                        # HTML сломан — пробуем без HTML-разметки
                        logger.warning(
                            "Ошибка парсинга HTML для %s, отправляем без разметки", tg_id
                        )
                        plain_text = re.sub(r'<[^>]+>', '', message_text)
                        try:
                            await self.bot.send_photo(
                                chat_id=tg_id,
                                photo=default_photo_id,
                                caption=plain_text[:1024],
                            )
                            return
                        except Exception as e2:
                            logger.error(f"Ошибка send_photo без HTML {tg_id}: {e2}")
                    elif "caption" in error_msg or "too long" in error_msg:
                        logger.warning(
                            "Caption слишком длинный для %s, отправляем раздельно", tg_id
                        )
                    else:
                        logger.error(f"Ошибка send_photo с caption {tg_id}: {e}")
            # Текст длиннее 1024 — фото отдельно, текст отдельно
            try:
                await self.bot.send_photo(chat_id=tg_id, photo=default_photo_id)
            except Exception as e:
                logger.error(f"Ошибка отправки дефолтного фото {tg_id}: {e}")
        else:
            logger.warning(f"Дефолтное фото не задано — отправляем только текст {tg_id}")

        # Отправляем текст, при ошибке HTML — без разметки
        try:
            await self._send_html_messages(tg_id, message_text)
        except Exception as e:
            error_msg = str(e).lower()
            if "parse entities" in error_msg or "can't parse" in error_msg:
                logger.warning("Ошибка HTML при отправке текста %s, отправляем plain", tg_id)
                plain_text = re.sub(r'<[^>]+>', '', message_text)
                await self.bot.send_message(
                    chat_id=tg_id,
                    text=plain_text,
                    disable_web_page_preview=True,
                )
            else:
                raise

