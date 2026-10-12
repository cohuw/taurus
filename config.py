from __future__ import annotations
import os
from pathlib import Path

def load_env():
    env_path = Path('.env')
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line and (not line.strip().startswith('#')):
                    k, v = line.strip().split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('\'"')
load_env()

class Settings:

    def __init__(self) -> None:
        self.bot_token: str = os.environ.get('TOKEN', '')
        self.cryptobot_token: str | None = os.environ.get('CRYPTOBOT_TOKEN')
        self.database_path: Path = Path(os.environ.get('DATABASE_PATH', 'data/taurus_mafia.db'))
        self.owner_id: int = int(os.environ.get('OWNER_ID', '0'))
        self.coder_id: int | None = int(os.environ['CODER_ID']) if os.environ.get('CODER_ID') else None
        self.main_chat_id: int | None = int(os.environ['MAIN_CHAT_ID']) if os.environ.get('MAIN_CHAT_ID') else None
        self.log_chat_id: int | None = int(os.environ['LOG_CHAT_ID']) if os.environ.get('LOG_CHAT_ID') else None
        self.admin_log_thread_id: int | None = int(os.environ['ADMIN_LOG_THREAD_ID']) if os.environ.get('ADMIN_LOG_THREAD_ID') else None
        self.mission_log_thread_id: int | None = int(os.environ['MISSION_LOG_THREAD_ID']) if os.environ.get('MISSION_LOG_THREAD_ID') else None
        self.player_log_thread_id: int | None = int(os.environ['PLAYER_LOG_THREAD_ID']) if os.environ.get('PLAYER_LOG_THREAD_ID') else None
        self.roulette_log_thread_id: int | None = int(os.environ['ROULETTE_LOG_THREAD_ID']) if os.environ.get('ROULETTE_LOG_THREAD_ID') else None
        self.bonus_log_thread_id: int | None = int(os.environ['BONUS_LOG_THREAD_ID']) if os.environ.get('BONUS_LOG_THREAD_ID') else None

    @property
    def admin_ids(self) -> set[int]:
        val = os.environ.get('ADMIN_IDS', '')
        ids = {int(x.strip()) for x in val.split(',') if x.strip()}
        ids.add(self.owner_id)
        return ids

    @property
    def token_is_placeholder(self) -> bool:
        token = (self.bot_token or '').strip()
        return not token or token == 'PUT_TELEGRAM_BOT_TOKEN_HERE'

_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings