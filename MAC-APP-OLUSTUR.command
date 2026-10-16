#!/bin/bash
# Build .app on the Mac itself. PyInstaller cannot build a native macOS app on Windows.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "DeskLink v0.5.0 - macOS .app olusturma"
fail() {
  echo "HATA: $1"
  printf '\nPencereyi kapatmak icin Enter: '
  read -r _
  exit 1
}
if [ "$(uname -s)" != "Darwin" ]; then
  echo "Bu komut yalnizca macOS uzerinde calisir."
  exit 1
fi
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.14 python3 python \
  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  /Library/Frameworks/Python.framework/Versions/3.11/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1 && \
      "$candidate" -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  fail "Tkinter destekli Python 3.11+ bulunamadi. python.org macOS surumunu kurun."
fi
VENV="$DIR/.build-macos"
"$PYTHON" -m venv "$VENV" || fail "Paketleme sanal ortami olusturulamadi."
"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade -r "$DIR/requirements-client.txt" 'pyinstaller>=6.9,<7' || fail "PyInstaller veya istemci bagimliliklari kurulamadı."
cd "$DIR" || fail "Proje klasorune gecilemiyor."
"$VENV/bin/python" build_standalone.py
RESULT=$?
if [ "$RESULT" -eq 0 ]; then
  echo "HAZIR: $DIR/dist/DeskLink.app"
  echo "Not: Bu .app imzasizdir. Genis dagitim icin Apple kod imzasi ve notarizasyon gerekir."
else
  echo "HATA: Mac .app build tamamlanamadi. Yukaridaki mesaji paylasin."
fi
printf '\nKapatmak icin Enter: '; read -r _
exit "$RESULT"
