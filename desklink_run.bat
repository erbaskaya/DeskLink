@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
set "ROLE=%~1"
if /I "%ROLE%"=="server" goto valid_mode
if /I "%ROLE%"=="client" goto valid_mode
if /I "%ROLE%"=="diagnostic" goto valid_mode
echo HATA: desklink_run.bat server ^| client ^| diagnostic
exit /b 2

:valid_mode
pushd "%~dp0"
if errorlevel 1 (
  echo HATA: DeskLink klasoru acilamadi.
  exit /b 2
)
set "LOG=DeskLink-python-tani-log.txt"
if /I "%ROLE%"=="server" set "LOG=DeskLink-sunucu-log.txt"
if /I "%ROLE%"=="client" set "LOG=DeskLink-baslatma-log.txt"
rem Also protect the diagnostic mode against an implicit Python Install Manager download.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"

if /I "%ROLE%"=="diagnostic" goto diagnostic_only

echo =========================================================
echo  DESKLINK v0.2.0 - %ROLE% / DOGRUDAN PYTHON CALISTIRMA
echo =========================================================
echo Python 3.11 veya daha yenisi gercek kod calistirarak araniyor...
echo.

rem Do not silently auto-install runtimes while probing Windows app aliases.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
set "PY_EXEC="
call :probe py -3.13
if defined PY_EXEC goto python_ready
call :probe py -3.14
if defined PY_EXEC goto python_ready
call :probe py -3.12
if defined PY_EXEC goto python_ready
call :probe py -3.11
if defined PY_EXEC goto python_ready
call :probe py -3
if defined PY_EXEC goto python_ready
call :probe python
if defined PY_EXEC goto python_ready
call :probe python3
if defined PY_EXEC goto python_ready

echo HATA: Python 3.11+ bu komutlarla calistirilamadi.
echo YENIDEN KURULUM DENENMEYECEK. Once gercek hata incelenmeli.
call :diagnose
echo.
echo LUTFEN BU DOSYAYI GONDERIN: "%CD%\%LOG%"
popd
exit /b 3

:python_ready
echo Python komutu dogrulandi: %PY_EXEC%
echo.
echo DeskLink %ROLE% baslatiliyor...
echo.
%PY_EXEC% "%~dp0desklink_bootstrap.py" %ROLE%
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo DeskLink hata kodu: %RESULT%
  echo Hata ayrintilari "%CD%\%LOG%" dosyasinda olabilir.
)
popd
exit /b %RESULT%

:probe
rem %* is one of: "py -3.13", "py -3.14", "py -3.12", "py -3.11", "py -3", "python", "python3".
rem Probe by executing actual Python code, not by checking whether py.exe exists.
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not "%ERRORLEVEL%"=="0" exit /b 1
set "PY_EXEC=%*"
exit /b 0

:diagnostic_only
echo =========================================================
echo  DESKLINK v0.2.0 - PYTHON TANI
 echo =========================================================
call :diagnose
echo.
echo Rapor: "%CD%\%LOG%"
popd
exit /b 0

:diagnose
> "%LOG%" echo DeskLink v0.2.0 - Python tanilama
>> "%LOG%" echo Mod: %ROLE%
>> "%LOG%" echo Tarih: %DATE% %TIME%
>> "%LOG%" echo.
>> "%LOG%" echo === where py ===
where py >> "%LOG%" 2>&1
>> "%LOG%" echo.
>> "%LOG%" echo === py list ===
py list >> "%LOG%" 2>&1
>> "%LOG%" echo.
>> "%LOG%" echo === py list --format=exe ===
py list --format=exe >> "%LOG%" 2>&1
>> "%LOG%" echo.
>> "%LOG%" echo === py -3.13 -c runtime test ===
py -3.13 -c "import sys;print(sys.executable);print(sys.version)" >> "%LOG%" 2>&1
>> "%LOG%" echo.
>> "%LOG%" echo === python -c runtime test ===
python -c "import sys;print(sys.executable);print(sys.version)" >> "%LOG%" 2>&1
echo Python tanilama raporu kaydedildi: "%CD%\%LOG%"
exit /b 0
