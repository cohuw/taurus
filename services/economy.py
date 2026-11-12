from __future__ import annotations
import math
from aiogram.types import User
from db import Database

class EconomyError(Exception):
    pass


XP_PER_LEVEL = 100


def rating_level_progress(xp: int) -> tuple[int, int, int]:
    """Return level, XP inside it, and XP cost of the next level."""
    xp = max(0, int(xp))
    level = max(1, int((1 + math.sqrt(1 + 8 * xp / XP_PER_LEVEL)) / 2))
    while XP_PER_LEVEL * level * (level - 1) // 2 > xp:
        level -= 1
    while XP_PER_LEVEL * level * (level + 1) // 2 <= xp:
        level += 1
    level_start = XP_PER_LEVEL * level * (level - 1) // 2
    return level, xp - level_start, XP_PER_LEVEL * level

class EconomyService:

    def __init__(self, db: Database) -> None:
        self.db = db
        self.ton_rub_rate = 110.0

    async def get_tg_price_rub(self) -> int:
        val = await self.db.fetch_val("SELECT value FROM parametrs WHERE name = 'tg_price_rub'")
        return int(val) if val else 170

    async def set_tg_price_rub(self, price: int) -> None:
        await self.db.execute("UPDATE parametrs SET value = ? WHERE name = 'tg_price_rub'", (price,))

    async def ensure_user(self, user: User, *, is_admin: bool=False) -> None:
        await self.db.execute('\n            INSERT INTO users (telegram_id, full_name, username, is_admin)\n            VALUES (?, ?, ?, ?)\n            ON CONFLICT(telegram_id) DO UPDATE SET\n                full_name = excluded.full_name,\n                username = excluded.username,\n                is_admin = MAX(users.is_admin, excluded.is_admin),\n                updated_at = CURRENT_TIMESTAMP\n            ', (user.id, user.full_name, user.username, int(is_admin)))

    async def profile(self, user_id: int):
        return await self.db.fetch_one('SELECT * FROM users WHERE telegram_id = ?', (user_id,))

    async def find_user(self, identifier: str):
        ident = identifier.strip()
        if ident.startswith('@'):
            return await self.db.fetch_one('SELECT * FROM users WHERE lower(username) = lower(?)', (ident[1:],))
        if ident.isdigit() or (ident.startswith('-') and ident[1:].isdigit()):
            return await self.profile(int(ident))
        return None

    async def all_users(self, *, page: int | None=None, per_page: int=100):
        if page is None:
            return await self.db.fetch_all('SELECT * FROM users ORDER BY created_at DESC')
        offset = max(page - 1, 0) * per_page
        return await self.db.fetch_all('SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?', (per_page, offset))

    async def user_count(self) -> int:
        return int(await self.db.fetch_val('SELECT COUNT(*) FROM users') or 0)

    async def top_taurons(self, limit: int | None=10):
        sql = '\n            SELECT telegram_id, full_name, username, taurons\n            FROM users\n            WHERE taurons > 0\n            ORDER BY taurons DESC, full_name COLLATE NOCASE ASC, telegram_id ASC\n        '
        params: tuple[int, ...] = ()
        if limit is not None:
            sql += ' LIMIT ?'
            params = (limit,)
        return await self.db.fetch_all(sql, params)

    async def total_taurons(self) -> int:
        return int(await self.db.fetch_val('SELECT COALESCE(SUM(taurons), 0) FROM users') or 0)

    async def experience(self, user_id: int) -> int:
        """Return XP earned from spending T/TC, without adding DB columns."""
        value = await self.db.fetch_val('''
            SELECT COALESCE(SUM(-amount), 0)
            FROM balance_transactions
            WHERE user_id = ?
              AND currency IN ('T', 'TC')
              AND amount < 0
              AND reason NOT LIKE 'admin_take:%'
              AND reason NOT LIKE 'transfer_to:%'
        ''', (user_id,))
        return max(0, int(value or 0))

    async def rating_stats(self, user_id: int) -> tuple[int, int, int, int, int]:
        xp = await self.experience(user_id)
        level, progress, next_cost = rating_level_progress(xp)
        position = int(await self.db.fetch_val('''
            SELECT COUNT(*) + 1
            FROM users u
            WHERE (
                SELECT COALESCE(SUM(-bt.amount), 0)
                FROM balance_transactions bt
                WHERE bt.user_id = u.telegram_id
                  AND bt.currency IN ('T', 'TC')
                  AND bt.amount < 0
                  AND bt.reason NOT LIKE 'admin_take:%'
                  AND bt.reason NOT LIKE 'transfer_to:%'
            ) > ?
        ''', (xp,)) or 1)
        return xp, level, progress, next_cost, position

    async def top_rating(self, limit: int | None=20):
        sql = '''
            SELECT u.telegram_id, u.full_name, u.username,
                   COALESCE(SUM(CASE WHEN bt.currency IN ('T', 'TC')
                                      AND bt.amount < 0
                                      AND bt.reason NOT LIKE 'admin_take:%'
                                      AND bt.reason NOT LIKE 'transfer_to:%'
                                     THEN -bt.amount ELSE 0 END), 0) AS experience
            FROM users u
            LEFT JOIN balance_transactions bt ON bt.user_id = u.telegram_id
            GROUP BY u.telegram_id
            ORDER BY experience DESC, u.full_name COLLATE NOCASE ASC, u.telegram_id ASC
        '''
        params: tuple[int, ...] = ()
        if limit is not None:
            sql += ' LIMIT ?'
            params = (limit,)
        return await self.db.fetch_all(sql, params)

    async def add_taurons(self, user_id: int, amount: int, reason: str) -> None:
        await self.change_balance(user_id, 'T', amount, reason)

    async def add_taurcoins(self, user_id: int, amount: int, reason: str) -> None:
        await self.change_balance(user_id, 'TC', amount, reason)

    async def add_taurgems(self, user_id: int, amount: int, reason: str) -> None:
        await self.change_balance(user_id, 'TG', amount, reason)

    async def change_balance(self, user_id: int, currency: str, amount: int, reason: str) -> None:
        column = {'T': 'taurons', 'TC': 'taurcoins', 'TG': 'taurgems'}.get(currency)
        if not column:
            raise EconomyError('Неизвестная валюта')
        row = await self.profile(user_id)
        if row is None:
            raise EconomyError('Пользователь не найден в базе. Он должен нажать /start.')
        await self.db.execute(f'UPDATE users SET {column} = {column} + ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?', (amount, user_id))
        await self.db.execute('INSERT INTO balance_transactions (user_id, currency, amount, reason) VALUES (?, ?, ?, ?)', (user_id, currency, amount, reason))

    async def transfer(self, sender_id: int, receiver_id: int, currency: str, amount: int) -> None:
        if amount <= 0:
            raise EconomyError('Количество должно быть положительным.')
        if sender_id == receiver_id:
            raise EconomyError('Самому себе передавать нельзя.')
        sender = await self.profile(sender_id)
        receiver = await self.profile(receiver_id)
        if sender is None:
            raise EconomyError('Профиль отправителя не найден. Нажмите /start.')
        if receiver is None:
            raise EconomyError('Получатель не найден в системе.')
        column = {'T': 'taurons', 'TC': 'taurcoins', 'TG': 'taurgems'}.get(currency)
        if not column:
            raise EconomyError('Неизвестная валюта для перевода.')
        if int(sender[column]) < amount:
            raise EconomyError(f'Недостаточно {currency}.')
        await self.change_balance(sender_id, currency, -amount, f'transfer_to:{receiver_id}')
        await self.change_balance(receiver_id, currency, amount, f'transfer_from:{sender_id}')

    async def get_rate(self) -> int:
        value = await self.db.fetch_val("SELECT value FROM parametrs WHERE name = 'convert_rate'")
        return int(value or 10)

    async def set_rate(self, rate: int) -> None:
        if rate <= 0:
            raise EconomyError('Курс должен быть положительным.')
        await self.db.execute("INSERT INTO parametrs (name, value) VALUES ('convert_rate', ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value", (rate,))

    async def convert_one(self, user_id: int) -> tuple[int, int, int]:
        row = await self.profile(user_id)
        if row is None:
            raise EconomyError('Профиль не найден.')
        rate = await self.get_rate()
        if int(row['taurcoins']) < rate:
            raise EconomyError(f'Недостаточно Taurcoins. Нужно минимум {rate} TC.')
        await self.change_balance(user_id, 'TC', -rate, 'convert_to_t')
        await self.change_balance(user_id, 'T', 1, 'convert_from_tc')
        updated = await self.profile(user_id)
        return (rate, int(updated['taurons']), int(updated['taurcoins']))

    async def set_admin(self, user_id: int, value: bool) -> None:
        row = await self.profile(user_id)
        if row is None:
            raise EconomyError('Пользователь не найден в базе.')
        await self.db.execute('UPDATE users SET is_admin = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?', (int(value), user_id))

    async def is_admin(self, user_id: int, settings=None) -> bool:
        if settings and user_id in settings.admin_ids:
            return True
        row = await self.profile(user_id)
        return bool(row and row['is_admin'])

    async def grant_prize(self, user_id: int, prize_code: str, prize_name: str, count: int=1) -> None:
        await self.db.execute('\n            INSERT INTO user_prizes (user_id, prize_code, prize_name, count, updated_at)\n            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)\n            ON CONFLICT(user_id, prize_code) DO UPDATE SET\n                count = count + excluded.count,\n                prize_name = excluded.prize_name,\n                updated_at = CURRENT_TIMESTAMP\n            ', (user_id, prize_code, prize_name, count))

    async def use_prize(self, user_id: int, prize_code: str) -> None:
        row = await self.db.fetch_one('SELECT count FROM user_prizes WHERE user_id = ? AND prize_code = ?', (user_id, prize_code))
        if row is None or int(row['count']) <= 0:
            raise EconomyError('Бонус не найден в инвентаре.')
        await self.db.execute('UPDATE user_prizes SET count = count - 1, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND prize_code = ?', (user_id, prize_code))
