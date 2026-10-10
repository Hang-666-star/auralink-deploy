# Auralink Deployment

This repository owns deployment configuration for the current ArtLIVE R25
Chinese-painting project and retains the older Auralink music template.

> Current production uses PostgreSQL, the Core API, Web, Guide and Critic.
> The Compose files below are a legacy Docker template, including a SQLite Core
> API, VMM and Vision. Every legacy service requires the `legacy` profile;
> the default configuration does not start them. Configuration CI validates
> the template without deploying it.
> See [CONTRIBUTING.md](CONTRIBUTING.md) for validation and
> [the collaboration guide](docs/collaboration.md) for the four-repository workflow
> and the remaining R25 deployment integration work.

## R25 production

Application ownership is split across `auralink-web`, `auralink-core-api` and
`auralink-ai-service` (Guide/Critic). This repository owns the coordinated release
contract in [r25/CORE_RELEASE_CONTRACT.md](r25/CORE_RELEASE_CONTRACT.md).
Guide/Critic publication is described in
[r25/AI_RELEASE_CONTRACT.md](r25/AI_RELEASE_CONTRACT.md).
The release transaction implementation is being validated before installation;
its presence in Git does not mean the server is already using it.

A push to `release` produces the Actions artifact
`r25-controller-<sha>-<run>-<attempt>`, containing the fixed controller ZIP and
its file manifest. This workflow tests and packages the reviewed controllers
for later installation. Its result is explicitly `NOT_DEPLOYED`; it does not
connect to the server or install a controller.

The production database, media, model files and credentials remain on the server.
Legacy Compose commands below do not manage the R25 processes.

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

## Start the legacy music template explicitly

    ./scripts/start.sh --legacy

Running `./scripts/start.sh` without the flag refuses before invoking Docker.
`docker compose up` has no default services. Explicitly selecting a legacy
service, enabling `--profile legacy`, or setting `COMPOSE_PROFILES=legacy` opts
into that template. See [Docker's profile documentation](https://docs.docker.com/compose/how-tos/profiles/).

## View service status

    ./scripts/status.sh

## Stop services

    ./scripts/stop.sh

The container image names in `.env.example` are placeholders until each
application repository publishes its corresponding image.
