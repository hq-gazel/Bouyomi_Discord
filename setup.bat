@echo off
setlocal

rem =====================================================================
rem  Bouyomi_Discord �Z�b�g�A�b�v�X�N���v�g
rem
rem  Irodori-TTS�{�̂̎擾�Evenv�\�z�E.env�̋@�B�I�Ɍ��܂鍀�ڂ̎������͂�
rem  �s���BDiscord/Twitch�֘A�̃g�[�N���擾�ȂǁA���[�U�[�{�l���蓮��
rem  �s���K�v������ݒ�ɂ͈�ؐG��Ȃ�(.env�ɂ͋󗓂̂܂܎c��)�B
rem
rem  ����1: cmd.exe�̓o�b�`�t�@�C������ɃV�X�e����ANSI�R�[�h�y�[�W(���{��
rem  Windows�ł͒ʏ�Shift_JIS/CP932)�œǂݍ��ނ��߁A���̃t�@�C�����̂�
rem  Shift_JIS(CP932)�ŕۑ����邱�ƁBUTF-8�ŕۑ�����ƁA���o�C�g������
rem  �o�C�g���E��cmd.exe�̓����o�b�t�@���E��2�o�C�g�������߂ƃY���āA
rem  ���{����܂ލs�������_���ɕ��������E����߂����(���m�̕s�)�B
rem  ���̂��ߖ{�t�@�C����chcp 65001���g�p���Ȃ��B
rem
rem  ����2: �O�̂��߁Aif/else�̕����s�̊ۊ��ʃu���b�N���g�킸�Agoto ��
rem  ��郉�x������݂̂Ő��䂵�Ă���B
rem =====================================================================

rem ---- �ݒ� (���ɍ��킹�ĕK�v�ł���Ώ��������Ă�������) -----------
rem Irodori-TTS�̐ݒu��p�X�B���ɕʂ̏ꏊ�ɃZ�b�g�A�b�v�ς݂̏ꍇ�͂�����
rem ����������B
set "IRODORI_DIR=C:\path\to\Irodori-TTS"

rem uv��GPU extra���BNVIDIA GPU(CUDA)���Ȃ� "cu128" �̂܂܁B
rem CPU���̏ꍇ�� "cpu" �ɕύX����B
set "IRODORI_EXTRA=cu128"
rem ----------------------------------------------------------------------

set "PROJECT_ROOT=%~dp0"

echo.
echo ===== Bouyomi_Discord �Z�b�g�A�b�v���J�n���܂� =====
echo.

rem ---- ���O�`�F�b�N: �K�v�ȃR�}���h�̑��݊m�F ----
where git >nul 2>&1
if errorlevel 1 goto NO_GIT

where uv >nul 2>&1
if errorlevel 1 goto NO_UV

where pwsh >nul 2>&1
if errorlevel 1 goto NO_PWSH

goto PRECHECK_OK

:NO_GIT
echo [�G���[] git ��������܂���BGit���C���X�g�[�����Ă���Ď��s���Ă��������B
echo          https://git-scm.com/downloads
pause
exit /b 1

:NO_UV
echo [�G���[] uv ��������܂���Buv���C���X�g�[�����Ă���Ď��s���Ă��������B
echo          https://docs.astral.sh/uv/getting-started/installation/
pause
exit /b 1

:NO_PWSH
echo [�G���[] pwsh (PowerShell 7) ��������܂���B�C���X�g�[�����Ă���Ď��s���Ă��������B
echo          https://learn.microsoft.com/powershell/scripting/install/installing-powershell
pause
exit /b 1

:PRECHECK_OK
rem ---- 1. Irodori-TTS�{�̂̎擾 ----
echo [1/6] Irodori-TTS�{�̂��m�F���Ă��܂�...
if exist "%IRODORI_DIR%\pyproject.toml" goto SKIP_CLONE

echo       -^> "%IRODORI_DIR%" ��������Ȃ����߁AGitHub����擾���܂��B
git clone https://github.com/Aratako/Irodori-TTS.git "%IRODORI_DIR%"
if errorlevel 1 goto CLONE_FAILED
goto CLONE_DONE

:CLONE_FAILED
echo [�G���[] Irodori-TTS�̃N���[���Ɏ��s���܂����B
pause
exit /b 1

:SKIP_CLONE
echo       -^> ���� "%IRODORI_DIR%" �ɃZ�b�g�A�b�v�ς݂̂��߁A�擾���X�L�b�v���܂��B

:CLONE_DONE
rem ---- 2. Irodori-TTS����venv/�ˑ��֌W���\�z ----
echo.
echo [2/6] Irodori-TTS�̈ˑ��֌W���\�z���Ă��܂� (uv sync --extra %IRODORI_EXTRA%)...
pushd "%IRODORI_DIR%"

uv sync --extra %IRODORI_EXTRA%
if errorlevel 1 goto UV_SYNC_IRODORI_FAILED
goto UV_SYNC_IRODORI_OK

:UV_SYNC_IRODORI_FAILED
echo [�G���[] Irodori-TTS�� "uv sync" �Ɏ��s���܂����B
popd
pause
exit /b 1

:UV_SYNC_IRODORI_OK
rem ---- 3. TTS�T�C�h�J�[�p�̒ǉ��p�b�P�[�W���C���X�g�[�� ----
echo.
echo [3/6] Irodori-TTS��venv�� fastapi / uvicorn ��ǉ��C���X�g�[�����Ă��܂�...
".venv\Scripts\python.exe" -m pip install fastapi "uvicorn[standard]"
if errorlevel 1 goto PIP_INSTALL_FAILED
goto PIP_INSTALL_OK

:PIP_INSTALL_FAILED
echo [�G���[] fastapi / uvicorn �̃C���X�g�[���Ɏ��s���܂����B
popd
pause
exit /b 1

:PIP_INSTALL_OK
popd

rem ---- 4. Bouyomi_Discord���g�̈ˑ��֌W���C���X�g�[�� ----
echo.
echo [4/6] Bouyomi_Discord�̈ˑ��֌W���\�z���Ă��܂� (uv sync)...
pushd "%PROJECT_ROOT%"

uv sync
if errorlevel 1 goto UV_SYNC_PROJECT_FAILED
goto UV_SYNC_PROJECT_OK

:UV_SYNC_PROJECT_FAILED
echo [�G���[] Bouyomi_Discord�� "uv sync" �Ɏ��s���܂����B
popd
pause
exit /b 1

:UV_SYNC_PROJECT_OK
rem ---- 5. .env�̎��������E�@�B�I���ڂ̎������� ----
echo.
echo [5/6] .env �t�@�C�����������Ă��܂�...
pwsh -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%tools\setup_env.ps1" -IrodoriDir "%IRODORI_DIR%"
if errorlevel 1 goto ENV_SETUP_FAILED
goto ENV_SETUP_OK

:ENV_SETUP_FAILED
echo [�G���[] .env �̏����Ɏ��s���܂����B
popd
pause
exit /b 1

:ENV_SETUP_OK
popd

rem ---- 6. �蓮�ݒ肪�K�v�ȍ��ڂ̈ē� ----
echo.
echo [6/6] �Z�b�g�A�b�v���������܂����B
echo.
echo =====================================================================
echo  �ȉ��̍��ڂ͎����ݒ�ł��Ȃ����߁A".env" ���蓮�ŕҏW���Ă��������B
echo =====================================================================
echo   - DISCORD_BOT_TOKEN        (Discord Bot�g�[�N��)
echo   - DISCORD_ADMIN_USER_ID    (�Ǘ��҂�Discord���[�U�[ID)
echo   - DISCORD_GUILD_ID         (�C��: �ΏۃT�[�o�[ID)
echo   - TWITCH_CLIENT_ID         (Twitch�A�v���P�[�V�����̃N���C�A���g ID)
echo   - TWITCH_OAUTH_TOKEN       (Twitch�`���b�g�{�b�g�pOAuth�g�[�N��)
echo   - TWITCH_BOT_NICK          (Twitch�`���b�g�{�b�g�̃j�b�N�l�[��)
echo   - TWITCH_CHANNEL           (�R�����g�擾�Ώۂ�Twitch�`�����l����)
echo   - IRODORI_TTS_REF_WAV      (�Q�Ɖ���wav�t�@�C���̃p�X)
echo   - FFMPEG_PATH              (�C��: ffmpeg���C���X�g�[���̏ꍇ)
echo =====================================================================
echo.
echo ".env" ���e�L�X�g�G�f�B�^�ŊJ���ď�L�̍��ڂ���͂��Ă��������B
echo.
pause
exit /b 0
