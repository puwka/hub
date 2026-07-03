"""
Клиент Supabase для работы с пользовательскими вакансиями.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List

import httpx

from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Минимальный Supabase-клиент для user_vacancies."""

    def __init__(self):
        self.base_url = f"{SUPABASE_URL}/rest/v1"
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = httpx.Client(headers=self.headers, timeout=15)
        logger.info("✅ Supabase клиент инициализирован")

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[list]:
        url = f"{self.base_url}/{endpoint}"
        try:
            resp = self._client.request(method, url, **kwargs)
            resp.raise_for_status()
            if resp.status_code == 204:
                return []
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Supabase HTTP error: {e.response.status_code} {e.response.text[:200]}")
            raise
        except Exception as e:
            logger.error(f"Supabase request error: {e}")
            raise

    # ----- user_vacancies -----

    async def create_user_vacancy(
        self,
        tg_id: int,
        username: Optional[str],
        text: str,
        category: str,
        contact: str,
    ) -> Optional[Dict]:
        """Создать вакансию от пользователя."""
        try:
            data = {
                "tg_id": tg_id,
                "username": username,
                "text": text,
                "category": category,
                "contact": contact,
                "status": "pending",
            }
            result = self._request("POST", "user_vacancies", json=data)
            logger.info(f"✅ Создана вакансия от пользователя {tg_id}")
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка создания вакансии: {e}")
            return None

    async def get_user_vacancy(self, vacancy_id: int) -> Optional[Dict]:
        """Получить вакансию по ID."""
        try:
            result = self._request(
                "GET", f"user_vacancies?id=eq.{vacancy_id}&select=*"
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения вакансии {vacancy_id}: {e}")
            return None

    async def approve_user_vacancy(
        self, vacancy_id: int, moderator_id: int
    ) -> bool:
        """Одобрить вакансию."""
        try:
            self._request(
                "PATCH",
                f"user_vacancies?id=eq.{vacancy_id}",
                json={
                    "status": "approved",
                    "moderator_id": moderator_id,
                    "moderated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(f"✅ Вакансия {vacancy_id} одобрена")
            return True
        except Exception as e:
            logger.error(f"Ошибка одобрения вакансии {vacancy_id}: {e}")
            return False

    async def reject_user_vacancy(
        self, vacancy_id: int, moderator_id: int, reason: str = ""
    ) -> bool:
        """Отклонить вакансию."""
        try:
            self._request(
                "PATCH",
                f"user_vacancies?id=eq.{vacancy_id}",
                json={
                    "status": "rejected",
                    "moderator_id": moderator_id,
                    "moderated_at": datetime.now(timezone.utc).isoformat(),
                    "rejection_reason": reason,
                },
            )
            logger.info(f"❌ Вакансия {vacancy_id} отклонена")
            return True
        except Exception as e:
            logger.error(f"Ошибка отклонения вакансии {vacancy_id}: {e}")
            return False
