"""Утилиты подписки на вакансии."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Поле в Supabase (legacy-имя колонки)
SUBSCRIPTION_UNTIL_FIELD = "x2_until"


def parse_subscription_until(value) -> Optional[datetime]:
    """Распарсить дату окончания подписки из БД."""
    if not value:
        return None
    try:
        if isinstance(value, str):
            dt_str = value.replace("Z", "+00:00")
            if "+" not in dt_str and "T" in dt_str:
                dt_str += "+00:00"
            dt = datetime.fromisoformat(dt_str)
        else:
            dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logger.error("Ошибка парсинга даты подписки: %s, value=%s", e, value)
        return None


def is_subscription_active(subscription_until) -> bool:
    """Активна ли подписка."""
    until = parse_subscription_until(subscription_until)
    if not until:
        return False
    return until > datetime.now(timezone.utc)


def format_subscription_status_html(subscription_until) -> str:
    """HTML-блок со статусом подписки."""
    until = parse_subscription_until(subscription_until)
    if not until or until <= datetime.now(timezone.utc):
        return "📅 <b>Подписка:</b> неактивна\n\n"

    now = datetime.now(timezone.utc)
    seconds_left = int((until - now).total_seconds())
    days_left = seconds_left // 86400
    hours_left = (seconds_left % 86400) // 3600

    if days_left >= 1:
        day_word = _days_word(days_left)
        text = f"📅 <b>Подписка активна</b>\n⏰ Осталось: {days_left} {day_word}"
        if hours_left > 0 and days_left < 3:
            text += f" {hours_left} ч."
        return text + "\n\n"

    if hours_left >= 1:
        return f"📅 <b>Подписка активна</b>\n⏰ Осталось: {hours_left} ч.\n\n"

    return "📅 <b>Подписка активна</b>\n⏰ Осталось: менее часа\n\n"


def _days_word(n: int) -> str:
    n = abs(n) % 100
    n1 = n % 10
    if 11 <= n <= 19:
        return "дней"
    if n1 == 1:
        return "день"
    if 2 <= n1 <= 4:
        return "дня"
    return "дней"
