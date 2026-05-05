"""
Telethon парсер для Telegram каналов и групп.
Использует user account для доступа к сообщениям.
"""

import re
import logging
import asyncio
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, Message
from telethon.errors import (
    FloodWaitError, 
    ChannelPrivateError,
    ChatAdminRequiredError
)

from config import (
    config, CATEGORIES, SPAM_KEYWORDS,
    RESUME_STRONG_INDICATORS, RESUME_WEAK_INDICATORS, RESUME_START_PATTERNS,
    VACANCY_STRONG_INDICATORS, VACANCY_CONDITIONS_INDICATORS,
    VACANCY_TASK_INDICATORS, VACANCY_ACTION_INDICATORS,
    SUSPICIOUS_VACANCY_PHRASES, MISSING_COMPANY_PATTERNS, MISSING_POSITION_PATTERNS,
    PROFESSIONAL_TASK_PATTERNS, SKILLS_PATTERNS, WORK_FORMAT_PATTERNS,
    TASK_DESCRIPTION_PATTERNS, BOT_CONTACT_PATTERNS, MASS_RECRUITMENT_PATTERNS
)
from database import db

logger = logging.getLogger(__name__)


class TelegramParser:
    """
    Парсер Telegram каналов и групп через Telethon.
    Бот НЕ добавляется в каналы - используется user session.
    """
    
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.is_authorized = False
        
    async def start(self) -> bool:
        """
        Запуск Telethon клиента.
        При первом запуске потребуется ввести код из Telegram.
        """
        try:
            self.client = TelegramClient(
                config.telethon.session_name,
                config.telethon.api_id,
                config.telethon.api_hash
            )
            
            await self.client.start(phone=config.telethon.phone)
            self.is_authorized = await self.client.is_user_authorized()
            
            if self.is_authorized:
                me = await self.client.get_me()
                logger.info(f"✅ Telethon авторизован как: {me.first_name} (@{me.username})")
                return True
            else:
                logger.error("❌ Telethon не авторизован. Требуется ввести код.")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telethon: {e}")
            return False
    
    async def stop(self) -> None:
        """Остановка клиента"""
        if self.client:
            await self.client.disconnect()
            logger.info("Telethon отключен")
    
    def _detect_category(self, text: str) -> str:
        """
        Автоопределение категории вакансии по ключевым словам.
        Улучшенный алгоритм с приоритетами и проверкой контекста.
        """
        text_lower = text.lower()
        scores: Dict[str, float] = {}
        
        # Приоритетные фразы для каждой категории (более специфичные)
        priority_phrases = {
            "it": [
                r"\b(программист|разработчик|developer|devops|backend|frontend|fullstack)\b",
                r"\b(python|javascript|java|react|node|php|golang|rust)\s+(разработчик|developer)\b",
                r"\b(веб|мобильн|ios|android)\s+разработк",
            ],
            "design": [
                r"\b(дизайнер|designer)\b",
                r"\b(ui|ux|графическ|веб)\s+дизайн",
                r"\b(логотип|брендинг|айдентика)\b",
            ],
            "marketing": [
                r"\b(маркетолог|marketer|smm|таргет|seo)\s+(специалист|менеджер|manager)\b",
                r"\b(контент|content)\s+маркетолог",
                r"\b(стратег|strategist)\s+(маркетинг|marketing)\b",
            ],
            "copywriting": [
                r"\b(копирайтер|copywriter|редактор|editor)\b",
                r"\b(текст|статья|контент)\s+(для|написани)",
                r"\b(сценарист|scriptwriter|writer)\b",
            ],
            "video": [
                r"\b(монтажер|видеограф|видеооператор|video\s+editor)\b",
                r"\b(монтаж|montage|editing)\s+(видео|video)\b",
                r"\b(motion\s+design|моушн\s+дизайн)\b",
            ],
            "ai_ml": [
                r"\b(ai|ml|machine\s+learning|data\s+science)\s+(специалист|engineer|scientist)\b",
                r"\b(нейросет|искусственн\s+интеллект)\b",
            ],
        }
        
        # Сначала проверяем приоритетные фразы (более специфичные)
        for cat_id, phrases in priority_phrases.items():
            for phrase_pattern in phrases:
                if re.search(phrase_pattern, text_lower, re.IGNORECASE):
                    scores[cat_id] = scores.get(cat_id, 0) + 5.0  # Высокий приоритет
                    logger.debug(f"Найдена приоритетная фраза для {cat_id}: {phrase_pattern}")
        
        # Затем проверяем обычные ключевые слова
        for cat_id, cat_data in CATEGORIES.items():
            if cat_id == "other":
                continue
            
            # Пропускаем категории, которые уже получили высокий приоритет
            if cat_id in scores and scores[cat_id] >= 5.0:
                continue
                
            score = scores.get(cat_id, 0.0)
            for keyword in cat_data["keywords"]:
                keyword_lower = keyword.lower()
                
                # Проверяем точное совпадение слова (с границами слов)
                pattern = r'\b' + re.escape(keyword_lower) + r'\b'
                if re.search(pattern, text_lower):
                    # Бонус за точное совпадение
                    base_score = 1.0
                    # Бонус за длину ключевого слова (более длинные = более специфичные)
                    length_bonus = len(keyword_lower) / 10.0
                    score += base_score + length_bonus
                # Также проверяем частичное совпадение (для составных слов)
                elif keyword_lower in text_lower:
                    score += 0.3  # Меньший вес для частичных совпадений
            
            if score > 0:
                scores[cat_id] = score
        
        if not scores:
            return "other"
        
        # Возвращаем категорию с максимальным score
        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]
        
        # Если лучший score слишком низкий (< 1.0), возвращаем other
        if best_score < 1.0:
            logger.debug(f"Слишком низкий score ({best_score:.2f}), возвращаем other")
            return "other"
        
        logger.debug(f"Определена категория: {best_category} (score: {best_score:.2f})")
        return best_category
    
    def _is_spam(self, text: str) -> bool:
        """Проверка текста на спам/рекламу"""
        text_lower = text.lower()
        
        # Проверяем каждое спам-слово
        spam_count = 0
        for spam_word in SPAM_KEYWORDS:
            if spam_word.lower() in text_lower:
                spam_count += 1
                logger.debug(f"🚫 Обнаружен спам: {spam_word}")
        
        # Если найдено 2+ спам-слова - точно спам
        if spam_count >= 2:
            return True
        
        # Проверяем на рекламные паттерны
        ad_patterns = [
            r"скидк[аи]?\s*\d+%",  # Скидка X%
            r"акци[яи]",  # Акция
            r"только\s+сегодня",  # Только сегодня
            r"ограниченное\s+время",  # Ограниченное время
            r"подписывайся\s+на",  # Подписывайся на
            r"лайкни\s+и\s+репост",  # Лайкни и репост
            r"переходи\s+по\s+ссылке",  # Переходи по ссылке
            r"жми\s+на\s+ссылку",  # Жми на ссылку
            r"курс\s+по\s+",  # Курс по
            r"обучение\s+",  # Обучение
            r"мастер-класс",  # Мастер-класс
        ]
        
        for pattern in ad_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"🚫 Обнаружен рекламный паттерн: {pattern}")
                return True
        
        # Проверяем на слишком много ссылок (реклама)
        url_count = len(re.findall(r'https?://|t\.me/|@\w+', text_lower))
        if url_count > 3:  # Больше 3 ссылок - подозрительно
            logger.debug(f"🚫 Слишком много ссылок: {url_count}")
            return True
        
        # Проверяем на короткие сообщения с эмодзи (часто реклама)
        if len(text.strip()) < 100 and len(re.findall(r'[🔥💎⭐✨🎁🎉]', text)) > 3:
            logger.debug("🚫 Подозрительное сообщение: много эмодзи в коротком тексте")
            return True
        
        return False
    
    def _is_resume(self, text: str) -> bool:
        """
        Строгая проверка является ли сообщение резюме/предложением услуг.
        Исключаем резюме из парсинга ДО сохранения в БД.
        
        Логика:
        1. Проверяем начало сообщения (эвристика)
        2. Проверяем сильные индикаторы резюме
        3. Проверяем слабые индикаторы (нужно >= 2)
        
        Returns:
            True если это резюме/предложение услуг, False если вакансия
        """
        text_lower = text.lower()
        text_stripped = text_lower.strip()
        
        # ЭВРИСТИКА: Проверяем начало сообщения
        # Если начинается с "Ищу..." или "Предлагаю..." - это резюме
        for pattern in RESUME_START_PATTERNS:
            if re.search(pattern, text_stripped):
                # ИСКЛЮЧЕНИЕ: "Ищу дизайнера" - это вакансия, не резюме
                # Проверяем что после "ищу" идет профессия/должность, а не "работу"/"заказ" и т.д.
                if pattern == r"^ищу\s+":
                    # Если после "ищу" идет профессия (не "работу", "заказ" и т.д.) - это вакансия
                    after_ищу = text_stripped[4:].strip()  # Берем текст после "ищу "
                    # Проверяем что это НЕ резюме-фраза
                    resume_after_ищу = [
                        "работу", "заказ", "проект", "заказчика", "клиента",
                        "сотрудничество", "работодател", "компанию",
                        "удаленную работу", "удаленку", "фриланс", "вакансию", "позицию"
                    ]
                    if not any(after_ищу.startswith(word) for word in resume_after_ищу):
                        # Это вакансия типа "Ищу дизайнера"
                        logger.debug("✅ Обнаружена вакансия: начинается с 'Ищу [профессия]'")
                        return False
                    else:
                        # Это резюме типа "Ищу работу"
                        logger.debug(f"🚫 Обнаружено резюме: начинается с '{pattern}'")
                        return True
                else:
                    # Для других паттернов (предлагаю, готов и т.д.) - это резюме
                    logger.debug(f"🚫 Обнаружено резюме: начинается с '{pattern}'")
                    return True
        
        # ПРИОРИТЕТ: Если есть хештег #ищу - это ВАКАНСИЯ, не резюме
        if re.search(r"#ищу\b", text_lower):
            logger.debug("✅ Обнаружена вакансия с хештегом #ищу")
            return False
        
        # Проверяем сильные индикаторы резюме (если есть хотя бы один - это резюме)
        for pattern in RESUME_STRONG_INDICATORS:
            if re.search(pattern, text_lower):
                logger.debug(f"🚫 Обнаружено резюме (сильный индикатор): {pattern}")
                return True
        
        # Проверяем слабые индикаторы резюме (нужно >= 2 для определения как резюме)
        weak_matches = 0
        for pattern in RESUME_WEAK_INDICATORS:
            if re.search(pattern, text_lower):
                weak_matches += 1
        
        # Если >= 2 слабых признака - это резюме
        if weak_matches >= 2:
            logger.debug(f"🚫 Обнаружено резюме (слабые индикаторы: {weak_matches})")
            return True
        
        return False
    
    def _is_vacancy(self, text: str) -> bool:
        """
        Строгая проверка является ли сообщение вакансией.
        Парсим ТОЛЬКО вакансии, полностью исключаем резюме/предложения услуг.
        
        Логика:
        1. Сначала проверяем что это НЕ резюме
        2. Проверяем приоритетные индикаторы вакансии (ищу/#ищу в начале)
        3. Проверяем сильные индикаторы вакансии
        4. Проверяем комбинацию условий/задач/призывов к действию
        
        Returns:
            True если это вакансия, False если нет
        """
        # Сначала проверяем что это НЕ резюме
        if self._is_resume(text):
            return False
        
        text_lower = text.lower()
        text_stripped = text_lower.strip()
        
        # Исключаем слишком короткие сообщения (менее 50 символов)
        if len(text.strip()) < 50:
            return False
        
        # ПРИОРИТЕТ: Проверяем приоритетные индикаторы вакансии
        # Если "ищу" в начале сообщения (но не "ищу работу") или есть #ищу - это вакансия
        if text_stripped.startswith("ищу "):
            # Проверяем что после "ищу" идет профессия, а не "работу"/"заказ"
            after_ищу = text_stripped[4:].strip()
            resume_words = ["работу", "заказ", "проект", "заказчика", "клиента",
                           "сотрудничество", "работодател", "компанию",
                           "удаленную работу", "удаленку", "фриланс", "вакансию", "позицию"]
            if not any(after_ищу.startswith(word) for word in resume_words):
                logger.debug("✅ Приоритетная вакансия: начинается с 'Ищу [профессия]'")
                return True
        
        # Проверяем хештег #ищу
        if re.search(r"#ищу\b", text_lower):
            logger.debug("✅ Приоритетная вакансия: содержит хештег #ищу")
            return True
        
        # Проверяем на рекламные паттерны (исключаем)
        ad_patterns = [
            r"скидк[аи]", r"акци[яи]", r"распродаж", r"специальное предложение",
            r"только сегодня", r"ограниченное время", r"успей",
            r"подписывайся", r"лайкни", r"репост", r"поделись",
            r"переходи по ссылке", r"жми на ссылку", r"переходите",
            r"курс", r"обучение", r"школа", r"мастер-класс", r"вебинар",
            r"продам", r"куплю", r"продажа", r"покупка",
            r"реклам[аы]", r"продвижение", r"раскрутк[аи]", r"накрутк[аи]",
            r"подписчик[иов]", r"лайк[иов]", r"просмотр[ыов]",
            r"скидк[аи]\s+\d+%", r"-\d+%", r"экономи[яи]",
            r"бесплатно", r"даром", r"подарок", r"бонус",
            r"только\s+сегодня", r"последний\s+день", r"успей\s+купить",
            r"заказать\s+сейчас", r"купить\s+сейчас", r"оформить\s+заказ",
            r"промокод", r"промо\s+код", r"купон",
            r"инстаграм", r"instagram", r"подписка\s+на\s+канал",
            r"канал\s+в\s+telegram", r"подписывайтесь\s+на",
        ]
        
        for pattern in ad_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"🚫 Обнаружена реклама: {pattern}")
                return False
        
        # Подсчитываем индикаторы вакансии
        strong_matches = 0  # Сильные индикаторы (ищем, нужен, требуется и т.д.)
        conditions_matches = 0  # Условия работы (оплата, график и т.д.)
        task_matches = 0  # Задачи и требования
        action_matches = 0  # Призывы к действию
        
        # Проверяем сильные индикаторы вакансии
        for pattern in VACANCY_STRONG_INDICATORS:
            if re.search(pattern, text_lower):
                strong_matches += 1
        
        # Проверяем индикаторы условий работы
        for pattern in VACANCY_CONDITIONS_INDICATORS:
            if re.search(pattern, text_lower):
                conditions_matches += 1
        
        # Проверяем индикаторы задач и требований
        for pattern in VACANCY_TASK_INDICATORS:
            if re.search(pattern, text_lower):
                task_matches += 1
        
        # Проверяем индикаторы призыва к действию
        for pattern in VACANCY_ACTION_INDICATORS:
            if re.search(pattern, text_lower):
                action_matches += 1
        
        total_matches = strong_matches + conditions_matches + task_matches + action_matches
        
        # КРИТЕРИИ ПРИЗНАНИЯ ВАКАНСИЕЙ:
        # 1. Есть хотя бы 1 сильный индикатор + хотя бы 1 из других категорий
        if strong_matches >= 1 and (conditions_matches >= 1 or task_matches >= 1 or action_matches >= 1):
            logger.debug(
                f"✅ Обнаружена вакансия: сильных={strong_matches}, "
                f"условий={conditions_matches}, задач={task_matches}, действий={action_matches}"
            )
            return True
        
        # 2. Есть хотя бы 2 сильных индикатора
        if strong_matches >= 2:
            logger.debug(f"✅ Обнаружена вакансия: сильных индикаторов={strong_matches}")
            return True
        
        # 3. Есть условия работы + задачи/требования (даже без сильных индикаторов)
        if conditions_matches >= 1 and task_matches >= 1:
            logger.debug(
                f"✅ Обнаружена вакансия: условия={conditions_matches}, "
                f"задачи={task_matches}"
            )
            return True
        
        # 4. Минимум 3 совпадения из любых категорий
        if total_matches >= 3:
            logger.debug(f"✅ Обнаружена вакансия: всего индикаторов={total_matches}")
            return True
        
        logger.debug(
            f"❌ Не вакансия: сильных={strong_matches}, условий={conditions_matches}, "
            f"задач={task_matches}, действий={action_matches}, всего={total_matches}"
        )
        return False
    
    def _is_suspicious_vacancy(self, text: str) -> Tuple[bool, str]:
        """
        Строгая фильтрация низкокачественных и сомнительных вакансий.
        Использует scoring-систему для оценки качества.
        
        Логика:
        1. Проверяем стоп-фразы (если найдена - сразу отклоняем)
        2. Подсчитываем баллы за наличие важных элементов (+1 за каждый)
        3. Вычитаем баллы за подозрительные элементы (-2 за каждый)
        4. Если итоговый score < 0 → отклоняем
        
        Returns:
            Tuple[is_suspicious: bool, reason: str]
            - is_suspicious: True если вакансия подозрительная/низкокачественная
            - reason: Причина отклонения (для логирования)
        """
        text_lower = text.lower()
        reasons = []  # Список причин отклонения
        
        # ============================================
        # ШАГ 1: Проверка стоп-фраз (жесткая блокировка)
        # ============================================
        for pattern in SUSPICIOUS_VACANCY_PHRASES:
            if re.search(pattern, text_lower):
                matched_phrase = pattern.replace(r"\b", "").replace(r"\s+", " ")
                reasons.append(f"стоп-фраза: '{matched_phrase}'")
                logger.debug(f"🚫 Низкокачественная вакансия: найдена стоп-фраза '{matched_phrase}'")
                return True, f"Стоп-фраза: {matched_phrase}"
        
        # Проверка на массовый набор (шаблоны)
        for pattern in MASS_RECRUITMENT_PATTERNS:
            if re.search(pattern, text_lower):
                reasons.append("массовый набор")
                logger.debug("🚫 Низкокачественная вакансия: обнаружен массовый набор")
                return True, "Массовый набор (шаблон)"
        
        # Проверка контакта через бота (не человека)
        bot_contact_found = False
        for pattern in BOT_CONTACT_PATTERNS:
            if re.search(pattern, text_lower):
                bot_contact_found = True
                reasons.append("контакт через бота")
                break
        
        # ============================================
        # ШАГ 2: Scoring-система
        # ============================================
        score = 0
        
        # +1 балл за наличие названия должности
        has_position = False
        for pattern in MISSING_POSITION_PATTERNS:
            if re.search(pattern, text_lower):
                has_position = True
                score += 1
                break
        
        # +1 балл за наличие стека/навыков
        has_skills = False
        for pattern in SKILLS_PATTERNS:
            if re.search(pattern, text_lower):
                has_skills = True
                score += 1
                break
        
        # +1 балл за формат работы (remote/full-time и т.д.)
        has_work_format = False
        for pattern in WORK_FORMAT_PATTERNS:
            if re.search(pattern, text_lower):
                has_work_format = True
                score += 1
                break
        
        # +1 балл за внятное описание задач
        has_task_description = False
        for pattern in TASK_DESCRIPTION_PATTERNS:
            if re.search(pattern, text_lower):
                has_task_description = True
                score += 1
                break
        
        # +1 балл за профессиональные задачи
        has_professional_tasks = False
        for pattern in PROFESSIONAL_TASK_PATTERNS:
            if re.search(pattern, text_lower):
                has_professional_tasks = True
                score += 1
                break
        
        # ============================================
        # ШАГ 3: Вычитание баллов за подозрительные элементы
        # ============================================
        
        # -2 балла за "без опыта"
        if re.search(r"без\s+опыта|опыт\s+не\s+(обязателен|нужен|требуется)", text_lower):
            score -= 2
            reasons.append("без опыта")
        
        # -2 балла за заработок "от N в день"
        if re.search(r"\d+\s*(₽|руб|рублей)\s+в\s+день|заработок\s+от\s+\d+|доход\s+от\s+\d+", text_lower):
            score -= 2
            reasons.append("заработок 'от N в день'")
        
        # -2 балла за опросы/отзывы/установки
        if re.search(r"опрос|отзыв|установк[аи]\s+приложени", text_lower):
            score -= 2
            reasons.append("опросы/отзывы/установки")
        
        # -2 балла за отсутствие работодателя (компании)
        has_company = False
        for pattern in MISSING_COMPANY_PATTERNS:
            if re.search(pattern, text_lower):
                has_company = True
                break
        
        if not has_company:
            score -= 2
            reasons.append("нет названия компании")
        
        # -2 балла за контакт через бота
        if bot_contact_found:
            score -= 2
        
        # ============================================
        # ШАГ 4: Финальная оценка
        # ============================================
        
        # Если итоговый score < 0 → отклоняем
        if score < 0:
            reason_str = ", ".join(reasons) if reasons else f"низкий score ({score})"
            logger.debug(
                f"🚫 Низкокачественная вакансия: score={score}, "
                f"причины: {reason_str}"
            )
            return True, f"Низкий score ({score}): {reason_str}"
        
        # Если score >= 0, но есть подозрительные элементы - логируем, но не блокируем
        if reasons:
            logger.debug(
                f"⚠️ Вакансия с подозрительными элементами (score={score}): "
                f"{', '.join(reasons)}, но проходит фильтр"
            )
        
        return False, ""
    
    def _convert_markdown_to_html(self, text: str) -> str:
        """
        Конвертирует Markdown форматирование в HTML.
        **текст** -> <b>текст</b>
        *текст* -> <i>текст</i>
        __текст__ -> <b>текст</b>
        _текст_ -> <i>текст</i>
        
        Важно: обрабатываем в правильном порядке, чтобы избежать конфликтов.
        """
        # Сначала конвертируем **текст** в <b>текст</b> (жирный, двойные звездочки)
        # Обрабатываем многострочные случаи
        text = re.sub(r'\*\*([^*\n]+(?:\*[^*\n]+)*)\*\*', r'<b>\1</b>', text)
        
        # Конвертируем __текст__ в <b>текст</b> (жирный, двойные подчеркивания)
        text = re.sub(r'__([^_\n]+(?:_[^_\n]+)*)__', r'<b>\1</b>', text)
        
        # Конвертируем *текст* в <i>текст</i> (курсив, одинарные звездочки)
        # Но только если это не часть уже обработанного **текст**
        # Используем негативный lookbehind/lookahead
        text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', text)
        
        # Конвертируем _текст_ в <i>текст</i> (курсив, одинарные подчеркивания)
        # Но только если это не часть уже обработанного __текст__
        text = re.sub(r'(?<!_)_([^_\n]+)_(?!_)', r'<i>\1</i>', text)
        
        return text
    
    def _clean_text(self, text: str) -> str:
        """Очистка текста от лишних символов и конвертация Markdown в HTML"""
        # Убираем специальные ссылки Telegram (tg://searchhashtag и tg://search_hashtag)
        # Паттерны: [[(tg://searchhashtag?hashtag=...) " или [#](tg://search_hashtag?hashtag=...)
        # Убираем все варианты этих ссылок
        text = re.sub(r'\[\[\(tg://searchhashtag[^\)]+\)\s*"[^"]*"', '', text)
        text = re.sub(r'\[#\]\(tg://search_hashtag[^\)]+\)', '', text)
        text = re.sub(r'\[#\]\(tg://searchhashtag[^\)]+\)', '', text)
        text = re.sub(r'\[\(tg://searchhashtag[^\)]+\)\s*"[^"]*"', '', text)
        text = re.sub(r'\[\(tg://search_hashtag[^\)]+\)\s*"[^"]*"', '', text)
        text = re.sub(r'\[\(tg://searchhashtag[^\)]+\)', '', text)
        text = re.sub(r'\[\(tg://search_hashtag[^\)]+\)', '', text)
        
        # Убираем оставшиеся следы этих ссылок (без скобок)
        text = re.sub(r'tg://searchhashtag[^\s\)]+', '', text)
        text = re.sub(r'tg://search_hashtag[^\s\)]+', '', text)
        
        # Убираем оставшиеся квадратные скобки и кавычки от этих ссылок
        text = re.sub(r'\[\[[^\]]*\]', '', text)
        text = re.sub(r'\[#[^\]]*\]', '', text)
        
        # Сначала конвертируем Markdown в HTML
        text = self._convert_markdown_to_html(text)
        
        # Убираем множественные пробелы и переносы
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        
        # Убираем ссылки на инвайты (опционально)
        # text = re.sub(r't\.me/joinchat/\S+', '[ссылка удалена]', text)
        
        return text.strip()
    
    async def parse_source(
        self, 
        source_id: str,
        source_type: str,
        last_message_id: int = 0,
        limit: int = 100
    ) -> List[Dict]:
        """
        Парсинг одного источника (канала или группы).
        
        Args:
            source_id: @username канала или chat_id группы
            source_type: 'channel' или 'group'
            last_message_id: ID последнего обработанного сообщения
            limit: Максимум сообщений для обработки
            
        Returns:
            Список словарей с вакансиями
        """
        vacancies = []
        
        if not self.is_authorized:
            logger.warning("Telethon не авторизован, парсинг невозможен")
            return vacancies
        
        try:
            # Получаем entity (канал или группу)
            entity = await self.client.get_entity(source_id)
            entity_title = getattr(entity, 'title', source_id)
            
            logger.info(f"📡 Парсинг: {entity_title} ({source_id})")
            
            # Читаем сообщения
            messages: List[Message] = await self.client.get_messages(
                entity,
                limit=limit,
                min_id=last_message_id
            )
            
            max_message_id = last_message_id
            processed = 0
            found = 0
            
            for message in messages:
                if not message.text:
                    continue
                
                processed += 1
                max_message_id = max(max_message_id, message.id)
                
                text = self._clean_text(message.text)
                
                # Пропускаем слишком короткие сообщения (менее 80 символов)
                # Вакансии обычно содержат описание, требования, условия
                if len(text) < 80:
                    continue
                
                # Пропускаем сообщения состоящие только из ссылок и эмодзи
                text_without_links = re.sub(r'https?://\S+|t\.me/\S+', '', text)
                text_without_emoji = re.sub(r'[🔥💎⭐✨🎁🎉💼💰📱]', '', text_without_links)
                if len(text_without_emoji.strip()) < 50:
                    continue
                
                # Проверяем на спам
                if self._is_spam(text):
                    continue
                
                # Проверяем является ли резюме (должно быть ПЕРЕД проверкой вакансии)
                if self._is_resume(text):
                    logger.debug(f"🚫 Обнаружено резюме, пропуск: {text[:100]}...")
                    continue
                
                # Проверяем является ли вакансией
                if not self._is_vacancy(text):
                    continue
                
                # ============================================
                # СТРОГАЯ ФИЛЬТРАЦИЯ НИЗКОКАЧЕСТВЕННЫХ ВАКАНСИЙ
                # Проверяем ДО сохранения в БД
                # ============================================
                is_suspicious, rejection_reason = self._is_suspicious_vacancy(text)
                if is_suspicious:
                    logger.info(
                        f"🚫 Отклонена низкокачественная вакансия: {rejection_reason}\n"
                        f"Текст: {text[:200]}..."
                    )
                    continue
                
                # Определяем категорию
                category = self._detect_category(text)
                
                # Проверяем дубликат в БД
                if await db.vacancy_exists(text):
                    continue
                
                # Проверяем наличие фото
                has_photo = False
                
                if message.media:
                    try:
                        # Проверяем есть ли фото (MessageMediaPhoto)
                        from telethon.tl.types import MessageMediaPhoto
                        if isinstance(message.media, MessageMediaPhoto):
                            has_photo = True
                            logger.debug(f"📷 Фото обнаружено в сообщении {message.id}")
                    except Exception as e:
                        logger.debug(f"Ошибка проверки медиа в сообщении {message.id}: {e}")
                
                # Получаем username автора сообщения для использования как контакт
                author_username = None
                try:
                    # Пробуем разные способы получения автора
                    if message.from_id:
                        sender = await message.get_sender()
                        if sender:
                            author_username = getattr(sender, 'username', None)
                            if author_username:
                                author_username = f"@{author_username}"
                                logger.debug(f"Найден username автора: {author_username}")
                    
                    # Если не получилось через from_id, пробуем получить username канала/группы
                    if not author_username:
                        try:
                            # Для каналов и групп можно использовать username самого канала/группы
                            if hasattr(entity, 'username') and entity.username:
                                author_username = f"@{entity.username}"
                                logger.debug(f"Найден username канала/группы: {author_username}")
                        except:
                            pass
                    
                    # Если не получилось, пробуем через peer_id
                    if not author_username and hasattr(message, 'peer_id'):
                        try:
                            peer = message.peer_id
                            if hasattr(peer, 'user_id'):
                                user_entity = await self.client.get_entity(peer.user_id)
                                if user_entity:
                                    author_username = getattr(user_entity, 'username', None)
                                    if author_username:
                                        author_username = f"@{author_username}"
                                        logger.debug(f"Найден username автора через peer_id: {author_username}")
                        except:
                            pass
                except Exception as e:
                    logger.warning(f"Не удалось получить username автора сообщения {message.id}: {e}")
                
                # Проверяем есть ли контакт в тексте (в исходном тексте ДО очистки)
                original_text = message.text
                has_contact = bool(
                    re.search(r'@[\w]+', original_text) or
                    re.search(r'(\+?\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', original_text) or
                    re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', original_text)
                )
                
                # Если контакта нет и есть username автора - добавляем его
                if not has_contact and author_username:
                    # Добавляем контакт автора в конец текста
                    text += f"\n\nКонтакты для отклика: {author_username}"
                    logger.info(f"✅ Добавлен контакт автора в вакансию: {author_username}")
                elif not has_contact and not author_username:
                    logger.warning(f"⚠️ Вакансия без контакта и без username автора (message_id: {message.id})")
                
                # Создаем структуру вакансии
                # is_vacancy всегда True здесь, так как мы уже проверили выше
                # is_suspicious всегда False здесь, так как мы уже отфильтровали подозрительные
                vacancy = {
                    "text": text,
                    "category": category,
                    "source": source_id,
                    "source_message_id": message.id,
                    "source_title": entity_title,
                    "date": message.date,
                    "has_photo": has_photo,
                    "photo_message_id": message.id if has_photo else None,
                    "is_vacancy": True,  # Флаг для отладки: всегда True здесь
                    "is_suspicious": False  # Флаг подозрительности: False после фильтрации
                }
                
                vacancies.append(vacancy)
                found += 1
            
            # Обновляем last_message_id в БД
            if max_message_id > last_message_id:
                await db.update_source_last_message(source_id, max_message_id)
            
            logger.info(
                f"✅ {entity_title}: обработано {processed}, "
                f"найдено вакансий: {found}"
            )
            
        except ChannelPrivateError:
            logger.warning(f"⚠️ Канал {source_id} приватный или недоступен")
        except ChatAdminRequiredError:
            logger.warning(f"⚠️ Требуются права админа для {source_id}")
        except FloodWaitError as e:
            logger.warning(f"⏳ FloodWait: ждем {e.seconds} секунд")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга {source_id}: {e}")
        
        return vacancies
    
    async def parse_all_sources(self) -> Tuple[int, int]:
        """
        Парсинг всех активных источников.
        
        Returns:
            Tuple (количество обработанных источников, количество найденных вакансий)
        """
        if not self.is_authorized:
            logger.warning("Telethon не авторизован")
            return 0, 0
        
        sources = await db.get_active_sources()
        
        if not sources:
            logger.info("Нет активных источников для парсинга")
            return 0, 0
        
        total_vacancies = 0
        processed_sources = 0
        
        for source in sources:
            try:
                vacancies = await self.parse_source(
                    source_id=source["source_id"],
                    source_type=source["source_type"],
                    last_message_id=source.get("last_message_id", 0),
                    limit=config.parser.max_vacancies_per_parse
                )
                
                # Сохраняем вакансии в БД
                for vacancy in vacancies:
                    has_photo = vacancy.get("has_photo", False)
                    photo_msg_id = vacancy.get("photo_message_id")
                    
                    if has_photo:
                        logger.debug(
                            f"Сохранение вакансии с фото: "
                            f"category={vacancy['category']}, "
                            f"photo_message_id={photo_msg_id}"
                        )
                    
                    result = await db.create_vacancy(
                        text=vacancy["text"],
                        category=vacancy["category"],
                        source=vacancy["source"],
                        source_message_id=vacancy["source_message_id"],
                        has_photo=has_photo,
                        photo_message_id=photo_msg_id
                    )
                    
                    if result and has_photo:
                        logger.info(f"✅ Вакансия с фото сохранена: ID={result.get('id')}")
                
                total_vacancies += len(vacancies)
                processed_sources += 1
                
                # Пауза между источниками для избежания rate limit
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Ошибка обработки источника {source['source_id']}: {e}")
        
        logger.info(
            f"📊 Парсинг завершен: {processed_sources} источников, "
            f"{total_vacancies} новых вакансий"
        )
        
        return processed_sources, total_vacancies
    
    async def get_channel_info(self, source_id: str) -> Optional[Dict]:
        """Получить информацию о канале/группе"""
        if not self.is_authorized:
            return None
        
        try:
            entity = await self.client.get_entity(source_id)
            
            return {
                "id": entity.id,
                "title": getattr(entity, 'title', source_id),
                "username": getattr(entity, 'username', None),
                "participants_count": getattr(entity, 'participants_count', None),
                "is_channel": isinstance(entity, Channel),
                "is_group": isinstance(entity, Chat)
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о {source_id}: {e}")
            return None


# Глобальный инстанс парсера
parser = TelegramParser()


