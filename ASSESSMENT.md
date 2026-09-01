# Senior Backend Engineer: Take-Home Assessment

**Role:** Senior Engineer, Backend Lead
**Time:** 4 hours, self-timeboxed
**Submission:** Private GitHub repo shared with the contacts in your invite email

---

## Before you start

Your window starts when this kit is delivered. The time box is intentionally tight: part of
what we're evaluating is what you choose to do first, what you defer, and what you decide is
too risky to touch at all.

How to work:

1. Bring up the stack, read this brief, and start probing.
2. Commit as you go so we can see your progress and your process.
3. At the 4-hour mark, stop. Post-window commits are fine if you label them as such in your
   writeup. We'd rather see honesty than a silent overrun.

**Use AI tools.** We do, and we expect you to. We're evaluating your judgment and your output.

If something goes wrong (life, illness, internet), just tell us. Rescheduling is fine; silent
extensions are not.

---

## The situation

ShowCall Software sells crew scheduling to live-event venues: theaters, arenas, festival
operators. Each customer org schedules its stagehands, riggers, and techs across its venues.
The product works and customers depend on it daily.

The backend, **Callboard**, is fifteen years old. The engineers who understood it are gone.
The company has hired us to replace it incrementally — a strangler fig migration onto a new
FastAPI backend, codename **Encore** — with **zero disruption to customers**. The legacy
frontend keeps working throughout; per-org routing decides which backend serves which
customer for which functional area; rollback must always be an edit to a config file, never
a deploy.

You are the backend lead. This kit is a scale model of your first two weeks, compressed.

## What's in the box

```
docker compose up --build -d      # the callboard image pulls from a public registry
```

| Piece | What it is |
| --- | --- |
| `callboard` | The legacy backend. **A black box** — compiled binary, no source. Nobody has the source. Probing it over HTTP and watching its database is exactly how you learn what it does. |
| `db` | Postgres, seeded, **fully open to you** (`showcall/showcall@localhost:5432/showcall`). Schema in `db/init.sql`. This is your best instrument. |
| `gateway` | The migration proxy (source included). `proxy/routes.yaml` maps (path prefix, org) → backend. Everything starts on `callboard`. |
| `encore` | A FastAPI skeleton (source-mounted with reload). You build here. |
| `traffic/` | ~50 recorded requests from the legacy frontend, plus `replay.py` to fire them at any backend. There are no recorded responses — capturing those is your job. |
| `templates/` | Skeletons for the documents below. |

Two things you should know about the environment:

- Callboard runs a "nightly" maintenance job. In this environment it is **accelerated to
  every 5 minutes**. What it does is for you to determine.
- Every request carries an `X-Org-Id` header. Orgs 3, 7, 12, and 19 are seeded.

House rules: extracting or reverse-engineering the Callboard image (decompiling, dumping the
binary, poking at its container) is out of bounds — and we'll walk through your discovery
process together in the follow-up conversation, so shortcuts will be obvious. The database,
the traffic log, the gateway, and the running system are all fair game, in any combination.

## Your job

**1. Map the seams (`SEAMS.md`).** Before you port anything, figure out how this system is
actually coupled. The endpoints suggest tidy functional areas — crew, scheduling, messaging.
Migrations fail when those tidy areas turn out to share state in ways nobody wrote down.
Your seam map should cover:

- Which endpoints, background behaviors, and tables actually belong together, with the
  **evidence** for each coupling you found (your probe log: what you tried, what you saw,
  what you concluded).
- A wave plan: what you'd migrate first, second, third — and for any coupling your waves cut
  through, what specifically goes wrong mid-migration and how you'd mitigate it. Think in
  intermediate states: *org 7 is half-migrated; what happens tonight?*

**2. Port wave 1 to Encore.** For the first tranche in your plan:

- Clean, modern endpoints under `/v3/...` — the API you'd actually want in 2026.
- **Legacy-compatible wrappers** answering the original `/callboard/...` paths with
  Callboard's exact wire behavior. The legacy frontend must not be able to tell the
  difference. The gateway forwards original paths verbatim to whichever backend
  `routes.yaml` names.
- Business logic implemented **once**, shared by both tiers.
- Flip `routes.yaml` so at least one org gets your wave 1 from Encore.

Wave 1 should be small enough to finish well. We would rather see two endpoints with exact
fidelity and a sharp seam map than ten endpoints that are approximately right.

**3. Prove parity.** Characterization tests, replay diffs, DB snapshot comparisons —
your choice, but "it looks right" doesn't count. Show us how you'd know if your wrapper
drifted from Callboard.

**4. `SCOPING.md` and `TRADEOFFS.md`** — short. What you committed to, what you cut and why,
what you assumed, what you'd do next, and what you know is broken.

## Expectations and norms

- **Fidelity beats features.** The #1 failure mode of real migrations is a port that's
  *almost* right. Weird behavior in Callboard is not yours to fix in the wrapper — it's
  yours to notice, reproduce, and (in `/v3`) deliberately not reproduce, with the difference
  written down.
- **The migration must be safe, not just done.** We will read your wave plan asking "what
  breaks while this is half-finished?" You should too.
- **Ship something that runs.** `docker compose up`, flip the flag, it works.
- **Document unfinished work.** Stubs with clear TODOs are fine.
- **Expect your system to be exercised** with requests you didn't design for, in mixed
  routing states you didn't demo.

Good luck.
