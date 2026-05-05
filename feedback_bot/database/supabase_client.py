"""
Клиент для работы с Supabase.
Использует REST API для взаимодействия с базой данных.
"""

import logging
import httpx
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta

from config import config

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Клиент для работы с Supabase через REST API.
    """
    
    def __init__(self):
        self.url = config.supabase.url.rstrip('/')
        self.key = config.supabase.key
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        self.client = httpx.AsyncClient(timeout=10.0)
    
    async def _request(self, method: str, endpoint: str, json: Optional[Dict] = None) -> Any:
        """
        Выполнить HTTP запрос к Supabase.
        
        Args:
            method: HTTP метод (GET, POST, PATCH, DELETE)
            endpoint: Endpoint без базового URL (например, "users?tg_id=eq.123")
            json: JSON данные для POST/PATCH запросов
            
        Returns:
            Ответ от API (список или словарь)
        """
        url = f"{self.url}/rest/v1/{endpoint}"
        
        try:
            response = await self.client.request(
                method=method,
                url=url,
                headers=self.headers,
                json=json
            )
            response.raise_for_status()
            
            # Если ответ пустой - возвращаем пустой список
            if not response.text or response.text.strip() == '':
                return []
            
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка запроса к Supabase {method} {endpoint}: {e}")
            if e.response is not None:
                logger.error(f"Ответ сервера: {e.response.text[:500]}")
            raise
        except Exception as e:
            logger.error(f"Ошибка запроса к Supabase {method} {endpoint}: {e}")
            raise
    
    async def close(self):
        """Закрыть HTTP клиент"""
        await self.client.aclose()
    
    # =========================================
    # REVIEWS
    # =========================================
    
    async def create_review(
        self,
        tg_id: int,
        text: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        rating: Optional[int] = None
    ) -> Optional[Dict]:
        """Создать новый отзыв"""
        try:
            result = await self._request(
                "POST",
                "reviews",
                json={
                    "tg_id": tg_id,
                    "username": username,
                    "first_name": first_name,
                    "text": text,
                    "rating": rating,
                    "status": "pending"
                }
            )
            logger.info(f"✅ Отзыв создан для пользователя {tg_id}")
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка создания отзыва: {e}")
            return None
    
    async def get_pending_reviews(self, limit: int = 10) -> List[Dict]:
        """Получить отзывы на модерацию"""
        try:
            result = await self._request(
                "GET",
                f"reviews?status=eq.pending&order=created_at.desc&limit={limit}"
            )
            return result if result else []
        except Exception as e:
            logger.error(f"Ошибка получения отзывов на модерацию: {e}")
            return []
    
    async def approve_review(
        self,
        review_id: int,
        moderator_id: int
    ) -> bool:
        """Одобрить отзыв и начислить 3 дня x2"""
        try:
            # Обновляем статус отзыва
            await self._request(
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
            
            # Получаем отзыв для получения tg_id пользователя
            review = await self._request("GET", f"reviews?id=eq.{review_id}")
            if not review:
                logger.error(f"Отзыв {review_id} не найден")
                return False
            
            user_tg_id = review[0]["tg_id"]
            
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
            await self._request(
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
            user = await self._request("GET", f"users?tg_id=eq.{tg_id}")
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
            await self._request(
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
    
    async def get_user_review_count(self, tg_id: int) -> int:
        """Получить количество одобренных отзывов пользователя"""
        try:
            result = await self._request(
                "GET",
                f"reviews?tg_id=eq.{tg_id}&status=eq.approved&select=id"
            )
            return len(result) if result else 0
        except Exception as e:
            logger.error(f"Ошибка подсчета отзывов: {e}")
            return 0
    
    async def get_user_reviews(self, tg_id: int) -> List[Dict]:
        """Получить все отзывы пользователя (любого статуса)"""
        try:
            result = await self._request(
                "GET",
                f"reviews?tg_id=eq.{tg_id}&order=created_at.desc"
            )
            return result if result else []
        except Exception as e:
            logger.error(f"Ошибка получения отзывов пользователя {tg_id}: {e}")
            return []

