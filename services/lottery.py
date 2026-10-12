from __future__ import annotations
import random
from datetime import datetime
from typing import Any
from db import Database
from services.economy import EconomyError, EconomyService

class LotteryService:
    TICKET_PRICE = 1
    TICKET_CURRENCY = 'TG'

    def __init__(self, db: Database) -> None:
        self.db = db
        self.rng = random.SystemRandom()

    async def create_draw(self, nft_link: str, max_parts: int, max_tickets: int, min_tickets: int, end_time: str) -> int:
        await self.db.execute("\n            INSERT INTO lottery_draws (nft_link, max_participants, max_tickets_per_user, min_tickets, end_time, status)\n            VALUES (?, ?, ?, ?, ?, 'active')\n            ", (nft_link, max_parts, max_tickets, min_tickets, end_time))
        row = await self.db.fetch_one('SELECT last_insert_rowid()')
        return int(row[0]) if row else 0

    async def get_active_draws(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch_all("SELECT * FROM lottery_draws WHERE status = 'active' ORDER BY id ASC")
        return [dict(r) for r in rows]

    async def get_draw(self, draw_id: int) -> dict[str, Any] | None:
        row = await self.db.fetch_one('SELECT * FROM lottery_draws WHERE id = ?', (draw_id,))
        return dict(row) if row else None

    async def get_tickets_for_draw(self, draw_id: int) -> list[dict[str, Any]]:
        rows = await self.db.fetch_all('SELECT * FROM lottery_tickets WHERE draw_id = ?', (draw_id,))
        return [dict(r) for r in rows]

    async def get_user_tickets_count(self, user_id: int, draw_id: int) -> int:
        val = await self.db.fetch_val('SELECT COUNT(*) FROM lottery_tickets WHERE draw_id = ? AND user_id = ?', (draw_id, user_id))
        return int(val or 0)

    async def get_total_tickets_count(self, draw_id: int) -> int:
        val = await self.db.fetch_val('SELECT COUNT(*) FROM lottery_tickets WHERE draw_id = ?', (draw_id,))
        return int(val or 0)

    async def get_unique_participants_count(self, draw_id: int) -> int:
        val = await self.db.fetch_val('SELECT COUNT(DISTINCT user_id) FROM lottery_tickets WHERE draw_id = ?', (draw_id,))
        return int(val or 0)

    async def get_participants_summary(self, draw_id: int) -> list[dict]:
        rows = await self.db.fetch_all(
            'SELECT user_id, COUNT(*) as tickets FROM lottery_tickets WHERE draw_id = ? GROUP BY user_id ORDER BY tickets DESC',
            (draw_id,)
        )
        return [dict(r) for r in rows]

    async def buy_ticket(self, user_id: int, draw_id: int, economy: EconomyService) -> None:
        draw = await self.get_draw(draw_id)
        if not draw:
            raise EconomyError('Розыгрыш не найден.')
        if draw['status'] != 'active':
            raise EconomyError('Розыгрыш уже завершен.')
        try:
            end_dt = datetime.strptime(draw['end_time'], '%d.%m.%Y %H:%M')
            if datetime.now() >= end_dt:
                raise EconomyError('Время на покупку билетов в эту лотерею истекло.')
        except ValueError:
            pass
        max_t = int(draw['max_tickets_per_user'])
        if max_t > 0:
            user_count = await self.get_user_tickets_count(user_id, draw_id)
            if user_count >= max_t:
                raise EconomyError(f'Вы достигли лимита билетов ({max_t}) для этого розыгрыша.')
        max_p = int(draw['max_participants'])
        if max_p > 0:
            user_count = await self.get_user_tickets_count(user_id, draw_id)
            if user_count == 0:
                total_p = await self.get_unique_participants_count(draw_id)
                if total_p >= max_p:
                    raise EconomyError(f'Достигнут лимит участников ({max_p}) для этого розыгрыша.')
        profile = await economy.profile(user_id)
        if profile is None:
            raise EconomyError('Профиль не найден. Нажмите /start.')
        if int(profile['taurgems']) < self.TICKET_PRICE:
            raise EconomyError(f'Недостаточно Taurgem (TG). Билет стоит {self.TICKET_PRICE} TG.')
        await economy.add_taurgems(user_id, -self.TICKET_PRICE, f'lottery_ticket_buy:{draw_id}')
        await self.db.execute('INSERT INTO lottery_tickets (user_id, draw_id) VALUES (?, ?)', (user_id, draw_id))

    async def check_and_draw_winners(self) -> list[dict[str, Any]]:
        now = datetime.now()
        draws = await self.get_active_draws()
        results = []
        for draw in draws:
            try:
                end_dt = datetime.strptime(draw['end_time'], '%d.%m.%Y %H:%M')
                if now >= end_dt:
                    total_tickets = await self.get_total_tickets_count(draw['id'])
                    min_tickets = int(draw.get('min_tickets', 0))
                    if min_tickets > 0 and total_tickets < min_tickets:
                        await self.db.execute("UPDATE lottery_draws SET status = 'pending_review' WHERE id = ?", (draw['id'],))
                        results.append({
                            'needs_review': True,
                            'draw_id': draw['id'],
                            'total_tickets': total_tickets,
                            'min_tickets': min_tickets
                        })
                    else:
                        res = await self.draw_winner(draw['id'])
                        results.append(res)
            except ValueError:
                pass
        return results

    async def draw_winner(self, draw_id: int) -> dict[str, Any]:
        draw = await self.get_draw(draw_id)
        if not draw:
            raise EconomyError('Розыгрыш не найден.')
        tickets = await self.get_tickets_for_draw(draw_id)
        winner_id = None
        winner_tickets = 0
        total = len(tickets)
        if tickets:
            winner_row = self.rng.choice(tickets)
            winner_id = winner_row['user_id']
            winner_tickets = sum((1 for t in tickets if t['user_id'] == winner_id))
        await self.db.execute("UPDATE lottery_draws SET status = 'completed' WHERE id = ?", (draw_id,))
        return {'draw_id': draw_id, 'nft_link': draw['nft_link'], 'user_id': winner_id, 'tickets_bought': winner_tickets, 'total_tickets': total}

    async def force_draw(self, draw_id: int) -> dict[str, Any]:
        return await self.draw_winner(draw_id)

    async def cancel_draw(self, draw_id: int, refund: bool, economy: EconomyService) -> None:
        draw = await self.get_draw(draw_id)
        if not draw:
            raise EconomyError('Розыгрыш не найден.')
        await self.db.execute("UPDATE lottery_draws SET status = 'cancelled' WHERE id = ?", (draw_id,))
        if refund:
            tickets = await self.get_tickets_for_draw(draw_id)
            for t in tickets:
                await economy.add_taurgems(t['user_id'], self.TICKET_PRICE, f'lottery_refund:{draw_id}')