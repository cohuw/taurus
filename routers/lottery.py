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
    await send_rich_to(message.bot, winner_id, [heading('Поздравляем!'), para(f"Ты выиграл в лотерее #{draw_id}!\nТвой приз: <a href='{escape(result['nft_link'])}'>NFT</a>")])


@router.callback_query(F.data.startswith('lottery_force:'))
async def force_lottery(callback: CallbackQuery, lottery: LotteryService, settings: Settings) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer('Нет доступа.', show_alert=True)
        return
    draw_id = int(callback.data.split(':')[1])
    try:
        res = await lottery.force_draw(draw_id)
        winner_id = res.get('user_id')
        text = f"Лотерея #{draw_id} принудительно завершена.\nПобедитель: {winner_id or 'Никто'}"
        if callback.message:
            await send_rich(callback.message, [para(text)])
        if winner_id:
            from richfmt import heading, para, send_rich_to
            await send_rich_to(callback.bot, winner_id, [heading('Поздравляем!'), para(f"Ты выиграл в лотерее #{draw_id}!\nТвой приз: <a href='{res.get('nft_link', '')}'>NFT</a>")])
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
    except Exception as e:
        await callback.answer(f'Ошибка: {e}', show_alert=True)
    await callback.answer()