<#
.SYNOPSIS
    Bouyomi_Discord のセットアップ事前チェック・対話入力を行う。

.DESCRIPTION
    git / uv / ffmpeg の有無を確認し、無ければ winget での自動インストールを
    提案する(pwsh自体は setup.bat 側で確認済みの前提)。
    続けてIrodori-TTSの配置先パスとGPU使用有無を対話で確認し、
    結果を "KEY=VALUE" 形式で $OutFile に書き出す。

    setup.bat の `set /p` ではなく本スクリプトの Read-Host に対話入力を
    集約しているのは、chcp 65001環境下でバッチの `set /p` を使うと、
    標準入力がリダイレクトされる状況でまれにコマンド解析が壊れる
    cmd.exe側の問題が確認されたため。

.PARAMETER ProjectRoot
    Bouyomi_Discordのプロジェクトルート(末尾に "\" を含まない絶対パス)。

.PARAMETER OutFile
    結果を書き出すテキストファイルのパス。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$OutFile
)

$ErrorActionPreference = "Stop"

function Confirm-YesNo {
    param([string]$Prompt, [bool]$DefaultYes = $true)
    $suffix = if ($DefaultYes) { "[Y/n]" } else { "[y/N]" }
    $ans = Read-Host "$Prompt $suffix"
    if ([string]::IsNullOrWhiteSpace($ans)) { return $DefaultYes }
    return ($ans -match '^[Yy]')
}

function Ensure-Tool {
    param([string]$CmdName, [string]$WingetId, [string]$ManualUrl)

    if (Get-Command $CmdName -ErrorAction SilentlyContinue) {
        Write-Host "  -> $CmdName : OK"
        return $true
    }

    Write-Host ""
    Write-Host "[警告] $CmdName が見つかりません。"

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "[エラー] winget も利用できないため自動導入できません。手動でインストールしてください。"
        Write-Host "         $ManualUrl"
        return $false
    }

    $doInstall = Confirm-YesNo "winget で $CmdName ($WingetId) を自動インストールしますか?"
    if (-not $doInstall) {
        Write-Host "[エラー] $CmdName が必要です。手動でインストールしてください。"
        Write-Host "         $ManualUrl"
        return $false
    }

    winget install --id $WingetId -e --source winget
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[エラー] winget install --id $WingetId に失敗しました(exit=$LASTEXITCODE)。"
        Write-Host "         手動でインストールしてください: $ManualUrl"
        return $false
    }

    # winget install直後は現在のプロセスのPATHに反映されないため、
    # レジストリのMachine/User Pathを読み直してこのプロセスに反映する。
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"

    if (-not (Get-Command $CmdName -ErrorAction SilentlyContinue)) {
        Write-Host "[エラー] $CmdName のインストール後もコマンドが見つかりません。"
        Write-Host "         一度ウィンドウを閉じてから、再度 setup.bat を実行してください。"
        return $false
    }

    Write-Host "  -> $CmdName のインストールが完了しました。"
    return $true
}

Write-Host "===== 事前チェック: 必要なコマンドの確認 ====="
if (-not (Ensure-Tool "git" "Git.Git" "https://git-scm.com/downloads")) { exit 1 }
if (-not (Ensure-Tool "uv" "astral-sh.uv" "https://docs.astral.sh/uv/getting-started/installation/")) { exit 1 }
if (-not (Ensure-Tool "ffmpeg" "Gyan.FFmpeg" "https://ffmpeg.org/download.html")) { exit 1 }

$defaultIrodoriDir = Join-Path (Split-Path -Parent $ProjectRoot) "Irodori-TTS"

Write-Host ""
Write-Host "===== Irodori-TTSの配置先・GPU設定 ====="
$irodoriDir = Read-Host "Irodori-TTSの配置先パスを入力してください (空欄でデフォルト: $defaultIrodoriDir)"
if ([string]::IsNullOrWhiteSpace($irodoriDir)) { $irodoriDir = $defaultIrodoriDir }

$useGpu = Confirm-YesNo "NVIDIA GPU(CUDA)を使用しますか?"
$irodoriExtra = if ($useGpu) { "cu128" } else { "cpu" }

Write-Host ""
Write-Host "  Irodori-TTS配置先: $irodoriDir"
Write-Host "  GPU extra        : $irodoriExtra"
Write-Host ""

@"
IRODORI_DIR=$irodoriDir
IRODORI_EXTRA=$irodoriExtra
"@ | Set-Content -LiteralPath $OutFile -Encoding utf8NoBOM -NoNewline

exit 0
