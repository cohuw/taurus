from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from cachetools import TTLCache

class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, limit_sec: float = 1.0):
        self.limit_sec = limit_sec
        self.cache = TTLCache(maxsize=10000, ttl=limit_sec)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            if user_id in self.cache:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("Не так быстро!", show_alert=False)
                    except Exception:
                        pass
                return None
                
            self.cache[user_id] = True
            
        return await handler(event, data)
