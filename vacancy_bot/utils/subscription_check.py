"""
Проверка подписки пользователя на обязательный канал.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

from config import config

logger = logging.getLogger(__name__)

_SUBSCRIBED_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.RESTRICTED,
}


@dataclass
class SubscriptionResult:
    subscribed: bool
    bot_can_check: bool = True
    error: Optional[str] = None


def _channel_chat_id() -> str:
    return config.channel.required_channel.strip()


async def verify_bot_channel_access(bot: Bot) -> Optional[str]:
    """
    Проверяет, может ли бот проверять подписку на канале.
    Возвращает текст ошибки или None, если всё ок.
    """
    channel = _channel_chat_id()
    if not channel:
        return None

    try:
        chat = await bot.get_chat(channel)
    except TelegramBadRequest as e:
        return (
            f"Канал {channel} недоступен боту: {e.message}. "
            "Проверьте REQUIRED_CHANNEL в .env."
        )
    except Exception as e:
        return f"Не удалось получить канал {channel}: {e}"

    try:
        me = await bot.get_me()
        await bot.get_chat_member(chat.id, me.id)
    except TelegramBadRequest as e:
        if "member list is inaccessible" in (e.message or "").lower():
            return (
                f"Бот не может проверять подписку на {channel}. "
                "Добавьте бота администратором канала "
                "(достаточно права «Добавление участников» или любого минимального)."
            )
        if "user not found" in (e.message or "").lower():
            return (
                f"Бот не добавлен в канал {channel}. "
                "Добавьте бота в канал как администратора."
            )
        return f"Ошибка доступа бота к каналу {channel}: {e.message}"
    except Exception as e:
        return f"Ошибка проверки доступа бота к каналу {channel}: {e}"

    return None


async def check_channel_subscription(bot: Bot, user_id: int) -> SubscriptionResult:
    """Проверить, подписан ли пользователь на обязательный канал."""
    channel = _channel_chat_id()
    if not channel:
        return SubscriptionResult(subscribed=True)

    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return SubscriptionResult(
            subscribed=member.status in _SUBSCRIBED_STATUSES
        )
    except TelegramBadRequest as e:
        message = (e.message or "").lower()
        if "member list is inaccessible" in message:
            logger.error(
                "Бот не админ канала %s — проверка подписки невозможна",
                channel,
            )
            return SubscriptionResult(
                subscribed=False,
                bot_can_check=False,
                error="bot_not_admin",
            )
        logger.error("Ошибка проверки подписки для %s: %s", user_id, e.message)
        return SubscriptionResult(subscribed=False, error=e.message)
    except Exception as e:
        logger.error("Ошибка проверки подписки для %s: %s", user_id, e)
        return SubscriptionResult(subscribed=False, error=str(e))
