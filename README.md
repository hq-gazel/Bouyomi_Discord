# Bouyomi_Discord

Twitchのコメントを取得し、Irodori-TTSで音声合成した上でDiscord BotがボイスチャンネルでTTS読み上げを行う常駐アプリケーション。

## 概要

- Twitchチャンネルのコメントをリアルタイムで取得する
- 取得したコメントをIrodori-TTS(別プロジェクト)に渡して音声合成する
- 合成した音声をDiscord Bot経由でボイスチャンネルに再生する

## セットアップ手順

### 1. 依存関係のインストール

本プロジェクトは [uv](https://docs.astral.sh/uv/) でPython環境・パッケージを管理する。

```powershell
uv sync
```

Python 3.12系を使用する(discord.py / PyNaCl / TwitchIOのPython 3.14対応が不透明なため)。`.python-version` で固定済み。

### 2. 環境変数の設定

`.env.example` を `.env` にコピーし、各値を実際の設定に置き換える。

```powershell
Copy-Item .env.example .env
```

`.env` は `.gitignore` により管理対象外のため、実際のトークン等は `.env` にのみ記載すること。

## 環境変数(.env)の主要項目

### Discord

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `DISCORD_BOT_TOKEN` | 必須 | Discord Developer Portalで発行したBotトークン |
| `DISCORD_ADMIN_USER_ID` | 必須 | 管理者として扱うDiscordユーザーID |
| `DISCORD_GUILD_ID` | 任意 | Botを動作させる対象サーバー(ギルド)ID。未設定なら全ギルド対象 |
| `ADMIN_CHECK_INTERVAL_SECONDS` | 任意 | 管理者状態のチェック間隔(秒)。デフォルト`5.0` |

### Twitch

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `TWITCH_CLIENT_ID` | 必須 | Twitch Developer ConsoleのアプリケーションClient ID |
| `TWITCH_OAUTH_TOKEN` | 必須 | TwitchチャットBot用OAuthトークン(`oauth:`形式) |
| `TWITCH_BOT_NICK` | 必須 | TwitchチャットBotのニックネーム |
| `TWITCH_CHANNEL` | 必須 | コメントを取得する対象のTwitchチャンネル名 |

### Irodori-TTS連携

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `IRODORI_TTS_DIR` | 必須 | Irodori-TTSプロジェクトのルートディレクトリ |
| `IRODORI_TTS_VENV_PYTHON` | 必須 | Irodori-TTS用仮想環境のPython実行ファイルパス |
| `IRODORI_TTS_HF_CHECKPOINT` | 二者択一 | HuggingFace上のチェックポイントID |
| `IRODORI_TTS_CHECKPOINT` | 二者択一 | ローカルに配置したチェックポイントのパス |
| `IRODORI_TTS_REF_WAV` | 必須 | 固定話者として使用する参照音声wavファイルのパス |

`IRODORI_TTS_HF_CHECKPOINT` と `IRODORI_TTS_CHECKPOINT` はどちらか一方の設定が必須(両方未設定はエラー)。

### TTSサイドカーサーバー

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `TTS_SERVER_HOST` | 任意 | TTSサーバーのバインドホスト。デフォルト`127.0.0.1` |
| `TTS_SERVER_PORT` | 任意 | TTSサーバーのバインドポート。デフォルト`8765` |

### 任意設定

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `FFMPEG_PATH` | 任意 | ffmpeg実行ファイルのパス。未設定ならPATH上のffmpegを使用 |
# Bouyomi_Discord
