from telethon import TelegramClient
import asyncio

# ここを自分の情報に書き換えてください
api_id = 12345678
api_hash = "your_api_hash_here"

async def main():
    async with TelegramClient("session", api_id, api_hash) as client:
        dialogs = await client.get_dialogs()
        for d in dialogs:
            print(f"{d.name}: {d.id}")

if __name__ == "__main__":
    asyncio.run(main())
