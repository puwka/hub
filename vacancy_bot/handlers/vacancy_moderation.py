"""Модерация спарсенных вакансий в отдельном чате."""

import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from config import is_admin, get_moderation_chat_id
from database import db

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data.startswith("vac_mod:approve:"))
async def approve_parsed_vacancy(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    vacancy_id = int(callback.data.split(":")[2])
    vacancy = await db.get_vacancy(vacancy_id)
    if not vacancy:
        await callback.answer("Вакансия не найдена", show_alert=True)
        return

    if vacancy.get("moderation_status") == "approved":
        await callback.answer("Уже принята", show_alert=True)
        return

    await db.set_vacancy_moderation_status(vacancy_id, "approved")
    await callback.answer("✅ Вакансия принята — уйдёт в рассылку")

    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>ПРИНЯТО</b> — отправится подписчикам",
            reply_markup=None,
            parse_mode="HTML",
        )
    except Exception:
        pass

    logger.info("Вакансия %s принята модератором %s", vacancy_id, callback.from_user.id)


@router.callback_query(F.data.startswith("vac_mod:reject:"))
async def reject_parsed_vacancy(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    vacancy_id = int(callback.data.split(":")[2])
    vacancy = await db.get_vacancy(vacancy_id)
    if not vacancy:
        await callback.answer("Вакансия не найдена", show_alert=True)
        return

    if vacancy.get("moderation_status") == "rejected":
        await callback.answer("Уже отклонена", show_alert=True)
        return

    await db.set_vacancy_moderation_status(vacancy_id, "rejected")
    await callback.answer("❌ Вакансия отклонена")

    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>",
            reply_markup=None,
            parse_mode="HTML",
        )
    except Exception:
        pass

    logger.info("Вакансия %s отклонена модератором %s", vacancy_id, callback.from_user.id)
