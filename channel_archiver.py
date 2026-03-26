import asyncio
import yaml
import sqlite3
import os
from telethon import TelegramClient, events
from telethon.errors import RPCError
from datetime import datetime

# ========================
# config読み込み
# ========================

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

api_id = config["api_id"]
api_hash = config["api_hash"]

channel_targets_list = config.get("channel_targets", [])
channel_targets = {t["channel_id"]: t for t in channel_targets_list}

audit_id = config.get("全通信監査ログ")

client = TelegramClient("session_channel", api_id, api_hash)

# ========================
# DB 初期化
# ========================

conn = sqlite3.connect("channel_log.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS messages(
    msg_id INTEGER,
    archive_chat_id INTEGER,
    text TEXT,
    PRIMARY KEY (msg_id, archive_chat_id)
)
""")
conn.commit()

# ========================
# ヘルパー
# ========================

def format_message(event, sender_name):
    time_str = event.message.date.strftime("%Y-%m-%d %H:%M:%S")
    text = event.message.text or ""
    return f"[{time_str}] {sender_name}\n{text}"

async def get_sender_name(event):
    try:
        sender = await event.get_sender()
        if sender:
            if hasattr(sender, "first_name"):
                name = sender.first_name or ""
                if sender.last_name:
                    name += f" {sender.last_name}"
                return name.strip()
            elif hasattr(sender, "title"):
                return sender.title
    except Exception:
        pass
    return "チャンネル投稿"

async def get_last_text(archive_id):
    cur.execute(
        "SELECT text FROM messages WHERE archive_chat_id=? ORDER BY rowid DESC LIMIT 1",
        (archive_id,)
    )
    row = cur.fetchone()
    return row[0] if row else None

# ========================
# 新規メッセージ
# ========================

@client.on(events.NewMessage)
async def new_message_handler(event):
    try:
        if event.chat_id not in channel_targets:
            return

        target = channel_targets[event.chat_id]
        archive_id = target["archive_channel_id"]

        sender_name = await get_sender_name(event)
        current_text = format_message(event, sender_name)

        # 重複ガード
        last_text = await get_last_text(archive_id)
        if last_text == current_text:
            return

        # 送信
        await client.send_message(archive_id, current_text)

        # DB保存
        cur.execute(
            "INSERT OR REPLACE INTO messages VALUES (?,?,?)",
            (event.message.id, archive_id, current_text)
        )
        conn.commit()

        # 添付
        if event.message.media:
            file = await event.message.download_media()
            if file:
                await client.send_file(archive_id, file)
                if os.path.exists(file):
                    os.remove(file)

    except RPCError as e:
        print(f"RPC Error: {e}")
    except Exception as e:
        print(f"Error: {e}")

# ========================
# 削除検知
# ========================

@client.on(events.MessageDeleted)
async def deleted_handler(event):
    try:
        for mid in event.deleted_ids:
            cur.execute("SELECT archive_chat_id, text FROM messages WHERE msg_id=?", (mid,))
            rows = cur.fetchall()

            for archive_id, old_text in rows:
                msg = f"## ?? メッセージが削除されました\n\n{old_text}"
                await client.send_message(archive_id, msg)

                if audit_id:
                    await client.send_message(audit_id, msg)

    except Exception as e:
        print(f"Delete Error: {e}")

# ========================
# 編集検知
# ========================

@client.on(events.MessageEdited)
async def edited_handler(event):
    try:
        if event.chat_id not in channel_targets:
            return

        target = channel_targets[event.chat_id]
        archive_id = target["archive_channel_id"]

        sender_name = await get_sender_name(event)
        new_text = format_message(event, sender_name)

        cur.execute(
            "SELECT text FROM messages WHERE msg_id=? AND archive_chat_id=?",
            (event.message.id, archive_id)
        )
        row = cur.fetchone()
        old_text = row[0] if row else "(不明)"

        if old_text == new_text:
            return

        msg = (
            "## ?? メッセージが編集されました\n\n"
            "[前]\n"
            f"{old_text}\n\n"
            "[後]\n"
            f"{new_text}"
        )

        await client.send_message(archive_id, msg)

        if audit_id:
            await client.send_message(audit_id, msg)

        # DB更新
        cur.execute(
            "UPDATE messages SET text=? WHERE msg_id=? AND archive_chat_id=?",
            (new_text, event.message.id, archive_id)
        )
        conn.commit()

    except Exception as e:
        print(f"Edit Error: {e}")

# ========================
# 起動
# ========================

async def main():
    print("Channel Archiver started")
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
