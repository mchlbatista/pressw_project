# Setup Requirements

**Read this before you start the timer.** This assessment runs fully in Docker. There is nothing to install per language. Put the items below in place first, so setup does not use your working time. Budget about 15 minutes for setup.

## Hardware & OS

- macOS (Apple Silicon or Intel), Linux, or Windows with WSL2.
- ~4 GB free RAM and ~5 GB free disk for the container images.

## Required tools

| Tool | Version | Check | Install |
|------|---------|-------|---------|
| Docker Desktop / Engine | Compose v2 (`docker compose`, not `docker-compose`) | `docker compose version` | https://docs.docker.com/get-docker/ |
| Git | any recent | `git --version` | https://git-scm.com |

The FastAPI services, the legacy service, and Postgres all build and run inside `docker compose`. A local Python install is **not required**. Python 3.12+ and a REST client such as curl, Postman, or HTTPie are useful to test the API.

## Accounts / keys

- **No LLM or third-party API keys are needed.**
- The stack pulls a provided legacy-service image on its own, the first time you run `docker compose` during the assessment. Do not start the stack before the assessment begins.

## Ports that must be free

`5432` (Postgres), `8080` (gateway), `8091` (legacy service), `8092` (encore service). Stop anything already bound to these.

## Pre-flight check

Run this the day before, not when the timer starts:

```bash
docker compose version                 # expect Compose v2.x
docker run --rm hello-world            # confirm Docker can pull and run an image
```

Do not run `docker compose up` in this repo until the assessment begins. The stack includes a provided service that is part of the exercise.

When Docker is installed and the required ports are free, you are ready.
