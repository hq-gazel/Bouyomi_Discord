@echo off
chcp 65001 >nul
setlocal

rem =====================================================================
rem  Bouyomi_Discord セットアップスクリプト
rem
rem  必要ツール(git/uv/pwsh/ffmpeg)の確認・自動導入、Irodori-TTS本体の
rem  取得・venv構築、.envの雛形コピーまでを自動で行います。
rem  実行後、Discord/Twitchのトークンや対象サーバー/チャンネルなどの
rem  実行に必要な環境変数を設定してください(.envファイルを直接編集)。
rem =====================================================================

set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT_NOSLASH=%PROJECT_ROOT:~0,-1%"

echo.
echo ===== Bouyomi_Discord セットアップを開始します =====
echo.

rem ---- 事前チェック: pwshの存在確認 ----
where pwsh >nul 2>&1
if errorlevel 1 goto NO_PWSH

goto PRECHECK_OK

:NO_PWSH
echo [エラー] pwsh (PowerShell 7) が見つかりません。インストールしてから実行してください。
echo          https://learn.microsoft.com/powershell/scripting/install/installing-powershell
pause
exit /b 1

:PRECHECK_OK
rem ---- 事前チェック: git/uv/ffmpegの確認・自動導入、Irodori-TTS配置先/GPU設定の対話入力 ----
set "PRECHECK_OUT=%TEMP%\bouyomi_precheck_%RANDOM%.tmp"
pwsh -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%tools\setup_precheck.ps1" -ProjectRoot "%PROJECT_ROOT_NOSLASH%" -OutFile "%PRECHECK_OUT%"
if errorlevel 1 goto PRECHECK_FAILED

for /f "usebackq tokens=1,* delims==" %%K in ("%PRECHECK_OUT%") do set "%%K=%%L"
del "%PRECHECK_OUT%" >nul 2>&1

rem git/uvがsetup_precheck.ps1内でwinget自動導入された場合、その更新は
rem ps1の子プロセス内に閉じており、このsetup.bat自身のPATHには反映されない。
rem レジストリから読み直して、同一セッション内でもgit/uvコマンドを使えるようにする。
set "MACHINE_PATH="
set "USER_PATH="
for /f "usebackq skip=2 tokens=2,*" %%A in (`reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul`) do set "MACHINE_PATH=%%B"
for /f "usebackq skip=2 tokens=2,*" %%A in (`reg query "HKCU\Environment" /v Path 2^>nul`) do set "USER_PATH=%%B"
if defined MACHINE_PATH if defined USER_PATH set "PATH=%MACHINE_PATH%;%USER_PATH%"
if defined MACHINE_PATH if not defined USER_PATH set "PATH=%MACHINE_PATH%"

echo.
echo   Irodori-TTS配置先: %IRODORI_DIR%
echo   GPU extra        : %IRODORI_EXTRA%

goto PRECHECK_DONE

:PRECHECK_FAILED
echo.
echo [エラー] 事前チェックに失敗しました。上記メッセージを確認してください。
pause
exit /b 1

:PRECHECK_DONE
rem ---- 1. Irodori-TTS本体の取得 ----
echo [1/6] Irodori-TTS本体を確認しています...
if exist "%IRODORI_DIR%\pyproject.toml" goto SKIP_CLONE

echo       -^> "%IRODORI_DIR%" が見つからないため、GitHubから取得します。
git clone https://github.com/Aratako/Irodori-TTS.git "%IRODORI_DIR%"
if errorlevel 1 goto CLONE_FAILED
goto CLONE_DONE

:CLONE_FAILED
echo [エラー] Irodori-TTSのクローンに失敗しました。
pause
exit /b 1

:SKIP_CLONE
echo       -^> 既に "%IRODORI_DIR%" にセットアップ済みの為、取得をスキップします。

:CLONE_DONE
rem ---- 2. Irodori-TTS側のvenv/依存関係の構築 ----
echo.
echo [2/6] Irodori-TTSの依存関係を構築しています (uv sync --extra %IRODORI_EXTRA%)...
pushd "%IRODORI_DIR%"
if errorlevel 1 goto PUSHD_IRODORI_FAILED

uv sync --extra %IRODORI_EXTRA%
if errorlevel 1 goto UV_SYNC_IRODORI_FAILED
goto UV_SYNC_IRODORI_OK

:PUSHD_IRODORI_FAILED
echo [エラー] "%IRODORI_DIR%" ディレクトリへの移動に失敗しました。パスを確認してください。
pause
exit /b 1

:UV_SYNC_IRODORI_FAILED
echo [エラー] Irodori-TTSの "uv sync" に失敗しました。
popd
pause
exit /b 1

:UV_SYNC_IRODORI_OK
if not exist ".venv\Scripts\python.exe" goto VENV_NOT_FOUND

rem ---- 3. TTSサイドカー用の追加パッケージインストール ----
echo.
echo [3/6] Irodori-TTSのvenvに fastapi / uvicorn を追加インストールしています...
".venv\Scripts\python.exe" -m pip install fastapi "uvicorn[standard]"
if errorlevel 1 goto PIP_INSTALL_FAILED
goto PIP_INSTALL_OK

:VENV_NOT_FOUND
echo [エラー] Irodori-TTSのvenv (.venv\Scripts\python.exe) が見つかりません。"uv sync" が正常に完了しているか確認してください。
popd
pause
exit /b 1

:PIP_INSTALL_FAILED
echo [エラー] fastapi / uvicorn のインストールに失敗しました。
popd
pause
exit /b 1

:PIP_INSTALL_OK
popd

rem ---- 4. Bouyomi_Discord側(自環境)の依存関係インストール ----
echo.
echo [4/6] Bouyomi_Discordの依存関係を構築しています (uv sync)...
pushd "%PROJECT_ROOT%"
if errorlevel 1 goto PUSHD_PROJECT_ROOT_FAILED

uv sync
if errorlevel 1 goto UV_SYNC_PROJECT_FAILED
goto UV_SYNC_PROJECT_OK

:PUSHD_PROJECT_ROOT_FAILED
echo [エラー] "%PROJECT_ROOT%" ディレクトリへの移動に失敗しました。パスを確認してください。
pause
exit /b 1

:UV_SYNC_PROJECT_FAILED
echo [エラー] Bouyomi_Discordの "uv sync" に失敗しました。
popd
pause
exit /b 1

:UV_SYNC_PROJECT_OK
rem ---- 5. .envの初期生成・Irodoriパスの自動設定 ----
echo.
echo [5/6] .env ファイルの初期設定を行っています...
pwsh -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%tools\setup_env.ps1" -IrodoriDir "%IRODORI_DIR%"
if errorlevel 1 goto ENV_SETUP_FAILED
goto ENV_SETUP_OK

:ENV_SETUP_FAILED
echo [エラー] .env の初期設定に失敗しました。
popd
pause
exit /b 1

:ENV_SETUP_OK
popd

rem ---- 6. 完了と必要な環境変数の設定案内 ----
echo.
echo [6/6] セットアップが完了しました。
echo.
echo =====================================================================
echo  以下の項目は自動設定できないため、".env" を開いて手動で設定してください。
echo =====================================================================
echo   - DISCORD_BOT_TOKEN        (Discord Botのトークン)
echo   - DISCORD_ADMIN_USER_ID    (管理者権限を持つユーザーのID)
echo   - DISCORD_GUILD_ID         (対象となるサーバーのID)
echo   - TWITCH_CLIENT_ID         (TwitchアプリのClient ID)
echo   - TWITCH_OAUTH_TOKEN       (TwitchのOAuthトークン)
echo   - TWITCH_BOT_NICK          (TwitchのBot名)
echo   - TWITCH_CHANNEL           (Twitchの対象チャンネル名)
echo   - IRODORI_TTS_REF_WAV      (参考音声wavファイルのパス)
echo   - FFMPEG_PATH              (ffmpegの実行パス。必要な場合)
echo =====================================================================
echo.
echo ".env" をテキストエディタで開き、上記の設定を入力してください。
echo.
pause
exit /b 0
