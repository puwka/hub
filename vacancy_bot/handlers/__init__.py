"""
Handlers package for aiogram bot.
"""
from .user import router as user_router
from .categories import router as categories_router
from .user_vacancy import router as user_vacancy_router
from .admin import router as admin_router

__all__ = [
    "user_router",
    "categories_router", 
    "user_vacancy_router",
    "admin_router"
]





