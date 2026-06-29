"""
Главная точка входа Vacancy Bot.

Запуск:
    python main.py

При первом запуске Telethon попросит ввести код из Telegram.
"""

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import config, moderation_enabled
from database import db
from scheduler import TaskScheduler
from utils.proxy import (
    create_aiogram_session,
    get_telegram_api_server,
    iter_proxy_candidates,
    warn_if_remote_proxy_misconfigured,
)
from utils.subscription_check import verify_bot_channel_access
from handlers import (
    user_router,
    categories_router,
    user_vacancy_router,
    admin_router,
    subscription_router,
    vacancy_moderation_router,
)
from middlewares import SubscriptionMiddleware


# =========================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# =========================================

def setup_logging():
    """Настройка логирования"""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure:
                reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("bot.log", encoding="utf-8")
        ]
    )
    
    # Уменьшаем шум от библиотек
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# =========================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# =========================================

async def create_bot() -> Bot:
    """Создаёт бота, автоматически подбирая рабочий прокси."""
    warn_if_remote_proxy_misconfigured()
    api_server = get_telegram_api_server()
    candidates = iter_proxy_candidates()
    if not candidates and not api_server:
        candidates = [None]

    bot_kwargs = {
        "token": config.bot.token,
        "default": DefaultBotProperties(parse_mode=ParseMode.HTML),
    }
    if api_server:
        bot_kwargs["api"] = api_server

    last_error: Exception | None = None
    for proxy in candidates:
        session = create_aiogram_session(proxy)
        bot = Bot(session=session, **bot_kwargs)
        try:
            me = await bot.get_me()
            via = proxy or "без прокси"
            logger.info("Telegram API: OK (@%s) через %s", me.username, via)
            if proxy and proxy != config.network.proxy_url:
                logger.warning(
                    "Обновите PROXY_URL в .env на: %s", proxy
                )
            return bot
        except TelegramUnauthorizedError:
            await bot.session.close()
            logger.error(
                "BOT_TOKEN недействителен (Unauthorized).\n"
                "Откройте @BotFather → /mybots → ваш бот → API Token "
                "и вставьте полный токен в .env"
            )
            sys.exit(1)
        except Exception as e:
            last_error = e
            await bot.session.close()
            logger.debug("Прокси %s не подошёл: %s", proxy or "direct", e)

    logger.error(
        "Не удалось подключиться к Telegram Bot API.\n"
        "Последняя ошибка: %s\n"
        "Включите VPN (v2rayN/Clash) и укажите локальный прокси, "
        "например PROXY_URL=socks5://127.0.0.1:10808",
        last_error,
    )
    sys.exit(1)


async def on_startup(bot: Bot, scheduler: TaskScheduler):
    """Действия при запуске бота"""
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК VACANCY BOT")
    logger.info("=" * 50)
    
    # Подключаемся к Supabase
    db.connect()

    channel_error = await verify_bot_channel_access(bot)
    if channel_error:
        logger.error("Проверка подписки: %s", channel_error)
        for admin_id in config.admin.ids:
            try:
                await bot.send_message(
                    admin_id,
                    f"⚠️ <b>Настройка канала</b>\n\n{channel_error}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    
    # Запускаем планировщик
    await scheduler.start()

    if scheduler.distributor and moderation_enabled():
        await scheduler.distributor.send_pending_to_moderation()
    
    # Информация о боте
    me = await bot.get_me()
    logger.info(f"🤖 Бот: @{me.username}")
    logger.info(f"📊 Админы: {config.admin.ids}")
    logger.info(f"📢 Обязательный канал: {config.channel.required_channel}")
    if moderation_enabled():
        logger.info(f"📥 Чат модерации: {config.channel.moderation_chat}")
    logger.info("=" * 50)
    
    # Уведомляем админов
    for admin_id in config.admin.ids:
        try:
            await bot.send_message(
                admin_id,
                "✅ Бот запущен и готов к работе!"
            )
        except Exception:
            pass


async def on_shutdown(bot: Bot, scheduler: TaskScheduler):
    """Действия при остановке бота"""
    logger.info("⏹ Остановка бота...")
    
    # Останавливаем планировщик
    await scheduler.stop()
    
    # Уведомляем админов
    for admin_id in config.admin.ids:
        try:
            await bot.send_message(admin_id, "⚠️ Бот остановлен")
        except Exception:
            pass
    
    logger.info("✅ Бот остановлен")


# =========================================
# ГЛАВНАЯ ФУНКЦИЯ
# =========================================

async def main():
    """Главная функция запуска бота"""
    
    # Настраиваем логирование
    setup_logging()
    
    # Проверяем конфигурацию
    if not config.bot.token:
        logger.error("❌ BOT_TOKEN не указан в .env файле!")
        sys.exit(1)
    
    if not config.supabase.url or not config.supabase.key:
        logger.error("❌ SUPABASE_URL или SUPABASE_KEY не указаны!")
        sys.exit(1)

    if not config.network.proxy_url and not config.network.telegram_api_server:
        logger.warning(
            "PROXY_URL не задан — будет выполнен авто-поиск локального VPN-прокси"
        )

    bot = await create_bot()
    
    # Создаем диспетчер
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрируем middleware
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    
    # Регистрируем роутеры
    dp.include_router(admin_router)  # Админ первый для приоритета
    dp.include_router(vacancy_moderation_router)
    dp.include_router(user_vacancy_router)
    dp.include_router(categories_router)
    dp.include_router(subscription_router)
    dp.include_router(user_router)  # Пользователь последний (catch-all)
    
    # Создаем планировщик
    scheduler = TaskScheduler(bot)
    
    try:
        await on_startup(bot, scheduler)
        
        # Запускаем polling
        logger.info("🔄 Запуск polling...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True
        )
        
    except KeyboardInterrupt:
        logger.info("⚠️ Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        await on_shutdown(bot, scheduler)
        await bot.session.close()


# =========================================
# ТОЧКА ВХОДА
# =========================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

