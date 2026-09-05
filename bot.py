import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import LabeledPrice, PreCheckoutQuery, Message

TOKEN = "8134671011:AAGi4n7E9mvcPwEGAUdpIyZ1z9HVjwpIX-M"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("ppay"))
async def cmd_ppay(message: Message, command: CommandObject):
    args = command.args
    if not args or not args.isdigit():
        await message.reply("Использование: /ppay <сумма_в_звездах>")
        return

    amount = int(args)
    if amount <= 0:
        await message.reply("Сумма должна быть больше 0.")
        return

    try:
        # Отправляем счет на оплату
        await bot.send_invoice(
            chat_id=message.chat.id,
            title=f"Оплата {amount} Stars",
            description=f"Счет на {amount} Telegram Stars",
            payload=f"stars_payment_{amount}",
            provider_token="",  # Для Stars токен должен быть пустым
            currency="XTR",
            prices=[LabeledPrice(label=f"{amount} Stars", amount=amount)],
        )
    except Exception as e:
        await message.reply(f"Ошибка при отправке счета: {e}")

# Обработка pre_checkout_query (подтверждение готовности принять платеж)
@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    # Здесь можно добавить дополнительные проверки (наличие товара и т.д.)
    await pre_checkout_query.answer(ok=True)

# Обработка успешного платежа
@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    amount = message.successful_payment.total_amount
    currency = message.successful_payment.currency
    await message.answer(f"✅ Успешно! Оплата получена: {amount} {currency}.")

async def main():
    # Пропускаем накопившиеся апдейты
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
