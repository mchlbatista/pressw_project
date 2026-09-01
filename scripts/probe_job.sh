#!/usr/bin/env bash
# Probing helper for the callboard->encore migration (Phase 1: background-job observation).
#
# Runs the same three checks every time instead of retyping psql by hand, so t0/t1
# snapshots are guaranteed comparable:
#   - table activity counters (pg_stat_user_tables: inserts/updates/deletes, O(1),
#     no table scan — the check that still works when a table holds millions of rows)
#   - the callboard_queue rows seeded by db/init.sql
#   - the specific assignments those queue rows reference (indexed point lookup,
#     not a full-table scan)
#
# Usage:
#   scripts/probe_job.sh counters [table ...]              # print activity counters, optionally filtered
#   scripts/probe_job.sh snapshot <label>                   # capture all three checks under <label>
#   scripts/probe_job.sh diff <label1> <label2>             # diff two snapshots
#   scripts/probe_job.sh changed-since '<since>' [table ...] # rows changed since a timestamp
#
# `changed-since` is a watermark filter (WHERE updated_on > <since>) - the scale-safe
# alternative to guessing via `ORDER BY updated_on DESC LIMIT n` (which sorts the whole
# table) once you have a specific checkpoint to filter from, e.g. the wall-clock time you
# ran `snapshot t0`. Two real caveats, found by inspecting this schema (see
# scratch/DISCOVERIES.md): (1) `updated_on` has no index on assignments/shifts, so this is
# still a full sequential scan until one is added - it only narrows the *result set*, not
# the work Postgres does to find it; (2) `messages` and `tg_crew` have no last-modified
# timestamp column at all (`messages.sent` is insert-time only), so a watermark filter can
# find new rows there but can never see an in-place update (e.g. a message's `read` flag
# flipping) - that gap has to be closed by adding the column, not worked around in SQL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/scratch/snapshots"
mkdir -p "$OUT"

psql_exec() {
  docker compose exec -T db psql -U showcall -d showcall -c "$1"
}

cmd_counters() {
  local filter=""
  if [ "$#" -gt 0 ]; then
    local list
    list=$(printf "'%s'," "$@")
    filter="WHERE relname IN (${list%,})"
  fi
  psql_exec "SELECT relname, n_live_tup, n_tup_ins, n_tup_upd, n_tup_del
             FROM pg_stat_user_tables $filter ORDER BY relname;"
}

cmd_snapshot() {
  local label="${1:?usage: probe_job.sh snapshot <label>}"
  cmd_counters > "$OUT/activity_${label}.txt"
  psql_exec "SELECT id, org_id, kind, payload, queued_at FROM callboard_queue
             ORDER BY queued_at;" > "$OUT/queue_watchset_${label}.txt"
  psql_exec "SELECT a.id, a.org_id, a.status, a.updated_on FROM assignments a
             WHERE a.id IN (
               SELECT (payload::json->>'assignment_id')::int FROM callboard_queue
             ) ORDER BY a.id;" > "$OUT/assignments_watchset_${label}.txt"
  echo "wrote $OUT/{activity,queue_watchset,assignments_watchset}_${label}.txt"
}

cmd_diff() {
  local a="${1:?usage: probe_job.sh diff <label1> <label2>}"
  local b="${2:?usage: probe_job.sh diff <label1> <label2>}"
  local changed=0
  for f in activity queue_watchset assignments_watchset; do
    if ! diff -q "$OUT/${f}_${a}.txt" "$OUT/${f}_${b}.txt" > /dev/null; then
      changed=1
      echo "=== $f: $a -> $b ==="
      diff "$OUT/${f}_${a}.txt" "$OUT/${f}_${b}.txt" || true
      echo
    fi
  done
  if [ "$changed" -eq 0 ]; then
    echo "no diffs between $a and $b"
  fi
}

cmd_changed_since() {
  local since="${1:?usage: probe_job.sh changed-since '<YYYY-MM-DD HH24:MI:SS>' [table ...]}"
  shift
  local tables=("$@")
  if [ "${#tables[@]}" -eq 0 ]; then
    tables=(assignments shifts)
  fi
  for t in "${tables[@]}"; do
    case "$t" in
      assignments)
        echo "=== assignments: updated_on > '$since' ==="
        psql_exec "SELECT id, org_id, status, updated_on FROM assignments
                    WHERE updated_on > '$since' ORDER BY updated_on;"
        ;;
      shifts)
        echo "=== shifts: updated_on > '$since' ==="
        psql_exec "SELECT id, org_id, staffing_status, open_slots, updated_on FROM shifts
                    WHERE updated_on > '$since' ORDER BY updated_on;"
        ;;
      messages)
        echo "=== messages: sent > '$since' (NEW rows only - messages has no updated_on," \
             "so an in-place change like a read-flag flip is invisible to this filter) ==="
        psql_exec "SELECT id, org, crew_id, kind, sent FROM messages
                    WHERE sent > extract(epoch from timestamp '$since')::int ORDER BY sent;"
        ;;
      *)
        echo "no update-timestamp column exists for '$t' (e.g. tg_crew has none at all) -" \
             "can't filter by time; use 'counters' plus a targeted id lookup instead" >&2
        ;;
    esac
  done
}

case "${1:-}" in
  counters)      shift; cmd_counters "$@" ;;
  snapshot)      shift; cmd_snapshot "$@" ;;
  diff)          shift; cmd_diff "$@" ;;
  changed-since) shift; cmd_changed_since "$@" ;;
  *)
    echo "usage: $0 {counters [table ...] | snapshot <label> | diff <label1> <label2> |" \
         "changed-since '<since>' [table ...]}" >&2
    exit 1
    ;;
esac
