import aiohttp

class CryptoPayService:

    def __init__(self, token: str):
        self.token = token
        self.base_url = 'https://pay.crypt.bot/api'
        self.headers = {'Crypto-Pay-API-Token': self.token}

    async def create_invoice(self, amount_rub: float, description: str='', ton_price_rub: float=550.0) -> dict:
        async with aiohttp.ClientSession() as session:
            payload = {'currency_type': 'fiat', 'fiat': 'RUB', 'amount': str(amount_rub), 'description': description}
            async with session.post(f'{self.base_url}/createInvoice', headers=self.headers, json=payload) as resp:
                data = await resp.json()
                if not data.get('ok'):
                    ton_amount = round(amount_rub / ton_price_rub, 2)
                    payload = {'asset': 'TON', 'amount': str(ton_amount), 'description': description}
                    async with session.post(f'{self.base_url}/createInvoice', headers=self.headers, json=payload) as resp2:
                        data = await resp2.json()
                        if not data.get('ok'):
                            raise ValueError(f'CryptoBot Error: {data}')
                return data['result']

    async def get_invoice(self, invoice_id: int) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self.base_url}/getInvoices', headers=self.headers, params={'invoice_ids': str(invoice_id)}) as resp:
                data = await resp.json()
                if not data.get('ok') or not data['result']['items']:
                    raise ValueError(f'Invoice not found: {data}')
                return data['result']['items'][0]