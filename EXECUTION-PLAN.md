# ShowCall/Callboard → Encore migration — execution plan

## Context

This is a 4-hour, self-timeboxed take-home for a Senior Backend Engineer role. The scenario:
a 15-year-old closed-source legacy backend (`callboard`) is being strangled out incrementally
onto a new FastAPI service (`encore`), with a routing gateway (`proxy/`) deciding per
(path prefix, org) which backend serves a request. Nothing is built yet — `encore/app/main.py`
is a bare health check, `proxy/routes.yaml` sends 100% of traffic to `callboard`, and there is
no git repo (`git status` confirms "not a git repository").

Deliverables required by `README.md`: `SEAMS.md` (couplings + wave plan, from templates/),
a ported "wave 1" (both `/v3/...` clean endpoints and byte-exact `/callboard/...` legacy
wrappers sharing one business-logic layer), at least one org flipped to Encore in
`routes.yaml`, a parity-proving mechanism, and `SCOPING.md`/`TRADEOFFS.md`. Grading rewards
narrow, exact-fidelity work over broad, approximate work.

Already confirmed from reading the repo (no stack started yet, so this is static analysis,
not probing):
- Schema (`db/init.sql`): `tg_crew`, `venues`, `shifts`, `assignments`, `messages`,
  `callboard_queue`. Inconsistent org column naming (`tg_crew.org`, `shifts.org_id`,
  `assignments.org_id`, `messages.org`) — a real legacy wart, not something to "fix" in wrappers.
  `shifts` denormalizes `venue_name`/`venue_tz` at creation time rather than joining `venues`.
  `is_lead` is `CHAR(1)` 'Y'/'N'. `prefs_blob` is a hand-built JSON *string*. `tg_crew.password`
  exists as a column — whether it leaks over the API is an open probe question with real
  fidelity-vs-security implications for `/v3`.
- Traffic (`traffic/traffic.jsonl`, 51 requests across orgs 3/7/12/19): exercises
  `crew/{list,show,update}`, `shift/{list,show,create,cancel,roster_rows}`,
  `assignment/{offer,accept}`, `message/{list,send,confirm}`. `per_page=0` appears for both
  `crew/list` and `shift/list` — looks like a "no pagination" legacy convention worth confirming.
- `callboard_queue` + the accelerated 5-min "nightly" job is an unknown, high-risk coupling —
  seed data deliberately primes it with stale offers and queued ACCEPT rows so its first tick
  is observable.
- Ports: gateway 8080, callboard direct 8091, encore direct 8092, postgres 5432 (all free).
  Docker Compose v5.4.0 available.
- Housekeeping landmine: `venv/` exists at repo root with a real virtualenv (binaries
  included) and is **not** covered by `.gitignore` (which only lists `.venv/`). Must fix
  before the first commit or a `git add` will try to stage interpreter binaries.

Given the 4-hour box, the plan below front-loads probing (you cannot design a safe wave plan
for a black box you haven't watched), commits to the **smallest defensible wave 1** (crew
read+update — single table, no queue/background-job coupling, cheap to prove parity on
because reads can be diffed directly against the shared live DB), and reserves real time for
the two written deliverables the brief explicitly grades on (`SEAMS.md`'s evidence table and
the parity mechanism) rather than racing to add more endpoints.

## Time budget (4h box)

| Phase | Time | Goal |
| --- | --- | --- |
| 0. Setup | 15 min | Stack up, git initialized, safety net in place |
| 1. Probing | 70 min | Understand callboard's real wire behavior + background job + coupling |
| 2. Seam map | (rolls up from Phase 1 notes, ~15 min to finalize) | `SEAMS.md` written |
| 3. Build wave 1 | 90 min | `/v3/crew*` + `/callboard/crew/*` wrapper, shared logic, routes.yaml flip |
| 4. Parity proof | 35 min | Golden capture + diff script/tests |
| 5. Docs + wrap | 20 min | `SCOPING.md`, `TRADEOFFS.md`, final commit, sanity replay |
| Buffer | 15 min | Absorb overruns; if unused, spend on a stretch endpoint |

## Phase 0 — Setup (15 min)

1. Fix `.gitignore` (repo currently has a real venv at root that isn't covered):
   ```bash
   echo "venv/" >> .gitignore
   ```
2. `git init`, initial commit of the kit as-delivered (before any of my edits) so the diff
   history shows real progression, per the brief's "commit as you go" instruction:
   ```bash
   git init
   git add -A
   git status   # sanity-check: venv/ must NOT appear in the staged list
   git commit -m "chore: initial kit as delivered"
   ```
3. Bring up the stack and confirm health:
   ```bash
   docker compose up --build -d
   docker compose ps                              # all services healthy/running
   curl -s http://localhost:8080/gateway/healthz   # {"ok": true, "backends": {...}}
   curl -s http://localhost:8092/healthz           # {"ok": true}
   ```
4. Confirm baseline routing:
   ```bash
   python3 traffic/replay.py --list
   python3 traffic/replay.py --index 0 --base http://localhost:8080
   ```
   The first command lists all 51 requests indexed (sends nothing). The second replays
   request 0 through the gateway (port 8080, the tool's default `--base`) and should print
   `X-Served-By: callboard` in the response line, confirming `routes.yaml`'s current
   100%-to-callboard state is actually live before any routing changes are made.

## Phase 1 — Probing (≈70 min)

This assessment's tables are seeded small (`db/init.sql` is a hand-written
`INSERT ... VALUES` for 4 orgs, tens of rows each) — but treat that as an artifact of the
scale-down, not a license to write probes that only work at toy scale. The real system this
stands in for has millions of rows, so the probing technique itself should be one that still
works there: watch write *activity* via Postgres's own counters (O(1), no scan, no lock
contention) before ever touching row data, then drill into specific known rows by primary
key (indexed point lookups, not table scans). Never `\copy`/dump a fact table whole as a
detection mechanism — that's the part that would not survive contact with the real system.

**Run the whole phase with one command**, `scripts/run_phase1.sh` (already written):
```bash
chmod +x scripts/probe_job.sh scripts/run_phase1.sh   # first run only
scripts/run_phase1.sh
```
It waits for the stack's healthchecks, then sequences the two probing tracks below so they
don't confound each other — a real trap the first manual run of this hit: interleaving
write-probes with the job's t0/t1 snapshots leaves some activity-counter deltas
unattributable to "the job" vs. "a probe call" (see `scratch/DISCOVERIES.md`'s "Method
note" for the concrete example). The fix, baked into the script:
1. **t0** — snapshot job state immediately, before anything else touches the DB.
2. **Read-only probe pass** (`--methods GET`) against callboard direct — safe to run inside
   the job-diff window since reads can't perturb it.
3. **Sleep** for 2 job ticks (`README.md` states the "nightly" job is accelerated to run
   every 5 minutes here, so `TICK_WAIT` defaults to 600s — 2 ticks rather than 1, to absorb
   tick-boundary jitter without timing it exactly).
4. **t1** — snapshot again, then `diff t0 t1`. Because only reads happened in between, this
   diff is now cleanly attributable to the job alone.
5. **Write probe pass** (`--methods POST`) against callboard direct, bracketed by its own
   before/after activity-counter snapshot — a separate, clearly-labeled batch, not mixed
   into the job's diff.
6. **t2** — a final snapshot for reference.

Override the base URL or wait time if needed: `scripts/run_phase1.sh <base> <tick_wait_secs>`.

Under the hood it composes the two building-block scripts:
- `scripts/probe_job.sh snapshot <label>` captures, per label: Postgres's own
  insert/update/delete counters (`pg_stat_user_tables`, cheap at any table size — the check
  that still works when a table holds millions of rows), every row currently in
  `callboard_queue` (bounded by design; a healthy queue isn't where millions of rows
  accumulate), and the specific `assignments` that queue currently references (an indexed
  point lookup, not a scan). `scripts/probe_job.sh diff <a> <b>` reports what changed between
  two labels.
- `traffic/probe_endpoints.py --base <url> --methods GET|POST` replays one representative
  request per unique `(method, path)` pair from `traffic.jsonl` (reusing `replay.py`'s own
  `load()`/`send()`), writing each response to its own file under `scratch/probe/` — e.g.
  `GET_callboard_crew_list.txt`, `POST_callboard_crew_update.txt` — covering all 13 endpoints
  (`crew/list`, `crew/show`, `crew/update`, `shift/list`, `shift/show`, `shift/create`,
  `shift/cancel`, `shift/roster_rows`, `assignment/offer`, `assignment/accept`,
  `message/list`, `message/send`, `message/confirm`).

Read the results the same way we did last time: for the job, check `scripts/probe_job.sh
diff t0 t1` for whether `callboard_queue` drains, whether the watched `assignments.status='O'`
rows flip to `'E'`, and cross-reference `activity_t0.txt`/`activity_t1.txt` for anything the
watch-set doesn't cover (`shifts.open_slots`/`staffing_status`, new `messages` kind `DIGEST`,
whether `tg_crew` shows any counter movement at all — a read-only coupling is fine to cut
across waves, a write coupling is not). For the endpoints, work through each
`scratch/probe/*.txt` file and note in the `SEAMS.md` probe-log table: what I tried, the
exact response shape (keys, types, status code, content-type), and what I concluded — same
as `scratch/DISCOVERIES.md` already did for the first run.

Specific things to resolve for the crew cluster (the wave-1 candidate) — these directly
drive the wrapper implementation:
- `crew/list`: envelope shape (bare array vs `{data, total, page}`) and default `page`/
  `per_page` values are covered by `GET_callboard_crew_list.txt` above — but that file only
  captures the *first* recorded `crew/list` request (bare, no query params);
  `probe_endpoints.py` samples one request per `(method, path)`, not per distinct query, so
  the `per_page=0` variant (a *different* query on the same path, further down
  `traffic.jsonl`) needs its own manual probe:
  ```bash
  curl -s -i -H "X-Org-Id: 3" "http://localhost:8091/callboard/crew/list?per_page=0"
  ```
  If this confirms "no pagination, return everything," treat that as more than a wire quirk
  to reproduce faithfully: on a table with tens of rows it's harmless, but it's a real-scale
  production risk (unbounded result set/OOM/timeout) the legacy system got away with only
  because it never hit real data volume. Reproduce it byte-exact in `/callboard/crew/list`
  for fidelity, but flag it explicitly as a wart `/v3` must not inherit unbounded (cap
  `per_page`, document the deviation) — carry this into the `TRADEOFFS.md` entry below rather
  than treating it as cosmetic.
- `crew/show`: response for a valid id (covered above), plus two manual probes not in the
  traffic log:
  ```bash
  # 1. nonexistent id
  curl -s -i -H "X-Org-Id: 3" "http://localhost:8091/callboard/crew/show?crew_id=999999"

  # 2. cross-org id — first find a real crew_id that belongs to org 3:
  docker compose exec -T db psql -U showcall -d showcall \
    -c "SELECT crew_id, org, display_name FROM tg_crew WHERE org = 3 ORDER BY crew_id LIMIT 3;"
  # then request it with a DIFFERENT org's header, e.g. crew_id=<id from above>, org 7:
  curl -s -i -H "X-Org-Id: 7" "http://localhost:8091/callboard/crew/show?crew_id=<id>"
  ```
  The second call is the tenant-isolation check — does callboard leak cross-org rows?
- Does either endpoint ever emit `password`? Check the captured bodies:
  `grep -i password scratch/probe/*crew*.txt`
- `is_lead` on the wire: `"Y"/"N"` string as stored, or coerced? Check the captured bodies.
- `prefs_blob` on the wire: raw escaped string, or parsed object? Check the captured bodies.
- `crew/update`: request/response shape (covered above), whether unknown fields are silently
  ignored or rejected — probe manually with an extra field:
  ```bash
  curl -s -i -H "X-Org-Id: 3" -X POST http://localhost:8091/callboard/crew/update \
    --data-urlencode "crew_id=9" --data-urlencode "notes=probe" \
    --data-urlencode "not_a_real_field=xyz"
  ```
  and whether it has any side effect outside `tg_crew` — reuse the script's `counters`
  subcommand directly (same activity-counter check as the job observation, scoped to just
  the tables in question instead of a full-table dump):
  ```bash
  scripts/probe_job.sh counters callboard_queue messages > scratch/probe/activity_before.txt
  # ... run the crew/update call ...
  scripts/probe_job.sh counters callboard_queue messages > scratch/probe/activity_after.txt
  diff scratch/probe/activity_before.txt scratch/probe/activity_after.txt
  ```
  Any nonzero delta means `crew/update` has a side effect worth chasing down with a targeted
  `WHERE crew_id = 9` query on the affected table — only reach for that once the counters
  say something moved.

Secondary probing (time-permitting, to inform the wave plan / cut-coupling section even
though wave 1 won't touch these): one pass each through `shift/create`, `shift/cancel`,
`assignment/offer`, `assignment/accept`, `message/confirm` (indices already captured above)
with the same `scripts/probe_job.sh counters ...` before/after pattern used for
`crew/update` — check deltas across all six tables (omit the table-name args to check all of
them) before/after each call, then scope any follow-up query to the specific shift/
assignment/crew id the call touched. Specifically check whether `assignment/accept` and
`message/confirm` overlap in effect (does confirming a message also flip an assignment to
accepted, or vice versa?), and whether `shift/cancel` cascades to `assignments`/`messages`.

## Phase 2 — Seam map (`SEAMS.md`)

Fill in using `templates/SEAMS.md` structure, from the probe log built in Phase 1. In the
probe log itself, note the counters-then-targeted-lookup technique (not full-table dumps) as
a deliberate methodology choice — this is a scale-model of a system that has millions of
rows in reality, and a probing approach that only works because the seed data is small would
undercut the seam map's credibility.
- **Couplings found**: shifts↔assignments (derived `open_slots`/`staffing_status`), the
  background job as a cross-cutting coupling over `callboard_queue`+`assignments`+`shifts`
  (+possibly `messages`/`tg_crew` reads), messages↔assignments (via `assignment_id`,
  possible `message/confirm` interaction), crew's relative isolation (referenced by FK-like
  columns from `assignments`/`messages` but not written by them).
- **Wave plan**: Wave 1 = crew (read + update) — no queue/background-job coupling, safe to
  cut. Wave 2 = shifts + assignments + the background job together (they must move as a unit
  — the job's effects span both tables). Wave 3 = messages (depends on assignment/crew ids;
  whether it can trail wave 2 or must move with it depends on the `message/confirm`↔
  `assignment/accept` probe result).
- **Cut couplings & mitigations**: explicitly answer the brief's prompt — *"org 7 is
  half-migrated; what happens tonight?"* — for the wave-1/wave-2 boundary: since crew wave 1
  touches only `tg_crew` and the nightly job's writes (per Phase 1 findings) don't touch
  `tg_crew`, a half-migrated org should see no background-job drift; state this as a
  claim backed by the specific probe evidence, not an assumption.
- **Open questions**: anything Phase 1 didn't resolve in time (e.g., digest-message
  triggering logic) — flagged honestly rather than guessed at.

## Phase 3 — Build wave 1 (≈90 min)

**Scope decision:** `/v3/crew` + `/callboard/crew/{list,show}` as the must-finish core
(read-only, byte-diffable against live callboard for parity), with `crew/update` as a
stretch item if probing didn't reveal hidden side effects. This matches the brief's explicit
preference: "two endpoints with exact fidelity... rather than ten approximately right."

```bash
mkdir -p encore/app/services encore/app/schemas encore/app/routers
touch encore/app/services/__init__.py encore/app/schemas/__init__.py encore/app/routers/__init__.py
```

File layout under `encore/app/` (new files; `db.py`/`main.py` already exist and are reused
as-is for the engine/session):
- `services/crew.py` — the **shared business logic**, one function per operation
  (`list_crew(org, page, per_page)`, `get_crew(org, crew_id)`, `update_crew(org, crew_id,
  fields)`), using `sqlalchemy.text()` against `db.session()` (matches the raw-SQL style
  already implied by `main.py`'s `SELECT 1`; no ORM mapping needed for a 3-endpoint slice).
  Returns plain dicts/rows — no framework-specific shaping here, so both routers can format
  independently.
- `schemas/crew.py` — Pydantic response models for `/v3` (booleans for `is_lead`, parsed
  object for `prefs_blob`, `password` deliberately omitted — document this omission).
- `routers/v3_crew.py` — `/v3/crew` (GET, list w/ real pagination semantics), `/v3/crew/{id}`
  (GET), `/v3/crew/{id}` (PATCH) — modern verbs/status codes, calls `services/crew.py`.
- `routers/legacy_crew.py` — `/callboard/crew/list`, `/callboard/crew/show`,
  `/callboard/crew/update` — reproduces callboard's exact envelope, field names/types,
  status codes, and any confirmed quirks (e.g. `per_page=0`, `is_lead` as char, raw
  `prefs_blob` string) found in Phase 1, calling the **same** `services/crew.py` functions.
  Any confirmed legacy wart that `/v3` deliberately does not reproduce gets a one-line
  comment pointing at the `SEAMS.md`/`TRADEOFFS.md` note explaining the deviation.
- `main.py` — `app.include_router(...)` for both routers.

`proxy/routes.yaml` — add a crew-specific prefix rule (longest-prefix-wins, so this doesn't
affect other `/callboard/...` paths):
```yaml
routes:
  "/callboard/crew/":
    default: callboard
    orgs:
      7: encore
  "/callboard/":
    default: callboard
    orgs: {}
```
No rebuild/restart needed for code changes — `encore`'s container runs `uvicorn --reload`
over a source-mounted volume, so saving a file is enough. `routes.yaml` is also
read-fresh on every request by the gateway (`proxy/app.py`), so editing it takes effect
immediately too. Smoke-test each new endpoint directly against `encore` (8092) as it's
built, before wiring the gateway:
```bash
curl -s http://localhost:8092/v3/crew?org=3 | python3 -m json.tool
curl -s -H "X-Org-Id: 3" http://localhost:8092/callboard/crew/list | python3 -m json.tool
curl -s -H "X-Org-Id: 3" "http://localhost:8092/callboard/crew/show?crew_id=1"
curl -s -i -H "X-Org-Id: 3" -X POST http://localhost:8092/callboard/crew/update \
  --data-urlencode "crew_id=9" --data-urlencode "notes=test via encore"
```
Then confirm the gateway flip end-to-end once `routes.yaml` names org 7:
```bash
curl -s -i -H "X-Org-Id: 7" http://localhost:8080/callboard/crew/list | grep -i x-served-by   # encore
curl -s -i -H "X-Org-Id: 3" http://localhost:8080/callboard/crew/list | grep -i x-served-by   # callboard
```

## Phase 4 — Parity proof (≈35 min)

Two complementary mechanisms, chosen because callboard and encore share one live Postgres
instance, which makes read-endpoint parity checkable by direct comparison rather than
approximation:

1. **Golden capture + live diff** (`traffic/capture_golden.py`, new script): replay the
   crew-related lines from `traffic.jsonl` plus the hand-crafted edge cases from Phase 1
   (nonexistent id, cross-org id) against `callboard` directly (8091), save
   `{request, status, body}` to `traffic/golden/crew.json`. Then replay the *same* requests
   against `encore` directly (8092) for the *same* org — since it's the same DB row and both
   are GETs, the bodies should be comparable directly (after normalizing only the fields
   `/v3` deliberately changed, which for the legacy-wrapper paths should be zero). Report any
   diff. Intended CLI (build the script to match):
   ```bash
   python3 traffic/capture_golden.py --grep crew --base http://localhost:8091 \
     --out traffic/golden/crew.json
   python3 traffic/capture_golden.py --replay traffic/golden/crew.json \
     --base http://localhost:8092 --diff
   ```
2. **Pytest characterization tests** (`encore/tests/test_legacy_crew_parity.py`): same
   comparisons as (1) but asserted in CI-runnable form, using `httpx` against the live
   containers per the pattern already noted in `test_health.py`'s docstring ("run inside the
   running stack's network or with DATABASE_URL pointed at localhost:5432"). Per
   `REQUIREMENTS.md`, a local Python install isn't assumed, so run it inside the already-live
   `encore` container (source + tests are volume-mounted at `/srv`, but the image only
   installs main deps, so add `pytest`/`httpx` first):
   ```bash
   docker compose exec -T encore pip install pytest httpx
   docker compose exec -T encore pytest -v
   ```
3. **Write parity** (if `crew/update` gets built): apply the identical update via callboard
   for one crew_id and via encore for a different crew_id with equivalent seed data:
   ```bash
   curl -s -H "X-Org-Id: 3" -X POST http://localhost:8091/callboard/crew/update \
     --data-urlencode "crew_id=9" --data-urlencode "notes=parity check"
   curl -s -H "X-Org-Id: 3" -X POST http://localhost:8092/callboard/crew/update \
     --data-urlencode "crew_id=10" --data-urlencode "notes=parity check"
   ```
   then diff the resulting rows column-by-column (excluding `crew_id`) via direct SQL —
   proves the mutation logic matches without needing to reset the shared DB between runs:
   ```bash
   docker compose exec -T db psql -U showcall -d showcall \
     -c "SELECT org, notes, updated FROM tg_crew WHERE crew_id IN (9, 10) ORDER BY crew_id;"
   ```

Finish with an end-to-end sanity check of the routing flip:
```bash
python3 traffic/replay.py --grep crew --base http://localhost:8080
```
Requests recorded with `org=7` should show `X-Served-By: encore`; requests with
`org=3/12/19` should still show `X-Served-By: callboard`.

## Phase 5 — Docs + wrap (≈20 min)

- `SCOPING.md`: committed scope (crew list/show[/update]), cut scope (shifts/assignments/
  messages/background-job wave — with the seam-map reasoning for why), assumptions made
  during probing, risks accepted.
- `TRADEOFFS.md`: any confirmed legacy wart intentionally not carried into `/v3` (e.g.
  `password` exposure, `is_lead` char encoding, raw `prefs_blob` string, and — if confirmed —
  `crew/list`'s `per_page=0` unbounded-result convention, called out explicitly as a
  real-scale production risk the seed data is too small to expose, not just a wire quirk)
  with the specific reasoning; what's next; known-broken/unhandled cases; any post-window
  commits labeled as such if the box runs out mid-task.
- Final `git log` review — commits should tell the real story (setup → probing artifacts →
  wave 1 → parity → docs), not one squashed dump:
  ```bash
  git add -A
  git status   # re-check nothing unwanted (venv/, __pycache__/, scratch/) is staged
  git commit -m "docs: SCOPING.md, TRADEOFFS.md, final wrap"
  git log --oneline --graph
  ```

## Verification

Run these as a final pass before calling it done:
```bash
# clean-stack rebuild
docker compose down -v && docker compose up --build -d
docker compose ps

# tests pass against the fresh stack
docker compose exec -T encore pip install pytest httpx
docker compose exec -T encore pytest -v

# routing flip is correct end-to-end
python3 traffic/replay.py --grep crew --base http://localhost:8080

# zero unexplained parity diffs
python3 traffic/capture_golden.py --replay traffic/golden/crew.json \
  --base http://localhost:8092 --diff
```
- `docker compose up --build -d` brings up a clean stack; `docker compose down -v && docker
  compose up -d` resets to pristine data at any point without breaking anything.
- `encore/tests/` pass via `pytest` run against the live stack.
- `traffic/replay.py --grep crew --base http://localhost:8080` shows org 7 served by
  `encore` and org 3/12/19 still served by `callboard`, with matching data shape.
- `traffic/capture_golden.py` (or the pytest suite) shows zero unexplained diffs between
  callboard and encore for the wave-1 endpoints.
