from telethon import TelegramClient
import asyncio

api_id = 35574291
api_hash = "0348fb48d9848d6725c51916b839d1e4"

async def main():
    async with TelegramClient("session", api_id, api_hash) as client:
        dialogs = await client.get_dialogs()
        for d in dialogs:
            print(d.name, d.id)

asyncio.run(main())
