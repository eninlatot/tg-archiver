import asyncio
import yaml
import sqlite3
import os
import logging
from telethon import TelegramClient, events
from telethon.errors import RPCError
from datetime import datetime

# ログ設定
logging.basicConfig(level=logging.INFO)

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

client = TelegramClient("session_channel_v2", api_id, api_hash)

# ========================
# DB 初期化
# ========================
conn = sqlite3.connect("channel_log.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS messages(
    msg_id INTEGER,
    archive_chat_id INTEGER,
    archive_msg_id INTEGER,
    text TEXT,
    PRIMARY KEY (msg_id, archive_chat_id)
)
""")
conn.commit()

# ========================
# ヘルパー
# ========================
def format_message(event, sender_name):
    time_str = event.message.date.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    text = event.message.text or ""
    return f"[{time_str}] {sender_name}\n{text}"

async def get_sender_name(event):
    try:
        sender = await event.get_sender()
        if sender:
            if hasattr(sender, "first_name"):
                name = sender.first_name or ""
                if hasattr(sender, "last_name") and sender.last_name:
                    name += f" {sender.last_name}"
                return name.strip()
            elif hasattr(sender, "title"):
                return sender.title
    except Exception:
        pass
    return "チャンネル投稿"

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

        if event.message.media:
            sent_msg = await client.send_file(
                archive_id, 
                event.message.media, 
                caption=current_text
            )
        else:
            sent_msg = await client.send_message(archive_id, current_text)

        cur.execute(
            "INSERT OR REPLACE INTO messages VALUES (?,?,?,?)",
            (event.message.id, archive_id, sent_msg.id, current_text)
        )
        conn.commit()
        
        logging.info(f"Archived Channel Message: {event.message.id} -> {sent_msg.id}")

    except Exception as e:
        logging.error(f"NewMessage Error: {e}")

# ========================
# 削除検知 (上書きモード + 検知時刻追記)
# ========================
@client.on(events.MessageDeleted)
async def deleted_handler(event):
    try:
        # 削除を検知した「今」の時刻を取得
        now_time = datetime.now().astimezone().strftime('%H:%M:%S')

        for mid in event.deleted_ids:
            cur.execute("SELECT archive_chat_id, archive_msg_id, text FROM messages WHERE msg_id=?", (mid,))
            rows = cur.fetchall()

            for archive_id, archive_msg_id, old_text in rows:
                if not old_text.startswith("??【削除】"):
                    # 削除マークに検知時刻を添える
                    new_text = f"??【削除】(検知: {now_time})\n{old_text}"
                    await client.edit_message(archive_id, archive_msg_id, new_text)
                    
                    if audit_id:
                        await client.send_message(audit_id, f"## ?? 削除検知\n{new_text}")

                    cur.execute("UPDATE messages SET text=? WHERE msg_id=? AND archive_chat_id=?", 
                                (new_text, mid, archive_id))
        conn.commit()
    except Exception as e:
        logging.error(f"Delete Error: {e}")

# ========================
# 編集検知 (上書きモード)
# ========================
@client.on(events.MessageEdited)
async def edited_handler(event):
    try:
        if event.chat_id not in channel_targets:
            return

        target = channel_targets[event.chat_id]
        archive_id = target["archive_channel_id"]
        
        cur.execute("SELECT archive_msg_id, text FROM messages WHERE msg_id=? AND archive_chat_id=?", 
                    (event.message.id, archive_id))
        row = cur.fetchone()
        if not row: return
        
        archive_msg_id, old_text = row
        sender_name = await get_sender_name(event)
        new_content = format_message(event, sender_name)
        
        if old_text == new_content: return

        await client.edit_message(archive_id, archive_msg_id, new_content)

        if audit_id:
            msg = f"## ?? 編集検知\n[前]\n{old_text}\n\n[後]\n{new_content}"
            await client.send_message(audit_id, msg)

        cur.execute("UPDATE messages SET text=? WHERE msg_id=? AND archive_chat_id=?", 
                    (new_content, event.message.id, archive_id))
        conn.commit()
    except Exception as e:
        logging.error(f"Edit Error: {e}")

async def main():
    logging.info("Channel Archiver (Edit-Support Mode) started")
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
