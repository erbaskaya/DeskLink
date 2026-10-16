@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title DeskLink - Python Tani - v0.1.5
call "%~dp0desklink_run.bat" diagnostic
set "RETURN_CODE=%ERRORLEVEL%"
echo.
echo Tani tamamlandi. Hata kodu: %RETURN_CODE%
echo DeskLink-python-tani-log.txt dosyasini paylasabilirsiniz.
pause
exit /b %RETURN_CODE%
