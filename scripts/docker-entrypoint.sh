#!/usr/bin/env bash
set -euo pipefail

mkdir -p /config /logs /run/mt5-proxy /home/trader
chown -R trader:trader /config /logs /run/mt5-proxy /home/trader

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/mt5proxy.conf -n
