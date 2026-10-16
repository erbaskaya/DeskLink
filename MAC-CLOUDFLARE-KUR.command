#!/bin/bash
# Run on Mac. Deploys only the relay; does not install a hidden remote-access service.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/cloudflare" || exit 1
echo '=========================================================='
echo 'DESKLINK v0.3.1 - CLOUDFLARE RELAY KURULUMU'
echo '=========================================================='
echo 'Node.js 22+ ve ucretsiz Cloudflare hesabi gerekir.'
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo 'HATA: Node.js 22+ kurun: https://nodejs.org/en/download'
  read -r -p 'Kapatmak icin Enter: ' _
  exit 2
fi
if ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)'; then
  echo 'HATA: Node.js en az 22 surumu olmali.'
  read -r -p 'Kapatmak icin Enter: ' _
  exit 2
fi
node --version
npm --version
npm install --no-audit --no-fund || exit 1
npx wrangler login || exit 1
npx wrangler deploy
RESULT=$?
if [ "$RESULT" -eq 0 ]; then
  echo 'HAZIR. https://...workers.dev adresini wss://...workers.dev/ws olarak DeskLink icine girin.'
else
  echo 'HATA: Yukleme tamamlanamadi. Yukaridaki mesaji inceleyin.'
fi
read -r -p 'Kapatmak icin Enter: ' _
exit "$RESULT"
