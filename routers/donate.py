from __future__ import annotations
import re
from html import escape
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.enums import ButtonStyle
from config import Settings
from richfmt import heading, para, send_rich
from services.donations import DonationService
from services.economy import EconomyError, EconomyService
from services.cryptopay import CryptoPayService
router = Router(name='donate')

class DonateState(StatesGroup):
    choosing_method = State()
    waiting_for_amount = State()
    waiting_for_receipt = State()
    waiting_for_custom_amount = State()

async def is_admin(user_id: int, economy: EconomyService, settings: Settings) -> bool:
    return await economy.is_admin(user_id, settings)

@router.message(Command('пополнить'), F.chat.type == 'private')
@router.message(Command('donate'), F.chat.type == 'private')
@router.message(F.text.lower().in_({'донат', 'пополнить', 'donate'}), F.chat.type == 'private')
async def donate_start(message: Message, state: FSMContext, economy: EconomyService) -> None:
    await state.set_state(DonateState.choosing_method)
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='СБП (Карта РФ)', callback_data='pay_method:sbp', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Криптовалюта (Авто)', callback_data='pay_method:crypto', style=ButtonStyle.PRIMARY)]])
    tg_price = await economy.get_tg_price_rub()
    ton_amount = round(tg_price / economy.ton_rub_rate, 2)
    await send_rich(message, [heading('Пополнение баланса (Taurgems)'), para(f'Выбери удобный способ оплаты. <b>Курс:</b>\n1 TG = {tg_price} RUB\n1 TG = ~{ton_amount} GRAM (эквивалент в TON)\n\nВыбери способ ниже:')], reply_markup=markup)

@router.callback_query(DonateState.choosing_method, F.data.startswith('pay_method:'))
async def process_payment_method(callback: CallbackQuery, state: FSMContext, cryptopay: CryptoPayService | None=None) -> None:
    method = callback.data.split(':')[1]
    if method == 'crypto':
        if not cryptopay:
            await callback.answer('Оплата криптовалютой временно недоступна.', show_alert=True)
            return
        await state.set_state(DonateState.waiting_for_amount)
        await callback.message.edit_text('<b>Пополнение через CryptoBot</b>\n\nВведите количество Taurgems (TG), которое вы хотите купить:', reply_markup=None)
        await callback.answer()
        return
    details_text = 'Выбрана оплата картой (СБП).\nРеквизиты: <b>2200 7013 7702 8367 (ТБанк)</b>'
    await state.set_state(DonateState.waiting_for_receipt)
    await callback.message.edit_text(f'<b>Пополнение баланса</b>\n\n{details_text}\n\nПосле того, как вы совершили перевод, пожалуйста, <b>отправьте сюда фото или скриншот чека</b> об оплате.\n\n<i>За попытку обмана (фейк чек) списывается -1 TG!</i>', reply_markup=None)
    await callback.answer()

@router.message(DonateState.waiting_for_amount, ~F.text.startswith('/'))
async def process_crypto_amount(message: Message, state: FSMContext, cryptopay: CryptoPayService, economy: EconomyService) -> None:
    amount_str = (message.text or '').strip()
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await send_rich(message, [para('Пожалуйста, введите целое число больше нуля:')])
        return
    tg_amount = int(amount_str)
    tg_price = await economy.get_tg_price_rub()
    rub_amount = tg_amount * tg_price
    msg = await message.answer('Генерируем счет...')
    try:
        invoice = await cryptopay.create_invoice(rub_amount, f'Покупка {tg_amount} TG', economy.ton_rub_rate)
        invoice_id = invoice['invoice_id']
        pay_url = invoice['bot_invoice_url']
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Оплатить', url=pay_url, style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Проверить оплату', callback_data=f'check_crypto:{invoice_id}:{tg_amount}', style=ButtonStyle.SUCCESS)]])
        await msg.edit_text(f'<b>Счет создан!</b>\n\n<b>К оплате:</b> {rub_amount} RUB\n<b>К зачислению:</b> {tg_amount} TG\n\nПерейдите по ссылке ниже, оплатите счет в CryptoBot и нажмите «Проверить оплату».\n\n<i>ID счета: <code>{invoice_id}</code></i>', reply_markup=markup)
        await state.clear()
    except Exception as e:
        await msg.edit_text(f'Ошибка генерации счета: {e}')
        await state.clear()

@router.callback_query(F.data.startswith('check_crypto:'))
async def check_crypto_payment(callback: CallbackQuery, cryptopay: CryptoPayService, economy: EconomyService, settings: Settings) -> None:
    parts = callback.data.split(':')
    invoice_id = int(parts[1])
    tg_amount = int(parts[2])
    try:
        invoice = await cryptopay.get_invoice(invoice_id)
        if invoice['status'] == 'paid':
            await economy.add_taurgems(callback.from_user.id, tg_amount, f'crypto_purchase:{invoice_id}')
            await callback.message.edit_text(f'<b>Оплата прошла успешно!</b>\nВам начислено {tg_amount} TG.', reply_markup=None)
            if settings.log_chat_id:
                try:
                    kwargs = {'chat_id': settings.log_chat_id}
                    if settings.player_log_thread_id:
                        kwargs['message_thread_id'] = settings.player_log_thread_id
                    await callback.bot.send_message(text=f'<b>Авто-пополнение (CryptoBot)</b>\nЮзер <code>{callback.from_user.id}</code> купил {tg_amount} TG (Счет #{invoice_id})', **kwargs)
                except Exception:
                    pass
        elif invoice['status'] in ['active', 'expired']:
            await callback.answer(f"Счет еще не оплачен (статус: {invoice['status']}).", show_alert=True)
    except Exception as e:
        await callback.answer(f'Ошибка проверки: {e}', show_alert=True)

@router.message(DonateState.waiting_for_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext, donations: DonationService, settings: Settings) -> None:
    assert message.from_user is not None
    photo_id = message.photo[-1].file_id
    req_id = await donations.create_payment_request(message.from_user.id, photo_id)
    await state.clear()
    await send_rich(message, [para('<b>Чек отправлен на проверку.</b> Ожидайте зачисления!')])
    if settings.owner_id:
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Подтвердить', callback_data=f'pay_custom:{req_id}', style=ButtonStyle.SUCCESS)], [InlineKeyboardButton(text='Отмена', callback_data=f'pay_cancel:{req_id}', style=ButtonStyle.DANGER)]])
        admin_text = f'<b>Новая заявка на пополнение #{req_id}</b>\nПользователь: {escape(message.from_user.full_name)} (<code>{message.from_user.id}</code>)\nПроверьте чек и выберите действие.'
        try:
            await message.bot.send_photo(chat_id=settings.owner_id, photo=photo_id, caption=admin_text, reply_markup=markup)
        except Exception:
            pass

@router.message(DonateState.waiting_for_receipt, ~F.text.startswith('/'))
async def process_receipt_invalid(message: Message) -> None:
    await send_rich(message, [para('Пожалуйста, отправьте именно <b>фото</b> (скриншот) чека.')])

@router.callback_query(F.data.startswith('pay_cancel:'))
async def admin_cancel_payment(callback: CallbackQuery, settings: Settings) -> None:
    if callback.from_user.id != settings.owner_id:
        await callback.answer('Только для владельца.', show_alert=True)
        return
    req_id = callback.data.split(':')[1]
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ложный чек (попытка обмана)', callback_data=f'pay_fine:{req_id}', style=ButtonStyle.DANGER)], [InlineKeyboardButton(text='Без причины', callback_data=f'pay_reject:{req_id}', style=ButtonStyle.PRIMARY)]])
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=markup)
        except Exception:
            pass
    await callback.answer()

@router.callback_query(F.data.startswith('pay_reject:'))
async def admin_reject_payment(callback: CallbackQuery, economy: EconomyService, donations: DonationService, settings: Settings) -> None:
    if not await is_admin(callback.from_user.id, economy, settings):
        return
    req_id = int((callback.data or '').split(':')[1])
    req = await donations.get_payment_request(req_id)
    if not req or req['status'] != 'pending':
        await callback.answer('Уже обработано', show_alert=True)
        return
    await donations.update_payment_request(req_id, 'rejected')
    await callback.answer('Отклонено')
    if callback.message:
        try:
            await callback.message.edit_caption(caption=f'{callback.message.html_text}\n\n<b>ОТКЛОНЕНО</b>', reply_markup=None)
        except Exception:
            pass
    try:
        await callback.bot.send_message(req['user_id'], 'Ваша заявка на пополнение была отклонена.')
    except Exception:
        pass

@router.callback_query(F.data.startswith('pay_fine:'))
async def admin_fine_payment(callback: CallbackQuery, economy: EconomyService, donations: DonationService, settings: Settings) -> None:
    if not await is_admin(callback.from_user.id, economy, settings):
        return
    req_id = int((callback.data or '').split(':')[1])
    req = await donations.get_payment_request(req_id)
    if not req or req['status'] != 'pending':
        await callback.answer('Уже обработано', show_alert=True)
        return
    await donations.update_payment_request(req_id, 'rejected_fined')
    try:
        await economy.add_taurgems(req['user_id'], -1, f'donation_fake_fine:{req_id}')
    except EconomyError:
        pass
    await callback.answer('Оштрафован!')
    if callback.message:
        try:
            await callback.message.edit_caption(caption=f'{callback.message.html_text}\n\n<b>ШТРАФ:</b> списан 1 TG за обман.', reply_markup=None)
        except Exception:
            pass
    try:
        await callback.bot.send_message(req['user_id'], 'Ваша заявка отклонена как подозрительная (попытка обмана). За это списан <b>1 TG</b> штрафа.')
    except Exception:
        pass

@router.callback_query(F.data.startswith('pay_custom:'))
async def admin_custom_payment(callback: CallbackQuery, economy: EconomyService, settings: Settings, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id, economy, settings):
        return
    req_id = int((callback.data or '').split(':')[1])
    await state.update_data(req_id=req_id, msg_id=callback.message.message_id if callback.message else 0, chat_id=callback.message.chat.id if callback.message else 0)
    await state.set_state(DonateState.waiting_for_custom_amount)
    await callback.answer('Введите сумму в чат')
    if callback.message:
        try:
            await callback.bot.send_message(callback.message.chat.id, f'Введите сумму TG для выдачи по заявке #{req_id}:', reply_to_message_id=callback.message.message_id)
        except Exception:
            pass

@router.message(DonateState.waiting_for_custom_amount, ~F.text.startswith('/'))
async def process_custom_amount(message: Message, state: FSMContext, economy: EconomyService, donations: DonationService) -> None:
    data = await state.get_data()
    req_id = data.get('req_id')
    amount_str = (message.text or '').strip()
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await send_rich(message, [para('Введите целое положительное число.')])
        return
    amount = int(amount_str)
    req = await donations.get_payment_request(req_id)
    if not req or req['status'] != 'pending':
        await send_rich(message, [para('Заявка уже обработана.')])
        await state.clear()
        return
    await donations.update_payment_request(req_id, 'approved')
    await economy.add_taurgems(req['user_id'], amount, f'donation_approved:{req_id}')
    await send_rich(message, [para(f'Успешно выдано {amount} TG по заявке #{req_id}.')])
    try:
        await message.bot.edit_message_caption(chat_id=data['chat_id'], message_id=data['msg_id'], caption=f'<b>ОДОБРЕНО:</b> выдано {amount} TG.', reply_markup=None)
    except Exception:
        pass
    try:
        await message.bot.send_message(req['user_id'], f'Ваша заявка на пополнение одобрена! Вам начислено <b>{amount} TG</b>.')
    except Exception:
        pass
    await state.clear()

@router.callback_query(F.data.startswith('claim_check:'))
async def claim_check_callback(callback: CallbackQuery, economy: EconomyService, donations: DonationService) -> None:
    check_id = int((callback.data or '').split(':')[1])
    try:
        amount = await donations.claim_money_check(check_id, callback.from_user.id, economy)
        name = escape(callback.from_user.full_name)
        await callback.answer(f'Вы успешно забрали {amount} TG!', show_alert=True)
        if callback.message:
            await callback.message.edit_text(f'Чек на <b>{amount} TG</b> успешно активировал {name}!', reply_markup=None)
    except EconomyError as exc:
        await callback.answer(str(exc), show_alert=True)
        if 'активирован' in str(exc) and callback.message:
            try:
                await callback.message.edit_text(f'Чек уже кто-то забрал.', reply_markup=None)
            except Exception:
                pass