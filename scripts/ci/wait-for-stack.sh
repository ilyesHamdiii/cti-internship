#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: wait-for-stack.sh <service> [service...]" >&2
  exit 2
fi

timeout_seconds="${STACK_HEALTH_TIMEOUT_SECONDS:-420}"
deadline=$((SECONDS + timeout_seconds))

while [ "$SECONDS" -lt "$deadline" ]; do
  all_ready=true
  for service in "$@"; do
    container_id="$(docker compose ps -q "$service" 2>/dev/null || true)"
    if [ -z "$container_id" ]; then
      echo "service $service has no container yet"
      all_ready=false
      continue
    fi

    state="$(docker inspect -f '{{.State.Status}}' "$container_id")"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"

    if [ "$state" != "running" ]; then
      echo "service $service is $state"
      all_ready=false
      continue
    fi

    if [ "$health" != "none" ] && [ "$health" != "healthy" ]; then
      echo "service $service health is $health"
      all_ready=false
      continue
    fi
  done

  if [ "$all_ready" = true ]; then
    docker compose ps
    exit 0
  fi

  sleep 5
done

echo "Timed out waiting for stack health" >&2
docker compose ps >&2 || true
exit 1
