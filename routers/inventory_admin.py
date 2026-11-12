from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from richfmt import strip_tags
from routers.shop import get_bonus_lock
from services.economy import EconomyService
from services.shop import ShopService

router = Router(name='inventory_admin')
INVENTORY_ADMIN_ID = 990002509
PAGE_SIZE = 8


async def inventory_panel(shop: ShopService, user_id: int, page: int = 0):
    items = await shop.inventory_editor_items(user_id)
    last_page = max(0, (len(items) - 1) // PAGE_SIZE)
    page = min(max(0, page), last_page)
    text = [f'<b>Инвентарь пользователя <code>{user_id}</code></b>',
            f'Страница {page + 1}/{last_page + 1}. Выдача бесплатная.']
    buttons = []
    for index, item in enumerate(items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], page * PAGE_SIZE + 1):
        name = escape(strip_tags(item['name'])[:60])
        text.append(f"{index}. {name} — {item['count']} шт.")
        row = []
        if item['shop_id'] is not None:
            row.append(InlineKeyboardButton(text=f'{index}. Выдать 1',
                callback_data=f"agive:give:{user_id}:{item['shop_id']}:{page}"))
        if item['inventory_id'] is not None and item['count'] > 0:
            for action, label in [('take', 'Убрать 1'), ('clear', 'Убрать всё')]:
                row.append(InlineKeyboardButton(text=f'{index}. {label}',
                    callback_data=f"agive:{action}:{user_id}:{item['inventory_id']}:{page}"))
        buttons.append(row)
    if not items:
        text.append('Магазин и инвентарь пусты.')
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='←', callback_data=f'agive:page:{user_id}:0:{page - 1}'))
    if page < last_page:
        nav.append(InlineKeyboardButton(text='→', callback_data=f'agive:page:{user_id}:0:{page + 1}'))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text='Обновить', callback_data=f'agive:page:{user_id}:0:{page}'),
                    InlineKeyboardButton(text='Закрыть', callback_data=f'agive:close:{user_id}:0:0')])
    return '\n\n'.join(text), InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command('agive'))
async def agive_command(message: Message, economy: EconomyService, shop: ShopService) -> None:
    if not message.from_user or message.from_user.id != INVENTORY_ADMIN_ID:
        await message.answer('Нет доступа.')
        return
    parts = (message.text or '').split()
    if len(parts) != 2 or not parts[1].isascii() or not parts[1].isdigit() or not 0 < int(parts[1]) < 2**63:
        await message.answer('Формат: /agive ID — например, /agive 123456789')
        return
    user_id = int(parts[1])
    if await economy.profile(user_id) is None:
        await message.answer('Пользователь не найден в базе. Он должен сначала нажать /start.')
        return
    text, markup = await inventory_panel(shop, user_id)
    await message.answer(text, reply_markup=markup, parse_mode='HTML')


@router.callback_query(F.data.startswith('agive:'))
async def agive_callback(callback: CallbackQuery, economy: EconomyService, shop: ShopService) -> None:
    if callback.from_user.id != INVENTORY_ADMIN_ID:
        await callback.answer('Нет доступа.', show_alert=True)
        return
    try:
        _, action, user_s, item_s, page_s = (callback.data or '').split(':')
        user_id, item_id, page = int(user_s), int(item_s), int(page_s)
        if action not in ('give', 'take', 'clear', 'page', 'close') or not 0 < user_id < 2**63 or not 0 <= item_id < 2**63 or page < 0:
            raise ValueError
    except ValueError:
        await callback.answer('Некорректная кнопка. Откройте /agive заново.', show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer('Откройте /agive заново.', show_alert=True)
        return
    if action == 'close':
        await callback.answer()
        await callback.message.delete()
        return
    if await economy.profile(user_id) is None:
        await callback.answer('Пользователь не найден.', show_alert=True)
        return
    notice = None
    if action in ('give', 'take', 'clear'):
        # Use the same lock as bonus redemption to prevent overlapping removals.
        if action == 'give':
            code = str(item_id)
        else:
            code = await shop.db.fetch_val('SELECT prize_code FROM user_prizes WHERE user_id = ? AND rowid = ?', (user_id, item_id))
        async with get_bonus_lock(user_id, str(code)):
            changed = await shop.edit_inventory(user_id, action, item_id)
        notice = {'give': 'Выдан 1 предмет.', 'take': 'Убран 1 предмет.', 'clear': 'Все экземпляры предмета убраны.'}[action] if changed else 'Предмет уже отсутствует. Список обновлён.'
    await callback.answer(notice)
    text, markup = await inventory_panel(shop, user_id, page)
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode='HTML')
    except TelegramBadRequest as exc:
        if 'message is not modified' not in str(exc).lower():
            raise
