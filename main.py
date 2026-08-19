from __future__ import annotations
import asyncio
import aiohttp
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import get_settings
from db import Database
from routers import admin, missions, roulette, shop, start, donate, lottery
from services.economy import EconomyService
from services.missions import MissionService
from services.roulette import RouletteService
from services.shop import ShopService
from services.donations import DonationService
from services.lottery import LotteryService
from services.cryptopay import CryptoPayService
from middlewares.access import AccessMiddleware

async def crypto_rate_loop(economy_service: EconomyService) -> None:
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=rub') as resp:
                    data = await resp.json()
                    if 'the-open-network' in data and 'rub' in data['the-open-network']:
                        economy_service.ton_rub_rate = float(data['the-open-network']['rub'])
        except Exception as e:
            logging.getLogger(__name__).error(f'crypto_rate_loop: {e}')
        await asyncio.sleep(900)

async def auto_draw_loop(bot: Bot, lottery_service: LotteryService, economy_service: EconomyService, settings: Settings) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            results = await lottery_service.check_and_draw_winners()
            for res in results:
                draw_id = res['draw_id']
                if res.get('needs_review'):
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    from aiogram.enums import ButtonStyle
                    if settings.owner_id:
                        btns = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text='Закончить', callback_data=f'lottery_force:{draw_id}', style=ButtonStyle.PRIMARY)],
                            [InlineKeyboardButton(text='Отменить (Вернуть ТГ)', callback_data=f'lottery_cancel_ref:{draw_id}', style=ButtonStyle.DANGER)],
                            [InlineKeyboardButton(text='Отменить (НЕ вернуть)', callback_data=f'lottery_cancel_noref:{draw_id}', style=ButtonStyle.DANGER)]
                        ])
                        await bot.send_message(settings.owner_id, f"Лотерея #{draw_id} завершилась, но не набрала минимум билетов (продано {res['total_tickets']} из {res['min_tickets']}). Выберите действие:", reply_markup=btns)
                    continue

                winner_id = res.get('user_id')
                if not winner_id:
                    continue
                winner_profile = await economy_service.profile(winner_id)
                winner_name = winner_profile['full_name'] if winner_profile else str(winner_id)
                try:
                    from richfmt import heading, para, send_rich_to
                    await send_rich_to(bot, winner_id, [heading('Поздравляем!'), para(f"Ты выиграл в лотерее #{draw_id}!\nТвой приз: <a href='{res['nft_link']}'>NFT</a>")])
                except Exception:
                    pass
        except Exception as e:
            logging.getLogger(__name__).error(f'auto_draw_loop: {e}')

async def create_dispatcher(settings=None) -> Dispatcher:
    settings = settings or get_settings()
    db = Database(settings.database_path)
    await db.migrate()
    shop_service = ShopService(db)
    economy_service = EconomyService(db)
    mission_service = MissionService(db)
    roulette_service = RouletteService(db)
    donation_service = DonationService(db)
    lottery_service = LotteryService(db)
    cryptopay_service = CryptoPayService(settings.cryptobot_token) if settings.cryptobot_token else None
    dp = Dispatcher(settings=settings, db=db, shop=shop_service, economy=economy_service, missions=mission_service, roulette=roulette_service, donations=donation_service, lottery=lottery_service, cryptopay=cryptopay_service)
    
    access_middleware = AccessMiddleware(db, settings)
    dp.message.middleware(access_middleware)
    dp.callback_query.middleware(access_middleware)
    dp['access'] = access_middleware
    
    dp.include_router(start.router)
    dp.include_router(shop.router)
    dp.include_router(roulette.router)
    dp.include_router(admin.router)
    dp.include_router(missions.router)
    dp.include_router(donate.router)
    dp.include_router(lottery.router)
    return dp

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        handlers=[
            logging.FileHandler('bot_debug.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    settings = get_settings()
    if settings.token_is_placeholder:
        raise RuntimeError('а токен')
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = await create_dispatcher(settings)
    crypto_task = asyncio.create_task(crypto_rate_loop(dp['economy']))
    draw_task = asyncio.create_task(auto_draw_loop(bot, dp['lottery'], dp['economy'], settings))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        crypto_task.cancel()
        draw_task.cancel()
        await dp['db'].close()
        await bot.session.close()

def run() -> None:
    asyncio.run(main())
if __name__ == '__main__':
    run()