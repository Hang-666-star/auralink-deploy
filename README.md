# Auralink Deployment

This repository contains deployment configuration for the Auralink platform.

> Current scope: the Compose files below are a legacy Docker template, including
> a SQLite Core API. They do not describe the current R25 PostgreSQL production
> runtime. Configuration CI does not start services or deploy this template.
> See [CONTRIBUTING.md](CONTRIBUTING.md) for validation and
> [the collaboration guide](docs/collaboration.md) for the four-repository workflow
> and the remaining R25 deployment integration work.

## Included services

- Web frontend
- Core API
- VMM music generation service
- Vision understanding service
- Nginx reverse proxy

## Not included

This repository does not contain:

- application source code
- model weights
- painting image assets
- runtime databases
- generated audio
- production secrets

## Requirements

- Docker Engine
- Docker Compose plugin
- NVIDIA Container Toolkit for GPU deployment
- access to the private Auralink container images

## Initial configuration

Create the real environment file:

    cp .env.example .env

Edit `.env` and replace all placeholder values.

The real `.env` file must never be committed to Git.

Create the persistent directories configured in `.env`.

Copy `paintings.csv` from the `auralink-core-api` repository to the path
specified by `PAINTINGS_CSV_HOST_PATH`.

Model weights and painting image files must be distributed separately.

## Validate configuration

    ./scripts/validate.sh

## Start services

    ./scripts/start.sh

## View service status

    ./scripts/status.sh

## Stop services

    ./scripts/stop.sh

The container image names in `.env.example` are placeholders until each
application repository publishes its corresponding image.
