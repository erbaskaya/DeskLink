@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title DeskLink - LAN Test Sunucusu - v0.2.0
echo.
echo DIKKAT: Sifresiz ws:// yalnizca guvendiginiz yerel agda kullanilmali.
echo Modemi yonlendirip 8765 portunu internete ACMAYIN.
echo.
set "DESKLINK_LAN_TEST=1"
call "%~dp0desklink_run.bat" server
set "RETURN_CODE=%ERRORLEVEL%"
echo.
echo LAN test sunucusu durdu. Hata kodu: %RETURN_CODE%
pause
exit /b %RETURN_CODE%
