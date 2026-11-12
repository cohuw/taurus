from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile

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
        self.rating_settings_path: Path = Path(os.environ.get('RATING_SETTINGS_PATH', 'data/rating_settings.json'))
        self.rating_banned_ids: set[int] = set()
        self.rating_static_titles: dict[int, str] = {}
        self.rating_static_disabled_ids: set[int] = set()
        self._load_rating_settings()

    def _load_rating_settings(self) -> None:
        """Load rating controls without making a missing or invalid file fatal."""
        try:
            payload = json.loads(self.rating_settings_path.read_text(encoding='utf-8'))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return

        def ids(value: object) -> set[int]:
            if not isinstance(value, list):
                return set()
            result: set[int] = set()
            for item in value:
                try:
                    result.add(int(item))
                except (TypeError, ValueError):
                    continue
            return result

        self.rating_banned_ids = ids(payload.get('banned_ids'))
        self.rating_static_disabled_ids = ids(payload.get('static_disabled_ids'))
        raw_titles = payload.get('static_titles')
        if isinstance(raw_titles, dict):
            for user_id, title in raw_titles.items():
                if not isinstance(title, str) or not title.strip() or not str(user_id).lstrip('-').isdigit():
                    continue
                self.rating_static_titles[int(user_id)] = title.strip()[:80]

    def save_rating_settings(self) -> None:
        """Persist rating bans and titles atomically in a small JSON sidecar."""
        payload = {
            'banned_ids': sorted(self.rating_banned_ids),
            'static_titles': {str(user_id): title for user_id, title in sorted(self.rating_static_titles.items())},
            'static_disabled_ids': sorted(self.rating_static_disabled_ids),
        }
        self.rating_settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=self.rating_settings_path.parent,
                prefix=f'.{self.rating_settings_path.name}.', suffix='.tmp', delete=False,
            ) as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                temporary_path = Path(stream.name)
            temporary_path.replace(self.rating_settings_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

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
