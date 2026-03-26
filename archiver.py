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
# 「全通信監査ログ」のIDを取得（未設定ならNone）
audit_id = config.get("全通信監査ログ")

# targetsを辞書化 (user_idがキー)
targets = {t["user_id"]: t for t in config["targets"]}

client = TelegramClient("session", api_id, api_hash)

# ========================
# DB 初期化
# ========================

conn = sqlite3.connect("message_log.db")
cur = conn.cursor()

# 主キーを (msg_id, archive_chat_id) の複合キーに変更して衝突を防止
cur.execute("""
CREATE TABLE IF NOT EXISTS messages(
    msg_id INTEGER,
    archive_msg_id INTEGER,
    archive_chat_id INTEGER,
    text TEXT,
    PRIMARY KEY (msg_id, archive_chat_id)
)
""")
conn.commit()

# ========================
# ヘルパー関数
# ========================

def format_message(event, direction, name):
    sender = "自分" if direction == "out" else name
    time_str = event.message.date.strftime("%Y-%m-%d %H:%M:%S")
    text = event.message.text or ""
    return f"[{time_str}] {sender}\n{text}"

async def get_last_text(archive_id):
    """そのチャネルの最新の保存テキストを取得"""
    cur.execute(
        "SELECT text FROM messages WHERE archive_chat_id=? ORDER BY rowid DESC LIMIT 1",
        (archive_id,)
    )
    row = cur.fetchone()
    return row[0] if row else None

# ========================
# 新規メッセージ受信
# ========================

@client.on(events.NewMessage)
async def handler(event):
    try:
        if not event.is_private:
            return

        uid = event.chat_id
        if uid not in targets:
            return

        target = targets[uid]
        archive_id = target["archive_channel_id"]
        name = target["name"]
        direction = "out" if event.out else "in"
        
        current_text = format_message(event, direction, name)

        # --- 重複ガード (位置情報などの連投対策) ---
        last_text = await get_last_text(archive_id)
        if last_text == current_text:
            return # 同じ内容なら何もしない

        # アーカイブ送信
        sent = await client.send_message(archive_id, current_text)

        # DB保存
        cur.execute(
            "INSERT OR REPLACE INTO messages VALUES (?,?,?,?)",
            (event.message.id, sent.id, archive_id, current_text)
        )
        conn.commit()

        # 添付ファイル処理
        if event.message.media:
            file = await event.message.download_media()
            if file:
                # キャプションがある場合は別途送る（現在の仕様を維持）
                caption = event.message.text or ""
                if caption:
                    await client.send_message(archive_id, f"[添付キャプション]\n{caption}")
                
                await client.send_file(archive_id, file)
                if os.path.exists(file):
                    os.remove(file)

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

            for row in rows:
                archive_id, old_text = row
                
                # 1. メインチャネルへ「足跡＋内容」を投稿
                delete_notice = f"?? **メッセージが削除されました**\n---\n{old_text}"
                await client.send_message(archive_id, delete_notice)

                # 2. 監査ログへ詳細を送信
                if audit_id:
                    target_name = next((t["name"] for t in targets.values() if t["archive_channel_id"] == archive_id), "不明")
                    audit_msg = f"?? 【削除ログ: {target_name}】\n内容:\n{old_text}"
                    await client.send_message(audit_id, audit_msg)

    except Exception as e:
        print(f"Delete Error: {e}")

# ========================
# 編集検知
# ========================

@client.on(events.MessageEdited)
async def edited_handler(event):
    try:
        uid = event.chat_id
        if uid not in targets:
            return

        target = targets[uid]
        archive_id = target["archive_channel_id"]
        name = target["name"]
        direction = "out" if event.out else "in"

        new_text = format_message(event, direction, name)

        # DBから修正前のテキストを取得
        cur.execute("SELECT text FROM messages WHERE msg_id=? AND archive_chat_id=?", (event.message.id, archive_id))
        row = cur.fetchone()
        old_text = row[0] if row else "(不明)"

        # 内容が変わっていない場合は無視
        if old_text == new_text:
            return

        # 1. メインチャネルへ「ビフォーアフター」を投稿
        edit_notice = f"?? **メッセージが編集されました**\n---\n**[前]**\n{old_text}\n**[後]**\n{new_text}"
        await client.send_message(archive_id, edit_notice)

        # 2. 監査ログへ詳細を送信
        if audit_id:
            audit_msg = f"?? 【編集ログ: {name}】\n修正前:\n{old_text}\n修正後:\n{new_text}"
            await client.send_message(audit_id, audit_msg)

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
    print("Telegram Archiver (Final Optimized) started")
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
