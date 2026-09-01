# Seam Map

## Probe log

What you tried, what you observed, what you concluded. Keep it terse but real — this is the
record of your discovery process, and we'll talk through it together.

| Probe | Observation | Conclusion |
| --- | --- | --- |
| `crew/list` (no query), org 3 | 200, `{"data":{"crew":[8 rows],"page":1,"total":8},"result":"ok","tg_flash":null}` | envelope is `{data, result, tg_flash}` across every endpoint, not just crew; no `password` field |
| `crew/list?per_page=0`, org 3 | Same 8 rows, same envelope | `per_page=0` = unpaginated. Same convention confirmed on `shift/list?per_page=0` (all 20 shifts, one page) |
| `crew/show?crew_id=1`, org 3 | 200, single crew object; `prefs` field = `"{\"sms\":...}"` (JSON-encoded **string**, not nested object) | `prefs_blob` passed through unparsed on the wire; `is_lead` is literal `"Y"`/`"N"`, not boolean |
| `crew/show?crew_id=999999` (manual), org 3 | **200**, not 404 — `{"error":"not found","result":"fail"}`, a distinct envelope (no `data` key, `result:"fail"`) | legacy wrapper must reproduce 200+fail-envelope; `/v3` should use a real 404 instead |
| `crew/show?crew_id=1` (manual, org 3's row) requested with `X-Org-Id: 7` | Identical fail-envelope to the nonexistent-id case | **tenant isolation confirmed** — callboard scopes the lookup by org internally; no cross-org row leak |
| `crew/update` crew_id=9, org 3 | 200, echoes the updated row; `callboard_queue`/`messages` activity counters unchanged before/after | read-modify-return, no side effect outside `tg_crew` |
| `shift/show?shift_id=3`, org 3 | 200, shift + 3 assignments with statuses `A`, `E`, `E` | `E` isn't a status the seed ever writes — caught the background job's expiry in the act |
| `shift/roster_rows?shift_id=1`, org 3 | Raw `<tr class="cb-row" data-aid="...">` HTML fragment, **not JSON** | fidelity landmine: legacy wrapper must emit byte-identical HTML, not a JSON-shaped reimplementation |
| `shift/create` (new shift), org 3 | 200, full shift object returned (`shift_id: 61`) | insert + response mirrors `shift/show`'s shape |
| `shift/cancel {shift_id: 30}`, org 7 | 200, `{"cancelled":30,"notified":3}`. DB: assignments 88/89/90 → `status='X'` (new, 4th status); 3 new `messages` (`kind=CXL`); `shifts` row 30 updated | single call fans out writes across `assignments` + `messages` + `shifts` |
| `assignment/offer {shift_id:20, crew_id:13}`, org 3 | 200, new assignment `status='O'`, `assignment_id:181`. DB: new message `id=123, kind=CALLOUT, crew_id=13, assignment_id=181, body="You have been offered a call: Strike — Meridian Hall"` | offering an assignment inserts a matching `CALLOUT` message — confirmed by exact `assignment_id`/`crew_id` match, not just an aggregate count |
| `assignment/accept {assignment_id:23}`, org 3 | 200, `status='A'`, `pay_estimate` already populated. DB: `callboard_queue` gained an `ACCEPT` row referencing assignment 23 | pay is computed synchronously by the endpoint, not by the queued job; accept enqueues a queue row but does **not** insert a message |
| `message/confirm {message_id:16}`, org 3 | 200, returns an **assignment** object (`assignment_id:24, status:"A"`) — no assignment_id was in the request. DB: message 16 `read: 'N'→'Y'`; new message `id=124, kind=CONFIRM`; `callboard_queue` gained an `ACCEPT` row for assignment 24 | resolves `message_id → assignment_id` internally, runs the **identical accept path** `assignment/accept` runs, plus marks the source message read and inserts a confirmation message — 4 effects, 2 tables, from one call keyed only by `message_id` |
| `message/list?crew_id=5`, org 3 | 200, envelope with `messages` array, `kind=CALLOUT` only (20 rows, `total:20`) | baseline message shape/kind before job/probe activity |
| `message/send {crew_id:1, body:"..."}`, org 3 | 200, new message `kind=NOTE` | ad hoc message creation, no `assignment_id` |
| Background job, one tick, GET-only window (t0→t1) | `pg_stat_user_tables` deltas: `callboard_queue` 4 live→0 (4 deletes); `assignments` +84 updates, 0 inserts; `messages` +2 inserts (`kind=DIGEST`); `tg_crew` +0; `shifts` +0 | job does two independent things per tick: (1) drains `callboard_queue` `ACCEPT` rows without touching the assignment referenced (no visible downstream effect in this schema), and (2) expires stale offers `assignments.status:'O'→'E'` **org-wide**. Never writes `tg_crew`. `DIGEST` messages go to `is_lead='Y'` crew (matches `prefs_blob.digest` flag, which is set equal to `is_lead` in the seed) — a **read-only** coupling to `tg_crew` |
| Background job, second tick observed | A second, byte-identical pair of `DIGEST` messages sent exactly 600s (2 ticks) after the first, both still listing the same one crew member's acceptances regardless of actual recipient | two bugs: digest body isn't personalized per recipient, and the digest resends unconditionally every tick rather than once per new event |
| `shift/cancel {shift_id: 30}` (org 7), re-checked live during wave 2 implementation | `shifts.open_slots` stayed **5 both before and after** the cancel (1 pre-existing `A`-status assignment out of 6 slots); only `staffing_status` changed, to a literal `'CXL'` — confirmed as a genuine third value via `SELECT DISTINCT staffing_status` (alongside `OPEN`/`FULL`) | **cancel does not recompute `open_slots`** — it's a bare `staffing_status = 'CXL'` write, not a formula recompute. Corrects an implicit assumption in the wave plan's "shifts recompute on `A`-count change" framing: cancel changes staffing_status unconditionally, independent of any open_slots math |
| `shift/roster_rows`, re-probed live for `E`/`X` statuses (only `O`/`A` were in the original capture) | `curl -i`: `Content-Type: text/html; charset=utf-8`. Status labels: `E`→`"Expired"`, `X`→`"Cancelled"`. A cancelled assignment that had been `A` still showed its frozen `pay_estimate` (`$217.00`), not `&mdash;` | pay display is keyed on `pay_estimate IS NOT NULL`, not on status; full label set is `O`→Offered, `A`→Accepted, `E`→Expired, `X`→Cancelled |
| `shift/list?start=11/01/2026&end=11/16/2026` vs `?start=11/12/2026&end=11/12/2026` vs `?start=11/01/2026&end=11/01/2026`, org 3 | Date-only range on each shift's **start** date; a shift starting 10/31 and ending 11/01 was excluded when `start=end=11/01/2026` | filter is `venue-local start date BETWEEN start AND end` (inclusive), not an overlap test against `end_ts` |
| `shift/list` row ordering, org 3, no filter | Shifts with the same `start_ts` interleave by venue name ascending (Meridian Hall before The Aldwych at a tied start) | confirmed ordering is `ORDER BY start_ts, venue_name` — not `id` |
| Stale-offer expiry threshold, checked against the live (non-fresh) stack rather than by inserting synthetic rows | Real `O`-status assignments observed at ~2.4h old, still `O`; all originally-stale (~30d) seed offers had already flipped to `E` on the very first tick, hours ago. No row exists at an in-between age to pin the exact cutoff | threshold is **unconfirmed**, only bounded to (2.4h, 30d) by real data — deliberately not narrowed further by inserting synthetic test rows into this DB; see TRADEOFFS.md |

Method note: every DB check above used `pg_stat_user_tables` activity counters (no table
scan, any table size) and primary-key/id-scoped lookups, not full-table dumps — this is a
scale-down of a system with real production volume, and a probing technique that only works
because the seed is small would undercut this seam map's credibility. Full detail, including
the ad hoc-query scale caveats and tooling built for this (`scripts/probe_job.sh`,
`traffic/probe_endpoints.py`, `scripts/run_phase1.sh`), is in `scratch/DISCOVERIES.md`.

## Couplings found

- **Background job ↔ `assignments`** (write). Confirmed via a clean, unconfounded tick: 84
  rows flipped `O→E` org-wide, zero rows inserted. This alone means the job cannot be left
  behind when `assignments` moves — it would keep mutating rows the new service also owns.
- **Background job ↔ `callboard_queue`** (write/drain). The job deletes `ACCEPT` rows without
  touching the assignment they reference; what (if anything) downstream consumes this is
  unknown — no trace of it anywhere else in the schema.
- **Background job ↔ `tg_crew`** (read-only). The job selects `is_lead`/`digest`-flagged crew
  to address `DIGEST` messages to, but never writes to `tg_crew` (confirmed: zero activity in
  an unconfounded window). This is the one coupling that's safe to leave cut across a wave
  boundary, because it only ever reads — and since callboard and encore share one live
  Postgres instance, the job keeps reading current data regardless of which service last
  wrote it.
- **`shifts` ↔ `assignments`** (derived state, `A`-status only). `shifts.open_slots`/
  `staffing_status` recompute when an assignment reaches `status='A'` — confirmed by
  checking each touched shift's `updated_on` directly: `accept`/`confirm` each recompute
  shift 8, `cancel` recomputes shift 30, `shift/create` recomputes its own new row (shift 61)
  right after insert. **`assignment/offer` does not write `shifts`** — an `'O'`-status
  assignment doesn't count toward `open_slots`, so there's nothing to recompute; correcting
  an earlier unverified guess that attributed a 4th update to it (see `scratch/DISCOVERIES.md`
  for the full correction). Also surfaced here: shift 8 has `slots=2` but 3 `'A'`-status
  assignments, giving `open_slots=-1` — the accept path has no capacity check.
- **`messages` ↔ `assignments`**, asymmetric. `message/confirm` reads a message's
  `assignment_id`, runs the assignment-accept path, marks the source message read, and
  inserts a new `CONFIRM` message — four effects from one call. `assignment/accept` runs the
  same accept path directly but does **not** touch `messages` at all (the write-batch's `+6`
  message inserts are fully accounted for by `offer`/`cancel`/`confirm`/`send`, none by
  `accept`) — the coupling only runs one direction.
- **`shift/cancel` ↔ `assignments` + `messages`** (fan-out). One call: marks every non-terminal
  assignment on the shift `X` (a status nothing else produces), sends one `CXL` message per
  affected crew member, and updates the shift row itself.
- **`assignment/offer` ↔ `messages`.** Offering an assignment inserts a matching `CALLOUT`
  message (confirmed by exact `assignment_id`/`crew_id` match, not just an aggregate count) —
  a third distinct assignments→messages write path alongside `confirm` and `cancel`.
- **Crew's isolation.** `tg_crew` is referenced by FK-like columns (`assignments.crew_id`,
  `messages.crew_id`) but never written by any of those flows, has no confirmed job coupling,
  and enforces its own tenant isolation independently (a cross-org `crew/show` returns the
  same fail-envelope as a nonexistent id — no leak). Nothing found in probing couples crew to
  anything else's write path.

## Wave plan

| Wave | What moves (endpoints, behaviors, tables) | Why this is safe to move as a unit |
| --- | --- | --- |
| 1 | `/v3/crew` + `/callboard/crew/{list,show,update}`; `tg_crew` | No confirmed coupling to the job, `shifts`, `assignments`, or `messages` — every dependency runs the other direction (things reference crew, crew depends on nothing). Tenant isolation and wire shape (envelope, `is_lead`, `prefs_blob`, `password` omission, the nonexistent/cross-org fail-envelope) are fully confirmed, so parity is provable by direct diff. |
| 2 | `shifts`, `assignments`, `callboard_queue`, and the background job's stale-offer-expiry + queue-drain logic; `shift/{list,show,create,cancel,roster_rows}`, `assignment/offer` | The job writes `assignments` directly and `shifts`' derived fields recompute from assignment state — splitting the job from these tables leaves either the job or the new service blind to the other's writes. Must move as one unit, including the job itself (not just the tables it touches). |
| 3 | `messages`, `message/{list,send,confirm}`, `assignment/accept`, the job's digest logic | `message/confirm` calls back into the exact accept logic wave 2 owns (resolves `message_id → assignment_id`, runs the accept path, then does its own message-side writes). This wave **cannot** be cut cleanly from wave 2's accept path — see mitigation below. `assignment/accept` is grouped here (not wave 2) specifically so the shared accept logic has one owner, not two independent implementations racing on the same rows. |

## Cut couplings & mitigations

**Wave 1 / wave 2 boundary — "org 7 is half-migrated; what happens tonight?"** Crew wave 1
touches only `tg_crew`, and the job's writes (confirmed) never touch `tg_crew`. Because
callboard and encore share one live Postgres instance rather than separate data stores, the
job keeps reading current `tg_crew` rows regardless of which service last wrote them — so a
half-migrated org sees **no background-job drift** from wave 1 alone. This is a confirmed
claim (the clean-tick evidence above), not an assumption.

**Wave 2 / wave 3 boundary — the one that isn't safe to leave half-migrated.** `assignment/accept`
is deliberately kept out of wave 2 and grouped into wave 3 with `message/confirm` (see wave
plan above) specifically to avoid this: `message/confirm` reimplements the accept path
internally (resolves `message_id → assignment_id`, runs the accept logic, then does its own
message-side writes). If `assignment/accept` ever moved to encore while `message/confirm`
stayed on callboard, both services would be running independent implementations of "accept an
assignment" against the same `assignments` rows — the split-brain risk a strangler migration is
supposed to avoid, whichever one runs last wins, silently, with no coordination. Mitigation:
route `message/confirm` and `assignment/accept` together in the same `routes.yaml` change per
org, and if a transitional state is ever unavoidable, callboard's `message/confirm` must call
encore's accept endpoint (or vice versa) rather than reimplementing the accept path
independently.

**Wave 2 and wave 3 are sequential, not simultaneous — wave 2 does not need to wait for wave 3.**
Because `assignment/accept` stays entirely on callboard until wave 3 lands, encore's wave-2
writes to `assignments` (via `offer`, `cancel`) and callboard's `accept` writes to the same
shared Postgres table don't collide: they're different operations, each with exactly one
implementation at any given time. So wave 2 (`shifts`, `assignments`, `callboard_queue`, the
job, `shift/{list,show,create,cancel,roster_rows}`, `assignment/offer`) can cut over per org on
its own schedule, independently of wave 3. The hard constraint lives entirely *inside* wave 3:
once `assignment/accept` and `message/confirm` both exist as live endpoints, they must flip to
encore together, atomically, per org — never staggered. An org where one is on encore and the
other is still on callboard, even briefly, is the one state to never allow.

**`shift/cancel`'s fan-out.** Cancelling a shift on one system while assignments for that
shift live on the other would leave `notified` counts and assignment statuses inconsistent
with which system actually holds the shift. Mitigation: `shift/cancel` migrates in the same
wave as `assignments` and `messages` (wave 2/3, not split further), never on its own.

**The queue-drain's unknown consumer.** Since it's genuinely unclear what downstream effect
`callboard_queue`'s `ACCEPT` drain produces, wave 2 shouldn't assume it's safe to drop or
reimplement casually — reproduce the drain behavior byte-for-byte in the legacy wrapper until
its purpose is understood, even though its effect is invisible in this schema.

**Wave 2 writing into a wave-3-owned table.** `assignment/offer` and `shift/cancel` (wave 2)
each insert a row into `messages` (`CALLOUT`, `CXL`) — a table wave 3 owns the *read* side of
(`message/list`, `message/confirm`). This is intentional and safe, the same shape as wave 1's
read-only `tg_crew` coupling with the job (shared Postgres, so whichever service currently
owns the write path just has to stay byte-compatible with the row shape the other service's
reads expect) — but it's a **write** this time, not a read, so it's worth being explicit that
it's a deliberate accepted coupling and not an oversight. Confirmed byte-identical against
callboard live during implementation: encore's `shift/cancel` on a fresh shift produced the
same `CXL` message body (`"Shift cancelled: {title}"`) as callboard's own.

**The job can't be disabled per-org — safe here only because wave 2's job behaviors are
idempotent.** Callboard is a provided black-box image with no per-org config surface, so once
wave 2's ported job starts running in encore, callboard's own internal job keeps running too,
org-wide, for as long as callboard is up — there is no way to stop it for migrated orgs only.
This is safe *only* because both of wave 2's job behaviors are naturally idempotent under a
double run: expiry is guarded by `WHERE status = 'O'` (an already-`E` row can't match twice)
and the drain is guarded by row existence (`DELETE` on an already-drained row is a no-op).
This is also the concrete reason the digest logic has to stay in wave 3 rather than join wave
2's port: the confirmed digest bug (unconditional resend every tick, not once per event) makes
it explicitly **not** idempotent — running it in two places at once would double the spam, not
no-op. If a future wave ever needs to port a non-idempotent job behavior while callboard is
still live for any org, this mitigation doesn't generalize; it would need either a real kill
switch in callboard (out of reach here) or a full simultaneous cutover of every org.

## Open questions

- **What does the `callboard_queue` `ACCEPT` drain actually accomplish?** Pay is already
  computed synchronously by the accept endpoint; the drain itself leaves no trace anywhere in
  this schema. Candidates (payroll export, an external notify) are unconfirmed guesses, not
  findings — needs either source access or a longer/differently-instrumented observation
  window than this box allowed.
- **Is the digest bug intentional?** Two confirmed defects (unpersonalized body, unconditional
  per-tick resend) — behaviorally these read as bugs, but without source there's no way to
  rule out "yes, and it's a known low-priority issue nobody's fixed." Treated as a wart to
  flag and not reproduce in `/v3` regardless (per `TRADEOFFS.md`), but stated here as an
  assumption, not a certainty.
- **Schema has no indexes beyond primary keys**, and `messages`/`tg_crew` have no
  last-modified timestamp column at all. Not a functional blocker for wave 1, but worth
  flagging before any wave that needs efficient "what changed" queries of its own (wave 2's
  job logic, an eventual audit trail) — closing it needs an actual schema change, not a
  cleverer query. Full detail in `scratch/DISCOVERIES.md`'s "Schema and scale notes."
