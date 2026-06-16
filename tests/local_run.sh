#!/usr/bin/env bash
set -euo pipefail
cp -n .env.example .env 2>/dev/null || true
docker compose build
docker compose up -d --force-recreate
docker compose ps
