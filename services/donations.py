from __future__ import annotations
from db import Database
from services.economy import EconomyError, EconomyService

class DonationService:

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create_payment_request(self, user_id: int, photo_id: str) -> int:
        await self.db.execute('INSERT INTO payment_requests (user_id, photo_id) VALUES (?, ?)', (user_id, photo_id))
        row = await self.db.fetch_one('SELECT last_insert_rowid()')
        return int(row[0])

    async def get_payment_request(self, request_id: int) -> dict | None:
        row = await self.db.fetch_one('SELECT * FROM payment_requests WHERE id = ?', (request_id,))
        if row is None:
            return None
        return dict(row)

    async def update_payment_request(self, request_id: int, status: str) -> None:
        await self.db.execute('UPDATE payment_requests SET status = ? WHERE id = ?', (status, request_id))

    async def create_money_check(self, admin_id: int, amount: int) -> int:
        if amount <= 0:
            raise EconomyError('Сумма чека должна быть положительной.')
        await self.db.execute('INSERT INTO money_checks (admin_id, amount) VALUES (?, ?)', (admin_id, amount))
        row = await self.db.fetch_one('SELECT last_insert_rowid()')
        return int(row[0])

    async def get_money_check(self, check_id: int) -> dict | None:
        row = await self.db.fetch_one('SELECT * FROM money_checks WHERE id = ?', (check_id,))
        if row is None:
            return None
        return dict(row)

    async def claim_money_check(self, check_id: int, user_id: int, economy: EconomyService) -> int:
        conn = await self.db.connect()
        cursor = await conn.execute('UPDATE money_checks SET is_claimed = 1, claimed_by = ? WHERE id = ? AND is_claimed = 0', (user_id, check_id))
        if cursor.rowcount == 0:
            check = await self.get_money_check(check_id)
            if not check:
                raise EconomyError('Чек не найден.')
            raise EconomyError('Этот чек уже был активирован.')
        await conn.commit()
        check = await self.get_money_check(check_id)
        amount = int(check['amount'])
        await economy.add_taurgems(user_id, amount, f'claimed_check:{check_id}')
        return amount