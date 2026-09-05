from __future__ import annotations
from html import escape
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from config import Settings
from keyboards import convert_keyboard, main_menu
from richfmt import EM_T, EM_TC, bullets, divider, heading, para, send_rich, table
from services.economy import EconomyError, EconomyService
import random

router = Router(name='start')

PM_ONLY_JOKES = [
    "Эй, шалунишка! Такие вещи мы делаем только один на один в ЛС.",
    "При всех?! Ну ты и извращенец... Жду в личке.",
    "Снимай штаны и пошли в ЛС, тут люди смотрят!",
    "Ого, какой смелый! Но давай-ка эти шалости оставим для привата.",
    "При людях стесняюсь... Пошли в личные сообщения, покажу кое-что интересное.",
    "Фу, как некультурно! Такие интимные дела решаются только с глазу на глаз.",
    "Хочешь это? Тогда ныряй ко мне в ЛС, там можно всё.",
    "Только после того, как угостишь меня кофе... в личке.",
    "А губа не дура! Но здесь слишком много свидетелей, го в ЛС.",
    "Мальчик, ты перепутал чат. За интимом — в мои личные сообщения.",
    "Ой, ну ты чего при всех-то начинаешь? Пошли уединимся.",
    "Покажи мне свои... намерения в ЛС, и тогда поговорим.",
    "Эту функцию я открываю только тем, кто не боится остаться со мной наедине.",
    "Любишь на публику? А я люблю в ЛС. Жду.",
    "Если хочешь по-взрослому, переходи в приват.",
    "Слишком много глаз! Давай сбежим от них в личные сообщения.",
    "Ух, горячо! Но давай без зрителей, пиши в ЛС.",    
    "Ты мне нравишься, но такие вещи я делаю только тет-а-тет.",
    "Доставай... свой телефон и пиши мне в личку!",
    "Здесь тебе не OnlyFans! Все приватные фишки только в ЛС."
]

@router.message(
    F.text.lower().in_({'магазин', 'мои бонусы', 'мои задания', 'донат', 'пополнить', 'donate', '/пополнить', '/donate'}) &
    F.chat.type.in_({'group', 'supergroup'})
)
async def pm_only_jokes_handler(message: Message) -> None:
    bot_me = await message.bot.get_me()
    btns = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Перейти в ЛС', url=f't.me/{bot_me.username}?start')]
    ])
    await message.reply(random.choice(PM_ONLY_JOKES), reply_markup=btns)

@router.message(CommandStart())
async def start(message: Message, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    existing = await economy.profile(message.from_user.id)
    await economy.ensure_user(message.from_user, is_admin=message.from_user.id in settings.admin_ids)
    greeting = 'создан' if existing is None else 'обновлён'
    if message.chat.type == 'private':
        await message.answer(f'<b>Профиль {greeting}.</b> Выбери действие:', reply_markup=main_menu())
    else:
        await message.reply(f'<b>Профиль {greeting}.</b>', reply_markup=ReplyKeyboardRemove())

@router.message(Command('help'))
@router.message(F.text.lower() == 'хелп')
async def help_command(message: Message) -> None:
    blocks = [heading('Помощь и команды Taur Bot'), para('Бот для управления экономикой, рулетками, заданиями и лотереями. Команды можно писать без слеша (/).'), heading('Основное меню (кнопки)'), bullets(['<b>Профиль</b> — Твоя статистика, статус и баланс валют.', '<b>Магазин</b> — Покупка игровых бонусов за Taurons.', '<b>Мои бонусы</b> — Твой инвентарь (купленные бонусы, которые можно использовать).', '<b>Мои задания</b> — Список доступных миссий для заработка.', '<b>Донат / Пополнить</b> — Пополнить баланс TG (Taurgems).', '<b>Рулетка</b> — Испытать удачу за 5 T (шанс выиграть NFT, прем или валюту).', '<b>Лотерея</b> — Купить билеты на еженедельный розыгрыш NFT.']), heading('Текстовые команды'), bullets(['<b>/top</b> или <b>топ</b> — Рейтинг самых богатых игроков.', '<b>/tw</b> — Быстрый просмотр твоего баланса.', '<b>/муу @user сумма</b> — Перевести Taurons другому игроку.', '<b>/буи @user сумма</b> — Перевести Taurcoins другому игроку.', '<b>/convert</b> — Конвертировать TC в T по установленному курсу.', '<b>/info</b> — Узнать системный ID текущего чата.']), divider(), para('Переводы работают по ID, через @username или ответом (реплаем) на сообщение игрока.')]
    await send_rich(message, blocks)

@router.message(Command('ahelp'))
async def admin_help_command(message: Message, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    is_admin = await economy.is_admin(message.from_user.id, settings)
    if not is_admin:
        return
    blocks = [heading('Команды Администратора'), bullets(['<b>/apanel</b> — Панель управления (создание лотерей, настройки).', '<b>/tm @user сумма</b> — Выдать игроку Taurons (T).', '<b>/tc @user сумма</b> — Выдать игроку Taurcoins (TC).', '<b>/tm_take @user сумма</b> — Забрать у игрока Taurons (T).', '<b>/tc_take @user сумма</b> — Забрать у игрока Taurcoins (TC).', '<b>/admin @user</b> — Выдать или забрать права администратора.', '<b>/rass</b> — Начать рассылку всем пользователям бота.', '<b>/users</b> — Показать список всех зарегистрированных юзеров.', '<b>/user @user</b> — Посмотреть полную карточку конкретного игрока.', '<b>/reset_missions</b> — Сбросить все выполненные миссии.', '<b>/gpm</b> <i>(реплаем)</i> — Получить системный ID премиум-эмодзи.', '<b>/cancel</b> — Отменить любое текущее действие (например, рассылку).', '<b>выдать т/тс победителям/участникам N</b> — Массовая выдача награды (работает реплаем на сообщение с результатами игры).']), divider(), para('Выдача валюты работает по ID, через @username или ответом (реплаем) на сообщение игрока.')]
    await send_rich(message, blocks)

@router.message(Command('info'))
async def chat_info(message: Message) -> None:
    thread = f'\nThread ID: <code>{message.message_thread_id}</code>' if message.message_thread_id else ''
    await message.reply(f'Chat ID: <code>{message.chat.id}</code>{thread}')

@router.message(F.text == 'Профиль')
async def profile(message: Message, economy: EconomyService) -> None:
    assert message.from_user is not None
    await economy.ensure_user(message.from_user)
    row = await economy.profile(message.from_user.id)
    bonuses = await economy.db.fetch_all('SELECT prize_code, prize_name, count FROM user_prizes WHERE user_id = ? AND count > 0 ORDER BY prize_name', (message.from_user.id,))
    bonus_items = [f"{b['prize_name']} — {b['count']} шт." for b in bonuses]
    blocks = [heading('Ваш профиль'), table([], [['Пользователь', escape(row['full_name'] or '')], ['ID', str(row['telegram_id'])], ['Статус', 'Админ' if row['is_admin'] else 'Игрок']], bordered=False), divider(), table(['Валюта', 'Баланс'], [['Taurons', f"{row['taurons']} {EM_T} T"], ['Taurcoins', f"{row['taurcoins']} {EM_TC} TC"]]), divider(), heading('Инвентарь')]
    if bonus_items:
        blocks.append(bullets(bonus_items))
    else:
        blocks.append(para('пусто'))
    await send_rich(message, blocks)

@router.message(Command('tw', prefix='!/'))
async def balance(message: Message, economy: EconomyService) -> None:
    assert message.from_user is not None
    row = await economy.profile(message.from_user.id)
    if row is None:
        await message.reply('<b>Твой профиль не найден. Попробуй команду /start.</b>')
        return
    await message.reply(f"<b>Твой баланс:</b> {row['taurons']} {EM_T} T, {row['taurcoins']} {EM_TC} TC")

@router.message(Command('top'))
@router.message(Command('topt'))
@router.message(F.text.casefold() == 'топ')
@router.message(F.text.casefold() == 'топ тауронов')
async def taurons_top(message: Message, economy: EconomyService) -> None:
    rows = await economy.top_taurons(limit=None)
    total = await economy.total_taurons()
    if not rows:
        await send_rich(message, [heading('Топ по Тауронам'), para('Пока нет пользователей.')])
        return
    table_rows = []
    for i, row in enumerate(rows, 1):
        name = escape(row['full_name'] or row['username'] or str(row['telegram_id']))
        table_rows.append([str(i), name, str(int(row['taurons']))])
    await send_rich(message, [heading('Топ по Тауронам'), table(['#', 'Пользователь', 'Taurons'], table_rows), divider(), para(f'Всего тауронов: {total}')])

@router.message(Command('convert'))
async def convert_menu(message: Message, economy: EconomyService) -> None:
    assert message.from_user is not None
    row = await economy.profile(message.from_user.id)
    if row is None:
        await message.reply('Профиль не найден.')
        return
    rate = await economy.get_rate()
    possible = int(row['taurcoins']) // rate
    text = f"<b>Конвертация TC → T</b>\n\n<b>Баланс:</b> <i>{row['taurcoins']}</i> TC / <i>{row['taurons']}</i> T\n<b>Курс:</b> <i>{rate}</i> TC = 1 T\n<b>Можно конвертировать:</b> <i>{possible}</i> T"
    await message.reply(text, reply_markup=convert_keyboard() if possible > 0 else None)

@router.callback_query(F.data == 'convert')
async def convert_callback(callback: CallbackQuery, economy: EconomyService) -> None:
    try:
        rate, taurons, taurcoins = await economy.convert_one(callback.from_user.id)
    except EconomyError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    markup = convert_keyboard() if taurcoins >= rate else None
    if callback.message:
        await callback.message.edit_text(f'<b>Конвертировано!</b>\nСписано: <i>{rate}</i> TC → Зачислено: <i>1</i> T\n\nБаланс: <i>{taurcoins}</i> TC / <i>{taurons}</i> T\nКурс: <i>{rate}</i> TC = 1 T', reply_markup=markup)
    await callback.answer()