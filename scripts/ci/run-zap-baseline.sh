#!/usr/bin/env bash
set -euo pipefail

mkdir -p artifacts/security

docker run --rm \
  --network host \
  -v "$PWD/artifacts/security:/zap/wrk:rw" \
  ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py \
  -t http://127.0.0.1:8080 \
  -J zap-baseline.json \
  -r zap-baseline.html \
  -w zap-baseline.md \
  -I
