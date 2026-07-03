"""
Планировщик фоновых задач.
Использует APScheduler для периодического парсинга и рассылки.
"""

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

from config import config
from parser.telethon_parser import TelegramParser, parser as telegram_parser
from services import VacancyDistributor
from database import db

logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Планировщик фоновых задач.
    
    Задачи:
    - Парсинг источников (каждые N минут)
    - Рассылка новых вакансий
    """
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.parser: Optional[TelegramParser] = None
        self.distributor: Optional[VacancyDistributor] = None
        
    async def start(self):
        """Запуск планировщика"""
        logger.info("🚀 Запуск планировщика задач...")
        
        # Используем глобальный парсер
        self.parser = telegram_parser
        await self.parser.start()
        
        # Инициализируем дистрибьютор с парсером
        self.distributor = VacancyDistributor(self.bot, self.parser)
        
        # Задача: Парсинг источников
        self.scheduler.add_job(
            self._parse_job,
            trigger=IntervalTrigger(minutes=config.parser.interval_minutes),
            id="parse_sources",
            name="Парсинг источников",
            replace_existing=True
        )
        
        # Задача: Рассылка вакансий (каждые 2 минуты)
        self.scheduler.add_job(
            self._distribute_job,
            trigger=IntervalTrigger(minutes=2),
            id="distribute_vacancies",
            name="Рассылка вакансий",
            replace_existing=True
        )
        
        # Запускаем планировщик
        self.scheduler.start()
        
        logger.info(
            f"✅ Планировщик запущен!\n"
            f"   Интервал парсинга: {config.parser.interval_minutes} мин\n"
            f"   Интервал рассылки: 2 мин"
        )
    
    async def stop(self):
        """Остановка планировщика"""
        logger.info("⏹ Остановка планировщика...")
        
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        
        if self.parser:
            await self.parser.stop()
        
        logger.info("✅ Планировщик остановлен")
    
    async def _parse_job(self):
        """Задача парсинга источников"""
        logger.info("⏰ Запуск задачи парсинга...")
        
        try:
            if not self.parser or not self.parser.is_authorized:
                logger.warning("Парсер не авторизован, пропуск задачи")
                return
            
            sources_count, vacancies_count = await self.parser.parse_all_sources()

            if self.distributor:
                await self.distributor.send_pending_to_moderation()
            
            logger.info(
                f"✅ Парсинг завершен: "
                f"{sources_count} источников, {vacancies_count} вакансий"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в задаче парсинга: {e}")
    
    async def _distribute_job(self):
        """Задача рассылки вакансий"""
        logger.debug("⏰ Запуск задачи рассылки...")
        
        try:
            if not self.distributor:
                return
            
            vacancies_count, sends_count = await self.distributor.distribute_all_pending()
            
            if vacancies_count > 0:
                logger.info(
                    f"✅ Рассылка: {vacancies_count} вакансий, "
                    f"{sends_count} отправок"
                )
            
            # Рассылка одобренных пользовательских вакансий
            user_sends = await self.distributor.distribute_user_vacancies()
            if user_sends > 0:
                logger.info(f"✅ User vacancies: {user_sends} отправок")
            
        except Exception as e:
            logger.error(f"❌ Ошибка в задаче рассылки: {e}")
    
    async def run_parse_now(self) -> tuple:
        """Запустить парсинг немедленно (вручную)"""
        if not self.parser or not self.parser.is_authorized:
            logger.warning("Парсер не авторизован")
            return 0, 0
        
        return await self.parser.parse_all_sources()
    
    async def run_distribute_now(self) -> tuple:
        """Запустить рассылку немедленно (вручную)"""
        if not self.distributor:
            return 0, 0
        
        return await self.distributor.distribute_all_pending()

