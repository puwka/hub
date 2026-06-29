"""
Клавиатуры для Telegram бота.
"""

from typing import List, Optional
from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from config import CATEGORIES, config, SUBSCRIPTION_PLANS


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню бота"""
    builder = ReplyKeyboardBuilder()
    
    builder.row(
        KeyboardButton(text="Мои направления"),
        KeyboardButton(text="Добавить вакансию")
    )
    builder.row(
        KeyboardButton(text="Реферальная система"),
        KeyboardButton(text="Помощь")
    )
    builder.row(KeyboardButton(text="Подписка"))
    
    return builder.as_markup(resize_keyboard=True)


def vacancy_subscription_plans_keyboard() -> InlineKeyboardMarkup:
    """Тарифы подписки на вакансии"""
    builder = InlineKeyboardBuilder()
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        if config.payment.stars_enabled:
            price_text = f"{plan['price_stars']} ⭐"
        else:
            price_text = f"{plan['price_rub']} ₽"
        builder.row(
            InlineKeyboardButton(
                text=f"{plan['label']} — {price_text}",
                callback_data=f"buy_sub:{plan_id}",
            )
        )
    return builder.as_markup()


def subscription_keyboard(channel: str) -> InlineKeyboardMarkup:
    """Клавиатура для проверки подписки на канал"""
    builder = InlineKeyboardBuilder()
    
    # Ссылка на канал
    channel_url = f"https://t.me/{channel.replace('@', '')}"
    builder.row(
        InlineKeyboardButton(
            text="Открыть канал",
            url=channel_url
        )
    )
    
    # Кнопка проверки
    builder.row(
        InlineKeyboardButton(
            text="Проверить",
            callback_data="check_subscription"
        )
    )
    
    return builder.as_markup()


def categories_keyboard(selected: Optional[List[str]] = None) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора категорий.
    Выбранные категории отмечаются ✅
    """
    if selected is None:
        selected = []
    
    builder = InlineKeyboardBuilder()
    
    for cat_id, cat_data in CATEGORIES.items():
        # Отмечаем выбранные категории
        if cat_id in selected:
            text = f"✅ {cat_data['name']}"
        else:
            text = cat_data['name']
        
        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"category:{cat_id}"
            )
        )
    
    # Кнопки управления
    builder.row(
        InlineKeyboardButton(
            text="Сбросить",
            callback_data="category:reset"
        ),
        InlineKeyboardButton(
            text="Сохранить",
            callback_data="category:save"
        )
    )
    
    return builder.as_markup()


def category_select_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора одной категории (для добавления вакансии)"""
    builder = InlineKeyboardBuilder()
    
    for cat_id, cat_data in CATEGORIES.items():
        builder.row(
            InlineKeyboardButton(
                text=cat_data['name'],
                callback_data=f"select_cat:{cat_id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="Отмена",
            callback_data="cancel_vacancy"
        )
    )
    
    return builder.as_markup()


def confirm_keyboard(action: str = "confirm") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="Отправить",
            callback_data=f"{action}:yes"
        ),
        InlineKeyboardButton(
            text="Отмена",
            callback_data=f"{action}:no"
        )
    )
    
    return builder.as_markup()


def back_keyboard(callback_data: str = "back") -> InlineKeyboardMarkup:
    """Кнопка назад"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="Назад",
            callback_data=callback_data
        )
    )
    
    return builder.as_markup()


def admin_keyboard() -> InlineKeyboardMarkup:
    """Админ-панель"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="Модерация вакансий",
            callback_data="admin:moderation"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Модерация отзывов",
            callback_data="admin:reviews_moderation"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Источники",
            callback_data="admin:sources"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Статистика",
            callback_data="admin:stats"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Рассылка",
            callback_data="admin:broadcast"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Запустить парсинг",
            callback_data="admin:parse_now"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Дефолтное фото",
            callback_data="admin:default_photo"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="FAQ фото",
            callback_data="admin:faq_photo"
        ),
        InlineKeyboardButton(
            text="Статистика фото",
            callback_data="admin:stats_photo"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Направления фото",
            callback_data="admin:categories_photo"
        ),
        InlineKeyboardButton(
            text="Приветствие фото",
            callback_data="admin:welcome_photo"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Рефералка фото",
            callback_data="admin:referral_photo"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Выдать подписку",
            callback_data="admin:grant_subscription"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Фильтр вакансий",
            callback_data="admin:filter_stats"
        )
    )
    stars_status = "✅" if config.payment.stars_enabled else "❌"
    builder.row(
        InlineKeyboardButton(
            text=f"Оплата Stars {stars_status}",
            callback_data="admin:toggle_stars"
        )
    )
    
    return builder.as_markup()


def admin_grant_plans_keyboard(tg_id: int) -> InlineKeyboardMarkup:
    """Выбор тарифа для выдачи подписки пользователю"""
    builder = InlineKeyboardBuilder()
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        builder.row(
            InlineKeyboardButton(
                text=f"{plan['label']} ({plan['days']} дн.)",
                callback_data=f"grant_sub:{plan_id}:{tg_id}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="← В панель", callback_data="admin:back")
    )
    return builder.as_markup()


def moderation_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    """Клавиатура модерации вакансии"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="Одобрить",
            callback_data=f"moderate:approve:{vacancy_id}"
        ),
        InlineKeyboardButton(
            text="Отклонить",
            callback_data=f"moderate:reject:{vacancy_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Далее",
            callback_data="moderate:skip"
        )
    )
    
    return builder.as_markup()


def sources_keyboard(sources: list) -> InlineKeyboardMarkup:
    """Клавиатура управления источниками"""
    builder = InlineKeyboardBuilder()
    
    for source in sources[:10]:  # Максимум 10 источников
        title = source.get("title") or source["source_id"]
        builder.row(
            InlineKeyboardButton(
                text=f"{title[:30]}",
                callback_data=f"source:remove:{source['source_id']}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="Добавить",
            callback_data="source:add"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="В панель",
            callback_data="admin:back"
        )
    )
    
    return builder.as_markup()


def vacancy_pagination_keyboard(
    current_page: int, 
    total_pages: int,
    vacancy_id: int
) -> InlineKeyboardMarkup:
    """Клавиатура пагинации вакансий на модерации"""
    builder = InlineKeyboardBuilder()
    
    # Кнопки модерации
    builder.row(
        InlineKeyboardButton(
            text="Одобрить",
            callback_data=f"moderate:approve:{vacancy_id}"
        ),
        InlineKeyboardButton(
            text="Отклонить",
            callback_data=f"moderate:reject:{vacancy_id}"
        )
    )
    
    # Пагинация
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"moderate:page:{current_page - 1}"
            )
        )
    
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"{current_page}/{total_pages}",
            callback_data="noop"
        )
    )
    
    if current_page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"moderate:page:{current_page + 1}"
            )
        )
    
    builder.row(*nav_buttons)
    
    builder.row(
        InlineKeyboardButton(
            text="В панель",
            callback_data="admin:back"
        )
    )
    
    return builder.as_markup()


