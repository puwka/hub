"""
Скрипт для первичной авторизации Telethon.
Запустите этот скрипт отдельно для авторизации user account.

Использование:
    python auth_telethon.py
"""

import asyncio
from telethon import TelegramClient
from dotenv import load_dotenv
import os

load_dotenv()


async def main():
    """Авторизация Telethon"""
    
    api_id = os.getenv("TELETHON_API_ID")
    api_hash = os.getenv("TELETHON_API_HASH")
    phone = os.getenv("TELETHON_PHONE")
    
    if not api_id or not api_hash:
        print("❌ Ошибка: TELETHON_API_ID и TELETHON_API_HASH не указаны в .env")
        print("\n📝 Как получить:")
        print("1. Перейдите на https://my.telegram.org")
        print("2. Войдите с номером телефона")
        print("3. Создайте приложение (API development tools)")
        print("4. Скопируйте api_id и api_hash")
        return
    
    print("=" * 50)
    print("🔐 АВТОРИЗАЦИЯ TELETHON")
    print("=" * 50)
    print(f"\n📱 Телефон: {phone}")
    print(f"🔑 API ID: {api_id}")
    print("\n⏳ Подключаемся к Telegram...")
    
    client = TelegramClient("vacancy_parser", int(api_id), api_hash)
    
    await client.start(phone=phone)
    
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"\n✅ Авторизация успешна!")
        print(f"👤 Аккаунт: {me.first_name} (@{me.username})")
        print(f"🆔 ID: {me.id}")
        print(f"\n📁 Session файл сохранен: vacancy_parser.session")
        print("\n🚀 Теперь можно запускать бота: python main.py")
    else:
        print("\n❌ Авторизация не удалась")
    
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())





