-- ShowCall / Callboard database
-- This schema is ~15 years old. It is what it is.

CREATE TABLE tg_crew (
    id            SERIAL PRIMARY KEY,
    org           INTEGER NOT NULL,
    org_name      TEXT,
    user_name     TEXT NOT NULL,          -- NOTE: legacy quirk, see docs... there are no docs
    display_name  TEXT,
    password      TEXT,
    rate          NUMERIC(8,2) DEFAULT 0,
    is_lead       CHAR(1) DEFAULT 'N',
    notes         TEXT DEFAULT '',
    prefs_blob    TEXT,
    created       INTEGER                  -- unix epoch
);

CREATE TABLE venues (
    id            SERIAL PRIMARY KEY,
    company_no    INTEGER NOT NULL,
    venue_name    TEXT NOT NULL,
    tz            TEXT DEFAULT 'America/Chicago',
    addr1         TEXT, addr2 TEXT, city TEXT, st TEXT, zip TEXT,
    created       INTEGER
);

CREATE TABLE shifts (
    id                 SERIAL PRIMARY KEY,
    org_id             INTEGER NOT NULL,
    venue_id           INTEGER NOT NULL,
    venue_name         TEXT,
    venue_tz           TEXT,
    title              TEXT NOT NULL,
    start_ts           INTEGER NOT NULL,   -- unix epoch, UTC
    end_ts             INTEGER NOT NULL,
    slots              INTEGER NOT NULL DEFAULT 1,
    open_slots         INTEGER NOT NULL DEFAULT 1,
    staffing_status    TEXT NOT NULL DEFAULT 'OPEN',
    lead_assignment_id INTEGER,
    extra              TEXT,
    created            INTEGER,
    updated_on         TEXT
);

CREATE TABLE assignments (
    id            SERIAL PRIMARY KEY,
    org_id        INTEGER NOT NULL,
    shift_id      INTEGER NOT NULL,
    crew_id       INTEGER NOT NULL,
    status        CHAR(1) NOT NULL DEFAULT 'O',   -- O offered, A accepted, X cancelled, E expired
    shift_title   TEXT,
    pay_estimate  NUMERIC(10,2),
    offered_at    INTEGER,
    accepted_at   INTEGER,
    updated_on    TEXT
);

CREATE TABLE messages (
    id           SERIAL PRIMARY KEY,
    org          INTEGER NOT NULL,
    crew_id      INTEGER NOT NULL,
    assignment_id INTEGER,
    kind         TEXT NOT NULL DEFAULT 'NOTE',    -- NOTE, CALLOUT, CONFIRM, CXL, DIGEST
    body         TEXT NOT NULL,
    shift_title  TEXT,
    sent         INTEGER,
    read         CHAR(1) DEFAULT 'N'
);

CREATE TABLE callboard_queue (
    id        SERIAL PRIMARY KEY,
    org_id    INTEGER NOT NULL,
    kind      TEXT NOT NULL,
    payload   TEXT NOT NULL,
    queued_at INTEGER
);

-- ---------------------------------------------------------------------------
-- Seed data. Orgs: 3 (Meridian Stageworks), 7 (Harbor Light Presents),
-- 12 (Ovation Venue Group), 19 (Northline Events).
-- ---------------------------------------------------------------------------

INSERT INTO venues (company_no, venue_name, tz, addr1, city, st, zip, created) VALUES
 (3,  'The Aldwych',        'America/Chicago',   '118 W Monroe',   'Chicago',     'IL', '60603', extract(epoch from now() - interval '900 days')::int),
 (3,  'Meridian Hall',      'America/Chicago',   '2200 Lake St',   'Evanston',    'IL', '60201', extract(epoch from now() - interval '850 days')::int),
 (7,  'Harbor Light Amp',   'America/New_York',  '41 Pier Ave',    'Boston',      'MA', '02110', extract(epoch from now() - interval '780 days')::int),
 (7,  'The Beacon Room',    'America/New_York',  '77 Tremont St',  'Boston',      'MA', '02108', extract(epoch from now() - interval '600 days')::int),
 (12, 'Ovation Center',     'America/Denver',    '900 Curtis St',  'Denver',      'CO', '80204', extract(epoch from now() - interval '500 days')::int),
 (19, 'Northline Pavilion', 'America/Chicago',   '5601 N Clark',   'Chicago',     'IL', '60660', extract(epoch from now() - interval '400 days')::int);

-- Crew. user_name carries the email; display_name is a generated abbreviation.
INSERT INTO tg_crew (org, org_name, user_name, display_name, password, rate, is_lead, notes, prefs_blob, created)
SELECT
  o.org,
  o.org_name,
  lower(n.fn) || '.' || lower(n.ln) || '@' || o.dom,
  upper(substr(n.fn,1,1)) || '. ' || initcap(n.ln),
  md5(n.fn || n.ln),
  n.rate,
  n.lead,
  n.notes,
  '{"sms": "' || n.sms || '", "ui_rows": 25, "digest": "' || n.lead || '"}',
  extract(epoch from now() - (n.age_days || ' days')::interval)::int
FROM (VALUES
  (3,  'Meridian Stageworks', 'meridianstage.example'),
  (7,  'Harbor Light Presents', 'harborlight.example'),
  (12, 'Ovation Venue Group', 'ovationvg.example'),
  (19, 'Northline Events', 'northline.example')
) AS o(org, org_name, dom)
JOIN (VALUES
  ('Marta','Kowalski', 31.00, 'Y', 'head rigger, day calls preferred', 'Y', 820),
  ('Deshawn','Avery',  24.50, 'N', '', 'Y', 640),
  ('Priya','Raman',    26.75, 'N', 'audio 2, has van', 'N', 610),
  ('Owen','Fitzgerald',22.00, 'N', '', 'Y', 555),
  ('Lucia','Marchetti',28.25, 'Y', 'production electrician', 'N', 480),
  ('Sam','Okafor',     15.55, 'N', 'new hire, shadowing only until cleared', 'Y', 90),
  ('Renee','Delacroix',25.00, 'N', '', 'N', 300),
  ('Toby','Anderson',  19.80, 'N', 'no fly rail', 'Y', 250)
) AS n(fn, ln, rate, lead, notes, sms, age_days) ON TRUE;

-- Shifts: pinned to ABSOLUTE dates around a fixed base week so the data is identical
-- on every machine that loads this file. Times are venue-local on the hour.
INSERT INTO shifts (org_id, venue_id, venue_name, venue_tz, title, start_ts, end_ts, slots, open_slots, staffing_status, extra, created, updated_on)
SELECT
  v.company_no,
  v.id,
  v.venue_name,
  v.tz,
  t.title || ' — ' || v.venue_name,
  extract(epoch from ((TIMESTAMP '2026-11-02 00:00:00' + (t.day_off || ' days')::interval + (t.hr || ' hours')::interval) AT TIME ZONE v.tz))::int,
  extract(epoch from ((TIMESTAMP '2026-11-02 00:00:00' + (t.day_off || ' days')::interval + ((t.hr + t.len) || ' hours')::interval) AT TIME ZONE v.tz))::int,
  t.slots,
  t.slots,
  'OPEN',
  '{"po": null, "loadin": ' || (CASE WHEN t.hr < 12 THEN 'true' ELSE 'false' END) || '}',
  extract(epoch from TIMESTAMP '2026-10-01 12:00:00' AT TIME ZONE 'UTC')::int,
  '2026-10-01 12:00:00'
FROM venues v
JOIN (VALUES
  ('Load-in',        -21, 8,  10, 4),
  ('Matinee changeover', -14, 13, 5, 2),
  ('Evening show call',  -7, 17, 6, 5),
  ('Strike',             -2, 22, 7, 6),
  ('Load-in',             1, 8,  10, 4),
  ('Evening show call',   3, 17, 6, 5),
  ('Full day festival',   6, 9,  12, 8),
  ('Matinee changeover', 10, 13, 5, 2),
  ('Evening show call',  14, 17, 6, 5),
  ('Strike',             28, 22, 7, 6)
) AS t(title, day_off, hr, len, slots) ON TRUE;

-- Assignments: for each shift, offer to a few org crew; some accepted, some still offered.
-- offered_at is deliberately RELATIVE to load time: offers on the late-window shifts are
-- fresh (confirmable), the rest are stale so the background job has visible work to do
-- on its first tick.
INSERT INTO assignments (org_id, shift_id, crew_id, status, shift_title, pay_estimate, offered_at, accepted_at, updated_on)
SELECT
  s.org_id,
  s.id,
  c.id,
  CASE WHEN rk = 1 THEN 'A' WHEN rk = 2 THEN 'O' ELSE 'O' END,
  s.title,
  CASE WHEN rk = 1 THEN round(((s.end_ts - s.start_ts) / 3600.0) * c.rate, 2) ELSE NULL END,
  CASE WHEN s.start_ts > extract(epoch from TIMESTAMP '2026-11-11 00:00:00' AT TIME ZONE 'UTC')::int
       THEN extract(epoch from now() - interval '45 minutes')::int
       ELSE extract(epoch from now() - interval '30 days')::int END,
  CASE WHEN rk = 1 THEN extract(epoch from now() - interval '29 days')::int ELSE NULL END,
  to_char(now() - interval '20 days', 'YYYY-MM-DD HH24:MI:SS')
FROM shifts s
JOIN LATERAL (
  SELECT id, rate, row_number() OVER (ORDER BY id) AS rk
  FROM tg_crew WHERE org = s.org_id ORDER BY id LIMIT 3
) c ON TRUE;

-- Keep derived columns legacy-consistent with the accepted counts above.
UPDATE shifts s SET
  open_slots = s.slots - (SELECT count(*) FROM assignments a WHERE a.shift_id = s.id AND a.status = 'A'),
  staffing_status = CASE
    WHEN s.slots - (SELECT count(*) FROM assignments a WHERE a.shift_id = s.id AND a.status = 'A') <= 0
    THEN 'FULL' ELSE 'OPEN' END;

-- A few recent messages so message/list has content.
INSERT INTO messages (org, crew_id, assignment_id, kind, body, shift_title, sent, read)
SELECT a.org_id, a.crew_id, a.id, 'CALLOUT',
       'You have been offered a call: ' || a.shift_title,
       a.shift_title, a.offered_at, 'N'
FROM assignments a WHERE a.status = 'O';

-- Pending queue rows: the drain is observable on the first background tick.
INSERT INTO callboard_queue (org_id, kind, payload, queued_at)
SELECT a.org_id, 'ACCEPT',
       '{"assignment_id": ' || a.id || ', "crew_id": ' || a.crew_id || ', "shift_id": ' || a.shift_id || '}',
       extract(epoch from now() - interval '9 minutes')::int
FROM assignments a WHERE a.status = 'A' AND a.org_id IN (3, 7) LIMIT 4;
