# Scoping

**Scope committed:**

- Wave 1 (crew): `/v3/crew` + `/callboard/crew/{list,show,update}`, org 7 cut over.
- Wave 2 (shifts, assignments, callboard_queue, the background job): `/v3/shifts`
  (list/get/create/cancel) + `/v3/shifts/{id}/assignments` (offer) + all 6 legacy wrappers
  (`shift/{list,show,create,cancel,roster_rows}`, `assignment/offer`) + the ported job
  (stale-offer expiry, queue drain), org 7 cut over for shift/assignment routes too.
- Business logic implemented once per domain (`services/shifts.py`, `services/assignments.py`,
  `services/job.py`), shared by both the `/v3` and legacy tiers.
- Parity proven live against callboard direct for every wave-2 endpoint (see verification
  section of the wave 2 plan) — not just "it looks right."

**Scope cut:**

- `assignment/accept`, `message/{list,send,confirm}`, and the job's digest logic — deliberately
  held for wave 3, per SEAMS.md's wave plan. `message/confirm` reimplements the accept path
  internally, so splitting `accept` into wave 2 would create two independent implementations
  racing on the same `assignments` rows.
- `roster_rows` has no `/v3` equivalent — it's a legacy-frontend HTML-fragment concern; `/v3`
  clients get the same data as `ShiftDetail.assignments` from `GET /v3/shifts/{id}`.
- No `parity` automated diff harness (byte-diffing legacy responses against callboard
  programmatically) — parity was proven manually via paired curl calls against both backends
  during implementation (see chat record / SEAMS.md's probe log additions), not committed as a
  reusable test script. Would do this next with more time.
- No schema migration to add missing indexes / `updated_on` columns flagged in SEAMS.md's open
  questions — out of scope for a strangler migration; a real schema change, not a query fix.

**Assumptions made:**

- `STALE_OFFER_SECONDS` defaults to 24h — unconfirmed against callboard's real threshold
  (only bounded to somewhere between 2.4h and 30d by real seed-data ages, see SEAMS.md). I
  didn't narrow this further by inserting synthetic rows into the shared dev database — I'm
  treating it like a real store, not a scratch pad, even under time pressure.
- `lead` is always `""` in every shift response — `lead_assignment_id` is never set by any
  wave-2 endpoint, so that code path is unexercised; I don't have a confirmed sample for the
  non-null case.
- Malformed `starts`/`ends`/`slots` on `shift/create` don't get byte-identical error parity
  with callboard (unlike malformed `shift_id`/`crew_id`, which do passthrough via Postgres's
  own error) — I don't have a probe sample for this input shape.

**Risks accepted:**

- Callboard's own background job cannot be disabled per-org (black-box image, no config
  surface) — during any period an org is migrated, both callboard's and encore's jobs run
  against the same rows. Accepted because wave 2's two job behaviors are provably idempotent
  under a double run (see SEAMS.md); this would NOT be safe to accept for a non-idempotent
  behavior like digest, which is exactly why digest stays in wave 3.
- The stale-offer threshold assumption above could be wrong in either direction (too
  aggressive or too lax vs. callboard's real cutoff) until it's pinned down by longer passive
  observation or a source-level answer.
