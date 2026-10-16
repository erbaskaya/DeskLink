#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
exec /bin/bash "$DIR/mac_run.sh" client
