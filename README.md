# MT5 Proxy Docker image — original bridge, automated runtime

This version deliberately keeps the original working Wine/MT5/bridge path intact.
The bridge is still started exactly as before from `mt5-stack.sh`:

```bash
wine "$WINE_PYTHON_EXE" -m mt5linux --host 0.0.0.0 -p 8001
```

Automation is added around the original scripts only:

- `docker compose up -d` starts Xvfb, Fluxbox, x11vnc, noVNC, FastAPI, MT5, Wine Python setup, and the bridge.
- `start-all.sh` restarts dead Linux-side services and restarts `mt5-stack.sh` if it exits.
- `mt5-stack.sh` keeps the original MT5/bridge self-healing loop.
- Docker Compose uses `restart: unless-stopped` for VM/GCP deployment.
- No Supervisor is used in this build.

## Local run

```bash
cp .env.example .env
nano .env
./tests/local_run.sh
```

Open noVNC:

```text
http://127.0.0.1:3000/vnc.html
```

Readiness:

```bash
curl -H 'X-API-Key: dev-api-key' 'http://127.0.0.1:8000/ready?deep=true'
```

Run external tests:

```bash
./tests/local_test.sh
```

Demo mutation test only:

```bash
# set TRADING_ENABLED=true first
./tests/local_test.sh --place-trades
```

## Restart bridge only

```bash
docker compose exec mt5proxy bash -lc 'gosu trader restart_bridge_original.sh'
```

## Clean persistent Wine prefix after experimental/broken builds

Previous failed experimental images may have modified the persistent `/config/.wine` volume. To preserve it before reset:

```bash
docker compose down
vol=$(docker volume ls --format '{{.Name}}' | grep 'mt5proxy_config' | head -1)
docker run --rm -v "$vol:/config" busybox sh -lc 'mv /config/.wine /config/.wine.broken.$(date +%s) 2>/dev/null || true'
docker compose up -d --force-recreate
```

Then initialize/login MT5 in noVNC if needed. The original stack will install Windows Python and start the bridge automatically.

## GCP VM

Keep ports bound to `127.0.0.1` and tunnel from your laptop:

```bash
gcloud compute ssh YOUR_VM --zone YOUR_ZONE -- \
  -L 3000:127.0.0.1:3000 \
  -L 8000:127.0.0.1:8000
```
