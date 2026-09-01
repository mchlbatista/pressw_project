# Trade-offs

**Built vs. scoped:** Waves 1 and 2 fully ported (see SCOPING.md for the exact endpoint list).
Wave 3 (`assignment/accept`, `messages`, digest) intentionally not started — the wave plan in
SEAMS.md explains why it can't be split from wave 2's accept-adjacent logic without risking
two independent "accept" implementations on the same rows.

**Specific trade-offs and why:**

- **`/v3` diverges from the legacy wire shape wherever the legacy shape was a historical
  accident, not a real constraint** — booleans instead of `Y`/`N`, a parsed `prefs` object
  instead of a JSON-encoded string, real HTTP 404s instead of a `200` + `{"result":"fail"}`
  envelope, ISO 8601 UTC datetimes instead of venue-local `MM/DD/YYYY HH:MM` strings, lowercase
  status words (`open`/`full`/`cancelled`, `offered`/`accepted`/`expired`/`cancelled`) instead
  of `OPEN`/`FULL`/`CXL` and `O`/`A`/`E`/`X`. The legacy wrapper reproduces every one of these
  byte-for-byte instead — the frontend can't tell the difference, and `/v3` doesn't inherit
  the debt.
- **No `roster_rows` in `/v3`.** It's a raw HTML fragment for the legacy frontend to inject
  directly into a table — there's no "modern" version of an HTML-fragment endpoint; a `/v3`
  client gets the identical data as JSON via `ShiftDetail.assignments`.
- **`shift/cancel` does not recompute `open_slots` — reproduced as-is, not fixed.** Confirmed
  live against callboard: cancelling a shift leaves `open_slots` exactly where it was pre-cancel
  (freed capacity from cancelled assignments is never reflected), and only sets
  `staffing_status = 'CXL'`. This reads as a bug (a cancelled shift's slots don't reopen), but
  per the brief's "weird behavior... yours to notice, reproduce, and (in `/v3`) deliberately
  not reproduce, with the difference written down" — `/v3`'s `CancelResult` doesn't return a
  full shift object at all, sidestepping the question of what `open_slots` should mean post-
  cancel rather than silently baking in the same staleness. Worth a real product decision, not
  a migration-time fix.
- **The accept path has no capacity check (pre-existing bug, not introduced here).** Shift 8 in
  the seed has `slots=2` but 3 `A`-status assignments, i.e. `open_slots=-1` — confirmed in
  SEAMS.md. Not reproduced or fixed in wave 2 since `accept` is wave 3's endpoint; flagged here
  so it isn't mistaken for a wave-2 regression when wave 3 lands.
- **The digest job's two known bugs (unpersonalized body, unconditional per-tick resend) are
  explicitly NOT ported**, even though digest logic is only wave 3's concern anyway — noting it
  here since it's the reason digest couldn't ride along with wave 2's job port (see SCOPING.md's
  risks-accepted section on job idempotency).
- **`STALE_OFFER_SECONDS` defaults to 24h — an assumption, not a confirmed value.** Real seed
  data only bounds callboard's actual cutoff to somewhere between ~2.4h (still `O`) and 30 days
  (already `E`); both seed age-buckets had already resolved by the time this was checked in a
  long-lived session, and no synthetic rows were inserted to pin it down further (explicit user
  direction: this database is treated as a real shared store, not a scratch pad for probing).
  Configurable via the `STALE_OFFER_SECONDS` env var if the real value is ever learned.

**What you'd do next with more time:**

- Pin down the real stale-offer threshold via passive observation (watch real `O` rows age
  past the current 24h default across a longer session) rather than the current bounded
  assumption.
- Add a `test_legacy_shift_parity.py` / `test_legacy_assignment_parity.py` that automates the
  paired-curl comparisons done manually during this implementation (legacy wrapper response vs.
  callboard direct, same inputs, byte-diffed) — `test_legacy_crew_parity.py` has the same gap
  from wave 1, referenced but never written.
- Confirm the malformed `starts`/`ends`/`slots` error-parity gap noted in SCOPING.md against
  callboard direct, and pass those errors through the same way `shift_id`/`crew_id` already do.
- Start wave 3, paired per the SEAMS.md mitigation (`assignment/accept` + `message/confirm`
  flipped together, never staggered).

**Known issues or unhandled cases:**

- `lead_assignment_id`-driven `lead` field is untested — always `""` in this wave's scope,
  never exercised, see SCOPING.md's assumptions.
- The single-file Docker bind mount on `proxy/routes.yaml` can detach if the host file is
  replaced via a rename-based write rather than edited in place (a known Docker Desktop
  quirk, not an app bug) — `docker compose restart gateway` re-establishes it if routing
  changes stop taking effect after an edit.

**Post-window commits, if any:** none.
