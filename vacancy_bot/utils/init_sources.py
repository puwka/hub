"""
Скрипт для добавления начальных источников парсинга.

Использование:
    python -m utils.init_sources
"""

import asyncio
import sys
sys.path.append('..')

from database import db
from config import config


# Список популярных каналов с вакансиями
DEFAULT_SOURCES = [
    # Добавьте сюда каналы, на которые подписан ваш Telethon аккаунт
    # ("@channel_username", "channel", "Название канала"),
    # ("@group_username", "group", "Название группы"),
]


async def init_sources():
    """Добавление начальных источников"""
    
    print("=" * 50)
    print("📡 ДОБАВЛЕНИЕ ИСТОЧНИКОВ ПАРСИНГА")
    print("=" * 50)
    
    # Подключаемся к БД
    db.connect()
    
    if not DEFAULT_SOURCES:
        print("\n⚠️ Список источников пуст!")
        print("\nОткройте файл utils/init_sources.py и добавьте каналы:")
        print('''
DEFAULT_SOURCES = [
    ("@freelance_vacancies", "channel", "Фриланс вакансии"),
    ("@remote_jobs", "channel", "Удалённая работа"),
    # ...
]
''')
        return
    
    added = 0
    for source_id, source_type, title in DEFAULT_SOURCES:
        result = await db.add_source(
            source_type=source_type,
            source_id=source_id,
            title=title
        )
        
        if result:
            print(f"✅ Добавлен: {title} ({source_id})")
            added += 1
        else:
            print(f"⚠️ Уже существует или ошибка: {source_id}")
    
    print(f"\n📊 Добавлено источников: {added}/{len(DEFAULT_SOURCES)}")
    
    # Показываем все источники
    sources = await db.get_active_sources()
    print(f"\n📡 Всего активных источников: {len(sources)}")
    for s in sources:
        print(f"  • {s.get('title') or s['source_id']}")


if __name__ == "__main__":
    asyncio.run(init_sources())





