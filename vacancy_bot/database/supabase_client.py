"""
Клиент для работы с Supabase через REST API.
Использует httpx напрямую для совместимости с Python 3.14.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from urllib.parse import quote

import httpx

from config import config

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Клиент для работы с Supabase через REST API.
    Инкапсулирует все операции с базой данных.
    """
    
    def __init__(self):
        self.client: Optional[httpx.Client] = None
        self.base_url = ""
        self.headers = {}
        
    def connect(self) -> None:
        """Инициализация подключения к Supabase"""
        try:
            self.base_url = f"{config.supabase.url}/rest/v1"
            self.headers = {
                "apikey": config.supabase.key,
                "Authorization": f"Bearer {config.supabase.key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
            self.client = httpx.Client(timeout=30.0)
            logger.info("✅ Подключение к Supabase установлено")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Supabase: {e}")
            raise
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[List[Dict]]:
        """Выполнить HTTP запрос к Supabase"""
        try:
            url = f"{self.base_url}/{endpoint}"
            response = self.client.request(
                method, url, headers=self.headers, **kwargs
            )
            response.raise_for_status()
            
            if response.status_code == 204:
                return []
            return response.json() if response.text else []
        except httpx.HTTPStatusError as e:
            logger.error(f"Supabase request error: {e}")
            if e.response.status_code == 400:
                logger.error(f"Bad Request details: {e.response.text[:500]}")
            return None
        except Exception as e:
            logger.error(f"Supabase request error: {e}")
            return None
    
    # =========================================
    # USERS
    # =========================================
    
    async def get_user(self, tg_id: int) -> Optional[Dict]:
        """Получить пользователя по Telegram ID"""
        try:
            result = self._request("GET", f"users?tg_id=eq.{tg_id}&select=*")
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя {tg_id}: {e}")
            return None
    
    async def create_user(
        self, 
        tg_id: int, 
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        referred_by: Optional[int] = None
    ) -> Optional[Dict]:
        """Создать нового пользователя"""
        import secrets
        # Генерируем уникальный реферальный код
        referral_code = secrets.token_urlsafe(8)[:12].upper()
        
        try:
            data = {
                "tg_id": tg_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "categories": [],
                "is_subscribed": False,
                "is_active": True,
                "referral_code": referral_code,
                "referral_count": 0
            }
            result = self._request("POST", "users", json=data)
            logger.info(f"✅ Создан пользователь: {tg_id} с реферальным кодом {referral_code}")
            
            # Если пользователь пришел по реферальной ссылке
            if referred_by:
                await self.add_referral(referred_by, tg_id)
            
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка создания пользователя {tg_id}: {e}")
            return None
    
    async def get_or_create_user(
        self,
        tg_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        referred_by: Optional[int] = None
    ) -> Optional[Dict]:
        """Получить или создать пользователя"""
        user = await self.get_user(tg_id)
        if user:
            # Если пользователь уже существует, но пришел по реферальной ссылке
            if referred_by:
                await self.add_referral(referred_by, tg_id)
            return user
        return await self.create_user(tg_id, username, first_name, last_name, referred_by)
    
    async def update_user_categories(self, tg_id: int, categories: List[str]) -> bool:
        """Обновить категории пользователя"""
        try:
            self._request(
                "PATCH", 
                f"users?tg_id=eq.{tg_id}",
                json={"categories": categories}
            )
            logger.info(f"✅ Обновлены категории для {tg_id}: {categories}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления категорий {tg_id}: {e}")
            return False
    
    async def update_user_subscription(self, tg_id: int, is_subscribed: bool) -> bool:
        """Обновить статус подписки пользователя"""
        try:
            self._request(
                "PATCH",
                f"users?tg_id=eq.{tg_id}",
                json={"is_subscribed": is_subscribed}
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления подписки {tg_id}: {e}")
            return False
    
    async def get_users_by_category(self, category: str) -> List[Dict]:
        """Получить активных пользователей по категории"""
        try:
            result = self._request(
                "GET",
                f"users?categories=cs.{{{category}}}&is_active=eq.true&is_subscribed=eq.true&is_banned=eq.false&select=*"
            )
            return result or []
        except Exception as e:
            logger.error(f"Ошибка получения пользователей категории {category}: {e}")
            return []
    
    async def get_all_active_users(self) -> List[Dict]:
        """Получить всех активных пользователей"""
        try:
            result = self._request(
                "GET",
                "users?is_active=eq.true&is_banned=eq.false&select=*"
            )
            return result or []
        except Exception as e:
            logger.error(f"Ошибка получения активных пользователей: {e}")
            return []
    
    async def get_users_count(self) -> int:
        """Получить общее количество пользователей"""
        try:
            headers = {**self.headers, "Prefer": "count=exact"}
            response = self.client.get(
                f"{self.base_url}/users?select=id",
                headers=headers
            )
            count_header = response.headers.get("content-range", "")
            if "/" in count_header:
                return int(count_header.split("/")[1])
            return len(response.json()) if response.text else 0
        except Exception as e:
            logger.error(f"Ошибка подсчета пользователей: {e}")
            return 0
    
    async def ban_user(self, tg_id: int, ban: bool = True) -> bool:
        """Заблокировать/разблокировать пользователя"""
        try:
            self._request(
                "PATCH",
                f"users?tg_id=eq.{tg_id}",
                json={"is_banned": ban}
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка бана пользователя {tg_id}: {e}")
            return False
    
    # =========================================
    # VACANCIES (из парсинга)
    # =========================================
    
    @staticmethod
    def _hash_text(text: str) -> str:
        """Создать хеш текста для дедупликации"""
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    async def vacancy_exists(self, text: str) -> bool:
        """Проверить существует ли вакансия (по хешу)"""
        try:
            text_hash = self._hash_text(text)
            result = self._request(
                "GET",
                f"vacancies?text_hash=eq.{text_hash}&select=id"
            )
            return len(result) > 0 if result else False
        except Exception as e:
            logger.error(f"Ошибка проверки вакансии: {e}")
            return True
    
    async def create_vacancy(
        self,
        text: str,
        category: str,
        source: str,
        source_message_id: Optional[int] = None,
        has_photo: bool = False,
        photo_message_id: Optional[int] = None
    ) -> Optional[Dict]:
        """Создать новую вакансию"""
        try:
            text_hash = self._hash_text(text)
            
            if await self.vacancy_exists(text):
                logger.debug(f"Вакансия уже существует (hash: {text_hash[:16]}...)")
                return None
            
            data = {
                "text": text,
                "category": category,
                "source": source,
                "source_message_id": source_message_id,
                "text_hash": text_hash,
                "is_sent": False,
                "has_photo": has_photo,
                "photo_message_id": photo_message_id
            }
            result = self._request("POST", "vacancies", json=data)
            logger.info(f"✅ Создана вакансия: {category} из {source}")
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка создания вакансии: {e}")
            return None
    
    async def get_unsent_vacancies(self, category: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Получить неотправленные вакансии"""
        try:
            endpoint = f"vacancies?is_sent=eq.false&order=created_at.asc&limit={limit}&select=*"
            if category:
                endpoint += f"&category=eq.{category}"
            result = self._request("GET", endpoint)
            return result or []
        except Exception as e:
            logger.error(f"Ошибка получения неотправленных вакансий: {e}")
            return []
    
    async def mark_vacancy_sent(self, vacancy_id: int) -> bool:
        """Отметить вакансию как отправленную"""
        try:
            self._request(
                "PATCH",
                f"vacancies?id=eq.{vacancy_id}",
                json={"is_sent": True}
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отметки вакансии {vacancy_id}: {e}")
            return False
    
    async def get_vacancies_count(self) -> int:
        """Получить общее количество вакансий"""
        try:
            headers = {**self.headers, "Prefer": "count=exact"}
            response = self.client.get(
                f"{self.base_url}/vacancies?select=id",
                headers=headers
            )
            count_header = response.headers.get("content-range", "")
            if "/" in count_header:
                return int(count_header.split("/")[1])
            return len(response.json()) if response.text else 0
        except Exception as e:
            logger.error(f"Ошибка подсчета вакансий: {e}")
            return 0
    
    # =========================================
    # SENT VACANCIES (история отправки)
    # =========================================
    
    async def record_sent_vacancy(self, user_id: int, vacancy_id: int) -> bool:
        """Записать факт отправки вакансии пользователю"""
        try:
            self._request(
                "POST",
                "sent_vacancies",
                json={"user_id": user_id, "vacancy_id": vacancy_id}
            )
            return True
        except Exception as e:
            if "duplicate" in str(e).lower():
                return False
            logger.error(f"Ошибка записи отправки: {e}")
            return False
    
    async def was_vacancy_sent_to_user(self, user_id: int, vacancy_id: int) -> bool:
        """Проверить была ли вакансия отправлена пользователю"""
        try:
            result = self._request(
                "GET",
                f"sent_vacancies?user_id=eq.{user_id}&vacancy_id=eq.{vacancy_id}&select=id"
            )
            return len(result) > 0 if result else False
        except Exception as e:
            logger.error(f"Ошибка проверки отправки: {e}")
            return True
    
    # =========================================
    # USER VACANCIES (от пользователей)
    # =========================================
    
    async def create_user_vacancy(
        self,
        tg_id: int,
        username: Optional[str],
        text: str,
        category: str,
        contact: str
    ) -> Optional[Dict]:
        """Создать вакансию от пользователя"""
        try:
            data = {
                "tg_id": tg_id,
                "username": username,
                "text": text,
                "category": category,
                "contact": contact,
                "status": "pending"
            }
            result = self._request("POST", "user_vacancies", json=data)
            logger.info(f"✅ Создана вакансия от пользователя {tg_id}")
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка создания пользовательской вакансии: {e}")
            return None
    
    async def get_pending_user_vacancies(self, limit: int = 50) -> List[Dict]:
        """Получить вакансии на модерацию"""
        try:
            result = self._request(
                "GET",
                f"user_vacancies?status=eq.pending&order=created_at.asc&limit={limit}&select=*"
            )
            return result or []
        except Exception as e:
            logger.error(f"Ошибка получения вакансий на модерацию: {e}")
            return []
    
    async def approve_user_vacancy(self, vacancy_id: int, moderator_id: int) -> bool:
        """Одобрить вакансию пользователя"""
        try:
            self._request(
                "PATCH",
                f"user_vacancies?id=eq.{vacancy_id}",
                json={
                    "status": "approved",
                    "moderator_id": moderator_id,
                    "moderated_at": datetime.now(timezone.utc).isoformat()
                }
            )
            logger.info(f"✅ Вакансия {vacancy_id} одобрена")
            return True
        except Exception as e:
            logger.error(f"Ошибка одобрения вакансии {vacancy_id}: {e}")
            return False
    
    async def reject_user_vacancy(
        self, 
        vacancy_id: int, 
        moderator_id: int,
        reason: str = ""
    ) -> bool:
        """Отклонить вакансию пользователя"""
        try:
            self._request(
                "PATCH",
                f"user_vacancies?id=eq.{vacancy_id}",
                json={
                    "status": "rejected",
                    "moderator_id": moderator_id,
                    "moderated_at": datetime.now(timezone.utc).isoformat(),
                    "rejection_reason": reason
                }
            )
            logger.info(f"❌ Вакансия {vacancy_id} отклонена")
            return True
        except Exception as e:
            logger.error(f"Ошибка отклонения вакансии {vacancy_id}: {e}")
            return False
    
    async def get_user_vacancy(self, vacancy_id: int) -> Optional[Dict]:
        """Получить вакансию пользователя по ID"""
        try:
            result = self._request(
                "GET",
                f"user_vacancies?id=eq.{vacancy_id}&select=*"
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения вакансии {vacancy_id}: {e}")
            return None
    
    # =========================================
    # PARSE SOURCES
    # =========================================
    
    async def get_active_sources(self) -> List[Dict]:
        """Получить активные источники парсинга"""
        try:
            result = self._request(
                "GET",
                "parse_sources?is_active=eq.true&select=*"
            )
            return result or []
        except Exception as e:
            logger.error(f"Ошибка получения источников: {e}")
            return []
    
    async def add_source(
        self,
        source_type: str,
        source_id: str,
        title: Optional[str] = None
    ) -> Optional[Dict]:
        """Добавить источник парсинга"""
        try:
            # Сначала проверяем существует ли источник (активный или неактивный)
            existing = self._request(
                "GET",
                f"parse_sources?source_id=eq.{source_id}&select=*"
            )
            
            if existing and len(existing) > 0:
                # Источник уже существует
                source = existing[0]
                
                if source.get("is_active"):
                    # Уже активен - возвращаем существующий
                    logger.info(f"ℹ️ Источник {source_id} уже активен")
                    return source
                else:
                    # Неактивен - активируем и обновляем
                    update_data = {
                        "is_active": True,
                        "title": title or source.get("title") or source_id
                    }
                    result = self._request(
                        "PATCH",
                        f"parse_sources?source_id=eq.{source_id}",
                        json=update_data
                    )
                    logger.info(f"✅ Источник {source_id} активирован")
                    return result[0] if result else source
            
            # Источника нет - создаем новый
            data = {
                "source_type": source_type,
                "source_id": source_id,
                "title": title or source_id,
                "is_active": True
            }
            result = self._request("POST", "parse_sources", json=data)
            logger.info(f"✅ Добавлен источник: {source_id}")
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка добавления источника {source_id}: {e}")
            return None
    
    async def update_source_last_message(self, source_id: str, message_id: int) -> bool:
        """Обновить ID последнего обработанного сообщения"""
        try:
            self._request(
                "PATCH",
                f"parse_sources?source_id=eq.{source_id}",
                json={
                    "last_message_id": message_id,
                    "last_parsed_at": datetime.now(timezone.utc).isoformat()
                }
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления источника {source_id}: {e}")
            return False
    
    async def remove_source(self, source_id: str) -> bool:
        """Деактивировать источник"""
        try:
            self._request(
                "PATCH",
                f"parse_sources?source_id=eq.{source_id}",
                json={"is_active": False}
            )
            logger.info(f"🗑 Источник деактивирован: {source_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления источника {source_id}: {e}")
            return False
    
    # =========================================
    # RATE LIMITING
    # =========================================
    
    async def record_send_log(self, user_id: int) -> bool:
        """Записать лог отправки сообщения"""
        try:
            self._request(
                "POST",
                "send_logs",
                json={"user_id": user_id}
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка записи лога: {e}")
            return False
    
    async def get_user_send_count_last_hour(self, user_id: int) -> int:
        """Получить количество отправленных сообщений за последний час"""
        try:
            hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            # Экранируем дату для URL (особенно символы + и :)
            hour_ago_encoded = quote(hour_ago, safe='')
            result = self._request(
                "GET",
                f"send_logs?user_id=eq.{user_id}&sent_at=gte.{hour_ago_encoded}&select=id"
            )
            return len(result) if result else 0
        except Exception as e:
            logger.error(f"Ошибка подсчета сообщений: {e}")
            return 0
    
    async def can_send_to_user(self, user_id: int) -> bool:
        """Проверить можно ли отправить сообщение пользователю (rate limit)"""
        count = await self.get_user_send_count_last_hour(user_id)
        return count < config.rate_limit.max_messages_per_hour
    
    # =========================================
    # STATISTICS
    # =========================================
    
    async def get_stats(self) -> Dict[str, Any]:
        """Получить статистику бота"""
        try:
            users_count = await self.get_users_count()
            vacancies_count = await self.get_vacancies_count()
            
            pending = self._request(
                "GET",
                "user_vacancies?status=eq.pending&select=id"
            )
            pending_count = len(pending) if pending else 0
            
            sources = self._request(
                "GET",
                "parse_sources?is_active=eq.true&select=id"
            )
            sources_count = len(sources) if sources else 0
            
            return {
                "users": users_count,
                "vacancies": vacancies_count,
                "pending_moderation": pending_count,
                "active_sources": sources_count
            }
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}
    
    # =========================================
    # DEFAULT PHOTO
    # =========================================
    
    async def get_default_photo(self) -> Optional[str]:
        """Получить file_id дефолтного фото"""
        try:
            result = self._request(
                "GET",
                "default_photo?select=file_id&order=uploaded_at.desc&limit=1"
            )
            return result[0]["file_id"] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения дефолтного фото: {e}")
            return None
    
    async def set_default_photo(self, file_id: str, file_unique_id: str, uploaded_by: int) -> bool:
        """Установить дефолтное фото"""
        try:
            # Удаляем все старые записи (в таблице должна быть только одна запись)
            # Используем WHERE clause для безопасности
            self._request("DELETE", "default_photo?id=gt.0")  # Удаляем все записи (id > 0)
            
            # Добавляем новое
            self._request(
                "POST",
                "default_photo",
                json={
                    "file_id": file_id,
                    "file_unique_id": file_unique_id,
                    "uploaded_by": uploaded_by
                }
            )
            logger.info("✅ Дефолтное фото обновлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка установки дефолтного фото: {e}")
            return False
    
    async def update_vacancy_photo(self, vacancy_id: int, photo_file_id: str) -> bool:
        """Обновить file_id фото для вакансии"""
        try:
            self._request(
                "PATCH",
                f"vacancies?id=eq.{vacancy_id}",
                json={"photo_file_id": photo_file_id}
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления фото вакансии: {e}")
            return False

    # =========================================
    # FAQ PHOTO
    # =========================================

    async def get_faq_photo(self) -> Optional[str]:
        """Получить file_id фото для FAQ"""
        try:
            result = self._request(
                "GET",
                "faq_photo?select=file_id&order=uploaded_at.desc&limit=1"
            )
            return result[0]["file_id"] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения FAQ фото: {e}")
            return None

    async def set_faq_photo(self, file_id: str, file_unique_id: str, uploaded_by: int) -> bool:
        """Установить фото для FAQ"""
        try:
            # Удаляем все старые записи (в таблице должна быть только одна запись)
            # Используем WHERE clause для безопасности
            self._request("DELETE", "faq_photo?id=gt.0")  # Удаляем все записи (id > 0)

            # Добавляем новое
            self._request(
                "POST",
                "faq_photo",
                json={
                    "file_id": file_id,
                    "file_unique_id": file_unique_id,
                    "uploaded_by": uploaded_by
                }
            )
            logger.info("✅ FAQ фото обновлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка установки FAQ фото: {e}")
            return False
    
    # =========================================
    # STATS PHOTO
    # =========================================

    async def get_stats_photo(self) -> Optional[str]:
        """Получить file_id фото для статистики"""
        try:
            result = self._request(
                "GET",
                "stats_photo?select=file_id&order=uploaded_at.desc&limit=1"
            )
            return result[0]["file_id"] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения фото статистики: {e}")
            return None

    async def set_stats_photo(self, file_id: str, file_unique_id: str, uploaded_by: int) -> bool:
        """Установить фото для статистики"""
        try:
            # Удаляем старое
            self._request("DELETE", "stats_photo")

            # Добавляем новое
            self._request(
                "POST",
                "stats_photo",
                json={
                    "file_id": file_id,
                    "file_unique_id": file_unique_id,
                    "uploaded_by": uploaded_by
                }
            )
            logger.info("✅ Фото статистики обновлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка установки фото статистики: {e}")
            return False
    
    # =========================================
    # CATEGORIES PHOTO
    # =========================================

    async def get_categories_photo(self) -> Optional[str]:
        """Получить file_id фото для направлений"""
        try:
            result = self._request(
                "GET",
                "categories_photo?select=file_id&order=uploaded_at.desc&limit=1"
            )
            return result[0]["file_id"] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения фото направлений: {e}")
            return None

    async def set_categories_photo(self, file_id: str, file_unique_id: str, uploaded_by: int) -> bool:
        """Установить фото для направлений"""
        try:
            # Удаляем старое
            self._request("DELETE", "categories_photo")

            # Добавляем новое
            self._request(
                "POST",
                "categories_photo",
                json={
                    "file_id": file_id,
                    "file_unique_id": file_unique_id,
                    "uploaded_by": uploaded_by
                }
            )
            logger.info("✅ Фото направлений обновлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка установки фото направлений: {e}")
            return False
    
    # =========================================
    # WELCOME PHOTO
    # =========================================

    async def get_welcome_photo(self) -> Optional[str]:
        """Получить file_id фото для приветственного сообщения"""
        try:
            result = self._request(
                "GET",
                "welcome_photo?select=file_id&order=uploaded_at.desc&limit=1"
            )
            return result[0]["file_id"] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения фото приветствия: {e}")
            return None

    async def set_welcome_photo(self, file_id: str, file_unique_id: str, uploaded_by: int) -> bool:
        """Установить фото для приветственного сообщения"""
        try:
            # Удаляем старое
            self._request("DELETE", "welcome_photo")

            # Добавляем новое
            self._request(
                "POST",
                "welcome_photo",
                json={
                    "file_id": file_id,
                    "file_unique_id": file_unique_id,
                    "uploaded_by": uploaded_by
                }
            )
            logger.info("✅ Фото приветствия обновлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка установки фото приветствия: {e}")
            return False
    
    # =========================================
    # REFERRAL PHOTO
    # =========================================

    async def get_referral_photo(self) -> Optional[str]:
        """Получить file_id фото для реферальной системы"""
        try:
            result = self._request(
                "GET",
                "referral_photo?select=file_id&order=uploaded_at.desc&limit=1"
            )
            return result[0]["file_id"] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения реферального фото: {e}")
            return None

    async def set_referral_photo(self, file_id: str, file_unique_id: str, uploaded_by: int) -> bool:
        """Установить фото для реферальной системы"""
        try:
            # Удаляем все старые записи (в таблице должна быть только одна запись)
            # Используем WHERE clause для безопасности
            self._request("DELETE", "referral_photo?id=gt.0")  # Удаляем все записи (id > 0)

            # Добавляем новое
            self._request(
                "POST",
                "referral_photo",
                json={
                    "file_id": file_id,
                    "file_unique_id": file_unique_id,
                    "uploaded_by": uploaded_by
                }
            )
            logger.info("✅ Реферальное фото обновлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка установки реферального фото: {e}")
            return False
    
    # =========================================
    # REVIEWS SYSTEM
    # =========================================
    
    async def get_pending_reviews(self, limit: int = 10) -> List[Dict]:
        """Получить отзывы на модерацию"""
        try:
            endpoint = f"reviews?status=eq.pending&order=created_at.desc&limit={limit}"
            logger.debug(f"Запрос к Supabase: GET {endpoint}")
            result = self._request("GET", endpoint)
            
            if result is None:
                logger.warning("get_pending_reviews вернул None - возможно ошибка запроса")
                return []
            
            if isinstance(result, list):
                logger.info(f"Получено отзывов на модерацию: {len(result)}")
                if result:
                    # Логируем первый отзыв для диагностики
                    first_review = result[0]
                    logger.debug(f"Первый отзыв: id={first_review.get('id')}, status={first_review.get('status')}, tg_id={first_review.get('tg_id')}")
                return result
            
            logger.warning(f"get_pending_reviews вернул неожиданный тип: {type(result)}")
            return []
        except Exception as e:
            logger.error(f"Ошибка получения отзывов на модерацию: {e}")
            logger.exception(e)
            return []
    
    async def get_review(self, review_id: int) -> Optional[Dict]:
        """Получить отзыв по ID"""
        try:
            result = self._request("GET", f"reviews?id=eq.{review_id}")
            if result is None:
                logger.warning(f"get_review вернул None для review_id={review_id}")
                return None
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения отзыва {review_id}: {e}")
            logger.exception(e)
            return None
    
    async def get_all_reviews(self, limit: int = 100) -> List[Dict]:
        """Получить все отзывы (для диагностики)"""
        try:
            result = self._request(
                "GET",
                f"reviews?order=created_at.desc&limit={limit}"
            )
            if result is None:
                logger.warning("get_all_reviews вернул None")
                return []
            if isinstance(result, list):
                logger.info(f"Найдено отзывов: {len(result)}")
                # Логируем статусы отзывов
                statuses = {}
                for review in result:
                    status = review.get("status", "unknown")
                    statuses[status] = statuses.get(status, 0) + 1
                logger.info(f"Статусы отзывов: {statuses}")
                return result
            return []
        except Exception as e:
            logger.error(f"Ошибка получения всех отзывов: {e}")
            logger.exception(e)
            return []
    
    async def approve_review(
        self,
        review_id: int,
        moderator_id: int
    ) -> bool:
        """Одобрить отзыв и начислить 3 дня x2"""
        try:
            # Получаем отзыв для получения tg_id пользователя
            review = await self.get_review(review_id)
            if not review:
                logger.error(f"Отзыв {review_id} не найден")
                return False
            
            user_tg_id = review["tg_id"]
            
            # Обновляем статус отзыва
            self._request(
                "PATCH",
                f"reviews?id=eq.{review_id}",
                json={
                    "status": "approved",
                    "moderator_id": moderator_id,
                    "moderated_at": datetime.now(timezone.utc).isoformat(),
                    "x2_awarded": True,
                    "x2_awarded_at": datetime.now(timezone.utc).isoformat()
                }
            )
            
            # Начисляем 3 дня x2 статуса
            await self.award_x2_status(user_tg_id, days=3)
            
            logger.info(f"✅ Отзыв {review_id} одобрен, x2 начислен пользователю {user_tg_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка одобрения отзыва: {e}")
            return False
    
    async def reject_review(
        self,
        review_id: int,
        moderator_id: int,
        reason: str = ""
    ) -> bool:
        """Отклонить отзыв"""
        try:
            self._request(
                "PATCH",
                f"reviews?id=eq.{review_id}",
                json={
                    "status": "rejected",
                    "moderator_id": moderator_id,
                    "moderated_at": datetime.now(timezone.utc).isoformat(),
                    "rejection_reason": reason
                }
            )
            logger.info(f"✅ Отзыв {review_id} отклонен")
            return True
        except Exception as e:
            logger.error(f"Ошибка отклонения отзыва: {e}")
            return False
    
    async def award_x2_status(self, tg_id: int, days: int = 3) -> bool:
        """Начислить x2 статус на указанное количество дней"""
        try:
            # Получаем текущего пользователя
            user = self._request("GET", f"users?tg_id=eq.{tg_id}")
            if not user:
                logger.error(f"Пользователь {tg_id} не найден")
                return False
            
            user_data = user[0]
            current_x2_until = user_data.get("x2_until")
            
            # Вычисляем новую дату окончания x2
            now = datetime.now(timezone.utc)
            
            if current_x2_until:
                # Если уже есть x2 статус - продлеваем
                try:
                    if isinstance(current_x2_until, str):
                        current_date = datetime.fromisoformat(current_x2_until.replace('Z', '+00:00'))
                    else:
                        current_date = current_x2_until
                    
                    # Если текущий статус еще действует - продлеваем от текущей даты
                    if current_date > now:
                        new_x2_until = current_date + timedelta(days=days)
                    else:
                        # Если истек - начинаем с текущей даты
                        new_x2_until = now + timedelta(days=days)
                except Exception as e:
                    logger.warning(f"Ошибка парсинга даты x2_until: {e}")
                    new_x2_until = now + timedelta(days=days)
            else:
                # Если x2 статуса нет - начинаем с текущей даты
                new_x2_until = now + timedelta(days=days)
            
            # Обновляем пользователя
            self._request(
                "PATCH",
                f"users?tg_id=eq.{tg_id}",
                json={
                    "x2_until": new_x2_until.isoformat()
                }
            )
            
            logger.info(f"✅ Начислено {days} дней x2 статуса пользователю {tg_id}, до {new_x2_until}")
            return True
        except Exception as e:
            logger.error(f"Ошибка начисления x2 статуса: {e}")
            return False
    
    # =========================================
    # REFERRAL SYSTEM
    # =========================================

    async def get_user_by_referral_code(self, referral_code: str) -> Optional[Dict]:
        """Получить пользователя по реферальному коду"""
        try:
            result = self._request(
                "GET",
                f"users?referral_code=eq.{referral_code}&select=*"
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя по реферальному коду: {e}")
            return None

    async def add_referral(self, referrer_id: int, referred_id: int) -> bool:
        """Добавить реферала"""
        try:
            # Проверяем, не регистрировался ли уже этот пользователь по реферальной ссылке
            existing = self._request(
                "GET",
                f"referrals?referred_id=eq.{referred_id}"
            )
            if existing:
                logger.info(f"Пользователь {referred_id} уже был приглашен ранее")
                return False
            
            # Добавляем реферала
            self._request(
                "POST",
                "referrals",
                json={
                    "referrer_id": referrer_id,
                    "referred_id": referred_id
                }
            )
            
            # Обновляем счетчик рефералов у пригласившего
            referrer = await self.get_user(referrer_id)
            if referrer:
                new_count = referrer.get("referral_count", 0) + 1
                self._request(
                    "PATCH",
                    f"users?tg_id=eq.{referrer_id}",
                    json={"referral_count": new_count}
                )
            
            # Добавляем +24 часа x2 статуса пригласившему
            referrer = await self.get_user(referrer_id)
            if referrer:
                current_x2_until = referrer.get("x2_until")
                now = datetime.now(timezone.utc)
                
                if current_x2_until:
                    try:
                        x2_str = current_x2_until.replace('Z', '+00:00')
                        if '+' not in x2_str and 'T' in x2_str:
                            x2_str += '+00:00'
                        current_x2_until_dt = datetime.fromisoformat(x2_str)
                        
                        # Делаем aware если нужно
                        if current_x2_until_dt.tzinfo is None:
                            current_x2_until_dt = current_x2_until_dt.replace(tzinfo=timezone.utc)
                        
                        if current_x2_until_dt > now:
                            # Увеличиваем существующий срок
                            new_x2_until = current_x2_until_dt + timedelta(hours=24)
                        else:
                            # Начинаем новый срок
                            new_x2_until = now + timedelta(hours=24)
                    except:
                        new_x2_until = now + timedelta(hours=24)
                else:
                    new_x2_until = now + timedelta(hours=24)
                
                self._request(
                    "PATCH",
                    f"users?tg_id=eq.{referrer_id}",
                    json={"x2_until": new_x2_until.isoformat()}
                )
            
            logger.info(f"✅ Добавлен реферал: {referrer_id} -> {referred_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления реферала: {e}")
            return False

    async def is_user_x2(self, tg_id: int) -> bool:
        """Проверить, активен ли у пользователя статус x2"""
        try:
            user = await self.get_user(tg_id)
            if not user:
                return False
            
            x2_until = user.get("x2_until")
            if not x2_until:
                return False
            
            try:
                # Пробуем разные форматы даты
                if isinstance(x2_until, str):
                    # Убираем Z и добавляем timezone если нужно
                    x2_str = x2_until.replace('Z', '+00:00')
                    if '+' not in x2_str and 'T' in x2_str:
                        x2_str += '+00:00'
                    x2_until_dt = datetime.fromisoformat(x2_str)
                else:
                    # Если это уже datetime объект
                    x2_until_dt = x2_until
                
                # Используем timezone-aware datetime для сравнения
                now = datetime.now(timezone.utc)
                
                # Если x2_until_dt naive - делаем его aware
                if x2_until_dt.tzinfo is None:
                    x2_until_dt = x2_until_dt.replace(tzinfo=timezone.utc)
                
                is_active = x2_until_dt > now
                logger.debug(f"Проверка x2 для {tg_id}: x2_until={x2_until_dt}, now={now}, active={is_active}")
                return is_active
            except Exception as e:
                logger.error(f"Ошибка парсинга даты x2_until для {tg_id}: {e}, значение: {x2_until}")
                return False
        except Exception as e:
            logger.error(f"Ошибка проверки x2 статуса для {tg_id}: {e}")
            return False

    async def get_referral_stats(self, tg_id: int) -> Dict[str, Any]:
        """Получить статистику по рефералам"""
        try:
            user = await self.get_user(tg_id)
            if not user:
                return {"referral_count": 0, "referral_code": None, "x2_active": False, "x2_until": None}
            
            referral_count = user.get("referral_count", 0)
            referral_code = user.get("referral_code")
            x2_active = await self.is_user_x2(tg_id)
            x2_until = user.get("x2_until")
            
            return {
                "referral_count": referral_count,
                "referral_code": referral_code,
                "x2_active": x2_active,
                "x2_until": x2_until
            }
        except Exception as e:
            logger.error(f"Ошибка получения статистики рефералов: {e}")
            return {"referral_count": 0, "referral_code": None, "x2_active": False, "x2_until": None}

    async def create_referral_code(self, tg_id: int) -> Optional[str]:
        """Создать реферальный код для существующего пользователя"""
        import secrets
        try:
            # Генерируем уникальный реферальный код
            referral_code = secrets.token_urlsafe(8)[:12].upper()
            
            # Проверяем уникальность
            existing = await self.get_user_by_referral_code(referral_code)
            if existing:
                # Если код уже существует, генерируем новый
                referral_code = secrets.token_urlsafe(8)[:12].upper()
            
            # Обновляем пользователя
            self._request(
                "PATCH",
                f"users?tg_id=eq.{tg_id}",
                json={"referral_code": referral_code}
            )
            logger.info(f"✅ Создан реферальный код {referral_code} для пользователя {tg_id}")
            return referral_code
        except Exception as e:
            logger.error(f"Ошибка создания реферального кода для {tg_id}: {e}")
            return None


# Глобальный инстанс клиента
db = SupabaseClient()
