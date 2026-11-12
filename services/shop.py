from __future__ import annotations
import re
from dataclasses import dataclass
from db import Database

@dataclass(frozen=True)
class BonusType:
    id: int
    code: str
    name: str
    description: str
    price: int

class ShopService:

    def __init__(self, db: Database) -> None:
        self.db = db

    async def list_bonus_types(self) -> list[BonusType]:
        rows = await self.db.fetch_all('SELECT id, code, name, description, price FROM shop_bonus_types ORDER BY id')
        return [self._row_to_bonus(row) for row in rows]

    async def get_bonus_type(self, bonus_id: int) -> BonusType | None:
        row = await self.db.fetch_one('SELECT id, code, name, description, price FROM shop_bonus_types WHERE id = ?', (bonus_id,))
        return self._row_to_bonus(row) if row else None

    async def create_bonus_type(self, name: str, description: str, price: int) -> BonusType:
        if price < 0:
            raise ValueError('Цена не может быть отрицательной')
        code_base = re.sub('[^a-zA-Z0-9_]+', '_', name.lower()).strip('_') or 'bonus'
        code = code_base
        suffix = 1
        while await self.db.fetch_val('SELECT 1 FROM shop_bonus_types WHERE code = ?', (code,)):
            suffix += 1
            code = f'{code_base}_{suffix}'
        await self.db.execute('INSERT INTO shop_bonus_types (code, name, description, price) VALUES (?, ?, ?, ?)', (code, name, description, price))
        new_id = int(await self.db.fetch_val('SELECT last_insert_rowid()'))
        bonus = await self.get_bonus_type(new_id)
        assert bonus is not None
        return bonus

    async def delete_bonus_type(self, bonus_id: int) -> bool:
        exists = await self.get_bonus_type(bonus_id)
        if exists is None:
            return False
        await self.db.execute('DELETE FROM shop_bonus_types WHERE id = ?', (bonus_id,))
        return True

    async def inventory_editor_items(self, user_id: int):
        return await self.db.fetch_all('''
            SELECT b.id AS shop_id, p.rowid AS inventory_id, b.name AS name,
                   COALESCE(p.count, 0) AS count
            FROM shop_bonus_types b
            LEFT JOIN user_prizes p ON p.user_id = ? AND p.prize_code = CAST(b.id AS TEXT)
            UNION ALL
            SELECT NULL, p.rowid, p.prize_name, p.count
            FROM user_prizes p
            WHERE p.user_id = ? AND p.count > 0
              AND NOT EXISTS (SELECT 1 FROM shop_bonus_types b WHERE p.prize_code = CAST(b.id AS TEXT))
            ORDER BY name
        ''', (user_id, user_id))

    async def edit_inventory(self, user_id: int, action: str, item_id: int) -> bool:
        conn = await self.db.connect()
        if action == 'give':
            cursor = await conn.execute('''
                INSERT INTO user_prizes (user_id, prize_code, prize_name, count)
                SELECT ?, CAST(id AS TEXT), name, 1 FROM shop_bonus_types
                WHERE id = ? AND EXISTS (SELECT 1 FROM users WHERE telegram_id = ?)
                ON CONFLICT(user_id, prize_code) DO UPDATE SET
                    count = user_prizes.count + 1,
                    prize_name = excluded.prize_name, updated_at = CURRENT_TIMESTAMP
            ''', (user_id, item_id, user_id))
        elif action in ('take', 'clear'):
            cursor = await conn.execute('''
                UPDATE user_prizes
                SET count = CASE WHEN ? = 'clear' THEN 0 ELSE count - 1 END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND rowid = ? AND count > 0
            ''', (action, user_id, item_id))
        else:
            raise ValueError('Неизвестное действие')
        changed = cursor.rowcount > 0
        await cursor.close()
        await conn.commit()
        return changed

    @staticmethod
    def _row_to_bonus(row) -> BonusType:
        return BonusType(id=int(row['id']), code=str(row['code']), name=str(row['name']), description=str(row['description']), price=int(row['price']))
