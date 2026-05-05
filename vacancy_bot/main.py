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
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import config
from database import db
from scheduler import TaskScheduler
from handlers import (
    user_router,
    categories_router,
    user_vacancy_router,
    admin_router
)
from middlewares import SubscriptionMiddleware


# =========================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# =========================================

def setup_logging():
    """Настройка логирования"""
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

async def on_startup(bot: Bot, scheduler: TaskScheduler):
    """Действия при запуске бота"""
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК VACANCY BOT")
    logger.info("=" * 50)
    
    # Подключаемся к Supabase
    db.connect()
    
    # Запускаем планировщик
    await scheduler.start()
    
    # Информация о боте
    me = await bot.get_me()
    logger.info(f"🤖 Бот: @{me.username}")
    logger.info(f"📊 Админы: {config.admin.ids}")
    logger.info(f"📢 Обязательный канал: {config.channel.required_channel}")
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
    
    # Создаем бота
    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Создаем диспетчер
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрируем middleware
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    
    # Регистрируем роутеры
    dp.include_router(admin_router)  # Админ первый для приоритета
    dp.include_router(user_vacancy_router)
    dp.include_router(categories_router)
    dp.include_router(user_router)  # Пользователь последний (catch-all)
    
    # Создаем планировщик
    scheduler = TaskScheduler(bot)
    
    try:
        # Запускаем бота
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

