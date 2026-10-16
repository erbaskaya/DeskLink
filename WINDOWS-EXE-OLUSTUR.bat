@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title DeskLink v0.4.0 - Windows EXE olustur

echo =========================================================
echo DeskLink v0.4.0 - Windows EXE derleme
echo =========================================================
echo Kurulu Python 3.11+ kontrol ediliyor...
set "PY_EXEC="
call :probe py -3.13
if defined PY_EXEC goto ready
call :probe py -3.12
if defined PY_EXEC goto ready
call :probe py -3.11
if defined PY_EXEC goto ready
call :probe py -3.14
if defined PY_EXEC goto ready
call :probe py -3
if defined PY_EXEC goto ready
call :probe python
if defined PY_EXEC goto ready

echo HATA: Python 3.11+ calisma ortami bulunamadi.
goto failed

:ready
echo Python hazir: %PY_EXEC%
%PY_EXEC% -m venv "%~dp0.build-windows"
if errorlevel 1 goto failed
"%~dp0.build-windows\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-client.txt "pyinstaller>=6.12,<7"
if errorlevel 1 goto failed
"%~dp0.build-windows\Scripts\python.exe" build_standalone.py
if errorlevel 1 goto failed
echo.
echo EXE hazir: %~dp0dist\DeskLink.exe
echo Yalnizca Windows'ta calisir. Mac icin MAC-APP-OLUSTUR.command kullanin.
pause
exit /b 0

:probe
%* -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
set "PY_EXEC=%*"
exit /b 0

:failed
echo.
echo HATA: Windows EXE derlemesi tamamlanamadi. Yukaridaki hata metnini inceleyin.
pause
exit /b 1
