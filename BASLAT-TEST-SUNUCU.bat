@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title DeskLink - Yerel Test Sunucusu - v0.2.0
call "%~dp0desklink_run.bat" server
set "RETURN_CODE=%ERRORLEVEL%"
echo.
echo Test sunucusu durdu. Hata kodu: %RETURN_CODE%
echo Pencereyi kapatmak icin bir tusa basin.
pause >nul
exit /b %RETURN_CODE%
