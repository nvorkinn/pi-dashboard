#!/usr/bin/env bash
# Run on the host by release.yml, from the folder it just unpacked this file and docker-compose.yml into.
# Pins the renderers to the release's image in .env, then pulls and brings up every renderer in the compose
# file: new ones are created, changed ones recreated, and ones no longer in the file are torn down and deleted,
# volumes too. Those hold a renderer's identity and its key, so adding one back registers a new device.
# Usage: deploy.sh <tag>
set -euo pipefail

tag="$1"
cd "${DEPLOY_DIR:-/opt/countdown-renderers}"

(
  flock 9
  (umask 077 && echo "COUNTDOWN_SERVER_VERSION=$tag" > .env.tmp)
  mv .env.tmp .env
  echo "Pinned the renderers to $tag"

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
) 9>.deploy.lock
