import yaml
import sqlite3
import logging
import os
from telethon import TelegramClient, events, types
from datetime import datetime

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

# 新規メッセージ受信（アーカイブ転送）
@client.on(events.NewMessage(chats=TARGET_USER_IDS))
async def my_event_handler(event):
    try:
        sender_id = event.chat_id
        dest_channel_id = target_map.get(sender_id)

        sender = await event.get_sender()
        name = sender.first_name if sender.first_name else "Unknown"
        timestamp = event.date.astimezone().strftime('%Y-%m-%d %H:%M:%S')

        msg_text = event.text if event.text else ""
        display_text = f"[{timestamp}] {name}\n{msg_text}"

        if event.message.media:
            # メディアがある場合は message オブジェクトを渡すのが最も安定
            sent_msg = await client.send_file(
                dest_channel_id,
                event.message,
                caption=display_text
            )
        else:
            sent_msg = await client.send_message(dest_channel_id, display_text)

        # ID紐付け保存 (is_read はデフォルト0)
        cursor = db.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO messages (original_id, archive_msg_id, channel_id, text, is_read) VALUES (?, ?, ?, ?, 0)",
            (event.id, sent_msg.id, dest_channel_id, display_text)
        )
        db.commit()
        logging.info(f"Archived: {event.id} -> {sent_msg.id}")

    except Exception as e:
        logging.error(f"Error in NewMessage: {e}")

# メッセージ削除検知
@client.on(events.MessageDeleted())
async def deleted_handler(event):
    try:
        cursor = db.cursor()
        now_time = datetime.now().astimezone().strftime('%H:%M:%S')

        for deleted_id in event.deleted_ids:
            cursor.execute(
                "SELECT archive_msg_id, channel_id, text FROM messages WHERE original_id=?",
                (deleted_id,)
            )
            row = cursor.fetchone()

            if row:
                archive_msg_id, channel_id, original_text = row
                if not original_text.startswith("??【削除】"):
                    new_text = f"??【削除】(検知: {now_time})\n{original_text}"
                    await client.edit_message(channel_id, archive_msg_id, new_text)

                    cursor.execute("UPDATE messages SET text=? WHERE original_id=?", (new_text, deleted_id))
                    db.commit()
                    logging.info(f"Marked as Deleted: {deleted_id}")

    except Exception as e:
        logging.error(f"Error in MessageDeleted: {e}")

# 相手の既読検知（アウトボックスの更新）
@client.on(events.Raw(types.UpdateReadHistoryOutbox))
async def read_handler(event):
    try:
        # event.max_id 以下のメッセージはすべて既読になったことを意味する
        max_read_id = event.max_id
        
        cursor = db.cursor()
        # 未読、かつ今回既読になったID以下のものを取得
        cursor.execute(
            "SELECT original_id, archive_msg_id, channel_id, text FROM messages "
            "WHERE original_id <= ? AND is_read = 0", 
            (max_read_id,)
        )
        rows = cursor.fetchall()

        for row in rows:
            orig_id, arch_id, chan_id, old_text = row
            
            # 本文の先頭に ?【既読】を追記
            # すでに ??【削除】 がある場合も考慮し、その前に付けるか後に付けるかはお好みですが、
            # ここではシンプルに先頭に追加します
            new_text = f"?【既読】\n{old_text}"
            
            try:
                await client.edit_message(chan_id, arch_id, new_text)
                
                cursor.execute(
                    "UPDATE messages SET text = ?, is_read = 1 WHERE original_id = ?",
                    (new_text, orig_id)
                )
                db.commit()
                logging.info(f"Marked as Read: {orig_id}")
            except Exception as e:
                # すでに消されているメッセージなどで編集失敗してもループを止めない
                logging.warning(f"Could not edit message {arch_id}: {e}")

    except Exception as e:
        logging.error(f"Error in read_handler: {e}")

print(f"Monitoring users: {TARGET_USER_IDS}")
client.start()
client.run_until_disconnected()
