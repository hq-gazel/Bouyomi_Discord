<#
.SYNOPSIS
    Irodori-TTS本体の.venvをGPU(CUDA)構成へ同期し、Bouyomi_Discordが
    サイドカーサーバー(tts_server.py)を動かすのに必要な追加パッケージを
    再インストールする。

.DESCRIPTION
    Irodori-TTS本体の pyproject.toml を変更せず、以下のみを行う。
      1. Irodori-TTS本体で `uv sync --extra <Extra>` を実行し、
         torch/torchaudio/transformers/huggingface-hub/dacvae等を
         ロックファイル通りに同期する(CPU版torchが入っていた場合はここで
         CUDA版に入れ替わる)。
      2. `uv sync` はロックファイルにないパッケージを削除するため、
         Bouyomi_Discord用に追加インストールしていた fastapi / uvicorn と、
         dacvaeのビルドに必要なsetuptoolsを同期後に入れ直す。
      3. 主要パッケージのimport確認とGPU認識状況を表示する。

.PARAMETER IrodoriDir
    Irodori-TTS本体のルートディレクトリの絶対パス。省略時はBouyomi_Discordの
    .env内の IRODORI_TTS_DIR を読み取る。

.PARAMETER Extra
    uv sync時に指定するGPU extra名。既定値は "cu128" (CUDA 12.8)。
    CPU環境に戻したい場合は "cpu" を指定する。

.EXAMPLE
    pwsh -NoProfile -File tools\sync_irodori_gpu.ps1
    pwsh -NoProfile -File tools\sync_irodori_gpu.ps1 -IrodoriDir "E:\Irodori-TTS" -Extra cu128
#>
[CmdletBinding()]
param(
    [string]$IrodoriDir,
    [string]$Extra = "cu128"
)

$ErrorActionPreference = "Stop"

function Resolve-IrodoriDirFromEnv {
    $envPath = Join-Path -Path (Get-Location) -ChildPath ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        throw "'-IrodoriDir' 未指定かつ '.env' が見つかりません: $envPath"
    }
    $line = Get-Content -LiteralPath $envPath -Encoding UTF8 |
        Where-Object { $_ -match '^\s*IRODORI_TTS_DIR\s*=\s*(.+)$' } |
        Select-Object -First 1
    if (-not $line) {
        throw "'.env' 内に 'IRODORI_TTS_DIR' が見つかりません。"
    }
    return ($line -replace '^\s*IRODORI_TTS_DIR\s*=\s*', '').Trim()
}

try {
    if (-not $IrodoriDir) {
        $IrodoriDir = Resolve-IrodoriDirFromEnv
    }
    if (-not (Test-Path -LiteralPath (Join-Path $IrodoriDir "pyproject.toml"))) {
        throw "Irodori-TTS本体が見つかりません: $IrodoriDir"
    }
    $venvPython = Join-Path -Path $IrodoriDir -ChildPath ".venv\Scripts\python.exe"

    Write-Host "===== Irodori-TTS GPU同期 (extra=$Extra) ====="
    Write-Host "IrodoriDir: $IrodoriDir"
    Write-Host ""

    Push-Location -LiteralPath $IrodoriDir
    try {
        Write-Host "[1/2] uv sync --extra $Extra"
        uv sync --extra $Extra
        if ($LASTEXITCODE -ne 0) {
            throw "'uv sync --extra $Extra' が失敗しました (exit=$LASTEXITCODE)。"
        }

        Write-Host ""
        Write-Host "[2/2] Bouyomi_Discord用パッケージを再インストール (fastapi / uvicorn[standard] / setuptools)"
        # `uv sync` で再作成された venv には pip 自体が入っていないため、
        # `python -m pip install` ではなく `uv pip install` を使う。
        uv pip install --python $venvPython fastapi "uvicorn[standard]" setuptools
        if ($LASTEXITCODE -ne 0) {
            throw "追加パッケージのインストールに失敗しました (exit=$LASTEXITCODE)。"
        }
    }
    finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "===== 動作確認 ====="
    $checkScript = @'
import importlib
mods = ["torch", "torchaudio", "transformers", "huggingface_hub", "dacvae", "setuptools", "fastapi", "uvicorn"]
for name in mods:
    try:
        m = importlib.import_module(name)
        ver = getattr(m, "__version__", "?")
        print(f"[OK] {name}=={ver}")
    except Exception as e:
        print(f"[NG] {name}: {e}")
import torch
print(f"[torch] cuda.is_available()={torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"[torch] cuda device={torch.cuda.get_device_name(0)}")
'@
    & $venvPython -c $checkScript

    Write-Host ""
    Write-Host "完了しました。"
    exit 0
}
catch {
    Write-Host "[エラー] $($_.Exception.Message)"
    exit 1
}
