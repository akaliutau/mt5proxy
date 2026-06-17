# MT5 Proxy Docker image

This project builds one all-in-one Ubuntu 22.04 container for MT5 under Wine, the Windows-side `mt5linux` bridge, noVNC, and the FastAPI proxy.

Important implementation points:

- Wine is installed from the official WineHQ Ubuntu 22.04 / `jammy` repository, default package `winehq-staging`.
- The image does not use `gmag11/metatrader5_vnc`.
- Windows Python stays at 3.9.13.
- Windows package defaults stay pinned to `MetaTrader5==5.0.36`, `mt5linux==1.0.3`, `rpyc==6.0.2`, and `numpy==1.26.4`.
- `supervisord` starts and restarts Xvfb, Fluxbox, x11vnc, noVNC, the API, and the MT5 stack.
- The MT5 stack automatically initializes Wine, installs/checks Windows Python packages, attempts MT5 auto-install, starts MT5, starts the bridge, and repeatedly probes MT5 initialization through the bridge.

## Ports

| Host URL/port                        | Container | Purpose                           |
|--------------------------------------|----------:|-----------------------------------|
| `http://127.0.0.1:3000/vnc.html`     |    `6080` | noVNC desktop                     |
| `127.0.0.1:5900`                     |    `5900` | raw VNC                           |
| `http://127.0.0.1:8000/health`       |    `8000` | REST API liveness                 |
| `http://127.0.0.1:8000/health/ready` |    `8000` | bridge + MT5 initialize readiness |
| `127.0.0.1:8001`                     |    `8001` | mt5linux bridge debug             |

All compose ports are bound to `127.0.0.1` by default, suitable for a GCP VM behind SSH tunnels.

## 1. Local build/run command

```bash
cp .env.example .env
nano .env
./scripts/local_up.sh
```

`local_up.sh` runs:

```bash
docker compose build
docker compose up -d --remove-orphans
docker compose ps
```

Follow logs:

```bash
docker compose logs -f mt5proxy
```

Open noVNC:

```text
http://127.0.0.1:3000/vnc.html
```

## 2. Local test command

```bash
./tests/run_external_tests.sh
```

The test command creates a local Python venv, waits for `/health/ready`, then runs the external API smoke tests against `http://127.0.0.1:8000`.

Read-only tests require a usable logged-in MT5 terminal/session. Mutation tests are disabled by default.

Demo mutation testing only:

```bash
TRADING_ENABLED=true docker compose up -d --force-recreate
PLACE_TRADES=true ./tests/run_external_tests.sh
```

in terminal: 

```text
Tools → Options → Expert Advisors → Allow algorithmic trading
```

## 3. Clean reset when switching Wine builds

If a previous container created a broken Wine prefix using the wrong Wine packages, reset the local named volumes before retesting:

```bash
./scripts/local_reset.sh
./scripts/local_up.sh
./tests/run_external_tests.sh
```

This removes the local `/config` and `/logs` named volumes. Do not use it on a VM where the MT5 login/profile must be preserved unless you have backed it up.

## 4. Autostart/self-healing design

The container entrypoint starts `supervisord`. Supervisor manages:

- `xvfb`
- `fluxbox`
- `x11vnc`
- `novnc`
- `api`
- `mt5-stack`

The MT5 stack process manages Wine/MT5-specific lifecycle:

1. Waits for X.
2. Initializes the Wine prefix.
3. Installs Wine Mono non-interactively when needed.
4. Ensures Windows embeddable Python and bridge packages are installed.
5. Attempts MT5 `/auto` install when `MT5_AUTOINSTALL=true`.
6. Starts MT5 terminal.
7. Starts the Windows-side `mt5linux` bridge.
8. Repeatedly probes `mt5.initialize()` through the bridge and logs failures to `/logs/bridge-init.log`.
9. Restarts MT5 or bridge if their processes/socket disappear.

Manual commands still exist for debugging, but normal boot should not require them:

```bash
docker exec -it mt5-proxy-scratch bash

gosu trader bash -lc 'wine_sanity.sh'
gosu trader bash -lc 'install_wine_python.sh'
gosu trader bash -lc 'start_mt5.sh'
gosu trader bash -lc 'start_bridge.sh'
```

`start_bridge.sh` now auto-runs `install_wine_python.sh` if Python/imports are missing, then starts the bridge.

## 5. Health endpoints

Liveness, used by Docker healthcheck:

```bash
curl http://127.0.0.1:8000/health
```

Readiness, used by local tests:

```bash
curl http://127.0.0.1:8000/health/ready
```

`/health/ready` requires more than an open bridge socket. It connects to the bridge and runs `mt5.initialize()` through the Windows-side MT5 Python API.

## 6. Important environment variables

| Variable | Default | Meaning |
|---|---|---|
| `BASE_IMAGE` | `ubuntu:22.04` | Docker base image |
| `WINEHQ_UBUNTU_CODENAME` | `jammy` | WineHQ Ubuntu repo codename |
| `WINEHQ_PACKAGE` | `winehq-staging` | WineHQ package to install |
| `MT5_AUTOINSTALL` | `true` | Try MT5 installer `/auto` during boot |
| `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` | empty | Optional auto-login credentials used by `mt5.initialize()` |
| `API_KEY` | `dev-api-key` | API key for `/v1/*` endpoints |
| `TRADING_ENABLED` | `false` | Must be true for mutation/trading endpoints |
| `READY_MT5_TIMEOUT_MS` | `15000` | Timeout used by `/health/ready` initialization probe |

## 7. GCP VM access

Keep ports bound to localhost on the VM and tunnel from your laptop:

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

## 8. Logs

Useful logs inside the container:

```bash
/logs/supervisord.log
/logs/mt5-stack.supervisor.log
/logs/wine-python-install.log
/logs/mt5-install.log
/logs/mt5-terminal.log
/logs/mt5-bridge.log
/logs/bridge-init.log
/logs/api.supervisor.log
```

From host:

```bash
docker compose logs -f mt5proxy
docker exec -it mt5-proxy-scratch bash -lc 'ls -lh /logs && tail -100 /logs/bridge-init.log'
```
