from __future__ import annotations
import json
from html import escape
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, InputMediaPhoto, InputMediaDocument
import asyncio
from config import Settings
from keyboards import back_keyboard
from richfmt import EM_T, EM_TC, heading, para, send_rich, divider, table, details
from services.economy import EconomyService
from services.missions import MissionService
router = Router(name='missions')

class MissionState(StatesGroup):
    waiting_proof = State()
    waiting_new_mission = State()
    waiting_import = State()

async def require_admin(message_or_callback, economy: EconomyService, settings: Settings) -> bool:
    user = message_or_callback.from_user
    return bool(user and await economy.is_admin(user.id, settings))

@router.message(F.text == 'Мои задания', F.chat.type == 'private')
async def my_tasks(message: Message, economy: EconomyService, missions: MissionService) -> None:
    assert message.from_user is not None
    await economy.ensure_user(message.from_user)
    await missions.ensure_for_user(message.from_user.id)
    active = await missions.active_missions(message.from_user.id)
    all_missions = missions.load()
    if not active:
        await message.reply('У тебя нет активных заданий')
        return
    blocks = [heading('Твои задания')]
    keyboard_rows = []
    for i, item in enumerate(active):
        mission = all_missions.get(str(item['mission_id']))
        if not mission:
            continue
        mid = item['mission_id']
        is_reported = item['status'] == 'reported'
        status = '<b>На проверке</b>' if is_reported else '<b>Активно</b>'
        summary = f"<b>{mission['name']}</b> <code>#{mid}</code> | {mission.get('reward_taurons', 0)} {EM_T} T / {mission.get('reward_taurcoins', 0)} {EM_TC} TC"
        blocks.append(details(summary_text=summary, blocks=[para(f'<b>Статус:</b> {status}'), para(f"<b>Цель:</b> <i>{mission['description']}</i>")]))
        if item['status'] == 'pending':
            keyboard_rows.append([InlineKeyboardButton(text=f'Сдать отчет {mid}', callback_data=f'report_mission:{mid}', style=ButtonStyle.PRIMARY)])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_rows) if keyboard_rows else None
    await send_rich(message, blocks, reply_markup=markup)

@router.callback_query(F.data.startswith('report_mission:'))
async def report_mission(callback: CallbackQuery, state: FSMContext) -> None:
    mission_id = int((callback.data or '').split(':')[1])
    await state.update_data(mission_id=mission_id)
    await state.set_state(MissionState.waiting_proof)
    await callback.answer()
    if callback.message:
        await callback.message.answer('<b>Пожалуйста, отправьте скриншот, документ или текстовое подтверждение выполнения задания.</b>')

album_cache: dict[str, list[Message]] = {}

@router.message(MissionState.waiting_proof, ~F.text.startswith('/'))
async def handle_proof(message: Message, state: FSMContext, missions: MissionService, settings: Settings) -> None:
    if message.media_group_id:
        if message.media_group_id not in album_cache:
            album_cache[message.media_group_id] = [message]
            await asyncio.sleep(0.5)
            msgs = album_cache.pop(message.media_group_id, [])
            if msgs:
                await _process_proof_messages(msgs, state, missions, settings)
        else:
            album_cache[message.media_group_id].append(message)
    else:
        await _process_proof_messages([message], state, missions, settings)

async def _process_proof_messages(msgs: list[Message], state: FSMContext, missions: MissionService, settings: Settings) -> None:
    first_msg = msgs[0]
    assert first_msg.from_user is not None
    data = await state.get_data()
    mission_id = int(data.get('mission_id', 0))
    if not mission_id:
        return
    texts = [m.text or m.caption for m in msgs if m.text or m.caption]
    combined_text = '\n'.join(texts)
    
    if len(msgs) == 1:
        m = msgs[0]
        file_id = None
        kind = 'text'
        if m.photo:
            file_id = m.photo[-1].file_id
            kind = 'photo'
        elif m.document:
            file_id = m.document.file_id
            kind = 'document'
        report_data = json.dumps({'kind': kind, 'file_id': file_id, 'text': combined_text}, ensure_ascii=False)
    else:
        file_ids = []
        for m in msgs:
            if m.photo:
                file_ids.append({'type': 'photo', 'id': m.photo[-1].file_id})
            elif m.document:
                file_ids.append({'type': 'document', 'id': m.document.file_id})
        report_data = json.dumps({'kind': 'album', 'file_ids': file_ids, 'text': combined_text}, ensure_ascii=False)

    await missions.report(first_msg.from_user.id, mission_id, report_data)
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Подтвердить', callback_data=f'confirm_task:{first_msg.from_user.id}:{mission_id}', style=ButtonStyle.SUCCESS), InlineKeyboardButton(text='Отклонить', callback_data=f'rejecttask:{first_msg.from_user.id}:{mission_id}', style=ButtonStyle.DANGER)]])
    all_missions = missions.load()
    mission = all_missions.get(str(mission_id), {'name': f'#{mission_id}', 'description': ''})
    admin_text = f"<b>Новый отчет о выполнении задания</b>\nПользователь: {escape(first_msg.from_user.full_name)} (<code>{first_msg.from_user.id}</code>)\nЗадание: <b>{mission['name']}</b>\nОписание задания: <i>{mission.get('description', '')}</i>\nКомментарий игрока: {escape(combined_text or 'Без комментария')}"
    
    if settings.log_chat_id:
        try:
            kwargs = {'chat_id': settings.log_chat_id}
            if settings.mission_log_thread_id:
                kwargs['message_thread_id'] = settings.mission_log_thread_id
            if len(msgs) > 1:
                media = []
                for m in msgs:
                    if m.photo:
                        media.append(InputMediaPhoto(media=m.photo[-1].file_id))
                    elif m.document:
                        media.append(InputMediaDocument(media=m.document.file_id))
                if media:
                    try:
                        await first_msg.bot.send_media_group(media=media, **kwargs)
                    except Exception:
                        pass
                kwargs['reply_markup'] = markup
                await first_msg.bot.send_message(text=admin_text, **kwargs)
            else:
                kwargs['reply_markup'] = markup
                m = msgs[0]
                if m.photo:
                    await first_msg.bot.send_photo(photo=m.photo[-1].file_id, caption=admin_text, **kwargs)
                elif m.document:
                    await first_msg.bot.send_document(document=m.document.file_id, caption=admin_text, **kwargs)
                else:
                    await first_msg.bot.send_message(text=admin_text, **kwargs)
        except Exception:
            pass
    
    await state.clear()
    try:
        await first_msg.answer('<b>Отчет отправлен на модерацию. Ожидайте подтверждения от администратора.</b>')
    except Exception:
        pass

@router.callback_query(F.data.startswith('confirm_task:') | F.data.startswith('rejecttask:'))
async def process_task(callback: CallbackQuery, economy: EconomyService, missions: MissionService, settings: Settings) -> None:
    if not await require_admin(callback, economy, settings):
        await callback.answer('У вас нет прав для выполнения этого действия.', show_alert=True)
        return
    action, user_id_s, mission_id_s = (callback.data or '').split(':')
    user_id, mission_id = (int(user_id_s), int(mission_id_s))
    all_missions = missions.load()
    mission = all_missions.get(str(mission_id), {'name': f'#{mission_id}', 'reward_taurons': 0, 'reward_taurcoins': 0})
    if action == 'confirm_task':
        ok = await missions.complete(user_id, mission_id, economy)
        if not ok:
            await callback.answer('Ошибка: задание не найдено', show_alert=True)
            return
        await callback.answer('Задание подтверждено!', show_alert=True)
        try:
            await callback.bot.send_message(user_id, f"Задание <b>{mission['name']}</b> подтверждено! Награда: {mission.get('reward_taurons', 0)} Taurons, {mission.get('reward_taurcoins', 0)} Taurcoins")
        except Exception:
            pass
        text = f"<b>Задание подтверждено</b>\nID пользователя: <code>{user_id}</code>\nЗадание: {mission['name']}\nОписание: <i>{mission.get('description', '')}</i>"
    else:
        await missions.reject(user_id, mission_id)
        await callback.answer('Задание отклонено', show_alert=True)
        try:
            await callback.bot.send_message(user_id, f"<b>Задание отклонено</b>\nЗадание: {mission['name']}\nМожно отправить отчет заново.")
        except Exception:
            pass
        text = f"<b>Задание отклонено</b>\nID пользователя: <code>{user_id}</code>\nЗадание: {mission['name']}\nОписание: <i>{mission.get('description', '')}</i>"
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=None)
        except Exception:
            await callback.message.answer(text)

@router.callback_query(F.data == 'admin_missions')
async def admin_missions(callback: CallbackQuery, missions: MissionService) -> None:
    await callback.answer()
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Посмотреть миссии', callback_data='view_missions', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Экспортировать миссии (JSON)', callback_data='export_missions', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Импортировать миссии (JSON)', callback_data='import_missions', style=ButtonStyle.PRIMARY)], [InlineKeyboardButton(text='Назад', callback_data='admin_back', style=ButtonStyle.PRIMARY)]])
    if callback.message:
        await callback.message.delete()
        await send_rich(callback.message, [heading('Управление заданиями'), para(f'Всего заданий: <b>{len(missions.load())}</b>')], reply_markup=markup)

@router.callback_query(F.data == 'view_missions')
async def view_missions(callback: CallbackQuery, missions: MissionService) -> None:
    await callback.answer()
    data = missions.load()
    if not data:
        blocks = [para('Заданий пока нет.')]
    else:
        blocks = [heading('Список заданий')]
        rows = [['ID', 'Название', 'Награда']]
        for mid, m in data.items():
            reward = f"{m.get('reward_taurons', 0)} {EM_T} T / {m.get('reward_taurcoins', 0)} {EM_TC} TC"
            rows.append([str(mid), m.get('name', 'Без названия'), reward])
        blocks.append(table(rows[0], rows[1:]))
    if callback.message:
        await callback.message.delete()
        await send_rich(callback.message, blocks, reply_markup=back_keyboard('admin_missions'))

@router.callback_query(F.data == 'export_missions')
async def export_missions(callback: CallbackQuery, missions: MissionService) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer('<pre>' + json.dumps(missions.load(), ensure_ascii=False, indent=2) + '</pre>')

@router.callback_query(F.data == 'import_missions')
async def import_missions(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(MissionState.waiting_import)
    if callback.message:
        await callback.message.answer('Отправь задание в одном из форматов:\n\n<b>Простой</b> (поддерживает прем эмодзи):\n<code>Название | Описание | Награда_T | Награда_TC</code>\n\n<b>JSON:</b>\n<code>{"name":"...", "description":"...", "reward_taurons":10, "reward_taurcoins":0}</code>')

@router.message(MissionState.waiting_import, ~F.text.startswith('/'))
async def process_mission_import(message: Message, state: FSMContext, missions: MissionService) -> None:
    raw = message.text or ''
    html = message.html_text or ''
    try:
        current = missions.load()
        if '|' in raw and (not raw.strip().startswith('{')):
            parts = [p.strip() for p in html.split('|')]
            if len(parts) < 2:
                raise ValueError('Формат: Название | Описание | Награда_T | Награда_TC')
            payload = {'name': parts[0], 'description': parts[1] if len(parts) > 1 else '', 'reward_taurons': int(parts[2]) if len(parts) > 2 else 0, 'reward_taurcoins': int(parts[3]) if len(parts) > 3 else 0}
            new_id = str(max([int(k) for k in current] or [0]) + 1)
            current[new_id] = payload
        else:
            payload = json.loads(raw)
            if all((k in payload for k in ('name', 'description'))):
                new_id = str(max([int(k) for k in current] or [0]) + 1)
                current[new_id] = payload
            elif isinstance(payload, dict):
                current = payload
            else:
                raise ValueError('Ожидался JSON-объект')
        missions.save(current)
    except Exception as exc:
        await message.answer(f'Ошибка импорта: {exc}')
        return
    await state.clear()
    await message.answer(f'<b>Задания сохранены.</b> Всего: {len(current)}')

@router.message(Command('reset_missions'))
async def reset_missions(message: Message, economy: EconomyService, missions: MissionService, settings: Settings) -> None:
    assert message.from_user is not None
    if not await economy.is_admin(message.from_user.id, settings):
        await message.reply('Нет доступа.')
        return
    count = await missions.reset_completed()
    await message.reply(f'<b>Сброшено выполненных заданий:</b> {count}')