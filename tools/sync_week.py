#!/usr/bin/env python3
"""Build a week of ledger blocks from iCalendar feeds.

The artifact cannot do this itself: it runs under a CSP that blocks every
external host except Google Fonts, so no ICS feed is reachable from the page.
The fetch has to happen here, and the result is published to the artifact.

Feeds are read from .env (gitignored — a feed URL is a credential: it exposes
the whole schedule to anyone holding it):

    LEDGER_FEED_HVL=https://cloud.timeedit.net/.../schedule.ics    (TimeEdit)
    LEDGER_FEED_UIB=https://.../feeds/calendars/user_....ics          (Canvas)
    LEDGER_FEED_WORK=https://.../schedule.ics                          (When I Work)

Only calendar events come from feeds. Everything self-directed — gym, runs,
climbing, guitar, study, team practices — is not in any feed and is pasted in
from templates/blocks.html instead.

    python3 tools/sync_week.py --list                 # what the feeds hold
    python3 tools/sync_week.py --week 2026-08-24      # blocks for that week
    python3 tools/sync_week.py --week 2026-08-24 --into index.html
    python3 tools/sync_week.py --from-file some.ics --list

Stdlib only — no icalendar/requests on this machine.
"""

import argparse
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

FEED_VARS = ('LEDGER_FEED_HVL', 'LEDGER_FEED_UIB', 'LEDGER_FEED_WORK')

# Courses no longer taken. The feeds keep sending them, so drop them here.
DROPPED_COURSES = ('DAT156',)

# A deadline has a date and no span, so it cannot be placed like a lecture.
# It becomes a short block at the end of its due day: last in the list, a
# sliver at the bottom of the diagram column, over nothing.
DEADLINE_START, DEADLINE_END = '23:30', '23:59'

# Which ledger category an event lands in, by what its summary looks like.
# First match wins; anything unmatched becomes 'life' and is flagged in --list
# so it can be classified rather than silently mis-coloured.
CATEGORY_RULES = (
    # Teaching comes in more shapes than "forelesning": HVL also files
    # veiledning, digital undervisning and informasjon, and all of them are
    # somewhere you have to be.
    ('study', r'forelesning|lecture|laboratorie|lab\b|seminar|kollokvie|øving|'
              r'veiledning|undervisning|informasjon|orientering|oppstart|gruppetime|'
              r'praksis|exam|eksamen'),
    ('work', r'trener|vakt|shift|resepsjon|arbeid|jobb'),
    ('fitness', r'trening|practice|match|kamp|gym|løp'),
    ('music', r'guitar|gitar|band'),
)


# ---------- .env ----------

def load_env(path='.env'):
    """Read KEY=VALUE lines. Values are not logged anywhere — they are secrets."""
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def feed_urls():
    env = {**load_env(), **os.environ}
    return {k: env[k] for k in FEED_VARS if env.get(k)}


# ---------- ICS ----------

def unfold(text):
    """RFC 5545 line folding: a leading space continues the previous line."""
    out = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if line[:1] in (' ', '\t') and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def unescape(v):
    return (v.replace('\\n', ' ').replace('\\N', ' ')
             .replace('\\,', ',').replace('\\;', ';').replace('\\\\', '\\'))


def parse_dt(value, params):
    """DTSTART/DTEND -> naive local datetime, or a date for all-day events.

    UTC stamps (trailing Z) are converted using the machine's own offset. That
    is right for a schedule lived in one timezone and wrong for one that is not;
    TZID-qualified values are taken at face value, which is the common case for
    TimeEdit.
    """
    if params.get('VALUE') == 'DATE' or re.fullmatch(r'\d{8}', value):
        return datetime.strptime(value[:8], '%Y%m%d').date()
    if value.endswith('Z'):
        utc = datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        return utc.astimezone().replace(tzinfo=None)
    return datetime.strptime(value[:15], '%Y%m%dT%H%M%S')


def parse_ics(text, source=''):
    """VEVENTs -> dicts. RRULEs are carried through unexpanded and reported,
    never silently dropped: a repeating lecture that quietly vanishes is the
    exact failure this rebuild exists to fix."""
    events, cur = [], None
    for line in unfold(text):
        if line == 'BEGIN:VEVENT':
            cur = {'source': source}
            continue
        if line == 'END:VEVENT':
            if cur is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None or ':' not in line:
            continue
        name, value = line.split(':', 1)
        parts = name.split(';')
        key = parts[0].upper()
        params = {}
        for p in parts[1:]:
            if '=' in p:
                pk, pv = p.split('=', 1)
                params[pk.upper()] = pv
        if key in ('DTSTART', 'DTEND'):
            try:
                cur[key.lower()] = parse_dt(value, params)
            except ValueError:
                cur.setdefault('bad', []).append(name)
        elif key in ('SUMMARY', 'LOCATION', 'DESCRIPTION', 'RRULE', 'UID'):
            cur[key.lower()] = unescape(value)
    return events


def fetch(url, timeout=30):
    # TimeEdit and Canvas hand out webcal:// links. It is http underneath, but
    # urllib has never heard of the scheme, so paste-what-they-give-you fails.
    if url.startswith(('webcal://', 'webcals://')):
        url = 'https://' + url.split('://', 1)[1]
    req = urllib.request.Request(url, headers={'User-Agent': 'week-ledger/1'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


# ---------- events -> blocks ----------

def categorise(summary):
    low = (summary or '').lower()
    for cat, pattern in CATEGORY_RULES:
        if re.search(pattern, low):
            return cat
    return 'life'


SHIFT_RE = re.compile(r'^\s*Shift as\s+(?P<role>.+?)\s+at\s+.+$', re.I)


def clean_summary(summary):
    """Strip what each feed adds and the ledger does not need.

    HVL and UiB both append the course code in brackets — "Forelesning DAT158
    [DAT158-1 26H]", "INF122: Forelesning [INF122]" — where the code is already
    in the title. When I Work wraps the role: "Shift as X at Y", and Y is the
    same roster name as the location.
    """
    summary = (summary or '').strip()
    shift = SHIFT_RE.match(summary)
    if shift:
        return shift.group('role').strip()
    summary = re.sub(r'\s*\[[^\]]*\]', '', summary)
    return re.sub(r'\s+', ' ', summary).strip(' ,;:') or 'Untitled'


def clean_location(location, source=''):
    """Drop TimeEdit's room-type suffix — "M005 <Auditorium>".

    The comma means different things per feed: TimeEdit separates alternative
    rooms ("Aud14 F118,HGSD2008"), while Canvas writes room and building
    ("Auditorium 1, Realfagbygget"). Only the former is a list.
    """
    location = re.sub(r'\s*<[^>]*>', '', (location or '').strip())
    location = re.sub(r'\s+', ' ', location).strip(' ,;')
    if source == 'hvl' and ',' in location:
        return ' / '.join(r.strip() for r in location.split(',') if r.strip())
    return location


def title_of(ev):
    summary = clean_summary(ev.get('summary'))
    # A shift's location is the roster it came from, which only restates the
    # role ("Resepsjonsvakt" at "Resepsjonsvakt - Timeplan"). Drop it.
    if SHIFT_RE.match((ev.get('summary') or '').strip()):
        return summary
    location = clean_location(ev.get('location'), ev.get('source', ''))
    if location and location.lower() != summary.lower():
        return f'{summary} · {location}'
    return summary


def block_key(start, title):
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return f'{start.strftime("%H-%M")}-{slug}'[:40]


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
             .replace('"', '&quot;'))


def block_html(ev, staged=False):
    """One .blk, matching what the app writes itself.

    A staged block is frozen the way the app freezes #nextdays — inputs
    disabled, text not editable — because rollWeek() re-enables exactly those
    when it promotes the week.
    """
    start, end = ev['dtstart'], ev.get('dtend') or ev['dtstart'] + timedelta(hours=1)
    title = title_of(ev)
    edit = 'false' if staged else 'plaintext-only'
    off = ' disabled=""' if staged else ''
    return (
        f'<li class="blk" data-cat="{categorise(ev.get("summary"))}" data-recur="0"'
        f' data-end="{end:%H:%M}" data-src="feed" data-key="{esc(block_key(start, title))}">'
        '<button class="grip" type="button" aria-label="Drag to move"'
        ' title="Drag to move · Alt+arrows">⠿</button>'
        f'<label class="tk"><input class="tick" type="checkbox" aria-label="Done"{off}></label>'
        '<button class="cat" type="button" aria-label="Change category"></button>'
        f'<span class="t" contenteditable="{edit}" aria-label="Time">{start:%H:%M}</span>'
        f'<span class="tend" contenteditable="plaintext-only" aria-label="End time">{end:%H:%M}</span>'
        f'<span class="ttl" contenteditable="{edit}" aria-label="Activity">{esc(title)}</span>'
        '<button class="rec" type="button" aria-label="Toggle recurring">↻</button>'
        '<button class="del" type="button" aria-label="Delete">×</button></li>')


def is_dropped(ev):
    haystack = f'{ev.get("summary", "")} {ev.get("description", "")}'.upper()
    return any(c.upper() in haystack for c in DROPPED_COURSES)


def as_deadline(ev):
    """An all-day item is a due date. Give it the end of its day, so it reads
    as "by tonight" and cannot sit on top of anything real."""
    day = ev['dtstart']
    h1, m1 = (int(x) for x in DEADLINE_START.split(':'))
    h2, m2 = (int(x) for x in DEADLINE_END.split(':'))
    out = dict(ev)
    out['dtstart'] = datetime(day.year, day.month, day.day, h1, m1)
    out['dtend'] = datetime(day.year, day.month, day.day, h2, m2)
    out['summary'] = 'Frist: ' + clean_summary(ev.get('summary'))
    out['location'] = ''
    out['deadline'] = True
    return out


def week_of(events, monday, deadlines=True):
    """Events falling in the seven days from monday, grouped by date and sorted
    by start. All-day items become end-of-day deadline blocks unless disabled."""
    days = {monday + timedelta(days=i): [] for i in range(7)}
    skipped = []
    for ev in events:
        start = ev.get('dtstart')
        if start is None:
            skipped.append((ev, 'no start'))
            continue
        if is_dropped(ev):
            skipped.append((ev, 'dropped course'))
            continue
        if not isinstance(start, datetime):
            if not deadlines:
                skipped.append((ev, 'all-day'))
                continue
            ev = as_deadline(ev)
            start = ev['dtstart']
        if start.date() in days:
            days[start.date()].append(ev)
        elif ev.get('rrule'):
            skipped.append((ev, 'repeats — RRULE not expanded'))
    for d in days:
        days[d].sort(key=lambda e: e['dtstart'])
    return days, skipped


# ---------- splice into the ledger ----------

def splice(html, days, section='days'):
    """Replace each day's <ul class="blks"> with the feed's blocks for that date.

    Only feed blocks are written. Anything hand-added to a day is dropped, so
    run this before adding gym/runs/practices to a week, not after.
    """
    marker = f'id="{section}"'
    if marker not in html:
        raise SystemExit(f'no #{section} in the target file')
    start = html.index(marker)
    end = html.index('</ol>', start)
    head, region, tail = html[:start], html[start:end], html[end:]
    staged = section == 'nextdays'
    written = 0

    def replace_day(m):
        nonlocal written
        iso = m.group('date')
        try:
            d = datetime.strptime(iso, '%Y-%m-%d').date()
        except ValueError:
            return m.group(0)
        if d not in days:
            return m.group(0)
        blocks = ''.join(block_html(ev, staged) for ev in days[d])
        written += len(days[d])
        return m.group('before') + '<ul class="blks">' + blocks + '</ul>'

    region = re.sub(
        r'(?P<before><li class="day" data-date="(?P<date>[^"]+)".*?)<ul class="blks">.*?</ul>',
        replace_day, region, flags=re.S)
    return head + region + tail, written


# ---------- cli ----------

def collect(args):
    if args.from_file:
        return parse_ics(open(args.from_file, encoding='utf-8').read(),
                         os.path.basename(args.from_file))
    urls = feed_urls()
    if not urls:
        raise SystemExit(
            'No feeds configured. Put them in .env (see .env.example):\n  '
            + '\n  '.join(f'{k}=...' for k in FEED_VARS))
    events = []
    for name, url in urls.items():
        label = name.replace('LEDGER_FEED_', '').lower()
        try:
            events += parse_ics(fetch(url), label)
        except Exception as exc:                      # noqa: BLE001 — report, don't abort
            print(f'! {label}: {type(exc).__name__}: {exc}', file=sys.stderr)
    return events


def monday_of(value):
    d = datetime.strptime(value, '%Y-%m-%d').date() if value else date.today()
    return d - timedelta(days=d.weekday())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--week', help='any date in the target week (default: this week)')
    ap.add_argument('--from-file', help='read one .ics from disk instead of the feeds')
    ap.add_argument('--into', help='ledger HTML to rewrite in place')
    ap.add_argument('--section', default='days', choices=('days', 'nextdays'),
                    help='which week to fill (default: days)')
    ap.add_argument('--list', action='store_true', help='print the week, write nothing')
    ap.add_argument('--no-deadlines', action='store_true',
                    help='leave all-day coursework due dates out entirely')
    args = ap.parse_args()

    events = collect(args)
    monday = monday_of(args.week)
    days, skipped = week_of(events, monday, deadlines=not args.no_deadlines)
    total = sum(len(v) for v in days.values())

    print(f'{len(events)} events in the feeds · {total} in the week of {monday}')
    for d in sorted(days):
        if not days[d]:
            print(f'  {d:%a %d}  —')
            continue
        for ev in days[d]:
            end = ev.get('dtend') or ev['dtstart'] + timedelta(hours=1)
            cat = categorise(ev.get('summary'))
            flag = ' ← unclassified' if cat == 'life' else ''
            print(f'  {d:%a %d}  {ev["dtstart"]:%H:%M}-{end:%H:%M}  {cat:8}'
                  f'{title_of(ev)[:56]}{flag}')
    if skipped:
        print(f'\nnot placed ({len(skipped)}):')
        for ev, why in skipped[:20]:
            print(f'  {why:32} {title_of(ev)[:52]}')

    if args.list or not args.into:
        if not args.into:
            print('\n(--into <file> to write these into a ledger)')
        return

    html = open(args.into, encoding='utf-8').read()
    out, written = splice(html, days, args.section)
    if args.section == 'nextdays':
        out = re.sub(r'(<span class="stagemeta" id="stagemeta">.*?·\s*)\d+( blocks</span>)',
                     rf'\g<1>{written}\g<2>', out, flags=re.S)
    open(args.into, 'w', encoding='utf-8').write(out)
    print(f'\nwrote {written} blocks into #{args.section} of {args.into}')
    print('gym, runs, climbing, guitar and practices are not in any feed — '
          'paste those from templates/blocks.html')


if __name__ == '__main__':
    main()
