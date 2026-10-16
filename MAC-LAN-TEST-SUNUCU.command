#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
export DESKLINK_LAN_TEST=1
exec /bin/bash "$DIR/mac_run.sh" server
