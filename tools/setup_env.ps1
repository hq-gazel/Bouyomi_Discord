<#
.SYNOPSIS
    Bouyomi_Discord の .env を初期化し、Irodori-TTS関連の機械的に決まる
    項目のみを自動入力する。

.DESCRIPTION
    カレントディレクトリ (Bouyomi_Discordのプロジェクトルートである前提) の
    .env.example を .env にコピーする。.env が既に存在する場合は何もせず
    終了する (上書き厳禁)。
    新規作成した .env のうち、以下の2行のみを実際のパスで置換する。
    それ以外の行 (Discord/Twitch関連のトークン等、コメント行を含む) は
    一切変更しない。
      - IRODORI_TTS_DIR=
      - IRODORI_TTS_VENV_PYTHON=

.PARAMETER IrodoriDir
    Irodori-TTS本体のルートディレクトリの絶対パス。

.EXAMPLE
    pwsh -NoProfile -File tools\setup_env.ps1 -IrodoriDir "E:\Irodori-TTS"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$IrodoriDir
)

$ErrorActionPreference = "Stop"

try {
    $envExamplePath = Join-Path -Path (Get-Location) -ChildPath ".env.example"
    $envPath = Join-Path -Path (Get-Location) -ChildPath ".env"

    if (Test-Path -LiteralPath $envPath) {
        Write-Host "  -> '.env' は既に存在するため、上書きしません。"
        exit 0
    }

    if (-not (Test-Path -LiteralPath $envExamplePath)) {
        Write-Host "[エラー] '.env.example' が見つかりません: $envExamplePath"
        exit 1
    }

    # まずはそのままコピーする(この時点ではエンコーディング・改行を一切変更しない)
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath

    $venvPython = Join-Path -Path $IrodoriDir -ChildPath ".venv\Scripts\python.exe"

    # 日本語コメントを含むため、明示的にUTF-8として読み書きする
    $content = Get-Content -LiteralPath $envPath -Raw -Encoding UTF8

    # IRODORI_TTS_DIR= / IRODORI_TTS_VENV_PYTHON= の2行だけをリテラル置換する。
    # (パスに '#' やバックスラッシュを含むため、正規表現ではなく文字列の
    #  literal Replace を用いて安全に置換する)
    $content = $content.Replace("IRODORI_TTS_DIR=", "IRODORI_TTS_DIR=$IrodoriDir")
    $content = $content.Replace("IRODORI_TTS_VENV_PYTHON=", "IRODORI_TTS_VENV_PYTHON=$venvPython")

    Set-Content -LiteralPath $envPath -Value $content -NoNewline -Encoding utf8NoBOM

    Write-Host "  -> '.env' を作成し、IRODORI_TTS_DIR / IRODORI_TTS_VENV_PYTHON を自動入力しました。"
    exit 0
}
catch {
    Write-Host "[エラー] .env の準備中に例外が発生しました: $($_.Exception.Message)"
    exit 1
}
