from __future__ import annotations
import asyncio
import re
from html import escape
from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, StateFilter
from aiogram.enums import ButtonStyle, ContentType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, FSInputFile
from config import Settings
from keyboards import admin_panel_keyboard, back_keyboard
from services.economy import EconomyError, EconomyService
from services.roulette import RouletteService
from richfmt import EM_T, EM_TC, heading, para, table, send_rich, send_rich_to, log_to_coder
import datetime
router = Router(name='admin')

class AdminState(StatesGroup):
    waiting_rate = State()
    waiting_tg_price = State()
    waiting_broadcast = State()

class GivePrizesState(StatesGroup):
    waiting_scope = State()

async def is_admin_user(user_id: int, economy: EconomyService, settings: Settings) -> bool:
    return await economy.is_admin(user_id, settings)

async def parse_target_and_amount(message: Message, economy: EconomyService) -> tuple[int, int]:
    parts = (message.text or '').split()
    if message.reply_to_message and message.reply_to_message.from_user:
        if len(parts) != 2 or not parts[1].lstrip('-').isdigit():
            raise EconomyError('Формат реплаем: /tm сумма или /tc сумма')
        return (message.reply_to_message.from_user.id, int(parts[1]))
    if len(parts) != 3 or not parts[2].lstrip('-').isdigit():
        raise EconomyError('Формат: /tm @user/ID сумма или /tc @user/ID сумма')
    row = await economy.find_user(parts[1])
    if row is None:
        raise EconomyError('Пользователь не найден в базе.')
    return (int(row['telegram_id']), int(parts[2]))

async def grant_currency(message: Message, economy: EconomyService, settings: Settings, currency: str) -> None:
    assert message.from_user is not None
    if not await is_admin_user(message.from_user.id, economy, settings):
        await send_rich(message, [para('<b>У тебя нет доступа к этой команде.</b>')])
        return
    try:
        target_id, amount = await parse_target_and_amount(message, economy)
        if currency == 'T':
            await economy.add_taurons(target_id, amount, f'admin:{message.from_user.id}')
        elif currency == 'TC':
            await economy.add_taurcoins(target_id, amount, f'admin:{message.from_user.id}')
        else:
            await economy.add_taurgems(target_id, amount, f'admin:{message.from_user.id}')
    except EconomyError as exc:
        await send_rich(message, [para(f'<b>Ошибка:</b> {exc}')])
        return
    curr_str = f'{EM_T} T' if currency == 'T' else (f'{EM_TC} TC' if currency == 'TC' else 'TG')
    await send_rich(message, [para(f'<b>Успешно выдано {amount} {curr_str}</b> пользователю <code>{target_id}</code>.')])
    await log_to_coder(message.bot, settings, f"Админ {message.from_user.id} выдал {amount} {currency} пользователю <code>{target_id}</code>")

@router.message(Command('tm'))
async def give_taurons_admin(message: Message, economy: EconomyService, settings: Settings) -> None:
    await grant_currency(message, economy, settings, 'T')

@router.message(Command('tc'))
async def give_taurcoins_admin(message: Message, economy: EconomyService, settings: Settings) -> None:
    await grant_currency(message, economy, settings, 'TC')

@router.message(Command('tg'))
async def give_taurgems_admin(message: Message, economy: EconomyService, settings: Settings) -> None:
    await grant_currency(message, economy, settings, 'TG')

async def take_currency(message: Message, economy: EconomyService, settings: Settings, currency: str) -> None:
    assert message.from_user is not None
    if not await is_admin_user(message.from_user.id, economy, settings):
        await send_rich(message, [para('<b>У тебя нет доступа к этой команде.</b>')])
        return
    try:
        target_id, amount = await parse_target_and_amount(message, economy)
        amount = abs(amount)
        if currency == 'T':
            await economy.add_taurons(target_id, -amount, f'admin_take:{message.from_user.id}')
        elif currency == 'TC':
            await economy.add_taurcoins(target_id, -amount, f'admin_take:{message.from_user.id}')
        else:
            await economy.add_taurgems(target_id, -amount, f'admin_take:{message.from_user.id}')
    except EconomyError as exc:
        await send_rich(message, [para(f'<b>Ошибка:</b> {exc}')])
        return
    curr_str = f'{EM_T} T' if currency == 'T' else (f'{EM_TC} TC' if currency == 'TC' else 'TG')
    await send_rich(message, [para(f'<b>Успешно забрано {amount} {curr_str}</b> у пользователя <code>{target_id}</code>.')])
    await log_to_coder(message.bot, settings, f"Админ {message.from_user.id} забрал {amount} {currency} у <code>{target_id}</code>")

@router.message(Command('tm_take'))
async def take_taurons_admin(message: Message, economy: EconomyService, settings: Settings) -> None:
    await take_currency(message, economy, settings, 'T')

@router.message(Command('tc_take'))
async def take_taurcoins_admin(message: Message, economy: EconomyService, settings: Settings) -> None:
    await take_currency(message, economy, settings, 'TC')

@router.message(Command('tg_take'))
async def take_taurgems_admin(message: Message, economy: EconomyService, settings: Settings) -> None:
    await take_currency(message, economy, settings, 'TG')

@router.message(Command('admin'))
async def manage_admin(message: Message, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    if message.from_user.id != settings.owner_id:
        await send_rich(message, [para('<b>Только владелец может менять админку.</b>')])
        return
    parts = (message.text or '').split()
    target_id: int | None = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif len(parts) == 2:
        found = await economy.find_user(parts[1])
        if found is None:
            await send_rich(message, [para('Пользователь не найден в базе.')])
            return
        target_id = int(found['telegram_id'])
    if target_id is None:
        await send_rich(message, [para('Формат: /admin @user/ID или реплаем')])
        return
    target_profile = await economy.profile(target_id)
    if target_profile is None:
        await send_rich(message, [para('Пользователь не найден в базе.')])
        return
    new_value = not bool(target_profile['is_admin'])
    await economy.set_admin(target_id, new_value)
    await send_rich(message, [para(f"Админка для <code>{target_id}</code>: {('выдана' if new_value else 'снята')}.")])

async def parse_transfer_target_and_amount(message: Message, economy: EconomyService) -> tuple[int, int]:
    parts = (message.text or '').split()
    if message.reply_to_message and message.reply_to_message.from_user:
        if len(parts) != 2 or not parts[1].isdigit():
            raise EconomyError('Формат реплаем: /муу сумма или /буи сумма')
        return (message.reply_to_message.from_user.id, int(parts[1]))
    if len(parts) != 3 or not parts[2].isdigit():
        raise EconomyError('Формат: /муу @user/ID сумма или /буи @user/ID сумма')
    row = await economy.find_user(parts[1])
    if row is None:
        raise EconomyError('Получатель не найден')
    return (int(row['telegram_id']), int(parts[2]))

async def transfer_currency(message: Message, economy: EconomyService, currency: str) -> None:
    assert message.from_user is not None
    try:
        receiver_id, amount = await parse_transfer_target_and_amount(message, economy)
        await economy.transfer(message.from_user.id, receiver_id, currency, amount)
    except EconomyError as exc:
        await send_rich(message, [para(f'<b>Ошибка:</b> {exc}')])
        return
    curr_str = f'{EM_T} T' if currency == 'T' else f'{EM_TC} TC'
    await send_rich(message, [para(f'<b>Успешная передача:</b> {amount} {curr_str} → <code>{receiver_id}</code>')])

@router.message(Command('муу'))
async def transfer_taurons(message: Message, economy: EconomyService) -> None:
    await transfer_currency(message, economy, 'T')

@router.message(Command('буи'))
async def transfer_taurcoins(message: Message, economy: EconomyService) -> None:
    await transfer_currency(message, economy, 'TC')

@router.message(F.text.regexp('^[-–—]прокрут(?:\\s|$)'))
async def reset_roulette_spins(message: Message, roulette: RouletteService, settings: Settings) -> None:
    assert message.from_user is not None
    if message.from_user.id != settings.owner_id:
        await send_rich(message, [para('<b>Только владелец может обнулять прокрутки рулетки.</b>')])
        return
    if (message.text or '').split()[1:] or message.reply_to_message:
        await send_rich(message, [para('<b>Формат:</b> <code>-прокрут</code>')])
        return
    deleted = await roulette.reset_all_spins()
    await send_rich(message, [para(f'<b>Общие прокрутки рулетки обнулены.</b>\nУдалено записей: <code>{deleted}</code>')])

@router.message(Command('apanel'))
async def admin_panel(message: Message, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    if not await is_admin_user(message.from_user.id, economy, settings):
        await send_rich(message, [para('<b>У вас нет доступа к админ панели.</b>')])
        return
    is_owner = message.from_user.id == settings.owner_id
    rate = await economy.get_rate()
    await send_rich(message, [heading('Админ Панель'), para(f'ID: <code>{message.from_user.id}</code>\nКурс обмена: 1 {EM_T} T = {rate} {EM_TC} TC\n\nВыберите действие:')], reply_markup=admin_panel_keyboard(is_owner))

@router.callback_query(F.data == 'admin_close')
async def admin_close(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.delete()

@router.callback_query(F.data == 'admin_back')
async def admin_back(callback: CallbackQuery, economy: EconomyService, settings: Settings) -> None:
    if not await is_admin_user(callback.from_user.id, economy, settings):
        return
    buttons = [[InlineKeyboardButton(text='Управление валютой', callback_data='admin_currency', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Управление миссиями', callback_data='admin_missions', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Управление бонусами', callback_data='admin_bonuses', style=ButtonStyle.PRIMARY)]]
    if callback.from_user.id == settings.owner_id:
        buttons.append([InlineKeyboardButton(text='Управление лотереями', callback_data='admin_lotteries', style=ButtonStyle.PRIMARY)])
    buttons.append([InlineKeyboardButton(text='Закрыть', callback_data='admin_close', style=ButtonStyle.DANGER)])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await callback.message.edit_text('<b>Панель администратора</b>\n\nВыберите раздел для управления:', reply_markup=markup)
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data == 'admin_currency')
async def admin_currency_menu(callback: CallbackQuery, economy: EconomyService, settings: Settings) -> None:
    if not await is_admin_user(callback.from_user.id, economy, settings):
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Пополнить баланс юзеру', callback_data='admin_grant', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Список пользователей', callback_data='admin_users:0', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Установить курс T к TG', callback_data='admin_set_rate', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Изменить курс TG (RUB)', callback_data='admin_set_tg_price', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Назад', callback_data='admin_back', style=ButtonStyle.PRIMARY)]])
    try:
        await callback.message.edit_text('<b>Управление Валютой</b>\n\nВыберите действие:', reply_markup=markup)
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data == 'admin_set_rate')
async def admin_set_rate(callback: CallbackQuery, economy: EconomyService, settings: Settings, state: FSMContext) -> None:
    if not await is_admin_user(callback.from_user.id, economy, settings):
        return
    await callback.answer()
    await state.set_state(AdminState.waiting_rate)
    if callback.message:
        await callback.message.delete()
        await send_rich(callback.message, [heading('Изменение курса'), para(f'Введите новый курс: сколько {EM_TC} TC нужно за 1 {EM_T} T. Например: <code>10</code>')])

@router.callback_query(F.data == 'admin_set_tg_price')
async def admin_set_tg_price(callback: CallbackQuery, economy: EconomyService, settings: Settings, state: FSMContext) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer('Нет доступа.', show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminState.waiting_tg_price)
    if callback.message:
        await callback.message.delete()
        current_price = await economy.get_tg_price_rub()
        await send_rich(callback.message, [heading('Изменение курса TG (RUB)'), para(f'Текущий курс: {current_price} RUB за 1 TG.\nВведите новый курс (целое число):')])
    
@router.callback_query(F.data == 'admin_lotteries')
async def admin_lotteries_menu(callback: CallbackQuery, settings: Settings) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer('Только для владельца', show_alert=True)
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Создать лотерею', callback_data='admin_create_lottery', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Назад', callback_data='admin_back', style=ButtonStyle.PRIMARY)]])
    try:
        await callback.message.edit_text('<b>Управление Лотереями</b>', reply_markup=markup)
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data == 'admin_create_lottery')
async def admin_create_lottery_cb(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if callback.from_user.id != settings.owner_id:
        return
    from routers.lottery import CreateLotteryState
    await state.set_state(CreateLotteryState.waiting_for_nft_link)
    if callback.message:
        await callback.message.delete()
        await send_rich(callback.message, [para('Введите ссылку на NFT, которая будет разыграна:')])
    await callback.answer()

@router.message(AdminState.waiting_rate, ~F.text.startswith('/'))
async def process_rate(message: Message, state: FSMContext, economy: EconomyService, settings: Settings) -> None:
    if message.text and message.text.isdigit():
        new_rate = int(message.text)
        await economy.set_rate(new_rate)
        await send_rich(message, [heading('Успех'), para(f'Курс обмена установлен: 1 {EM_T} T = {new_rate} {EM_TC} TC')])
        await log_to_coder(message.bot, settings, f"Админ {message.from_user.id} установил курс обмена: 1 T = {new_rate} TC")
    else:
        await send_rich(message, [para('Ошибка: Введите число.')])
    await state.clear()

@router.message(AdminState.waiting_tg_price, ~F.text.startswith('/'))
async def admin_save_tg_price(message: Message, economy: EconomyService, state: FSMContext, settings: Settings) -> None:
    if message.text and message.text.isdigit():
        new_price = int(message.text)
        await economy.set_tg_price_rub(new_price)
        await send_rich(message, [para(f'Курс TG успешно изменен на {new_price} RUB.')])
        await log_to_coder(message.bot, settings, f"Админ {message.from_user.id} изменил курс TG на {new_price} RUB.")
    else:
        await send_rich(message, [para('Ошибка: Введите число.')])
    await state.clear()

@router.callback_query(F.data.startswith('admin_users:'))
async def users_page_callback(callback: CallbackQuery, economy: EconomyService) -> None:
    page = int((callback.data or 'admin_users:0').split(':')[1])
    await callback.answer()
    if callback.message:
        await send_users_page(callback.message, economy, page)

@router.message(Command('users'))
async def users_command(message: Message, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    if not await is_admin_user(message.from_user.id, economy, settings):
        await send_rich(message, [para('Нет доступа.')])
        return
    await send_users_page(message, economy, 0)

async def send_users_page(message: Message | None, economy: EconomyService, page: int) -> None:
    if message is None:
        return
    per_page = 20
    start = page * per_page
    end = start + per_page
    users = await economy.all_users(page=page, per_page=per_page)
    total_users = await economy.user_count()
    if not users:
        blocks = [para('Пользователей нет.')]
    else:
        blocks = [heading(f'Пользователи — страница {page}, всего {total_users}')]
        rows = [['ID', 'Имя (Юзернейм)', 'Баланс']]
        for u in users:
            username = f"@{u['username']}" if u['username'] else 'без username'
            rows.append([str(u['telegram_id']), f"{escape(u['full_name'] or '')} ({username})", f"{u['taurons']} {EM_T} T / {u['taurcoins']} {EM_TC} TC"])
        blocks.append(table(rows[0], rows[1:]))
    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='Назад', callback_data=f'admin_users:{page - 1}', style=ButtonStyle.PRIMARY))
    if end < total_users:
        nav.append(InlineKeyboardButton(text='Вперед', callback_data=f'admin_users:{page + 1}', style=ButtonStyle.PRIMARY))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text='В меню валют', callback_data='admin_currency', style=ButtonStyle.PRIMARY)])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_rich(message, blocks, reply_markup=markup)

@router.message(Command('user'))
async def user_info(message: Message, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    if not await is_admin_user(message.from_user.id, economy, settings):
        await send_rich(message, [para('Нет доступа.')])
        return
    parts = (message.text or '').split()
    row = None
    if message.reply_to_message and message.reply_to_message.from_user:
        row = await economy.profile(message.reply_to_message.from_user.id)
    elif len(parts) == 2:
        row = await economy.find_user(parts[1])
    else:
        await send_rich(message, [para('Формат: /user @user/ID или реплаем')])
        return
    if row is None:
        await send_rich(message, [para('Пользователь не найден.')])
        return
    name = escape(row['full_name'] or '')
    username = f"@{row['username']}" if row['username'] else 'нет'
    await send_rich(message, [heading('Пользователь'), para(f"ID: <code>{row['telegram_id']}</code>\nИмя: {name}\nUsername: {username}\nБаланс: {row['taurons']} {EM_T} T / {row['taurcoins']} {EM_TC} TC\nАдмин: {('да' if row['is_admin'] else 'нет')}")])

@router.message(Command('rass'))
async def rass_start(message: Message, state: FSMContext, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    if not await is_admin_user(message.from_user.id, economy, settings):
        await send_rich(message, [para('Нет доступа.')])
        return
    await state.set_state(AdminState.waiting_broadcast)
    await send_rich(message, [heading('Рассылка'), para('Отправь текст рассылки. Для отмены: /cancel')])

@router.message(AdminState.waiting_broadcast, ~F.text.startswith('/'))
async def rass_send(message: Message, state: FSMContext, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    text = message.html_text or message.text or ''
    if len(text.strip()) < 3:
        await send_rich(message, [para('Текст слишком короткий.')])
        return
    users = await economy.all_users()
    total = len(users)
    delivered = failed = 0
    progress_msg = await send_rich(message, [heading('Рассылка...'), para(f'0/{total}')])
    for i, row in enumerate(users, 1):
        try:
            await send_rich_to(message.bot, row['telegram_id'], [para(text)])
            delivered += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await send_rich_to(message.bot, row['telegram_id'], [para(text)])
                delivered += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        if i % 25 == 0:
            try:
                await progress_msg.delete()
            except Exception:
                pass
            progress_msg = await send_rich(message, [heading('Рассылка...'), para(f'{i}/{total}')])
        await asyncio.sleep(0.05)
    await economy.db.execute('INSERT INTO broadcast_log (admin_id, text, delivered, failed) VALUES (?, ?, ?, ?)', (message.from_user.id, text, delivered, failed))
    await state.clear()
    try:
        await progress_msg.delete()
    except Exception:
        pass
    await send_rich(message, [heading('Рассылка завершена'), para(f'Доставлено: {delivered}, ошибок: {failed}.')])

@router.message(Command('cancel'), StateFilter('*'))
async def cancel_state(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current:
        await send_rich(message, [para('Действие отменено.')])


async def _extract_user_ids(text: str, economy: EconomyService) -> list[int]:
    plain_ids = set(re.findall('(?<!\\d)(\\d{5,15})(?!\\d)', text))
    mention_ids = set(re.findall('tg://user\\?id=(\\d+)', text))
    usernames = set(re.findall('@([a-zA-Z0-9_]+)', text))
    final_ids = {int(x) for x in plain_ids | mention_ids}
    for uname in usernames:
        user = await economy.find_user('@' + uname)
        if user:
            final_ids.add(int(user['telegram_id']))
    return list(final_ids)

@router.message(F.text.regexp('(?i)^выдать\\s+тс?\\s+\\-?\\d+'))
async def give_prizes_start(message: Message, economy: EconomyService, settings: Settings, state: FSMContext) -> None:
    assert message.from_user is not None
    if not await is_admin_user(message.from_user.id, economy, settings):
        await send_rich(message, [para('Нет доступа.')])
        return
    if not message.reply_to_message:
        await send_rich(message, [para('Команду нужно отправить реплаем на сообщение с завершённой игрой.')])
        return
    m = re.match('(?i)^выдать\\s+(тс|т)\\s+(\\-?\\d+)', message.text or '')
    if not m:
        return
    currency = 'TC' if m.group(1).lower() == 'тс' else 'T'
    amount = int(m.group(2))
    source = message.reply_to_message.html_text or message.reply_to_message.text or message.reply_to_message.caption or ''
    await state.set_state(GivePrizesState.waiting_scope)
    await state.update_data(currency=currency, amount=amount, source=source)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='Победителям', callback_data='give_scope:победителям', style=ButtonStyle.PRIMARY),
            InlineKeyboardButton(text='Участникам', callback_data='give_scope:участникам', style=ButtonStyle.PRIMARY),
        ],
        [
            InlineKeyboardButton(text='Списку', callback_data='give_scope:списку', style=ButtonStyle.PRIMARY),
            InlineKeyboardButton(text='Отмена', callback_data='give_scope:cancel', style=ButtonStyle.DANGER),
        ],
    ])
    curr_str = f'TC' if currency == 'TC' else 'T'
    await send_rich(message, [para(f'Выдать <b>{amount} {curr_str}</b>. Кому?')], reply_markup=markup)

@router.callback_query(F.data.startswith('give_scope:'), GivePrizesState.waiting_scope)
async def give_prizes_scope(callback: CallbackQuery, economy: EconomyService, state: FSMContext) -> None:
    scope = (callback.data or '').split(':', 1)[1]
    if scope == 'cancel':
        await state.clear()
        await callback.answer('Отменено.')
        if callback.message:
            await callback.message.delete()
        return
    data = await state.get_data()
    await state.clear()
    currency = data.get('currency', 'TC')
    amount = data.get('amount', 0)
    source = data.get('source', '')
    if scope == 'победителям':
        win_part = re.split('(?i)победител[ьи]:?', source, maxsplit=1)
        if len(win_part) > 1:
            win_text = win_part[1]
            other_part = re.split('(?i)другие игроки:?', win_text, maxsplit=1)
            source = other_part[0]
    ids = await _extract_user_ids(source, economy)
    if not ids:
        await callback.answer('Не нашёл ID пользователей в сообщении игры.', show_alert=True)
        if callback.message:
            await callback.message.delete()
        return
    ok = fail = 0
    for uid in ids:
        try:
            if currency == 'T':
                await economy.add_taurons(uid, amount, f'game_reward:{scope}')
            else:
                await economy.add_taurcoins(uid, amount, f'game_reward:{scope}')
            ok += 1
        except EconomyError:
            fail += 1
    curr_str = 'T' if currency == 'T' else 'TC'
    await callback.answer(f'Готово! Успешно: {ok}, ошибок: {fail}.')
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(f'Начислено <b>{amount} {curr_str}</b> [{scope}]: успешно {ok}, ошибок {fail}.')
        
    try:
        settings = Settings()
        await log_to_coder(callback.bot, settings, f"Админ {callback.from_user.id} выдал {amount} {currency} [{scope}].\nУспешно: {ok}, Ошибок: {fail}.")
    except Exception:
        pass



@router.message(Command('gpm'))
async def extract_premium_emojis(message: Message, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    if not await is_admin_user(message.from_user.id, economy, settings):
        await send_rich(message, [para('Нет доступа.')])
        return
    target_msg = message.reply_to_message
    if not target_msg:
        await send_rich(message, [para('Пожалуйста, отправьте эту команду реплаем на сообщение с премиум-эмодзи.')])
        return
    entities = target_msg.entities or target_msg.caption_entities or []
    text = target_msg.text or target_msg.caption or ''
    custom_emojis = []
    seen_ids = set()
    for ent in entities:
        if ent.type == 'custom_emoji' and ent.custom_emoji_id:
            if ent.custom_emoji_id in seen_ids:
                continue
            seen_ids.add(ent.custom_emoji_id)
            fallback = escape(ent.extract_from(text))
            custom_id = ent.custom_emoji_id
            premium_html = f'<tg-emoji emoji-id="{custom_id}">{fallback}</tg-emoji>'
            custom_emojis.append(f'{fallback} > {premium_html} | <code>{custom_id}</code>')
    if not custom_emojis:
        await send_rich(message, [para('В этом сообщении не найдено премиум-эмодзи.')])
        return
    await send_rich(message, [heading('Найденные эмодзи'), para('\n'.join(custom_emojis))])

async def parse_ban_args(message: Message, economy: EconomyService) -> tuple[int | None, datetime.datetime | None, str]:
    text = (message.text or '').split(maxsplit=1)[1] if len((message.text or '').split()) > 1 else ''
    duration_match = re.match(r'^(\d+)\s+(мин|час|день|дней|дня|мес|год|лет)\s*(.*)', text, re.IGNORECASE)
    unban_at = None
    rest_text = text
    if duration_match:
        val = int(duration_match.group(1))
        unit = duration_match.group(2).lower()
        rest_text = duration_match.group(3)
        td = None
        if unit.startswith('мин'): td = datetime.timedelta(minutes=val)
        elif unit.startswith('час'): td = datetime.timedelta(hours=val)
        elif unit.startswith('д'): td = datetime.timedelta(days=val)
        elif unit.startswith('мес'): td = datetime.timedelta(days=val*30)
        elif unit.startswith('год') or unit.startswith('лет'): td = datetime.timedelta(days=val*365)
        if td:
            unban_at = datetime.datetime.now() + td
            
    target_id = None
    reason = rest_text
    
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        target_match = re.search(r'(@[a-zA-Z0-9_]+|\d{5,15})', rest_text)
        if target_match:
            candidate = target_match.group(1)
            if candidate.startswith('@'):
                user = await economy.find_user(candidate)
                if user:
                    target_id = int(user['telegram_id'])
            else:
                target_id = int(candidate)
            reason = rest_text.replace(candidate, '', 1).strip()
            
    return target_id, unban_at, reason

@router.message(Command('aban'))
async def ban_user(message: Message, economy: EconomyService, settings: Settings, access: AccessMiddleware) -> None:
    assert message.from_user is not None
    if message.from_user.id != settings.owner_id:
        await send_rich(message, [para('Нет доступа.')])
        return

    target_id, unban_at, reason = await parse_ban_args(message, economy)
    if not target_id:
        await send_rich(message, [para('<b>Ошибка:</b> Не удалось определить пользователя для блокировки.\nФормат: /aban (число) мин/час/день @user [причина]')])
        return
        
    if target_id == settings.owner_id:
        await send_rich(message, [para('Нельзя забанить создателя.')])
        return
        
    unban_str = unban_at.isoformat() if unban_at else None
    
    await economy.db.execute(
        "INSERT OR REPLACE INTO banned_users (user_id, silent_mode, unban_at, reason) VALUES (?, 0, ?, ?)",
        (target_id, unban_str, reason)
    )
    access.invalidate(target_id)
    
    time_str = f"до {unban_at.strftime('%d.%m.%Y %H:%M')}" if unban_at else "навсегда"
    reason_str = f" (Причина: {reason})" if reason else ""
    
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Режим: Отчетность', callback_data=f'toggle_ban:{target_id}')]])
    await send_rich(message, [para(f'Пользователь <code>{target_id}</code> заблокирован {time_str}{reason_str}.')], reply_markup=markup)
    await log_to_coder(message.bot, settings, f"Админ {message.from_user.id} забанил <code>{target_id}</code> {time_str}{reason_str}.")

@router.message(Command('aunban'))
async def unban_user(message: Message, economy: EconomyService, settings: Settings, access: AccessMiddleware) -> None:
    assert message.from_user is not None
    if message.from_user.id != settings.owner_id:
        await send_rich(message, [para('Нет доступа.')])
        return
        
    target_id, _, _ = await parse_ban_args(message, economy)
    if not target_id:
        await send_rich(message, [para('Не удалось определить пользователя. Используйте @user, ID или реплай.')])
        return
        
    await economy.db.execute("DELETE FROM banned_users WHERE user_id = ?", (target_id,))
    access.invalidate(target_id)
    await send_rich(message, [para(f'Пользователь <code>{target_id}</code> разблокирован.')])
    await log_to_coder(message.bot, settings, f"Админ {message.from_user.id} разбанил <code>{target_id}</code>.")

@router.message(Command('db'))
async def cmd_get_db(message: Message, settings: Settings) -> None:
    if message.from_user.id != settings.coder_id:
        return
    if not settings.database_path.exists():
        await send_rich(message, [para('Файл БД не найден.')])
        return
    db_file = FSInputFile(settings.database_path)
    await message.reply_document(db_file, caption='Бэкап базы данных')


@router.callback_query(F.data.startswith('toggle_ban:'))
async def toggle_ban_mode(callback: CallbackQuery, economy: EconomyService, settings: Settings, access: AccessMiddleware) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer('Нет доступа.', show_alert=True)
        return
        
    target_id = int((callback.data or '').split(':')[1])
    row = await economy.db.fetch_one("SELECT silent_mode FROM banned_users WHERE user_id = ?", (target_id,))
    if not row:
        await callback.answer('Пользователь не найден в бан-листе.', show_alert=True)
        return
        
    new_mode = 0 if row['silent_mode'] else 1
    await economy.db.execute("UPDATE banned_users SET silent_mode = ? WHERE user_id = ?", (new_mode, target_id))
    access.invalidate(target_id)
    
    new_text = 'Режим: Молчание' if new_mode else 'Режим: Отчетность'
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=new_text, callback_data=f'toggle_ban:{target_id}')]])
    
    try:
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=markup)
        await callback.answer(f'Режим переключен на "{new_text}"')
    except Exception:
        pass