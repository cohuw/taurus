from __future__ import annotations
from html import escape
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from config import Settings
from keyboards import convert_keyboard, main_menu
from richfmt import EM_T, EM_TC, bullets, divider, heading, para, send_rich, table
from services.economy import EconomyError, EconomyService, rating_level_progress
import random

router = Router(name='start')

EM_FIRE = '<tg-emoji emoji-id="5427392916022667955">🔥</tg-emoji>'
EM_UP = '<tg-emoji emoji-id="5427395218125138820">⬆️</tg-emoji>'
EM_USER = '<tg-emoji emoji-id="5429240417679879990">👤</tg-emoji>'
EM_USER_ALT = '<tg-emoji emoji-id="5429334099506538571">👤</tg-emoji>'
EM_ID = '<tg-emoji emoji-id="5427171360134706350">🆔</tg-emoji>'
EM_TOP = '<tg-emoji emoji-id="5429288585738105301">🔝</tg-emoji>'
EM_STAR = '<tg-emoji emoji-id="5429259749327678061">⭐️</tg-emoji>'
EM_MONEY = '<tg-emoji emoji-id="5416114739925265635">💰</tg-emoji>'
EM_KISS = '<tg-emoji emoji-id="4967519884192777037">💋</tg-emoji>'


def rating_title(level: int) -> str:
    early_titles = {
        1: 'Искра',
        2: 'Первый рог',
        3: 'Медный бык',
        4: 'Бронзовый бык',
        5: 'Серебряный рог',
        6: 'Золотой рог',
        7: 'Жаркий игрок',
        8: 'Охотник за удачей',
        9: 'Хранитель казны',
        10: 'Алмазный бык',
        11: 'Ключник Taurus',
        12: 'Ловец оборота',
        13: 'Архитектор потока',
        14: 'Бархатный магнат',
        15: 'Коронованный рог',
        16: 'Повелитель резервов',
        17: 'Хранитель печати',
        18: 'Император счёта',
        19: 'Властелин ликвидности',
        20: 'Вершина Taurus',
        21: 'Ночной банкир',
        22: 'Мастер золотого хода',
        23: 'Господин процента',
        24: 'Князь капитала',
        25: 'Высший рог',
        26: 'Алхимик богатства',
        27: 'Гранд-казначей',
        28: 'Золотой стратег',
        29: 'Наследник Taurus',
        30: 'Титан оборота',
    }
    if level <= 30:
        return early_titles.get(max(level, 1), 'Искра')
    high_titles = (
        (10000, 'Создатель Taurus'),
        (5000, 'Бессмертный капитал'),
        (2500, 'Золотой архонт'),
        (1000, 'Верховный бык'),
        (500, 'Титан Taurus'),
        (250, 'Лорд ликвидности'),
        (100, 'Император капитала'),
        (75, 'Владыка рынка'),
        (50, 'Легенда казны'),
        (40, 'Великий держатель ключа'),
        (31, 'Старший магнат'),
    )
    for threshold, title in high_titles:
        if level >= threshold:
            return title
    return 'Титан оборота'


def rating_progress(progress: int, next_cost: int) -> str:
    filled = min(10, max(0, progress * 10 // max(1, next_cost)))
    return '▰' * filled + '▱' * (10 - filled)

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
    blocks = [heading('Помощь и команды Taur Bot'), para('Бот для управления экономикой, рулетками, заданиями и лотереями. Команды можно писать без слеша (/).'), heading('Основное меню (кнопки)'), bullets(['<b>Профиль</b> — Твоя статистика, статус, рейтинг и баланс валют.', '<b>Магазин</b> — Покупка игровых бонусов за Taurons.', '<b>Мои бонусы</b> — Твой инвентарь (купленные бонусы, которые можно использовать).', '<b>Мои задания</b> — Список доступных миссий для заработка.', '<b>Донат / Пополнить</b> — Пополнить баланс TG (Taurgems).', '<b>Рулетка</b> — Испытать удачу за 5 T (шанс выиграть NFT, прем или валюту).', '<b>Лотерея</b> — Купить билеты на еженедельный розыгрыш NFT.']), heading('Текстовые команды'), bullets(['<b>/top</b> или <b>топ</b> — Рейтинг самых богатых игроков.', '<b>/rating</b> или <b>рейтинг</b> — Таблица игроков по опыту за потраченные T и TC.', '<b>/tw</b> — Быстрый просмотр твоего баланса.', '<b>/муу @user сумма</b> — Перевести Taurons другому игроку.', '<b>/буи @user сумма</b> — Перевести Taurcoins другому игроку.', '<b>/convert</b> — Конвертировать TC в T по установленному курсу.', '<b>/info</b> — Узнать системный ID текущего чата.']), divider(), para('За каждый потраченный T или TC начисляется 1 XP. Чем выше уровень, тем больше XP требуется для следующего уровня.')]
    await send_rich(message, blocks)

@router.message(Command('ahelp'))
async def admin_help_command(message: Message, economy: EconomyService, settings: Settings) -> None:
    assert message.from_user is not None
    is_admin = await economy.is_admin(message.from_user.id, settings)
    if not is_admin:
        return
    blocks = [heading('Команды Администратора'), bullets(['<b>/apanel</b> — Панель управления (создание лотерей, настройки).', '<b>/tm @user сумма</b> — Выдать игроку Taurons (T).', '<b>/tc @user сумма</b> — Выдать игроку Taurcoins (TC).', '<b>/tm_take @user сумма</b> — Забрать у игрока Taurons (T).', '<b>/tc_take @user сумма</b> — Забрать у игрока Taurcoins (TC).', '<b>/admin @user</b> — Выдать или забрать права администратора.', '<b>/rass</b> — Начать рассылку всем пользователям бота.', '<b>/users</b> — Показать список всех зарегистрированных юзеров.', '<b>/user @user</b> — Посмотреть полную карточку конкретного игрока.', '<b>/reset_missions</b> — Сбросить все выполненные миссии.', '<b>/gpm</b> <i>(реплаем)</i> — Получить системный ID премиум-эмодзи.', '<b>/cancel</b> — Отменить любое текущее действие (например, рассылку).', '<b>выдать т/тс победителям/участникам N</b> — Массовая выдача награды (работает реплаем на сообщение с результатами игры).']), divider(), para('Выдача валюты работает по ID, через @username или ответом (реплаем) на сообщение игрока.')]
    blocks.insert(1, para('<b>/ratingstatic ID титул</b> — Выдать статичный титул без изменения места в топе.\n<b>/ratingstatic_remove ID</b> — Снять статичный титул.\n<b>/ratingban ID</b> / <b>/ratingunban ID</b> — Скрыть или вернуть игрока в топе.'))
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
    xp, level, progress, next_cost, position = await economy.rating_stats(message.from_user.id)
    progress_percent = progress * 100 // max(1, next_cost)
    rating_card = (
        f'<b>{EM_KISS} Уровень {level} · {EM_STAR} {rating_title(level)}</b>\n'
        f'<code>{rating_progress(progress, next_cost)}</code>  <b>{progress_percent}%</b> {EM_UP}\n'
        f'{EM_FIRE} <b>{xp} XP</b>  ·  {EM_TOP} место <b>#{position}</b>\n'
        f'{EM_UP} До следующего уровня: <b>{next_cost - progress} XP</b>'
    )
    blocks = [
        heading('Ваш профиль'),
        para(f"{EM_USER} <b>{escape(row['full_name'] or 'Игрок')}</b>\n{EM_ID} <code>{row['telegram_id']}</code>\n{EM_USER_ALT} Статус: <b>{'Админ' if row['is_admin'] else 'Игрок'}</b>"),
        divider(),
        heading(f'{EM_FIRE} Твой рейтинг'),
        para(rating_card),
        divider(),
        heading(f'{EM_MONEY} Баланс'),
        bullets([f"{EM_T} <b>{row['taurons']}</b> T", f"{EM_TC} <b>{row['taurcoins']}</b> TC"]),
        divider(),
        heading('Инвентарь'),
    ]
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

@router.message(Command('rating'))
@router.message(F.text.casefold() == 'рейтинг')
async def rating_top(message: Message, economy: EconomyService, settings: Settings) -> None:
    rows = await economy.top_rating(limit=None)
    static_titles = {}
    if settings.owner_id and settings.owner_id not in settings.rating_static_disabled_ids:
        static_titles[settings.owner_id] = 'OWNER'
    if settings.coder_id and settings.coder_id not in settings.rating_static_disabled_ids:
        static_titles.setdefault(settings.coder_id, 'CODER')
    static_titles.update(settings.rating_static_titles)
    static_titles = {
        user_id: title
        for user_id, title in static_titles.items()
        if user_id not in settings.rating_banned_ids
    }
    rows = [row for row in rows if int(row['telegram_id']) not in settings.rating_banned_ids]
    known_ids = {int(row['telegram_id']) for row in rows}
    for user_id in static_titles:
        if user_id in known_ids:
            continue
        profile = await economy.profile(user_id)
        display_name = (profile['full_name'] or (f"@{profile['username']}" if profile['username'] else str(user_id))) if profile else str(user_id)
        real_experience = await economy.experience(user_id)
        rows.append({
            'telegram_id': user_id,
            'full_name': display_name,
            'username': None,
            'experience': real_experience,
        })
    rows.sort(key=lambda row: (-int(row['experience']), str(row['full_name'] or ''), int(row['telegram_id'])))
    rows = rows[:20]
    if not rows:
        await send_rich(message, [heading('Рейтинг игроков'), para('Пока нет пользователей.')])
        return
    medals = ('🥇', '🥈', '🥉')
    blocks = [
        heading(f'{EM_TOP} Рейтинг игроков'),
    ]
    for place, row in enumerate(rows, 1):
        name = escape(row['full_name'] or row['username'] or str(row['telegram_id']))
        xp = int(row['experience'])
        level, _, _ = rating_level_progress(xp)
        marker = medals[place - 1] if place <= len(medals) else f'#{place}'
        static_title = static_titles.get(int(row['telegram_id']))
        title = escape(static_title) if static_title else rating_title(level)
        stats = f'уровень <b>{level}</b> · <code>{xp} XP</code>'
        blocks.append(para(f'{marker} {EM_USER_ALT} <b>{name}</b>\n{EM_UP} <i>{title}</i> · {stats}'))
        if place != len(rows):
            blocks.append(divider())
    await send_rich(message, blocks)


async def _change_rating_ban(message: Message, economy: EconomyService, settings: Settings, *, ban: bool) -> None:
    if not message.from_user or not await economy.is_admin(message.from_user.id, settings):
        await message.answer('Нет доступа.')
        return
    parts = (message.text or '').split()
    if len(parts) != 2 or not parts[1].lstrip('-').isdigit():
        await message.answer('Формат: /ratingban ID')
        return
    user_id = int(parts[1])
    if user_id in {settings.owner_id, settings.coder_id}:
        await message.answer('OWNER и CODER всегда остаются в рейтинге.')
        return
    if ban:
        settings.rating_banned_ids.add(user_id)
        settings.save_rating_settings()
        await message.answer(f'Пользователь <code>{user_id}</code> скрыт из рейтинга.')
    else:
        settings.rating_banned_ids.discard(user_id)
        settings.save_rating_settings()
        await message.answer(f'Пользователь <code>{user_id}</code> возвращён в рейтинг.')


@router.message(Command('ratingban'))
async def rating_ban(message: Message, economy: EconomyService, settings: Settings) -> None:
    await _change_rating_ban(message, economy, settings, ban=True)


@router.message(Command('ratingunban'))
async def rating_unban(message: Message, economy: EconomyService, settings: Settings) -> None:
    await _change_rating_ban(message, economy, settings, ban=False)


@router.message(Command('ratingstatic'))
async def rating_static_grant(message: Message, economy: EconomyService, settings: Settings) -> None:
    if not message.from_user or not await economy.is_admin(message.from_user.id, settings):
        await message.answer('Нет доступа.')
        return
    parts = (message.text or '').split(maxsplit=2)
    if len(parts) != 3 or not parts[1].lstrip('-').isdigit() or not parts[2].strip():
        await message.answer('Формат: /ratingstatic ID титул')
        return
    user_id = int(parts[1])
    title = parts[2].strip()[:80]
    settings.rating_static_titles[user_id] = title
    settings.rating_static_disabled_ids.discard(user_id)
    settings.rating_banned_ids.discard(user_id)
    settings.save_rating_settings()
    await message.answer(f'Статичный титул выдан пользователю <code>{user_id}</code>: <b>{escape(title)}</b>.')


@router.message(Command('ratingstatic_remove'))
async def rating_static_remove(message: Message, economy: EconomyService, settings: Settings) -> None:
    if not message.from_user or not await economy.is_admin(message.from_user.id, settings):
        await message.answer('Нет доступа.')
        return
    parts = (message.text or '').split()
    if len(parts) != 2 or not parts[1].lstrip('-').isdigit():
        await message.answer('Формат: /ratingstatic_remove ID')
        return
    user_id = int(parts[1])
    removed = settings.rating_static_titles.pop(user_id, None)
    default_static = user_id in {settings.owner_id, settings.coder_id}
    if default_static:
        settings.rating_static_disabled_ids.add(user_id)
    if removed is not None or default_static:
        settings.save_rating_settings()
    await message.answer('Статичный титул снят.' if removed or default_static else 'Статичный титул не найден.')

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
