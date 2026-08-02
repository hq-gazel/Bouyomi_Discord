# Bouyomi_Discord

Twitchのコメントを取得し、Irodori-TTSで音声合成した上でDiscord BotがボイスチャンネルでTTS読み上げを行う常駐アプリケーション。

設定面倒だからやや上級者向けかも...

## 概要

- Twitchチャンネルのコメントをリアルタイムで取得する
- 取得したコメントをIrodori-TTS(別プロジェクト)に渡して音声合成する
- 合成した音声をDiscord Bot経由でボイスチャンネルに再生する

## セットアップ手順

### クイックセットアップ (推奨)

`setup.bat` を実行するだけで、以下が自動化される。

```
setup.bat
```

- git / uv / pwsh (PowerShell 7) / ffmpeg の有無確認と、winget経由での自動インストール提案
- Irodori-TTS本体の取得(未取得の場合)とGPU(CUDA)向け依存関係の構築
- TTSサイドカーサーバー用の追加パッケージ(fastapi / uvicorn)のインストール
- Bouyomi_Discord自身の依存関係インストール(`uv sync`)
- `.env` の雛形生成、および `IRODORI_TTS_DIR` / `IRODORI_TTS_VENV_PYTHON` の自動入力

実行中に、Irodori-TTSの配置先パスとGPU使用有無を対話で尋ねられるので、その場で回答する。

以下は `setup.bat` では自動化できない残りの手順。上から順番に進めればOK。

### 1. Discord Bot を用意する

Discord Developer Portalで対象アプリケーションの `Bot` 設定画面を開き、**SERVER MEMBERS INTENT** を有効化する(管理者のVC入退室・メンバー情報取得に必須)。あわせてBOTをVCへの接続権限付きで対象サーバーに招待しておく。

### 2. Twitch OAuthトークンを発行する

Twitchの仕様は変わりやすいので、詳細は都度公式ドキュメント等で確認すること。おおまかな流れ:

- [twitchtokengenerator.com](https://twitchtokengenerator.com/) 等で、チャット読み取りに必要なスコープ(`chat:read` 等)を持つBOTアカウント用のOAuthトークンを発行する
- `oauth:` から始まる形式のまま `.env` の `TWITCH_OAUTH_TOKEN` に設定する

### 3. output.wavを作成
元になる録音データ（数秒で問題ない）を用意する。

### 4. .envの残りの項目を設定する

`setup.bat` 実行後に生成された `.env` を開き、Discord/Twitchのトークンや `IRODORI_TTS_REF_WAV` など、自動入力されない項目を入力する。

`.env` は `.gitignore` により管理対象外のため、実際のトークン等は `.env` にのみ記載すること。

### 5. 起動

```powershell
uv run main.py
```

起動すると、まずIrodori-TTSサイドカーサーバー(`tts_server.py`)を `IRODORI_TTS_VENV_PYTHON` で指定したインタプリタでsubprocessとして自動起動し、モデルロードとtorch.compileウォームアップが完了して `/health` が応答可能になるまで待機する(デフォルト最大600秒、`TTS_STARTUP_TIMEOUT_SECONDS`で変更可)。その後Discord BOTとTwitch BOTが並行して起動する。

終了時(Ctrl+C等)は、Discord/Twitch BOTの切断とTTSサイドカーサーバーの終了を行ってから終了する。

まぁ、要するに何も考えずに次回からはrun.batを使って起動して、ターミナル上はCTRL + Cで終了するってこった。

## 環境変数(.env)の主要項目

### ロギング

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `DEBUG_LOGGING` | 任意 | ルートロガーをDEBUGレベルにするか。デフォルト`false`(通常運転はINFOレベル) |

### Discord

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `DISCORD_BOT_TOKEN` | 必須 | Discord Developer Portalで発行したBotトークン |
| `DISCORD_ADMIN_USER_ID` | 必須 | 管理者として扱うDiscordユーザーID |
| `DISCORD_GUILD_ID` | 任意 | Botを動作させる対象サーバー(ギルド)ID。未設定なら全ギルド対象 |
| `ADMIN_CHECK_INTERVAL_SECONDS` | 任意 | 管理者状態のチェック間隔(秒)。デフォルト`5.0` |
| `PLAYBACK_TIMEOUT_SECONDS` | 任意 | 1回の音声再生のタイムアウト秒数。デフォルト`30.0` |

### Twitch

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `TWITCH_CLIENT_ID` | 必須 | Twitch Developer ConsoleのアプリケーションClient ID |
| `TWITCH_OAUTH_TOKEN` | 必須 | TwitchチャットBot用OAuthトークン(`oauth:`形式) |
| `TWITCH_BOT_NICK` | 必須 | TwitchチャットBotのニックネーム |
| `TWITCH_CHANNEL` | 必須 | コメントを取得する対象のTwitchチャンネル名 |
| `TWITCH_COMMENT_TEMPLATE` | 任意 | 読み上げ前にコメントへ適用するテンプレート文字列。デフォルト`{username}さん、{comment}` |

### Twitchコメントの読み上げテンプレートとユーザーエイリアス

`TWITCH_COMMENT_TEMPLATE` は `{username}`(発言者名)と `{comment}`(コメント本文)の
2つのプレースホルダーのみ使用できるテンプレート文字列で、敬称や語順を自由に変更できる
(例: `{username} からのコメント: {comment}`)。それ以外のプレースホルダーを含めると
起動時にエラーになる。

`{username}` に入る名前は、`cfg/user_aliases.json`(Git管理対象外)に発言者の
Twitchログイン名(小文字)をキーとしたエイリアスを登録しておくとそれが優先され、
未登録の場合はTwitchの表示名がそのまま使われる。書式は `cfg/user_aliases.json.example`
を参照(コピーして `cfg/user_aliases.json` を作成する)。ファイル自体が存在しない場合は
常に表示名が使われる(エラーにはならない)。

```json
{
  "twitchuser1": "ゆーざーいち",
  "another_login": "アナザー"
}
```

### NGワードフィルター

コメント本文(`{comment}`)に含まれるNGワードは、読み上げ前に伏字(ピー)へ自動置換される。
NGワードは `cfg/ng_words.txt`(Git管理対象)に1行1語で登録されており、デフォルトで
暴言・誹謗中傷、ネットスラング、卑猥語、差別用語などの一般的なNGワードが登録済み。
`#` から始まる行はコメント、空行は無視されるので、必要に応じて自由に追記・編集してよい。
ファイル自体が存在しない場合はフィルターは無効(常に未加工のまま読み上げ)になる。
また、コメント中のURL・メールアドレスはNGワード設定の有無にかかわらず常に自動検出され、
読み上げ前にそれぞれ「URL省略」「メールアドレス省略」に置換される。

### Irodori-TTS連携

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `IRODORI_TTS_DIR` | 必須 | Irodori-TTSプロジェクトのルートディレクトリ |
| `IRODORI_TTS_VENV_PYTHON` | 必須 | Irodori-TTS用仮想環境のPython実行ファイルパス |
| `IRODORI_TTS_HF_CHECKPOINT` | 二者択一 | HuggingFace上のチェックポイントID |
| `IRODORI_TTS_CHECKPOINT` | 二者択一 | ローカルに配置したチェックポイントのパス |
| `IRODORI_TTS_REF_WAV` | 必須 | 固定話者として使用する参照音声wavファイルのパス |
| `IRODORI_TTS_MODEL_PRECISION` | 任意 | モデルの推論精度。デフォルト`auto`(CUDA検出時`bf16`、CPU時`fp32`) |
| `IRODORI_TTS_CODEC_DEVICE` | 任意 | 参照音声エンコード(コーデック)の実行デバイス。デフォルト`auto`(CUDA使用可なら`cuda`、それ以外`cpu`) |
| `IRODORI_TTS_COMPILE_MODEL` | 任意 | torch.compileによるモデル事前コンパイルを有効にするか。デフォルト`true`。起動時にウォームアップ合成を1回実行する |
| `IRODORI_TTS_COMPILE_DYNAMIC` | 任意 | torch.compileの動的shape対応を有効にするか。デフォルト`true` |
| `IRODORI_TTS_NUM_STEPS` | 任意 | 音声合成のEuler積分ステップ数。デフォルト`28`(Irodori-TTS本体既定の`40`より速度寄りに調整、精度と速度のバランス値) |
| `IRODORI_TTS_DECODE_MODE` | 任意 | 候補デコード方式。デフォルト`batch`(`sequential`より高速、VRAM使用量は増加) |

`IRODORI_TTS_HF_CHECKPOINT` と `IRODORI_TTS_CHECKPOINT` はどちらか一方の設定が必須(両方未設定はエラー)。

### TTSサイドカーサーバー

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `TTS_SERVER_HOST` | 任意 | TTSサーバーのバインドホスト。デフォルト`127.0.0.1` |
| `TTS_SERVER_PORT` | 任意 | TTSサーバーのバインドポート。デフォルト`8765` |
| `TTS_STARTUP_TIMEOUT_SECONDS` | 任意 | TTSサーバーが起動完了(healthy)になるまでのタイムアウト秒数。デフォルト`600.0` |
| `TTS_DEBUG_LOGGING` | 任意 | TTS合成のステージ別タイミングログを標準出力に出すか。デフォルト`false` |
| `TTS_SYNTHESIZE_TIMEOUT_SECONDS` | 任意 | TTSサーバーへの`/synthesize`リクエストのタイムアウト秒数。デフォルト`60.0` |
| `TTS_HEALTH_CHECK_TIMEOUT_SECONDS` | 任意 | TTSサーバーへの`/health`リクエストのタイムアウト秒数。デフォルト`5.0` |
| `TTS_SHUTDOWN_TIMEOUT_SECONDS` | 任意 | TTSサイドカーサブプロセスをterminate()してからkill()に切り替えるまでの猶予秒数。デフォルト`10.0` |

### 任意設定

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `FFMPEG_PATH` | 任意 | ffmpeg実行ファイルのパス。未設定ならPATH上のffmpegを使用 |
