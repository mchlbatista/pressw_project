#!/usr/bin/env bash
# Phase 1 orchestrator. Run this once `docker compose up --build -d` is up.
#
# Sequences the DB job-observation and the endpoint probing so they don't confound each
# other the way the first manual run did (see scratch/DISCOVERIES.md "Method note" - that
# run had write-probes and the job's t0/t1 diff overlapping in the same window, so some
# activity-counter deltas couldn't be attributed to the job vs. a probe call):
#
#   1. t0  - snapshot the job state immediately, before anything else touches the DB.
#   2. GET-only probe pass against callboard direct - read-only, so it cannot perturb
#      the t0/t1 diff.
#   3. sleep for 2 job ticks (see README.md: job is accelerated to every 5 min here).
#   4. t1  - snapshot again. diff t0 vs t1: this diff is now attributable to the job alone,
#      since nothing but reads happened in between.
#   5. POST-only probe pass (mutating endpoints), bracketed by its own before/after activity
#      counters - a separate, clearly-labeled batch, not mixed into the job's diff.
#   6. t2  - final snapshot for reference.
#
# Usage:
#   scripts/run_phase1.sh                                  # callboard direct, default wait
#   scripts/run_phase1.sh http://localhost:8091 300         # override base / tick-wait secs
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE="${1:-http://localhost:8091}"
TICK_WAIT="${2:-600}"   # 2 ticks @ 5 min/tick per README.md's accelerated schedule

log() { echo; echo "==> $*"; }

wait_for_stack() {
  log "waiting for the stack to become healthy..."
  for _ in $(seq 1 60); do
    if curl -sf http://localhost:8080/gateway/healthz > /dev/null \
       && curl -sf http://localhost:8092/healthz > /dev/null \
       && docker compose exec -T db pg_isready -U showcall > /dev/null 2>&1; then
      log "stack is healthy"
      return 0
    fi
    sleep 2
  done
  echo "stack did not become healthy within 2 minutes" >&2
  exit 1
}

wait_for_stack

log "t0: snapshotting job state (before any probing)"
scripts/probe_job.sh snapshot t0

log "read-only probe pass (GET) against $BASE - safe to run inside the job-diff window"
python3 traffic/probe_endpoints.py --base "$BASE" --methods GET

log "waiting ${TICK_WAIT}s for the job to tick (nothing but the above reads has run so far)"
sleep "$TICK_WAIT"

log "t1: snapshotting job state again"
scripts/probe_job.sh snapshot t1

log "job-only diff (t0 -> t1) - clean, since only GETs ran in between"
scripts/probe_job.sh diff t0 t1

log "activity counters before the write-probe batch"
scripts/probe_job.sh counters > scratch/snapshots/activity_before_writes.txt

log "write probe pass (POST) against $BASE"
python3 traffic/probe_endpoints.py --base "$BASE" --methods POST

log "activity counters after the write-probe batch"
scripts/probe_job.sh counters > scratch/snapshots/activity_after_writes.txt

log "write-probe-batch diff (not job-attributed - this is the mutating calls' own footprint)"
diff scratch/snapshots/activity_before_writes.txt scratch/snapshots/activity_after_writes.txt || true

log "t2: final snapshot for reference"
scripts/probe_job.sh snapshot t2

log "done. Review scratch/probe/*.txt and scratch/snapshots/*.txt"
