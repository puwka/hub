"""
Покупка подписки на вакансии через Telegram Stars или вручную.
"""

import logging

from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    LabeledPrice,
    PreCheckoutQuery,
)
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    SUBSCRIPTION_PLANS,
    config,
    get_payment_contact_display,
    get_payment_contact_url,
)
from database import db
from keyboards.main import vacancy_subscription_plans_keyboard
from utils.subscription import format_subscription_status_html

logger = logging.getLogger(__name__)

router = Router()


# =========================================
# ТЕКСТЫ
# =========================================


def _subscription_menu_text(subscription_until) -> str:
    """Красивое сообщение меню подписки."""
    contact_display = get_payment_contact_display()
    contact_url = get_payment_contact_url()
    contact_line = (
        f'<a href="{contact_url}">{contact_display}</a>'
        if contact_url
        else contact_display
    )

    text = (
        "⭐ <b>Подписка на вакансии</b>\n\n"
        "Получайте свежие вакансии <b>первыми</b> — "
        "прямо в личные сообщения, без поиска и мониторинга каналов.\n\n"
        "🔹 <b>Автоматическая рассылка</b> по вашим направлениям\n"
        "🔹 <b>Мгновенные уведомления</b> о новых вакансиях\n"
        "🔹 <b>Фильтрация спама</b> — только качественные предложения\n"
        "🔹 <b>Без ограничений</b> на количество вакансий\n\n"
    )
    text += format_subscription_status_html(subscription_until)
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "💎 <b>Тарифы:</b>\n\n"

    if config.payment.stars_enabled:
        text += (
            "┣ 1 неделя — <b>50 ⭐</b>\n"
            "┣ 1 месяц — <b>175 ⭐</b>\n"
            "┣ 6 месяцев — <b>750 ⭐</b>  💰 <i>выгодно</i>\n"
            "┗ 1 год — <b>1 300 ⭐</b>  🔥 <i>лучшая цена</i>\n\n"
            "💳 <b>Способы оплаты:</b>\n"
            "• <b>Telegram Stars</b> — нажмите на тариф ниже\n"
            f"• <b>Через администратора</b> — напишите {contact_line}\n\n"
            "Выберите тариф ниже 👇"
        )
    else:
        text += (
            "┣ 1 неделя — <b>49 ₽</b>\n"
            "┣ 1 месяц — <b>199 ₽</b>\n"
            "┣ 6 месяцев — <b>899 ₽</b>  💰 <i>выгодно</i>\n"
            "┗ 1 год — <b>1 599 ₽</b>  🔥 <i>лучшая цена</i>\n\n"
            "💳 <b>Как оплатить:</b>\n"
            f"Напишите {contact_line}, укажите выбранный тариф.\n"
            "После подтверждения оплаты подписка будет активирована.\n\n"
            "Выберите тариф ниже 👇"
        )

    return text


def _manual_payment_text(plan: dict) -> str:
    """Инструкция по ручной оплате для конкретного тарифа."""
    contact_display = get_payment_contact_display()
    contact_url = get_payment_contact_url()
    contact_line = (
        f'<a href="{contact_url}">{contact_display}</a>'
        if contact_url
        else contact_display
    )
    return (
        f"🛒 <b>Тариф:</b> {plan['label']} — <b>{plan['price_rub']} ₽</b>\n\n"
        f"Для оплаты напишите {contact_line}\n"
        "Укажите выбранный тариф.\n\n"
        "<blockquote>После подтверждения оплаты подписка будет активирована "
        "в течение нескольких минут.</blockquote>"
    )


def _back_to_plans_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    contact_url = get_payment_contact_url()
    if contact_url:
        builder.row(
            InlineKeyboardButton(text="✉️ Написать для оплаты", url=contact_url)
        )
    builder.row(
        InlineKeyboardButton(text="← К тарифам", callback_data="sub:plans")
    )
    return builder


# =========================================
# МЕНЮ ПОДПИСКИ
# =========================================


@router.message(Command("subscription"))
@router.message(F.text == "Подписка")
async def cmd_subscription(message: Message):
    """Меню подписки"""
    stats = await db.get_referral_stats(message.from_user.id)
    subscription_until = stats.get("subscription_until")

    await message.answer(
        _subscription_menu_text(subscription_until),
        parse_mode="HTML",
        reply_markup=vacancy_subscription_plans_keyboard(),
    )


@router.callback_query(F.data == "sub:plans")
async def subscription_plans_callback(callback: CallbackQuery):
    """Вернуться к списку тарифов"""
    stats = await db.get_referral_stats(callback.from_user.id)
    subscription_until = stats.get("subscription_until")

    await callback.message.edit_text(
        _subscription_menu_text(subscription_until),
        parse_mode="HTML",
        reply_markup=vacancy_subscription_plans_keyboard(),
    )
    await callback.answer()


# =========================================
# ВЫБОР ТАРИФА
# =========================================


@router.callback_query(F.data.startswith("buy_sub:"))
async def buy_subscription_callback(callback: CallbackQuery, bot: Bot):
    """Выбор тарифа — Stars-инвойс или ручная инструкция."""
    plan_id = callback.data.split(":")[1]
    plan = SUBSCRIPTION_PLANS.get(plan_id)

    if not plan:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    if config.payment.stars_enabled:
        # Отправляем Stars-инвойс
        price = plan["price_stars"]
        label = plan["label"]

        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Подписка — {label}",
            description=(
                f"Подписка на рассылку вакансий на {label}.\n"
                "После оплаты вакансии начнут приходить автоматически "
                "по выбранным направлениям."
            ),
            payload=f"sub:{plan_id}",
            currency="XTR",
            prices=[LabeledPrice(label=f"Подписка {label}", amount=price)],
            provider_token="",
        )
    else:
        # Ручная оплата — инструкция
        text = _manual_payment_text(plan)
        keyboard = _back_to_plans_keyboard().as_markup()
        try:
            await callback.message.edit_text(
                text, parse_mode="HTML", reply_markup=keyboard
            )
        except Exception:
            await callback.message.answer(
                text, parse_mode="HTML", reply_markup=keyboard
            )

    await callback.answer()


# =========================================
# ОБРАБОТКА ПЛАТЕЖА (STARS)
# =========================================


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Подтверждение платежа — всегда OK."""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    """Успешная оплата — активация подписки."""
    payment = message.successful_payment
    payload = payment.invoice_payload  # "sub:week", "sub:month", ...

    if not payload.startswith("sub:"):
        logger.warning("Неизвестный payload платежа: %s", payload)
        return

    plan_id = payload.split(":")[1]
    plan = SUBSCRIPTION_PLANS.get(plan_id)

    if not plan:
        logger.error("Тариф %s не найден после оплаты!", plan_id)
        await message.answer(
            "❌ Ошибка: тариф не найден. Обратитесь к администратору."
        )
        return

    tg_id = message.from_user.id
    days = plan["days"]
    label = plan["label"]
    stars = payment.total_amount

    # Активируем подписку
    ok = await db.extend_subscription(tg_id, days=days)

    if ok:
        logger.info(
            "⭐ Оплата Stars: user=%s, plan=%s, stars=%s, days=%s",
            tg_id, plan_id, stars, days,
        )
        await message.answer(
            f"🎉 <b>Подписка активирована!</b>\n\n"
            f"📋 Тариф: <b>{label}</b>\n"
            f"⭐ Оплачено: <b>{stars} Stars</b>\n"
            f"📅 Добавлено: <b>+{days} дней</b>\n\n"
            "Вакансии будут приходить автоматически по вашим направлениям.\n\n"
            "💡 Настройте направления в меню «Мои направления», "
            "если ещё этого не сделали.",
            parse_mode="HTML",
        )
    else:
        logger.error(
            "❌ Не удалось активировать подписку после оплаты: user=%s, plan=%s",
            tg_id, plan_id,
        )
        await message.answer(
            "❌ Оплата прошла, но возникла ошибка при активации подписки.\n"
            "Обратитесь к администратору — оплата будет учтена.",
            parse_mode="HTML",
        )
