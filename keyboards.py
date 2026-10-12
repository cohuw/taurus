from __future__ import annotations
from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Профиль'), KeyboardButton(text='Магазин')], [KeyboardButton(text='Мои бонусы'), KeyboardButton(text='Мои задания')]], resize_keyboard=True)

def convert_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Обменять', callback_data='convert', style=ButtonStyle.PRIMARY)]])

def admin_panel_keyboard(is_owner: bool) -> InlineKeyboardMarkup:
    KB = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Управление валютой', callback_data='admin_currency', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Управление миссиями', callback_data='admin_missions', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Управление бонусами', callback_data='admin_bonuses', style=ButtonStyle.PRIMARY)]])
    if is_owner:
        KB.inline_keyboard.append([InlineKeyboardButton(text='Управление лотереями', callback_data='admin_lotteries', style=ButtonStyle.PRIMARY)])
    KB.inline_keyboard.append([InlineKeyboardButton(text='Закрыть', callback_data='admin_close', style=ButtonStyle.DANGER)])
    return KB

def back_keyboard(target: str='admin_back') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Назад', callback_data=target, style=ButtonStyle.PRIMARY)]])