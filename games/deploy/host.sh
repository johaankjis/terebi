#!/bin/sh
# Run from the uploaded source root on ZimaOS. Never prints the game admin key.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
compose() { docker compose -f games/deploy/compose.yaml "$@"; }
case "${1:-}" in
  build)
    compose build games
    ;;
  init)
    mkdir -p private
    chmod 700 private
    if [ ! -f private/game.json ]; then
      docker run --rm --user 0:0 -v "$PWD/private:/config" terebi-games-rps:local init --config /config/game.json
      docker run --rm --user 0:0 --entrypoint chown -v "$PWD/private:/config" terebi-games-rps:local 10001:10001 /config/game.json
    fi
    ;;
  start)
    test -f private/game.json
    compose up -d games tunnel
    ;;
  set-url)
    test "$#" -eq 2
    docker run --rm --user 0:0 -v "$PWD/private:/config" terebi-games-rps:local set-url --config /config/game.json --url "$2"
    compose restart games
    ;;
  status)
    compose ps
    compose logs --tail 35 tunnel
    ;;
  evidence)
    compose logs --no-log-prefix games
    ;;
  stop)
    compose down
    ;;
  *)
    echo 'Usage: sh games/deploy/host.sh build|init|start|set-url HTTPS_ORIGIN|status|evidence|stop'
    exit 2
    ;;
esac
