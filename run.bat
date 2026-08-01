@echo off
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 goto CD_FAILED

echo 終了するにはこの画面で CTRL + C を押してください。
uv run main.py
if errorlevel 1 goto RUN_FAILED
goto END

:CD_FAILED
echo [エラー] プロジェクトディレクトリへの移動に失敗しました: %~dp0
pause
exit /b 1

:RUN_FAILED
echo [エラー] "uv run main.py" が異常終了しました。
pause
exit /b 1

:END
