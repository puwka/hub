"""
Middleware для проверки подписки на обязательный канал.
"""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.enums import ChatMemberStatus

from config import config


class SubscriptionMiddleware(BaseMiddleware):
    """
    Middleware для проверки подписки пользователя на обязательный канал.
    Пропускает админов и callback-запросы проверки подписки.
    """
    
    # Callback'и которые пропускаем без проверки
    ALLOWED_CALLBACKS = [
        "check_subscription",
    ]
    
    # Команды которые пропускаем без проверки
    ALLOWED_COMMANDS = [
        "/start",
    ]
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Проверка подписки перед обработкой события"""
        
        # Если канал не указан - пропускаем проверку
        if not config.channel.required_channel:
            return await handler(event, data)
        
        # Получаем user_id
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
            
            # Пропускаем разрешенные команды
            if event.text and event.text.split()[0] in self.ALLOWED_COMMANDS:
                return await handler(event, data)
                
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            
            # Пропускаем разрешенные callback'и
            if event.data in self.ALLOWED_CALLBACKS:
                return await handler(event, data)
        
        if not user_id:
            return await handler(event, data)
        
        # Пропускаем админов
        if user_id in config.admin.ids:
            return await handler(event, data)
        
        # Проверяем подписку
        bot = data.get("bot")
        if bot:
            try:
                member = await bot.get_chat_member(
                    chat_id=config.channel.required_channel,
                    user_id=user_id
                )
                
                valid_statuses = [
                    ChatMemberStatus.MEMBER,
                    ChatMemberStatus.ADMINISTRATOR,
                    ChatMemberStatus.CREATOR
                ]
                
                if member.status in valid_statuses:
                    return await handler(event, data)
                    
            except Exception:
                pass
            
            # Не подписан - отправляем напоминание
            from keyboards import subscription_keyboard
            
            text = (
                f"📢 Для использования бота подпишись на канал "
                f"{config.channel.required_channel}"
            )
            
            if isinstance(event, Message):
                await event.answer(
                    text,
                    reply_markup=subscription_keyboard(config.channel.required_channel)
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "Подпишись на канал!",
                    show_alert=True
                )
            
            return None
        
        return await handler(event, data)





