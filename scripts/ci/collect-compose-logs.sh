#!/usr/bin/env bash
set -euo pipefail

mkdir -p artifacts/docker
docker compose ps > artifacts/docker/compose-ps.txt || true
docker compose logs --no-color > artifacts/docker/compose.log || true
docker compose --profile misp ps > artifacts/docker/compose-misp-ps.txt || true
docker compose --profile misp logs --no-color > artifacts/docker/compose-misp.log || true
