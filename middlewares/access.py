import datetime
import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import Settings
from db import Database

class AccessMiddleware(BaseMiddleware):
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.cache: dict[int, dict] = {} 

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            
        if not user:
            return await handler(event, data)
            
        user_id = user.id
        
        if user_id == self.settings.owner_id:
            return await handler(event, data)
            
        now = time.time()
        cached = self.cache.get(user_id)
        
        if not cached or cached['expires'] < now:
            row = await self.db.fetch_one("SELECT silent_mode, unban_at FROM banned_users WHERE user_id = ?", (user_id,))
            
            in_chat = True
            if self.settings.main_chat_id:
                try:
                    bot = data['bot']
                    member = await bot.get_chat_member(self.settings.main_chat_id, user_id)
                    if member.status in ['left', 'kicked']:
                        in_chat = False
                except Exception:
                    in_chat = True
            
            cached = {
                'banned': row is not None,
                'silent': bool(row['silent_mode']) if row else False,
                'unban_at': row['unban_at'] if row else None,
                'in_chat': in_chat,
                'expires': now + 60 
            }
            self.cache[user_id] = cached
            
        if cached['banned'] and cached['unban_at']:
            try:
                unban_dt = datetime.datetime.fromisoformat(cached['unban_at'])
                if datetime.datetime.now() > unban_dt:
                    await self.db.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
                    cached['banned'] = False
                    cached['silent'] = False
            except Exception:
                pass 
                
        if cached['banned']:
            if not cached['silent']:
                if isinstance(event, Message):
                    try:
                        await event.answer("<b>Вы заблокированы в боте.</b>")
                    except Exception:
                        pass
                elif isinstance(event, CallbackQuery):
                    try:
                        await event.answer("Вы заблокированы в боте.", show_alert=True)
                    except Exception:
                        pass
            return
            
        if not cached['in_chat'] and user_id not in self.settings.admin_ids:
            msg_text = "<b>Для использования бота необходимо состоять в основном чате.</b>"
            if isinstance(event, Message):
                try:
                    await event.answer(msg_text)
                except Exception:
                    pass
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer("Необходимо состоять в основном чате.", show_alert=True)
                except Exception:
                    pass
            return
            
        return await handler(event, data)
        
    def invalidate(self, user_id: int):
        if user_id in self.cache:
            del self.cache[user_id]
