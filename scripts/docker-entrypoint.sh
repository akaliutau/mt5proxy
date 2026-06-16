#!/usr/bin/env bash
set -euo pipefail

mkdir -p /config /logs /run/mt5-proxy /home/trader
chown -R trader:trader /config /logs /run/mt5-proxy /home/trader

# Keep inherited env for gosu. supervisord itself runs as trader and keeps all child processes self-healing.
exec gosu trader /usr/local/bin/start-all.sh
