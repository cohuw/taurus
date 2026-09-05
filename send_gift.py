import asyncio
from aiogram import Bot
from aiogram.methods import SendGift

TOKEN = "8134671011:AAGi4n7E9mvcPwEGAUdpIyZ1z9HVjwpIX-M"

async def main():
    bot = Bot(token=TOKEN)
    try:
        # Пытаемся использовать метод send_gift напрямую, если он уже есть в этой версии aiogram
        if hasattr(bot, "send_gift"):
            result = await bot.send_gift(
                user_id=762049886,
                gift_id="5170233102089322756", # ID подарка "Мишка 🧸" (стоит 15 звезд)
                text="@Taurus_paybot ⩘⩗"
            )
        else:
            # Если метода нет, вызываем через raw request или базовый request aiogram
            # aiogram позволяет отправлять кастомные запросы, если метод еще не обернут
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{TOKEN}/sendGift"
                data = {
                    "user_id": 762049886,
                    "gift_id": "5170233102089322756",
                    "text": "@Taurus_paybot ⩘⩗"
                }
                async with session.post(url, json=data) as resp:
                    result = await resp.json()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
