@echo off
setlocal EnableExtensions
chcp 65001 >nul
title DeskLink v0.5.0 - Cloudflare Sunucusunu Guncelle
cd /d "%~dp0cloudflare"
echo ========================================================
echo DeskLink 0.5.0 - CLOUDFLARE SUNUCUSU GUNCELLEME
echo ========================================================
echo.
echo Dikkat: Bu islem halihazirdaki desklink-relay Worker kodunu
 echo gunceller. workers.dev adresi ayni kalir.
echo.
where node >nul 2>nul
if errorlevel 1 goto :missing
where npm >nul 2>nul
if errorlevel 1 goto :missing
echo [1/2] Cloudflare paketleri kontrol ediliyor...
call npm install
if errorlevel 1 goto :failed
echo [2/2] Cloudflare Worker dagitiliyor...
call npx wrangler deploy
if errorlevel 1 goto :failed
echo.
echo BASARILI: Sunucu guncellendi. Artik yeni DeskLink .exe/.app kullanin.
goto :done
:missing
echo HATA: Node.js veya npm bulunamadi. Bu yalnizca sunucu yonetici PC icin gereklidir.
goto :done
:failed
echo HATA: Cloudflare yuklemesi basarisiz. CMD hata satirlarini paylasin.
:done
echo.
pause
endlocal
