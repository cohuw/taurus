from __future__ import annotations
import re
from datetime import datetime
from html import escape
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import Settings
from richfmt import details, heading, para, send_rich, send_rich_to
from services.economy import EconomyError, EconomyService
from services.lottery import LotteryService
router = Router(name='lottery')

class CreateLotteryState(StatesGroup):
    waiting_for_nft_link = State()
    waiting_for_max_parts = State()
    waiting_for_max_tickets = State()
    waiting_for_min_tickets = State()
    waiting_for_end_time = State()

class EditLotteryState(StatesGroup):
    waiting_for_field_value = State()

async def is_admin(user_id: int, economy: EconomyService, settings: Settings) -> bool:
    return await economy.is_admin(user_id, settings)

@router.message(Command('create_lottery'))
async def create_lottery_start(message: Message, economy: EconomyService, settings: Settings, state: FSMContext) -> None:
    assert message.from_user is not None
    if not await is_admin(message.from_user.id, economy, settings):
        return
    await state.set_state(CreateLotteryState.waiting_for_nft_link)
    await send_rich(message, [para('Введите ссылку на NFT, которая будет разыграна:')])

@router.message(CreateLotteryState.waiting_for_nft_link, ~F.text.startswith('/'))
async def cl_nft_link(message: Message, state: FSMContext) -> None:
    link = (message.text or '').strip()
    await state.update_data(nft_link=link)
    await state.set_state(CreateLotteryState.waiting_for_max_parts)
    await send_rich(message, [para('Введите максимальное количество уникальных участников (0 для безлимита):')])

@router.message(CreateLotteryState.waiting_for_max_parts, ~F.text.startswith('/'))
async def cl_max_parts(message: Message, state: FSMContext) -> None:
    parts = (message.text or '').strip()
    if not parts.isdigit():
        await send_rich(message, [para('Введите число:')])
        return
    await state.update_data(max_parts=int(parts))
    await state.set_state(CreateLotteryState.waiting_for_max_tickets)
    await send_rich(message, [para('Введите максимальное кол-во билетов на 1 пользователя (0 для безлимита):')])

@router.message(CreateLotteryState.waiting_for_max_tickets, ~F.text.startswith('/'))
async def cl_max_tickets(message: Message, state: FSMContext) -> None:
    tickets = (message.text or '').strip()
    if not tickets.isdigit():
        await send_rich(message, [para('Введите число:')])
        return
    await state.update_data(max_tickets=int(tickets))
    await state.set_state(CreateLotteryState.waiting_for_min_tickets)
    await send_rich(message, [para('Введите МИНИМАЛЬНОЕ количество проданных билетов для авто-завершения (0 для безлимита):')])

@router.message(CreateLotteryState.waiting_for_min_tickets, ~F.text.startswith('/'))
async def cl_min_tickets(message: Message, state: FSMContext) -> None:
    min_t = (message.text or '').strip()
    if not min_t.isdigit():
        await send_rich(message, [para('Введите число:')])
        return
    await state.update_data(min_tickets=int(min_t))
    await state.set_state(CreateLotteryState.waiting_for_end_time)
    await send_rich(message, [para('Введите дату окончания в формате ДД.ММ.ГГГГ ЧЧ:ММ (например: 15.08.2026 20:00):')])

@router.message(CreateLotteryState.waiting_for_end_time, ~F.text.startswith('/'))
async def cl_end_time(message: Message, state: FSMContext, lottery: LotteryService) -> None:
    time_str = (message.text or '').strip()
    try:
        dt = datetime.strptime(time_str, '%d.%m.%Y %H:%M')
        if dt <= datetime.now():
            await send_rich(message, [para('Время должно быть в будущем! Попробуйте еще раз:')])
            return
    except ValueError:
        await send_rich(message, [para('Неверный формат. Нужно ДД.ММ.ГГГГ ЧЧ:ММ (например: 15.08.2026 20:00):')])
        return
    data = await state.get_data()
    draw_id = await lottery.create_draw(nft_link=data['nft_link'], max_parts=data['max_parts'], max_tickets=data['max_tickets'], min_tickets=data.get('min_tickets', 0), end_time=time_str)
    await state.clear()
    await send_rich(message, [para(f'✅ Лотерея #{draw_id} успешно создана!\nКонец: {time_str}')])

@router.message(Command('лотерея'))
@router.message(Command('lottery'))
@router.message(F.text.lower().in_({'лотерея', 'лоторея'}))
async def lottery_menu(message: Message, economy: EconomyService, lottery: LotteryService) -> None:
    assert message.from_user is not None
    await economy.ensure_user(message.from_user)
    draws = await lottery.get_active_draws()
    if not draws:
        await send_rich(message, [heading('Активные Лотереи'), para('В данный момент нет активных лотерей')])
        return
    blocks = [heading('Активные Лотереи')]
    for draw in draws:
        draw_id = draw['id']
        total = await lottery.get_total_tickets_count(draw_id)
        user_tickets = await lottery.get_user_tickets_count(message.from_user.id, draw_id)
        limit_p = f"Макс. участников: {draw['max_participants']}" if draw['max_participants'] else 'Безлимит участников'
        limit_t = f"Макс. билетов: {draw['max_tickets_per_user']}" if draw['max_tickets_per_user'] else 'Безлимит билетов'
        blocks.append(details(summary_text=f'Лотерея #{draw_id} | Билетов: {total}', blocks=[para(f"<b>Приз:</b> <a href='{escape(draw['nft_link'])}'>NFT</a>"), para(f"<b>Окончание:</b> {draw['end_time']}"), para(f'<b>Лимиты:</b> {limit_p} | {limit_t}'), para(f'<b>Куплено вами билетов:</b> {user_tickets}'), para(f'<i>Цена билета: {lottery.TICKET_PRICE} {lottery.TICKET_CURRENCY}</i>')], is_open=True))
    markup_rows = []
    for draw in draws:
        markup_rows.append([InlineKeyboardButton(text=f"Купить билет #{draw['id']} (1 TG)", callback_data=f"lottery_buy:{draw['id']}", style=ButtonStyle.PRIMARY)])
    markup_rows.append([InlineKeyboardButton(text='Обновить', callback_data='lottery_refresh_all', style=ButtonStyle.PRIMARY)])
    markup = InlineKeyboardMarkup(inline_keyboard=markup_rows)
    await send_rich(message, blocks, reply_markup=markup)

@router.callback_query(F.data == 'lottery_refresh_all')
async def lottery_refresh_all(callback: CallbackQuery, economy: EconomyService, lottery: LotteryService) -> None:
    draws = await lottery.get_active_draws()
    if not draws:
        try:
            await callback.message.edit_text('<b>Активные Лотереи</b>\n\nВ данный момент нет активных лотерей', reply_markup=None)
        except Exception:
            pass
        await callback.answer('Обновлено')
        return
    html_lines = ['<b>Активные Лотереи</b>\n']
    markup_rows = []
    for draw in draws:
        draw_id = draw['id']
        total = await lottery.get_total_tickets_count(draw_id)
        user_tickets = await lottery.get_user_tickets_count(callback.from_user.id, draw_id)
        limit_p = f"{draw['max_participants']}" if draw['max_participants'] else 'Безлимит'
        limit_t = f"Макс. на юзера: {draw['max_tickets_per_user']}" if draw['max_tickets_per_user'] else 'Безлимит'
        html_lines.append(f'<b>Лотерея #{draw_id}</b> (Куплено билетов: {total})')
        html_lines.append(f"Приз: <a href='{escape(draw['nft_link'])}'>NFT</a>")
        html_lines.append(f"Конец: {draw['end_time']}")
        html_lines.append(f'Лимиты: {limit_p} | {limit_t}')
        html_lines.append(f'Ваши билеты: <b>{user_tickets}</b>\n')
        markup_rows.append([InlineKeyboardButton(text=f'Купить билет #{draw_id} (1 TG)', callback_data=f'lottery_buy:{draw_id}', style=ButtonStyle.PRIMARY)])
    markup_rows.append([InlineKeyboardButton(text='Обновить', callback_data='lottery_refresh_all', style=ButtonStyle.PRIMARY)])
    markup = InlineKeyboardMarkup(inline_keyboard=markup_rows)
    try:
        await callback.message.edit_text('\n'.join(html_lines), reply_markup=markup, disable_web_page_preview=True)
        await callback.answer('Обновлено')
    except Exception:
        await callback.answer('Уже актуально')

@router.callback_query(F.data.startswith('lottery_buy:'))
async def lottery_buy(callback: CallbackQuery, economy: EconomyService, lottery: LotteryService) -> None:
    draw_id = int((callback.data or '').split(':')[1])
    try:
        await lottery.buy_ticket(callback.from_user.id, draw_id, economy)
        await callback.answer(f'Билет на лотерею #{draw_id} успешно куплен!', show_alert=True)
        await lottery_refresh_all(callback, economy, lottery)
    except EconomyError as exc:
        await callback.answer(str(exc), show_alert=True)

@router.message(Command('draw_lottery'))
async def cmd_draw_lottery(message: Message, economy: EconomyService, lottery: LotteryService, settings: Settings) -> None:
    assert message.from_user is not None
    if not await is_admin(message.from_user.id, economy, settings):
        return
    parts = (message.text or '').split()
    if len(parts) != 2 or not parts[1].isdigit():
        await send_rich(message, [para('Формат: `/draw_lottery [ID лотереи]`')])
        return
    draw_id = int(parts[1])
    draw = await lottery.get_draw(draw_id)
    if not draw or draw['status'] != 'active':
        await send_rich(message, [para('Лотерея не найдена или уже завершена.')])
        return
    result = await lottery.draw_winner(draw_id)
    winner_id = result['user_id']
    if winner_id is None:
        await send_rich(message, [para(f'Лотерея #{draw_id} завершена, но никто не купил билеты.')])
        return
    winner_profile = await economy.profile(winner_id)
    winner_name = escape(winner_profile['full_name']) if winner_profile else str(winner_id)
    announce = f"<b>ИТОГИ ЛОТЕРЕИ #{draw_id}</b>\n\nПобедитель: <b>{winner_name}</b> (ID: <code>{winner_id}</code>)\nКуплено билетов победителем: <b>{result['tickets_bought']}</b> из {result['total_tickets']}\n\n<b>Приз:</b> <a href='{escape(result['nft_link'])}'>NFT по ссылке</a>"
    await send_rich(message, [para(announce)])
    if settings.owner_id:
        try:
            from richfmt import send_rich_to
            await send_rich_to(message.bot, settings.owner_id, [para(announce)])
        except Exception:
            pass
    await send_rich_to(message.bot, winner_id, [heading('Поздравляем!'), para(f"Ты выиграл в лотерее #{draw_id}!\nТвой приз: <a href='{escape(result['nft_link'])}'>NFT</a>")])
    from richfmt import log_to_coder
    await log_to_coder(message.bot, settings, f"Админ {message.from_user.id} подвел итоги лотереи #{draw_id}.\nПобедитель: {winner_name} ({winner_id}).")

    

@router.callback_query(F.data.startswith('lottery_force:'))
async def force_lottery(callback: CallbackQuery, lottery: LotteryService, settings: Settings) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer('Нет доступа.', show_alert=True)
        return
    draw_id = int(callback.data.split(':')[1])
    try:
        res = await lottery.force_draw(draw_id)
        winner_id = res.get('user_id')
        
        if winner_id:
            economy = EconomyService(lottery.db)
            winner_profile = await economy.profile(winner_id)
            winner_name = escape(winner_profile['full_name']) if winner_profile else str(winner_id)
            text = f"<b>Лотерея #{draw_id} принудительно завершена.</b>\n\nПобедитель: <b>{winner_name}</b> (ID: <code>{winner_id}</code>)\nКуплено его билетов: <b>{res.get('tickets_bought', 0)}</b> из {res.get('total_tickets', 0)}"
            if callback.message:
                await send_rich(callback.message, [para(text)])
            await send_rich_to(callback.bot, winner_id, [heading('Поздравляем!'), para(f"Ты выиграл в лотерее #{draw_id}!\nТвой приз: <a href='{escape(res.get('nft_link', ''))}'>NFT</a>")])
            from richfmt import log_to_coder
            await log_to_coder(callback.bot, settings, f"Владелец принудительно завершил лотерею #{draw_id}.\nПобедитель: {winner_id}")
        else:
            if callback.message:
                await send_rich(callback.message, [para(f"Лотерея #{draw_id} принудительно завершена.\nУчастников не было, победитель: Никто")])
            from richfmt import log_to_coder
            await log_to_coder(callback.bot, settings, f"Владелец принудительно завершил лотерею #{draw_id}.\nУчастников не было.")
            
    except Exception as e:
        await callback.answer(f'Ошибка: {e}', show_alert=True)
    await callback.answer()

@router.callback_query(F.data.startswith('lottery_cancel_ref:'))
async def cancel_ref_lottery(callback: CallbackQuery, lottery: LotteryService, economy: EconomyService, settings: Settings) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer('Нет доступа.', show_alert=True)
        return
    draw_id = int(callback.data.split(':')[1])
    try:
        await lottery.cancel_draw(draw_id, refund=True, economy=economy)
        if callback.message:
            await send_rich(callback.message, [para(f"Лотерея #{draw_id} отменена, билеты возвращены (по {lottery.TICKET_PRICE} TG).")])
        from richfmt import log_to_coder
        await log_to_coder(callback.bot, settings, f"Владелец отменил лотерею #{draw_id} с возвратом средств.")
    except Exception as e:
        await callback.answer(f'Ошибка: {e}', show_alert=True)
    await callback.answer()

@router.callback_query(F.data.startswith('lottery_cancel_noref:'))
async def cancel_noref_lottery(callback: CallbackQuery, lottery: LotteryService, economy: EconomyService, settings: Settings) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer('Нет доступа.', show_alert=True)
        return
    draw_id = int(callback.data.split(':')[1])
    try:
        await lottery.cancel_draw(draw_id, refund=False, economy=economy)
        if callback.message:
            await send_rich(callback.message, [para(f"Лотерея #{draw_id} отменена БЕЗ возврата билетов.")])
        from richfmt import log_to_coder
        await log_to_coder(callback.bot, settings, f"Владелец отменил лотерею #{draw_id} БЕЗ возврата средств.")
    except Exception as e:
        await callback.answer(f'Ошибка: {e}', show_alert=True)
    await callback.answer()

@router.message(Command('lot_edit'))
async def cmd_lot_edit(message: Message, settings: Settings, lottery: LotteryService, state: FSMContext) -> None:
    if message.from_user.id != settings.owner_id:
        return
    parts = (message.text or '').split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: /lot_edit [id]\nПример: /lot_edit 2")
        return
    draw_id = int(parts[1])
    draw = await lottery.get_draw(draw_id)
    if not draw:
        await message.answer(f"Лотерея #{draw_id} не найдена.")
        return
    await _send_lot_edit_menu(message, draw)

async def _send_lot_edit_menu(message: Message, draw: dict) -> None:
    draw_id = draw['id']
    text = (
        f"Лотерея #{draw_id}\n"
        f"Статус: {draw['status']}\n"
        f"NFT: {draw['nft_link']}\n"
        f"Конец: {draw['end_time']}\n"
        f"Макс. участников: {draw['max_participants'] or 'безлимит'}\n"
        f"Макс. билетов на юзера: {draw['max_tickets_per_user'] or 'безлимит'}\n"
        f"Мин. билетов для розыгрыша: {draw['min_tickets'] or 'нет'}"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить статус", callback_data=f"ledit:{draw_id}:status")],
        [InlineKeyboardButton(text="Изменить NFT-ссылку", callback_data=f"ledit:{draw_id}:nft_link")],
        [InlineKeyboardButton(text="Изменить время окончания", callback_data=f"ledit:{draw_id}:end_time")],
        [InlineKeyboardButton(text="Изменить макс. участников", callback_data=f"ledit:{draw_id}:max_participants")],
        [InlineKeyboardButton(text="Изменить макс. билетов на юзера", callback_data=f"ledit:{draw_id}:max_tickets_per_user")],
        [InlineKeyboardButton(text="Изменить мин. билетов", callback_data=f"ledit:{draw_id}:min_tickets")],
    ])
    await message.answer(text, reply_markup=markup)

@router.callback_query(F.data.startswith('ledit:'))
async def lot_edit_field_select(callback: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    parts = (callback.data or '').split(':')
    draw_id = int(parts[1])
    field = parts[2]

    labels = {
        'status': 'статус (active / completed / cancelled / pending_review)',
        'nft_link': 'новую ссылку на NFT',
        'end_time': 'новое время окончания (формат: 31.12.2025 23:59)',
        'max_participants': 'макс. участников (0 = безлимит)',
        'max_tickets_per_user': 'макс. билетов на юзера (0 = безлимит)',
        'min_tickets': 'мин. билетов для розыгрыша (0 = нет)',
    }
    await state.set_state(EditLotteryState.waiting_for_field_value)
    await state.update_data(draw_id=draw_id, field=field)
    await callback.answer()
    if callback.message:
        await callback.message.answer(f"Введите {labels.get(field, field)}:")

@router.message(EditLotteryState.waiting_for_field_value, ~F.text.startswith('/'))
async def lot_edit_apply(message: Message, settings: Settings, lottery: LotteryService, state: FSMContext) -> None:
    if message.from_user.id != settings.owner_id:
        await state.clear()
        return
    data = await state.get_data()
    draw_id = data['draw_id']
    field = data['field']
    value_raw = (message.text or '').strip()

    int_fields = {'max_participants', 'max_tickets_per_user', 'min_tickets'}
    if field in int_fields:
        if not value_raw.isdigit():
            await message.answer("Нужно ввести целое число.")
            return
        value = int(value_raw)
    else:
        value = value_raw

    try:
        await lottery.db.execute(f"UPDATE lottery_draws SET {field} = ? WHERE id = ?", (value, draw_id))
        await state.clear()
        draw = await lottery.get_draw(draw_id)
        await message.answer(f"Поле {field} обновлено.")
        if draw:
            await _send_lot_edit_menu(message, draw)
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        await state.clear()

PER_PAGE = 20

async def _send_tickets_page(target: Message | CallbackQuery, lottery: LotteryService, economy: EconomyService, draw_id: int, page: int) -> None:
    draw = await lottery.get_draw(draw_id)
    if not draw:
        text = f"Лотерея #{draw_id} не найдена."
        if isinstance(target, CallbackQuery) and target.message:
            await target.message.answer(text)
        else:
            await target.answer(text)
        return

    participants = await lottery.get_participants_summary(draw_id)
    total_tickets = sum(p['tickets'] for p in participants)
    total_pages = max(1, (len(participants) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = participants[page * PER_PAGE:(page + 1) * PER_PAGE]

    lines = [f"Лотерея #{draw_id} | Статус: {draw['status']} | Участников: {len(participants)} | Билетов: {total_tickets}\n"]
    for i, p in enumerate(chunk, start=page * PER_PAGE + 1):
        profile = await economy.profile(p['user_id'])
        name = escape(profile['full_name']) if profile else str(p['user_id'])
        lines.append(f"{i}. {name} (<code>{p['user_id']}</code>) — {p['tickets']} бил.")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="Назад", callback_data=f"ltickets:{draw_id}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Вперёд", callback_data=f"ltickets:{draw_id}:{page + 1}"))

    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="Вернуть TG всем", callback_data=f"ltickets_refund:{draw_id}")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(lines)

    if isinstance(target, CallbackQuery) and target.message:
        try:
            await target.message.edit_text(text, reply_markup=markup)
        except Exception:
            await target.message.answer(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)

@router.message(Command('lot_tickets'))
async def cmd_lot_tickets(message: Message, settings: Settings, lottery: LotteryService, economy: EconomyService) -> None:
    if message.from_user.id != settings.owner_id:
        return
    parts = (message.text or '').split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: /lot_tickets [id]\nПример: /lot_tickets 2")
        return
    await _send_tickets_page(message, lottery, economy, int(parts[1]), 0)

@router.callback_query(F.data.startswith('ltickets:'))
async def lot_tickets_page(callback: CallbackQuery, settings: Settings, lottery: LotteryService, economy: EconomyService) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    parts = (callback.data or '').split(':')
    draw_id = int(parts[1])
    page = int(parts[2])
    await _send_tickets_page(callback, lottery, economy, draw_id, page)

@router.callback_query(F.data.startswith('ltickets_refund:'))
async def lot_tickets_refund_confirm(callback: CallbackQuery, settings: Settings, lottery: LotteryService) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    draw_id = int((callback.data or '').split(':')[1])
    total = await lottery.get_total_tickets_count(draw_id)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, вернуть", callback_data=f"ltickets_refund_do:{draw_id}"),
            InlineKeyboardButton(text="Отмена", callback_data=f"ltickets:{draw_id}:0"),
        ]
    ])
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"Вернуть TG за все {total} билетов лотереи #{draw_id}?\n"
            f"Каждый участник получит по {lottery.TICKET_PRICE} TG за каждый билет.",
            reply_markup=markup
        )

@router.callback_query(F.data.startswith('ltickets_refund_do:'))
async def lot_tickets_refund_do(callback: CallbackQuery, settings: Settings, lottery: LotteryService, economy: EconomyService) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    draw_id = int((callback.data or '').split(':')[1])
    tickets = await lottery.get_tickets_for_draw(draw_id)
    ok = 0
    fail = 0
    for t in tickets:
        try:
            await economy.add_taurgems(t['user_id'], lottery.TICKET_PRICE, f'lottery_refund:{draw_id}')
            ok += 1
        except Exception:
            fail += 1
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"Возврат TG для лотереи #{draw_id} выполнен.\nУспешно: {ok}, ошибок: {fail}.",
            reply_markup=None
        )
    from richfmt import log_to_coder
    await log_to_coder(callback.bot, settings, f"Владелец вернул TG за билеты лотереи #{draw_id}. Успешно: {ok}, ошибок: {fail}.")
