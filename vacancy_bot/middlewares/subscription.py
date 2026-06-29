"""
Middleware для проверки подписки на обязательный канал.
"""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from config import config
from keyboards import subscription_keyboard
from utils.subscription_check import check_channel_subscription


class SubscriptionMiddleware(BaseMiddleware):
    """
    Middleware для проверки подписки пользователя на обязательный канал.
    Пропускает админов и callback-запросы проверки подписки.
    """
    
    ALLOWED_CALLBACKS = [
        "check_subscription",
    ]
    
    ALLOWED_COMMANDS = [
        "/start",
    ]
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not config.channel.required_channel:
            return await handler(event, data)
        
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
            
            if event.text and event.text.split()[0] in self.ALLOWED_COMMANDS:
                return await handler(event, data)
                
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            
            if event.data in self.ALLOWED_CALLBACKS:
                return await handler(event, data)
        
        if not user_id:
            return await handler(event, data)
        
        if user_id in config.admin.ids:
            return await handler(event, data)
        
        bot = data.get("bot")
        if bot:
            subscription = await check_channel_subscription(bot, user_id)
            
            if subscription.subscribed:
                return await handler(event, data)
            
            text = (
                f"Для использования бота подпишись на канал "
                f"{config.channel.required_channel}"
            )
            if not subscription.bot_can_check:
                text = (
                    "Проверка подписки временно недоступна. "
                    "Обратитесь к администратору бота."
                )
            
            if isinstance(event, Message):
                await event.answer(
                    text,
                    reply_markup=subscription_keyboard(config.channel.required_channel)
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "Подпишись на канал!" if subscription.bot_can_check else text,
                    show_alert=True
                )
            
            return None
        
        return await handler(event, data)
