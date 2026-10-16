@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title DeskLink - Cloudflare Relay Kurulumu v0.3.1

echo ==========================================================
echo  DESKLINK v0.3.1 - CLOUDFLARE UCRETSIZ RELAY KURULUMU
echo ==========================================================
echo.
echo NOT: Node.js, yalnizca Cloudflare sunucusunu kurmak icin gerekir.
echo Windows veya Mac uzerinden DeskLink kullanirken Node.js gerekmez.
echo Onerilen Node.js: 22 veya 24 LTS. Varsa yeniden kurmayin.
echo.

if not exist "%~dp0cloudflare\package.json" goto nofolder
cd /d "%~dp0cloudflare"
if errorlevel 1 goto nofolder

where node >nul 2>&1
if errorlevel 1 goto nonode
where npm >nul 2>&1
if errorlevel 1 goto nonode

echo [KONTROL] Node.js surumu:
node --version
if errorlevel 1 goto nonode
echo [KONTROL] npm surumu:
rem IMPORTANT: npm is npm.cmd on Windows; CALL is required from a .bat file.
call npm --version
if errorlevel 1 goto nonode
node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 22 ? 0 : 1)"
if errorlevel 1 goto oldnode

echo.
echo [1/3] Cloudflare Wrangler kuruluyor; bu islem biraz surebilir...
call npm install --no-audit --no-fund
if errorlevel 1 goto failure

echo.
echo [2/3] Cloudflare hesabiniza giris yapin. Tarayici acilabilir...
call npx wrangler login
if errorlevel 1 goto failure

echo.
echo [3/3] DeskLink relay Cloudflare'a yukleniyor...
call npx wrangler deploy
if errorlevel 1 goto failure

echo.
echo ==========================================================
echo KURULUM TAMAMLANDI.
echo Yukaridaki gercek https://...workers.dev adresini bulun.
echo DeskLink'te hem Windows hem Mac uzerinde su bicimde girin:
echo wss://desklink-relay.SIZIN-ALT-ALANINIZ.workers.dev/ws
echo ==========================================================
echo.
echo Bilgi: Farkli internetlerden baglanirken yerel test sunucusu gerekmez.
goto success

:nofolder
echo.
echo HATA: cloudflare klasoru veya package.json bulunamadi.
echo ZIP'in tumunu ayiklayin; BAT dosyasini tek basina tasimayin.
goto error

:nonode
echo.
echo HATA: node.exe veya npm.cmd calistirilamadi.
echo Node.js 24 LTS: https://nodejs.org/en/download
echo Yukledikten sonra yeni bir CMD penceresi acin.
goto error

:oldnode
echo.
echo HATA: Node.js surumunuz guncel degil.
echo Tavsiye: Node.js 24 LTS: https://nodejs.org/en/download
goto error

:failure
echo.
echo HATA: Cloudflare kurulumu veya deploy basarisiz oldu.
echo Yukaridaki hata satirlarini paylasin; API token / sifre paylasmayin.
goto error

:error
echo.
echo Islem tamamlanamadi. Pencere simdi acik kalacak.
echo Kapatmak icin bir tusa basin.
pause >nul
exit /b 1

:success
echo Islem bitti. Pencereyi kapatmak icin bir tusa basin.
pause >nul
exit /b 0
