# Bouyomi_Discord

Twitchのコメントを取得し、Irodori-TTSで音声合成した上でDiscord BotがボイスチャンネルでTTS読み上げを行う常駐アプリケーション。

設定面倒だからやや上級者向けかも...

## 概要

- Twitchチャンネルのコメントをリアルタイムで取得する
- 取得したコメントをIrodori-TTS(別プロジェクト)に渡して音声合成する
- 合成した音声をDiscord Bot経由でボイスチャンネルに再生する

## 事前準備

上から順番に進めればOK。

### 1. ffmpeg を入れる

Discord BOTの音声再生に必須。[公式サイト](https://ffmpeg.org/download.html)等からインストールし、PATHに追加するか、`.env` の `FFMPEG_PATH` に実行ファイルの絶対パスを設定する。

### 2. Discord Bot を用意する

Discord Developer Portalで対象アプリケーションの `Bot` 設定画面を開き、**SERVER MEMBERS INTENT** を有効化する(管理者のVC入退室・メンバー情報取得に必須)。あわせてBOTをVCへの接続権限付きで対象サーバーに招待しておく。

### 3. Twitch OAuthトークンを発行する

Twitchの仕様は変わりやすいので、詳細は都度公式ドキュメント等で確認すること。おおまかな流れ:

- [twitchtokengenerator.com](https://twitchtokengenerator.com/) 等で、チャット読み取りに必要なスコープ(`chat:read` 等)を持つBOTアカウント用のOAuthトークンを発行する
- `oauth:` から始まる形式のまま `.env` の `TWITCH_OAUTH_TOKEN` に設定する

### 4. Irodori-TTS 本体をセットアップする

本プロジェクトとは別に、Irodori-TTS本体が任意のディレクトリ(`.env` の `IRODORI_TTS_DIR` で指定するパス)にセットアップ済みで、専用の `.venv` が構築されていることが前提。Bouyomi_Discord自身のvenvにはIrodori-TTSの重い依存関係(torch等)は含めない。

### 5. Irodori-TTS側venvに追加パッケージを入れる

本プロジェクトの `tts_server.py` はIrodori-TTSの `.venv` のPythonで起動するFastAPIサーバーだが、`fastapi` / `uvicorn` / `setuptools`(dacvaeのビルドに必要)はIrodori-TTS本体の依存関係には含まれていないため、Irodori-TTS側の `.venv` に追加でインストールしておく必要がある(Irodori-TTS本体の `pyproject.toml` は変更しないこと)。

```powershell
& "<irodori-TTSが入ってるとこ>\.venv\Scripts\python.exe" -m pip install fastapi "uvicorn[standard]" setuptools
```

※Irodori-TTS側で後日 `uv sync` を実行すると、`pyproject.toml` に記載の無いこれらのパッケージが再インストール時に失われる可能性があるため、その場合は上記コマンドを再実行すること。

### 6. GPU(CUDA)構成に同期する(必須)

Irodori-TTSはCPU版torchでは動作しない(GPU必須)。依存ライブラリをインストールしたりする為、[tools/sync_irodori_gpu.ps1](tools/sync_irodori_gpu.ps1) を実行して同期する。内部で `uv sync --extra cu128` を実行した後、上記の追加パッケージを入れ直し、主要パッケージのimport確認とGPU認識状況を表示する。

```powershell
pwsh -NoProfile -File tools\sync_irodori_gpu.ps1
```

`-IrodoriDir` を省略した場合は `.env` の `IRODORI_TTS_DIR` を使用する。

## セットアップ手順

### 1. 依存関係のインストール

本プロジェクトは [uv](https://docs.astral.sh/uv/) でPython環境・パッケージを管理する。

```powershell
uv sync
```

Python 3.12系を使用する(discord.py / PyNaCl / TwitchIOのPython 3.14対応が不透明なため)。`.python-version` で固定済み。

### 2. output.wavを作成
元になる録音データ（数秒で問題ない）を用意する。

### 3. 環境変数の設定

`.env.example` を `.env` にコピーし、各値を実際の設定に置き換える。

```powershell
Copy-Item .env.example .env
```

`.env` は `.gitignore` により管理対象外のため、実際のトークン等は `.env` にのみ記載すること。

### 4. 起動

```powershell
uv run main.py
```

起動すると、まずIrodori-TTSサイドカーサーバー(`tts_server.py`)を `IRODORI_TTS_VENV_PYTHON` で指定したインタプリタでsubprocessとして自動起動し、モデルロードが完了して `/health` が応答可能になるまで待機する(最大180秒)。その後Discord BOTとTwitch BOTが並行して起動する。終了時(Ctrl+C等)は、Discord/Twitch BOTの切断とTTSサイドカーサーバーの終了を行ってから終了する。

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
