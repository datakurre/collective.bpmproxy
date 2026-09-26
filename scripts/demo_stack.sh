#!/usr/bin/env bash
# Bring up everything a screencast story needs, in the documented order, on a
# clean checkout -- the sequence in docs/*-scenario.md as one command:
#
#   scripts/demo_stack.sh review_process | contact_form | renovation_project
#   scripts/demo_stack.sh down
#
# Run it where `make` works (inside `make shell`, or `devenv shell -- ...`).
# It starts Plone and the story's external-task worker in the background (logs
# and pids under var/demo-stack/); the services (PostgreSQL, Keycloak, Mailpit,
# Operaton) stay under devenv, so `down` stops only Plone and the worker --
# `devenv processes down` stops the rest.
#
# It refuses to run when something else already answers on Plone's port: a
# story clears the engine's deployments in its first task, so it must only
# ever run against a stack you own.
set -euo pipefail
cd "$(dirname "$0")/.."

STATE=var/demo-stack
PIDS=$STATE/pids
mkdir -p "$STATE"

stop_background() {
  if [ -f "$PIDS" ]; then
    while read -r pid; do
      # Each was started with setsid, so its pid is its process group's.
      kill -TERM -- "-$pid" 2>/dev/null || true
    done < "$PIDS"
    rm -f "$PIDS"
  fi
}

wait_for() { # description url timeout-seconds
  local waited=0
  until curl -sf -m 4 -o /dev/null "$2"; do
    if [ "$waited" -ge "$3" ]; then
      echo "Timed out after ${3}s waiting for $1 ($2)." >&2
      return 1
    fi
    sleep 5
    waited=$((waited + 5))
  done
  echo "  $1 is up"
}

STORY=${1:-}
case "$STORY" in
  down)
    stop_background
    echo "Plone and the worker are stopped. Services: 'devenv processes down'."
    exit 0
    ;;
  review_process)
    DEMO=bootstrap-review-demo WORKER=examples/review-bot-py ;;
  contact_form)
    DEMO=bootstrap-contact-form-demo WORKER=examples/contact-form-bot-py ;;
  renovation_project)
    DEMO=bootstrap-renovation-demo WORKER= ;; # no external task in its BPMN
  *)
    echo "usage: $0 review_process|contact_form|renovation_project|down" >&2
    exit 2 ;;
esac

if [ -f "$PIDS" ]; then
  echo "A demo stack started by this checkout is already up (see $STATE/)." >&2
  echo "Run '$0 down' first." >&2
  exit 1
fi
if curl -s -m 2 -o /dev/null http://127.0.0.1:8080/; then
  echo "Something already answers on :8080 and it was not started by this" >&2
  echo "script. Stop it first: bootstrapping opens the ZODB, and the story" >&2
  echo "would run against a stack you do not own." >&2
  exit 1
fi

echo "Services (PostgreSQL, Keycloak, Mailpit, Operaton)"
if ! curl -sf -m 4 -o /dev/null http://127.0.0.1:8081/engine-rest/engine; then
  # The first, cold start downloads Operaton's Maven dependencies and can
  # take several minutes -- see docs/devenv-browser-smoke.md if it stalls.
  devenv up -d || true # often reports a cosmetic timeout; trust the probes
fi
wait_for Operaton http://127.0.0.1:8081/engine-rest/engine 900
wait_for Keycloak http://127.0.0.1:8082/realms/plone 300
wait_for Mailpit http://127.0.0.1:8025/api/v1/messages 60

echo "Plone site"
make reset-site
make bootstrap-site
make "$DEMO"

echo "Plone"
setsid nohup make start > "$STATE/plone.log" 2>&1 &
echo $! >> "$PIDS"
wait_for Plone http://127.0.0.1:8080/Plone 300

if [ -n "$WORKER" ]; then
  echo "Worker ($WORKER)"
  cp -n "$WORKER/secrets.example.env" "$WORKER/secrets.env"
  setsid nohup make -C "$WORKER" serve > "$STATE/worker.log" 2>&1 &
  echo $! >> "$PIDS"
  waited=0
  until grep -q "External task worker started" "$STATE/worker.log" 2>/dev/null; do
    if [ "$waited" -ge 300 ]; then
      echo "The worker did not start; see $STATE/worker.log." >&2
      exit 1
    fi
    sleep 3
    waited=$((waited + 3))
  done
  echo "  worker is polling"
fi

echo
echo "Ready. Record it with:  make screencast STORY=$STORY"
echo "Stop Plone and the worker with:  make demo-stack-down"
