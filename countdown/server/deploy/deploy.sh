#!/usr/bin/env bash
# Run by release.yml's deploy-renderers job, on the runner, against the host's Docker daemon (DOCKER_HOST=ssh://...),
# so nothing is installed on the host. Pins the renderers to the release's image, pulls it, and brings up every
# renderer in docker-compose.yml: new ones are created, changed ones recreated, and ones no longer in the file are
# torn down and deleted, volumes too. Those hold a renderer's identity and its key, so adding one back registers
# a new device. Run by hand it does the same to whatever daemon your docker talks to.
# Usage: deploy.sh <tag>
set -euo pipefail

export COUNTDOWN_SERVER_VERSION="$1"
cd "$(dirname "$0")"

docker compose pull
# Waits for the containers to be running, and fails the deploy if one isn't.
docker compose up -d --remove-orphans --wait --wait-timeout 120
docker compose ps

# --remove-orphans took their containers; this takes their volumes. The project's own volumes only (compose's
# label), and never when the file declares none, so a broken file can't delete every identity.
project="$(docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"
declared="$(docker compose config --volumes)"
[ -n "$declared" ] || { echo "No volumes declared in docker-compose.yml; not deleting any" >&2; exit 1; }
for volume in $(docker volume ls -q --filter "label=com.docker.compose.project=$project"); do
  if ! grep -qxF "${volume#"${project}_"}" <<< "$declared"; then
    echo "Deleting the volume of a removed renderer: $volume"
    docker volume rm "$volume"
  fi
done
