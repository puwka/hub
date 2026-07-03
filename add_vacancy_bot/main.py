"""
Бот для подачи вакансий FreelanceHub.

Пользователи отправляют вакансии → модерация → рассылка через vacancy_bot.
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from handlers import vacancy_router

# ─── Логирование ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не задан в .env!")
        return

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(vacancy_router)

    # Проверяем подключение
    me = await bot.get_me()
    logger.info("=" * 50)
    logger.info(f"🚀 ЗАПУСК ADD VACANCY BOT (@{me.username})")
    logger.info("=" * 50)

    try:
        await dp.start_polling(bot)
    finally:
        logger.info("⏹ Бот остановлен")
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("✅ Бот остановлен (Ctrl+C)")
