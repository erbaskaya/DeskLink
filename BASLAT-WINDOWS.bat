@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title DeskLink - Windows Baslat - v0.3.0
call "%~dp0desklink_run.bat" client
set "RETURN_CODE=%ERRORLEVEL%"
echo.
echo DeskLink kapandi. Hata kodu: %RETURN_CODE%
echo Pencereyi kapatmak icin bir tusa basin.
pause >nul
exit /b %RETURN_CODE%
