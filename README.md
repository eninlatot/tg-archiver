# Telegram Archiver (Raspberry Pi)

## ■ 概要

Telegramのメッセージを自動で保存する  
**常駐型アーカイブシステム。**

以下の2系統を独立して監視する：

### ① DMアーカイバ（archiver.py）
特定ユーザーとの1対1メッセージ

### ② チャンネルアーカイバ（channel_archiver.py）
指定チャンネルの投稿

---

## ■ 記録対象

### DM / チャンネル共通

* メッセージ本文
* 投稿者 / 送信者
* 添付ファイル（画像 / PDF / 動画 / 音声など）
* メッセージ編集
* メッセージ削除

削除されたメッセージも  
**削除ログとして復元・保存される。**

---

# ■ システム構成

実行環境

* OS : Raspberry Pi OS
* Python : 仮想環境（venv）
* ライブラリ : Telethon
* 常駐管理 : systemd

構成


Telegram
↓
Telegram API
↓
archiver.py（DM監視）
channel_archiver.py（チャンネル監視）
↓
アーカイブ用Telegramチャンネル
# ■ ディレクトリ構成


/home/pi/tg-archiver/

archiver.py DM監視
channel_archiver.py チャンネル監視

config.yaml 設定ファイル
get_ids.py ID取得ツール
README.md 本ドキュメント

session.session DM用セッション
session_channel.session チャンネル用セッション

message_log.db DMログDB
channel_log.db チャンネルログDB

venv/ Python仮想環境
# ■ 動作仕様

## ● DM監視（archiver.py）

1. 指定ユーザーとのメッセージ監視
2. 送受信を自動記録
3. アーカイブチャンネルへ保存

---

## ● チャンネル監視（channel_archiver.py）

1. 指定チャンネル投稿を監視
2. 投稿者名を取得（不可時は「チャンネル投稿」）
3. アーカイブチャンネルへ保存

---

## ■ 保存形式


[YYYY-MM-DD HH:MM:SS] 投稿者名
本文
## ■ 添付ファイル

以下すべて対応：

* 画像
* PDF
* 動画
* 音声
* ドキュメント

保存処理：

1. 本文保存
2. ファイル保存
3. ローカル削除

---

## ■ 編集検知

?? メッセージが編集されました

[前]
旧内容

[後]
新内容

---

## ■ 削除検知

※内容はDBから復元

---

# ■ 設定ファイル

config.yaml

```yaml
api_id: 123456
api_hash: "xxxxxxxxxxxxxxxxxxxx"

targets:
  - name: userA
    user_id: 111111111
    archive_channel_id: -1002222222222

channel_targets:
  - name: sample_channel
    channel_id: -1001234567890
    archive_channel_id: -1009999999999

全通信監査ログ: -1008888888888
■ 項目説明
共通

api_id / api_hash
Telegram API認証情報

全通信監査ログ
削除・編集ログの共通送信先（任意）

DM用（targets）

name
表示名

user_id
対象ユーザー

archive_channel_id
保存先

チャンネル用（channel_targets）

name
チャンネル名（識別用）

channel_id
監視対象チャンネル

archive_channel_id
保存先

■ API取得

https://my.telegram.org

手順：

1 Login
2 API development tools
3 API ID / API Hash取得

■ ID取得
python get_ids.py
■ サービス管理
● DM
tg-archiver.service
● チャンネル
channel-archiver.service
状態確認
sudo systemctl status tg-archiver
sudo systemctl status channel-archiver
起動
sudo systemctl start tg-archiver
sudo systemctl start channel-archiver
停止
sudo systemctl stop tg-archiver
sudo systemctl stop channel-archiver
再起動
sudo systemctl restart tg-archiver
sudo systemctl restart channel-archiver
■ ログ確認
journalctl -u tg-archiver -f
journalctl -u channel-archiver -f

終了：

Ctrl + C
■ ログ管理（重要）

ログ肥大防止のため以下を設定：

/etc/systemd/journald.conf
SystemMaxUse=200M
SystemKeepFree=100M
MaxRetentionSec=7day

反映：

sudo systemctl restart systemd-journald

これにより：

最大200MBまで制限

空き容量確保

7日以上のログ自動削除

■ Raspberry Pi 再起動
sudo reboot

再起動後：

両サービス自動起動

手動操作不要

■ 復旧手順

1 Pi起動
2 config.yaml確認
3 サービス再起動

sudo systemctl restart tg-archiver
sudo systemctl restart channel-archiver
■ バックアップ対象
config.yaml
session.session
session_channel.session
message_log.db
channel_log.db
■ セキュリティ注意

機密情報：

api_id

api_hash

sessionファイル

外部公開禁止

■ 運用状態

本システムは：

24時間監視

自動起動

自動ログ保存

を行う。

Raspberry Piが稼働している限り
Telegramデータは自動保存される。

■ 作成

Telegram Archiver System
Created 2026-03-02 / Updated 2026-03-23
