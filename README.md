# MT5 Proxy from-scratch all-in-one Docker image

This project builds one container from a plain Ubuntu base image. It does **not** use `gmag11/metatrader5_vnc` and does **not** add the WineHQ apt repository, so it avoids the WineHQ `NO_PUBKEY 76F1A20FF987672F` build failure.

The image contains:

- Ubuntu base image, default `ubuntu:22.04`
- Wine from Ubuntu apt repositories
- Xvfb virtual display
- Fluxbox desktop
- x11vnc + noVNC browser desktop
- MetaTrader 5 under Wine
- Windows Python 3.9 in Wine
- Windows `MetaTrader5` package
- `mt5linux` bridge on port `8001`
- FastAPI proxy on port `8000`

Host machine can be Ubuntu 24.04. The container defaults to Ubuntu 22.04 because MT5/Wine in Docker has been more reliable there.

## Ports

| Host URL/port | Container | Purpose |
|---|---:|---|
| `http://127.0.0.1:3000/vnc.html` | `6080` | noVNC desktop |
| `127.0.0.1:5900` | `5900` | raw VNC |
| `http://127.0.0.1:8000/health` | `8000` | REST API |
| `127.0.0.1:8001` | `8001` | mt5linux bridge debug |

All ports are bound to `127.0.0.1` by default.

## 1. Build and run

```bash
cp .env.example .env
nano .env

docker compose build --no-cache
docker compose up -d

docker compose ps
docker compose logs -f mt5proxy
```

Open desktop stream:

```text
http://127.0.0.1:3000/vnc.html
```

Check API:

```bash
curl http://127.0.0.1:8000/health
```

## 2. First-time Wine/MT5 checks

Enter container:

```bash
docker exec -it mt5-proxy-scratch bash
```

Run Wine sanity as the `trader` user:

```bash
gosu trader bash -lc 'wine_sanity.sh'
```

Expected final line:

```text
WINE_SANITY_PASSED
```

If you see first-run windows in noVNC, handle them there, then rerun the command.

## 3. Install/login MT5

The container attempts automatic MT5 install with `mt5setup.exe /auto` when `MT5_AUTOINSTALL=true`.

If MT5 is not installed automatically, run:

```bash
docker exec -it mt5-proxy-scratch bash
gosu trader bash -lc 'install_mt5_manual.sh'
```

Then finish the installer in noVNC:

```text
http://127.0.0.1:3000/vnc.html
```

After installation, log in manually:

```text
File -> Login to Trade Account
```

Enable your symbol:

```text
View -> Symbols -> EURUSD -> Show Symbol
```

## 4. Install/check Windows Python and packages

The container also tries this automatically. Manual command:

```bash
docker exec -it mt5-proxy-scratch bash
gosu trader bash -lc 'install_wine_python.sh'
```

## 5. Start MT5 and bridge manually if needed

```bash
docker exec -it mt5-proxy-scratch bash
gosu trader bash -lc 'start_mt5.sh'
gosu trader bash -lc 'start_bridge.sh'
```

The main supervisor normally starts both automatically. Logs:

```bash
docker exec -it mt5-proxy-scratch bash -lc 'ls -lh /logs && tail -100 /logs/mt5-stack.log && tail -100 /logs/mt5-bridge.log'
```

## 6. Test bridge directly

Read-only:

```bash
docker exec -it mt5-proxy-scratch bash -lc '/opt/mt5-proxy-venv/bin/python /app_tools/direct_bridge_check.py'
```

Expected:

```text
READ_ONLY_BRIDGE_TESTS_PASSED
```

Mutation test on DEMO only:

```bash
docker exec -it mt5-proxy-scratch bash -lc 'CHECK_PLACE_TRADE=true /opt/mt5-proxy-venv/bin/python /app_tools/direct_bridge_check.py'
```

## 7. Test Wine-side MetaTrader5 directly

Read-only:

```bash
docker exec -it mt5-proxy-scratch bash
gosu trader bash -lc 'wine python /usr/local/bin/mt5_wine_direct_smoke.py'
```

Mutation test on DEMO only:

```bash
gosu trader bash -lc 'CHECK_PLACE_TRADE=true wine python /usr/local/bin/mt5_wine_direct_smoke.py'
```

## 8. Test REST API from host

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install requests

python tests/external_test_all_ops.py \
  --base-url http://127.0.0.1:8000 \
  --api-key dev-api-key \
  --symbol EURUSD
```

Enable trading endpoints in `.env` only for demo testing:

```env
TRADING_ENABLED=true
```

Restart:

```bash
docker compose up -d --force-recreate
```

Mutation test:

```bash
python tests/external_test_all_ops.py \
  --base-url http://127.0.0.1:8000 \
  --api-key dev-api-key \
  --symbol EURUSD \
  --volume 0.01 \
  --place-trades
```

## 9. If Wine services still fail

The default compose already uses:

```yaml
security_opt:
  - seccomp=unconfined
```

If Wine still cannot start service processes, try the diagnostic privileged overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.privileged.yml up -d --force-recreate
```

If that fixes Wine, your Docker runtime/security profile was blocking some Wine service behavior.

## 10. GCP access

Keep compose ports localhost-only on the VM. Tunnel from your laptop:

```bash
gcloud compute ssh YOUR_VM --zone YOUR_ZONE -- \
  -L 3000:127.0.0.1:3000 \
  -L 8000:127.0.0.1:8000
```

Open:

```text
http://127.0.0.1:3000/vnc.html
http://127.0.0.1:8000/health
```

## 11. Why no WineHQ apt repo?

Your last build failed because the inherited image had a WineHQ Debian repository but the WineHQ signing key was missing. This from-scratch image avoids that entire path by using Ubuntu repository packages. If you later want WineHQ packages, add the key with `gpg --dearmor` and verify the `.sources` file has `Signed-By=/etc/apt/keyrings/winehq-archive.key` before `apt-get update`.

## Bridge fix notes

The mt5linux bridge server must run in **Windows Python under Wine**:

```bash
wine "$WINE_PYTHON_EXE" -m mt5linux --host 0.0.0.0 -p 8001
```

Linux Python is only the client side. If `/logs/mt5-bridge.log` does not exist, the startup sequence has not reached bridge startup yet. The most common reason is Windows Python installation hanging. This version uses the Python 3.9 embeddable ZIP instead of the interactive Windows installer to avoid that hang.

Manual recovery in an existing container:

```bash
docker exec -it mt5-proxy-scratch bash
pkill -f python-installer.exe || true
pkill -f msiexec.exe || true
gosu trader bash -lc 'wineserver -k || true'
gosu trader bash -lc 'install_wine_python.sh'
gosu trader bash -lc 'start_bridge.sh' >/logs/mt5-bridge.log 2>&1 &
ss -tuln | grep 8001
```
