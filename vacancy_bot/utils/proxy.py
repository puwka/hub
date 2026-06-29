"""
Настройка прокси для Telegram API (нужно для работы в РФ).
"""

from __future__ import annotations

import logging
import socket
from typing import Any, Iterable, Optional, Tuple
from urllib.parse import urlparse

from config import config

logger = logging.getLogger(__name__)

# Локальные порты VPN-клиентов (v2rayN, Clash и т.д.)
_LOCAL_VPN_PORTS = (
    (10808, "socks5"),
    (10809, "http"),
    (7890, "socks5"),
    (7891, "http"),
    (1080, "socks5"),
)


def _mask_proxy_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.username:
        return f"{parsed.scheme}://***:***@{parsed.hostname}:{parsed.port or ''}"
    return url


def _is_local_proxy(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _local_vpn_proxies() -> list[str]:
    found: list[str] = []
    for port, scheme in _LOCAL_VPN_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                found.append(f"{scheme}://127.0.0.1:{port}")
        except OSError:
            continue
    return found


def iter_proxy_candidates() -> list[str | None]:
    """Список прокси для перебора: из .env, затем авто-поиск локального VPN."""
    seen: set[str] = set()
    candidates: list[str | None] = []

    if config.network.proxy_url:
        candidates.append(config.network.proxy_url)
        seen.add(config.network.proxy_url)

    for proxy in _local_vpn_proxies():
        if proxy not in seen:
            candidates.append(proxy)
            seen.add(proxy)

    return candidates


def get_telethon_proxy() -> Optional[Tuple[Any, ...]]:
    """Прокси для Telethon из PROXY_URL."""
    proxy_url = config.network.proxy_url
    if not proxy_url:
        local = _local_vpn_proxies()
        proxy_url = local[0] if local else None
    if not proxy_url:
        return None

    return _parse_proxy_tuple(proxy_url)


def _parse_proxy_tuple(proxy_url: str) -> Optional[Tuple[Any, ...]]:
    try:
        from python_socks import ProxyType

        parsed = urlparse(proxy_url)
        scheme = parsed.scheme.lower()
        type_map = {
            "socks5": ProxyType.SOCKS5,
            "socks4": ProxyType.SOCKS4,
            "http": ProxyType.HTTP,
            "https": ProxyType.HTTP,
        }
        proxy_type = type_map.get(scheme)
        if not proxy_type:
            logger.error("Неподдерживаемый тип прокси: %s", scheme)
            return None

        return (
            proxy_type,
            parsed.hostname,
            parsed.port or 1080,
            True,
            parsed.username,
            parsed.password,
        )
    except Exception as e:
        logger.error("Ошибка разбора PROXY_URL: %s", e)
        return None


def create_aiogram_session(proxy_url: str | None = None):
    """HTTP-сессия aiogram с прокси."""
    from aiogram.client.session.aiohttp import AiohttpSession

    url = proxy_url if proxy_url is not None else config.network.proxy_url
    if not url:
        return AiohttpSession()

    logger.info("Bot API через прокси: %s", _mask_proxy_url(url))
    return AiohttpSession(proxy=url)


def warn_if_remote_proxy_misconfigured() -> None:
    """Предупреждение, если указан удалённый прокси, а VPN слушает локально."""
    proxy_url = config.network.proxy_url
    if not proxy_url or _is_local_proxy(proxy_url):
        return

    local = _local_vpn_proxies()
    if local:
        logger.warning(
            "PROXY_URL указывает на удалённый сервер (%s), "
            "но VPN уже слушает локально: %s. "
            "Используйте локальный адрес в .env.",
            _mask_proxy_url(proxy_url),
            ", ".join(local),
        )


def get_telegram_api_server():
    """Локальный Bot API сервер (опционально)."""
    server_url = config.network.telegram_api_server
    if not server_url:
        return None

    from aiogram.client.telegram import TelegramAPIServer

    logger.info("Bot API сервер: %s", server_url)
    return TelegramAPIServer.from_base(server_url)
