# syntax=docker/dockerfile:1.7
# From-scratch MT5 + noVNC + mt5linux bridge + FastAPI proxy.
# Default: Ubuntu 22.04 because Wine/MT5 has been more reliable there than 24.04 in Docker.
ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC \
    DISPLAY=:99 \
    SCREEN_WIDTH=1280 \
    SCREEN_HEIGHT=900 \
    SCREEN_DEPTH=24 \
    WINEPREFIX=/config/.wine \
    WINEARCH=win64 \
    WINEDEBUG=-all \
    LIBGL_ALWAYS_SOFTWARE=1 \
    MESA_LOADER_DRIVER_OVERRIDE=llvmpipe \
    WINEDLLOVERRIDES="mscoree=d;mshtml=d;winemenubuilder.exe=d" \
    NO_AT_BRIDGE=1 \
    API_KEY=dev-api-key \
    TRADING_ENABLED=false \
    MT5LINUX_HOST=127.0.0.1 \
    MT5LINUX_PORT=8001 \
    MT5LINUX_TIMEOUT=300 \
    MT5_TIMEOUT_MS=60000 \
    MT5_TEST_SYMBOL=EURUSD \
    MT5_TEST_VOLUME=0.01 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080 \
    MT5_AUTOINSTALL=true \
    MT5_CMD_OPTIONS="" \
    MT5_FILE="/config/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe" \
    PYTHON_WIN_URL="https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe" \
    PYTHON_EMBED_URL="https://www.python.org/ftp/python/3.9.13/python-3.9.13-embed-amd64.zip" \
    GET_PIP_URL="https://bootstrap.pypa.io/pip/3.9/get-pip.py" \
    WINE_PYTHON_DIR="/config/.wine/drive_c/Python39" \
    WINE_PYTHON_EXE="/config/.wine/drive_c/Python39/python.exe" \
    MT5_SETUP_URL="https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" \
    WINE_MONO_URL="https://dl.winehq.org/wine/wine-mono/10.3.0/wine-mono-10.3.0-x86.msi" \
    PATH="/opt/mt5-proxy-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install Wine from the WineHQ Ubuntu 22.04 (jammy) repository.
# This intentionally uses WineHQ, not Ubuntu universe Wine, because the Windows
# Python/MetaTrader5 bridge requires newer Wine CRT coverage than Ubuntu 22.04
# distro Wine provides.
ARG WINEHQ_UBUNTU_CODENAME=jammy
ARG WINEHQ_PACKAGE=winehq-staging
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        gnupg \
        software-properties-common \
    && add-apt-repository -y universe \
    && install -d -m 0755 /etc/apt/keyrings \
    && wget -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key \
    && chmod 0644 /etc/apt/keyrings/winehq-archive.key \
    && wget -O /etc/apt/sources.list.d/winehq-${WINEHQ_UBUNTU_CODENAME}.sources \
        https://dl.winehq.org/wine-builds/ubuntu/dists/${WINEHQ_UBUNTU_CODENAME}/winehq-${WINEHQ_UBUNTU_CODENAME}.sources \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --install-recommends \
        "${WINEHQ_PACKAGE}" \
        fonts-wine \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        unzip \
        cabextract \
        p7zip-full \
        xvfb \
        xauth \
        x11-utils \
        x11vnc \
        fluxbox \
        novnc \
        websockify \
        dbus-x11 \
        winbind \
        gosu \
        tini \
        supervisor \
        procps \
        iproute2 \
        net-tools \
        lsof \
        python3 \
        python3-venv \
        python3-pip \
        libegl1 \
        libgl1 \
        libgl1-mesa-dri \
        libglx-mesa0 \
        libvulkan1 \
        libegl1:i386 \
        libgl1:i386 \
        libgl1-mesa-dri:i386 \
        libglx-mesa0:i386 \
        libvulkan1:i386 \
        fonts-liberation \
        fonts-dejavu-core \
        fonts-dejavu-extra \
    && wine --version \
    && rm -rf /var/lib/apt/lists/*

RUN python3 --version \
    && python3 -m venv /opt/mt5-proxy-venv \
    && /opt/mt5-proxy-venv/bin/python -m pip install --upgrade pip setuptools wheel

COPY app/requirements-api.txt /app/requirements-api.txt
COPY app/requirements-bridge.txt /app/requirements-bridge.txt
RUN /opt/mt5-proxy-venv/bin/python -m pip install --no-cache-dir -r /app/requirements-api.txt \
    && /opt/mt5-proxy-venv/bin/python -m pip install --no-cache-dir --no-deps mt5linux==1.0.3 \
    && /opt/mt5-proxy-venv/bin/python -m pip install --no-cache-dir 'rpyc' 'plumbum' 'pyxdg>=0.28,<1' 'numpy>=1.26.4,<2'

RUN groupadd -g 1000 trader \
    && useradd -m -u 1000 -g trader -s /bin/bash trader \
    && mkdir -p /config /logs /home/trader /app /app_tools /run/mt5-proxy \
    && chown -R trader:trader /config /logs /home/trader /app /app_tools /run/mt5-proxy

COPY app /app
COPY tools /app_tools
COPY scripts/*.sh /usr/local/bin/
COPY scripts/*.py /usr/local/bin/
COPY docker/supervisord.conf /etc/supervisor/conf.d/mt5proxy.conf
RUN chmod +x /usr/local/bin/*.sh /usr/local/bin/*.py \
    && chown -R trader:trader /app /app_tools /etc/supervisor/conf.d/mt5proxy.conf

WORKDIR /app
VOLUME ["/config", "/logs"]
EXPOSE 6080 5900 8000 8001
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/health >/dev/null || exit 1
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
