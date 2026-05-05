"""
Бот для сбора отзывов о FreelanceHub.
Пользователи оставляют отзывы, которые проходят модерацию.
За одобренный отзыв начисляется 3 дня x2 статуса.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import db
from handlers import review_router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска бота"""
    
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
    
    # Регистрируем роутеры
    dp.include_router(review_router)
    
    try:
        # Запускаем бота
        logger.info("🚀 Запуск бота для отзывов...")
        me = await bot.get_me()
        logger.info(f"✅ Бот запущен: @{me.username}")
        
        # Запускаем polling
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
        await db.close()  # Закрываем HTTP клиент
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

