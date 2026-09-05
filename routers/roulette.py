from __future__ import annotations
from html import escape
from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import Settings
from richfmt import EM_T, heading, para, send_rich, table
from routers.shop import notify_admins
from services.economy import EconomyError, EconomyService
from services.roulette import ROULETTE_PRIZES, ROULETTE_SPIN_COST, RouletteResult, RouletteService
router = Router(name='roulette')

def roulette_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f'Крутить рулетку - {ROULETTE_SPIN_COST} T', callback_data='roulette:spin', style=ButtonStyle.PRIMARY)]])

@router.message(Command('spin'))
@router.message(F.text.casefold() == 'рулетка')
async def roulette_menu(message: Message, economy: EconomyService) -> None:
    assert message.from_user is not None
    await economy.ensure_user(message.from_user)
    prize_rows = [[p.name, f'{p.chance_percent}%'] for p in ROULETTE_PRIZES]
    await send_rich(message, [heading('Рулетка Taurus Mafia'), para(f'Стоимость крутки: {ROULETTE_SPIN_COST} {EM_T} T'), table(['Приз', 'Шанс'], prize_rows)], reply_markup=roulette_keyboard())

@router.callback_query(F.data == 'roulette:spin')
async def spin_roulette(callback: CallbackQuery, economy: EconomyService, roulette: RouletteService, settings: Settings) -> None:
    assert callback.from_user is not None
    await economy.ensure_user(callback.from_user)
    try:
        result = await roulette.spin(callback.from_user.id, economy)
    except EconomyError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await send_rich(callback.message, [para(format_spin_result(result))])
    await notify_admins(callback, settings, format_admin_spin_result(format_user_mention(callback.from_user.id, callback.from_user.full_name), result), log_chat_id=settings.roulette_log_chat_id, log_thread_id=settings.roulette_log_thread_id)

def format_spin_result(result: RouletteResult) -> str:
    prize_name = RouletteService.prize_display_name(result.prize, result.spin_number)
    if result.prize.kind == 'taurons':
        prize_name += f' {EM_T}'
    return f'<b>Прокрут #{result.spin_number}</b>\nВы выиграли: <b>{prize_name}</b>\n<i>{result.prize.description}</i>'

def format_user_mention(user_id: int, full_name: str) -> str:
    name = escape(full_name or str(user_id))
    return f'<a href="tg://user?id={user_id}">{name}</a>'

def format_admin_spin_result(user_mention: str, result: RouletteResult) -> str:
    prize_name = RouletteService.prize_display_name(result.prize, result.spin_number)
    return f'<b>Рулетка</b>\nПользователь: {user_mention}\nПрокрут: <code>{result.spin_number}</code>\nПриз: <b>{prize_name}</b>'