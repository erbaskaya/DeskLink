#!/bin/bash
# Shared macOS launcher used by the two .command shortcuts.
# Dependencies are installed to ~/Library/Application Support/DeskLink, not system Python.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-client}"
if [ "$MODE" != "client" ] && [ "$MODE" != "server" ]; then
  echo "Gecersiz DeskLink modu: $MODE"
  exit 2
fi

echo "========================================================="
echo " DESKLINK v0.3.0 - macOS $MODE"
echo "========================================================="

PYTHON=""
find_python() {
  local candidate
  for candidate in \
    python3.13 python3.12 python3.11 python3.14 python3 python \
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
    /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    if ! "$candidate" -c 'import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
      continue
    fi
    if [ "$MODE" = "client" ] && ! "$candidate" -c 'import tkinter' >/dev/null 2>&1; then
      continue
    fi
    PYTHON="$candidate"
    return 0
  done
  return 1
}

if ! find_python; then
  echo "HATA: Python 3.11+ ve (istemci icin) Tkinter bulunamadi."
  echo "Resmi macOS Python kurulumunu indirin: https://www.python.org/downloads/macos/"
  echo "Homebrew kullaniliyorsa ilgili python-tk paketini de yukleyin."
  echo "Kurulumdan sonra bu dosyayi tekrar acin."
  printf '\nKapatmak icin Enter: '
  read -r _
  exit 3
fi

echo "Python: $PYTHON"
echo "Ilk calistirmada kutuphane indirmek icin internet gerekebilir."
echo ""
if [ "${DESKLINK_LAN_TEST:-0}" = "1" ]; then
  echo "UYARI: Sifresiz LAN test sunucusu acilacak. Portu internete acmayin!"
fi
"$PYTHON" "$DIR/desklink_bootstrap.py" "$MODE"
RESULT=$?
echo ""
echo "DeskLink kapandi / hata kodu: $RESULT"
if [ "$RESULT" -ne 0 ]; then
  echo "Program klasorundeki log dosyasini kontrol edin."
fi
printf '\nPencereyi kapatmak icin Enter: '
read -r _
exit "$RESULT"
