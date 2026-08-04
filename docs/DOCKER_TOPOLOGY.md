# Docker Topology Contract

The platform runs with `docker compose up`.

Required platform containers:

- `frontend`
- `backend`
- `worker`
- `scheduler`
- `postgres`
- `redis`
- `nginx`

MISP must be deployed through an official Docker deployment and kept isolated. The platform communicates with MISP only through the MISP API.

Official local MISP profile services:

- `misp` (`ghcr.io/misp/misp-docker/misp-core`)
- `misp-modules` (`ghcr.io/misp/misp-docker/misp-modules`)
- `misp-db` (`mariadb:10.11`)
- `misp-valkey` (`valkey/valkey:7.2`)
- `misp-mail` (`ghcr.io/egos-tech/smtp`)

MISP is exposed to the host at `https://localhost:8443`. Backend, worker, and
scheduler reach it internally at `https://misp`.

Networks:

- `platform_internal`
- `misp_internal`

Volumes:

- `postgres_data`
- `redis_data`
- `deployment_artifacts`
- `misp_mysql_data`
- `misp_cache_data`
- `misp_configs`
- `misp_logs`
- `misp_files`
- `misp_ssl`
- `misp_gnupg`

Health checks must cover backend, worker, scheduler, PostgreSQL, Redis, MISP API connectivity, DeepSeek API connectivity, and pySigma availability. The platform System Health page must distinguish MISP `not_configured`, `unreachable`, `authentication_failed`, `authenticated`, and `healthy` states.
