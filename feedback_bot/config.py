"""
Конфигурация бота для отзывов.
Загружает настройки из .env файла.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


@dataclass
class BotConfig:
    """Настройки Telegram бота"""
    token: str = field(default_factory=lambda: os.getenv("FEEDBACK_BOT_TOKEN", ""))


@dataclass
class SupabaseConfig:
    """Настройки Supabase"""
    url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    key: str = field(default_factory=lambda: os.getenv("SUPABASE_KEY", ""))


@dataclass
class Config:
    """Главный конфиг приложения"""
    bot: BotConfig = field(default_factory=BotConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)


# Глобальный инстанс конфига
config = Config()

