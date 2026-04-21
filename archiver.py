import yaml
import sqlite3
import logging
from telethon import TelegramClient, events

# ログ設定
logging.basicConfig(level=logging.INFO)

# 設定読み込み
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# targetsから監視対象のリストを作成
target_map = {t['user_id']: t['archive_channel_id'] for t in config['targets']}
TARGET_USER_IDS = list(target_map.keys())

client = TelegramClient('archiver_session', config['api_id'], config['api_hash'])
db = sqlite3.connect('message_map.db')

# 新規メッセージ受信
@client.on(events.NewMessage(chats=TARGET_USER_IDS))
async def my_event_handler(event):
    try:
        sender_id = event.chat_id
        dest_channel_id = target_map.get(sender_id)
        
        sender = await event.get_sender()
        name = sender.first_name if sender.first_name else "Unknown"
        timestamp = event.date.strftime('%Y-%m-%d %H:%M:%S')
        
        # 本文の組み立て（テキストがない場合は空文字にする）
        msg_text = event.text if event.text else ""
        display_text = f"[{timestamp}] {name}\n{msg_text}"
        
        # --- 修正ポイント ---
        if event.message.media:
            # 画像などのメディアがある場合は send_file を使う
            sent_msg = await client.send_file(
                dest_channel_id, 
                event.message.media, 
                caption=display_text
            )
        else:
            # テキストのみの場合はこれまで通り send_message
            sent_msg = await client.send_message(dest_channel_id, display_text)
        # ------------------

        # ID紐付け保存（ここは変更なし）
        cursor = db.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO messages (original_id, archive_msg_id, channel_id, text) VALUES (?, ?, ?, ?)",
            (event.id, sent_msg.id, dest_channel_id, display_text)
        )
        db.commit()
        logging.info(f"Archived: {event.id} -> {sent_msg.id} (Channel: {dest_channel_id})")

    except Exception as e:
        logging.error(f"Error in NewMessage: {e}")

# メッセージ削除検知
@client.on(events.MessageDeleted())
async def deleted_handler(event):
    try:
        cursor = db.cursor()
        for deleted_id in event.deleted_ids:
            cursor.execute(
                "SELECT archive_msg_id, channel_id, text FROM messages WHERE original_id=?", 
                (deleted_id,)
            )
            row = cursor.fetchone()
            
            if row:
                archive_msg_id, channel_id, original_text = row
                if not original_text.startswith("??【削除】"):
                    new_text = f"??【削除】\n{original_text}"
                    await client.edit_message(channel_id, archive_msg_id, new_text)
                    
                    cursor.execute("UPDATE messages SET text=? WHERE original_id=?", (new_text, deleted_id))
                    db.commit()
                    logging.info(f"Message Edited (Deleted): {deleted_id}")

    except Exception as e:
        logging.error(f"Error in MessageDeleted: {e}")

print(f"Monitoring users: {TARGET_USER_IDS}")
client.start()
client.run_until_disconnected()
