"""Проверка подключения к Telegram Bot API."""
import asyncio
import socket
import sys

from aiogram import Bot
from aiogram.exceptions import TelegramUnauthorizedError
from config import config
from utils.proxy import create_aiogram_session, iter_proxy_candidates


async def _try_connect(proxy_url: str | None) -> tuple[bool, str | None]:
    session = create_aiogram_session(proxy_url)
    bot = Bot(token=config.bot.token, session=session)
    try:
        me = await bot.get_me()
        return True, f"@{me.username} (id={me.id})"
    except TelegramUnauthorizedError:
        return False, "unauthorized"
    except Exception as e:
        return False, str(e)
    finally:
        await bot.session.close()


async def main():
    if not config.bot.token or ":" not in config.bot.token:
        print("ОШИБКА: BOT_TOKEN не задан или имеет неверный формат.")
        sys.exit(1)

    print(f"Длина BOT_TOKEN: {len(config.bot.token)} символов")

    candidates = iter_proxy_candidates()
    if not candidates:
        print("Прокси не задан. Пробую прямое подключение...")
        candidates = [None]

    last_error = None
    for proxy in candidates:
        label = proxy or "без прокси"
        print(f"\nПроверка: {label}")
        ok, result = await _try_connect(proxy)
        if ok:
            print(f"OK: бот {result}")
            if proxy and proxy != config.network.proxy_url:
                print(f"\nПодсказка: рабочий прокси — {proxy}")
                print("Обновите PROXY_URL в .env на это значение.")
            return
        if result == "unauthorized":
            print("ОШИБКА: Telegram отклонил BOT_TOKEN (Unauthorized).")
            print("Скопируйте полный токен заново у @BotFather: /mybots -> API Token.")
            sys.exit(1)
        print(f"  не работает: {result}")
        last_error = result

    print("\nНе удалось подключиться ни через один прокси.")
    print("Проверьте, что VPN запущен (v2rayN/Clash).")
    if last_error:
        print(f"Последняя ошибка: {last_error}")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
