from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable
import aiosqlite

class Database:

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> aiosqlite.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self.path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute('PRAGMA foreign_keys = ON')
            await self._conn.execute('PRAGMA journal_mode = WAL')
        return self._conn

    async def migrate(self) -> None:
        conn = await self.connect()
        await self._migrate_legacy_users_schema(conn)
        
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL DEFAULT '',
                username TEXT,
                taurons INTEGER NOT NULL DEFAULT 0,
                taurcoins INTEGER NOT NULL DEFAULT 0,
                taurgems INTEGER NOT NULL DEFAULT 0,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                silent_mode INTEGER NOT NULL DEFAULT 0,
                banned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                unban_at TEXT,
                reason TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS user_prizes (
                user_id INTEGER NOT NULL,
                prize_code TEXT NOT NULL,
                prize_name TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, prize_code),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                photo_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS money_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                is_claimed INTEGER NOT NULL DEFAULT 0,
                claimed_by INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES users(telegram_id),
                FOREIGN KEY (claimed_by) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS lottery_draws (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nft_link TEXT NOT NULL,
                max_participants INTEGER NOT NULL DEFAULT 0,
                max_tickets_per_user INTEGER NOT NULL DEFAULT 0,
                min_tickets INTEGER NOT NULL DEFAULT 0,
                end_time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS lottery_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                draw_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                FOREIGN KEY (draw_id) REFERENCES lottery_draws(id)
            );

            CREATE TABLE IF NOT EXISTS balance_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                currency TEXT NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS parametrs (
                name TEXT PRIMARY KEY,
                value REAL NOT NULL
            );

            INSERT OR IGNORE INTO parametrs (name, value) VALUES ('convert_rate', 10);
            INSERT OR IGNORE INTO parametrs (name, value) VALUES ('tg_price_rub', 170);

            CREATE TABLE IF NOT EXISTS user_missions (
                user_id INTEGER NOT NULL,
                mission_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                report_data TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, mission_id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS shop_bonus_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS broadcast_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS roulette_spins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                spin_number INTEGER NOT NULL DEFAULT 0,
                prize_code TEXT NOT NULL DEFAULT '',
                prize_name TEXT NOT NULL DEFAULT '',
                guaranteed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE INDEX IF NOT EXISTS idx_user_prizes_user ON user_prizes(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_missions_status ON user_missions(status);
            CREATE INDEX IF NOT EXISTS idx_roulette_spins_user ON roulette_spins(user_id);
        """)

        try:
            await conn.execute('ALTER TABLE roulette_spins ADD COLUMN spin_number INTEGER NOT NULL DEFAULT 0')
        except aiosqlite.OperationalError as exc:
            if 'duplicate column name' not in str(exc).lower():
                raise
        await conn.execute('UPDATE roulette_spins SET spin_number = id WHERE spin_number = 0')
        try:
            await conn.execute('ALTER TABLE users ADD COLUMN taurgems INTEGER NOT NULL DEFAULT 0')
        except aiosqlite.OperationalError as exc:
            if 'duplicate column name' not in str(exc).lower():
                raise
        try:
            await conn.execute('ALTER TABLE lottery_tickets ADD COLUMN draw_id INTEGER NOT NULL DEFAULT 0')
        except aiosqlite.OperationalError as exc:
            if 'duplicate column name' not in str(exc).lower() and 'no such table' not in str(exc).lower():
                raise
        try:
            await conn.execute('ALTER TABLE lottery_draws ADD COLUMN min_tickets INTEGER NOT NULL DEFAULT 0')
        except aiosqlite.OperationalError as exc:
            if 'duplicate column name' not in str(exc).lower() and 'no such table' not in str(exc).lower():
                raise
        await conn.commit()

    async def _migrate_legacy_users_schema(self, conn: aiosqlite.Connection) -> None:
        columns = await self._table_columns(conn, 'users')
        if not columns or 'telegram_id' in columns or 'user_id' not in columns:
            return
        await conn.execute('PRAGMA foreign_keys = OFF')
        await conn.execute('ALTER TABLE users RENAME TO users_legacy')
        await conn.executescript("\n            CREATE TABLE users (\n                telegram_id INTEGER PRIMARY KEY,\n                full_name TEXT NOT NULL DEFAULT '',\n                username TEXT,\n                taurons INTEGER NOT NULL DEFAULT 0,\n                taurcoins INTEGER NOT NULL DEFAULT 0,\n                taurgems INTEGER NOT NULL DEFAULT 0,\n                is_admin INTEGER NOT NULL DEFAULT 0,\n                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n            );\n            ")
        await conn.execute("\n            INSERT INTO users (telegram_id, full_name, username, taurons, taurcoins, is_admin)\n            SELECT\n                user_id,\n                COALESCE(first_name, ''),\n                username,\n                COALESCE(taurons, 0),\n                COALESCE(taurcoins, 0),\n                COALESCE(is_admin, 0)\n            FROM users_legacy\n            ")
        await conn.execute('DROP TABLE users_legacy')
        await conn.execute('PRAGMA foreign_keys = ON')
        await conn.commit()

    @staticmethod
    async def _table_columns(conn: aiosqlite.Connection, table: str) -> set[str]:
        cursor = await conn.execute(f'PRAGMA table_info("{table}")')
        rows = await cursor.fetchall()
        return {str(row[1]) for row in rows}

    async def execute(self, sql: str, params: Iterable[Any]=()) -> None:
        conn = await self.connect()
        await conn.execute(sql, tuple(params))
        await conn.commit()

    async def fetch_one(self, sql: str, params: Iterable[Any]=()) -> aiosqlite.Row | None:
        conn = await self.connect()
        cursor = await conn.execute(sql, tuple(params))
        return await cursor.fetchone()

    async def fetch_all(self, sql: str, params: Iterable[Any]=()) -> list[aiosqlite.Row]:
        conn = await self.connect()
        cursor = await conn.execute(sql, tuple(params))
        return await cursor.fetchall()

    async def fetch_val(self, sql: str, params: Iterable[Any]=()) -> Any:
        row = await self.fetch_one(sql, params)
        if row is None:
            return None
        return row[0]

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None