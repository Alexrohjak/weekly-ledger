#!/usr/bin/env python3
"""Extract training data from The Week Ledger's HTML into tidy CSV/JSON.

The ledger keeps its state in its own markup: the live week under #days, filed
weeks cloned into <details class="wkfile"> under #archlist, and next week staged
under #nextdays. Filed weeks keep their inputs' values (disabled, not stripped),
so the whole history is recoverable from one file.

Reads live-snapshot.html by default. Writes data/runs.csv, data/sets.csv and
data/sessions.json. Staged (not-yet-happened) days are skipped.

Stdlib only — no bs4/lxml on this machine.

    python3 tools/extract_sessions.py
    python3 tools/extract_sessions.py --only-logged
    python3 tools/extract_sessions.py some-other-snapshot.html
"""

import argparse
import csv
import json
import os
import re
import sys
from html.parser import HTMLParser

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'source', 'track', 'wbr'}
SKIP_TEXT = {'script', 'style'}


class Node:
    __slots__ = ('tag', 'attrs', 'children', 'parent', 'text')

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.parent = parent
        self.text = ''

    def classes(self):
        return set((self.attrs.get('class') or '').split())

    def has(self, cls):
        return cls in self.classes()


class Builder(HTMLParser):
    """Minimal DOM builder. HTMLParser puts script/style in CDATA mode, so the
    app's JS (which contains HTML strings) is not parsed as markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('#root')
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, dict(attrs), self.cur))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        if self.cur.tag in SKIP_TEXT:
            return
        t = Node('#text', parent=self.cur)
        t.text = data
        self.cur.children.append(t)


def walk(node):
    for c in node.children:
        yield c
        yield from walk(c)


def text_of(node):
    if node is None:
        return ''
    if node.tag == '#text':
        return node.text
    if node.tag in SKIP_TEXT:
        return ''
    return ''.join(text_of(c) for c in node.children)


def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def find(node, pred):
    for n in walk(node):
        if pred(n):
            return n
    return None


def find_all(node, pred):
    return [n for n in walk(node) if pred(n)]


def parse_clock(v):
    """mm:ss, h:mm:ss, or bare minutes -> seconds. Mirrors the app's parseClock."""
    v = clean(v)
    if not v:
        return None
    parts = v.split(':')
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1] or 0)
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2] or 0)
        return int(round(float(v) * 60))
    except ValueError:
        return None


def fmt_clock(secs):
    if secs is None:
        return ''
    secs = int(round(secs))
    h, m, s = secs // 3600, secs % 3600 // 60, secs % 60
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def to_float(v):
    v = clean(v).replace(',', '.')
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def week_context(day):
    """Which week bucket a day belongs to: an archived week, the live week, or
    the staged next week (which we skip -- it hasn't happened)."""
    n = day.parent
    while n is not None:
        if n.tag == 'details' and n.has('wkfile'):
            summary = find(n, lambda x: x.tag == 'summary')
            wk = rng = score = ''
            if summary:
                wk = clean(text_of(find(summary, lambda x: x.has('fwk'))))
                rng = clean(text_of(find(summary, lambda x: x.has('frange'))))
                score = clean(text_of(find(summary, lambda x: x.has('fscore'))))
            return ('archived', wk, rng, score)
        if n.attrs.get('id') == 'nextdays':
            return ('staged', '', '', '')
        if n.attrs.get('id') == 'days':
            return ('live', '', '', '')
        n = n.parent
    return ('unknown', '', '', '')


def extract(path):
    with open(path, encoding='utf-8') as f:
        b = Builder()
        b.feed(f.read())
    root = b.root

    live_wk = clean(text_of(find(root, lambda n: n.attrs.get('id') == 'wknum')))
    live_rng = clean(text_of(find(root, lambda n: n.attrs.get('id') == 'wrange')))

    runs, sets_, sessions = [], [], []

    for day in find_all(root, lambda n: n.tag == 'li' and n.has('day')):
        kind, wk, rng, score = week_context(day)
        if kind == 'staged':
            continue
        if kind == 'live':
            wk, rng = live_wk, live_rng
        date = day.attrs.get('data-date', '')

        for blk in find_all(day, lambda n: n.tag == 'li' and n.has('blk')):
            tick = find(blk, lambda n: n.tag == 'input' and n.has('tick'))
            done = tick is not None and 'checked' in tick.attrs
            title = clean(text_of(find(blk, lambda n: n.has('ttl'))))
            start = clean(text_of(find(blk, lambda n: n.has('t') and n.tag == 'span')))
            cat = blk.attrs.get('data-cat', '')

            log = find(blk, lambda n: n.has('log'))
            stype = 'other'

            if log is not None:
                for row in find_all(log, lambda n: n.has('lg')):
                    if row.has('lrun'):
                        stype = 'run'
                        km = to_float((find(row, lambda n: n.has('lkm')) or Node('x')).attrs.get('value'))
                        secs = parse_clock((find(row, lambda n: n.has('ltime')) or Node('x')).attrs.get('value'))
                        pace = (secs / km) if (km and secs and km > 0) else None
                        runs.append({
                            'date': date, 'week': wk, 'title': title, 'category': cat,
                            'planned': clean(text_of(find(row, lambda n: n.has('lrx')))),
                            'done': done,
                            'km': km if km is not None else '',
                            'time': fmt_clock(secs),
                            'time_s': secs if secs is not None else '',
                            'pace_s_per_km': round(pace, 1) if pace else '',
                            'pace': fmt_clock(pace) + '/km' if pace else '',
                            'logged': bool(km or secs),
                            'archived': kind == 'archived',
                        })
                    else:
                        ex = row.attrs.get('data-ex', '')
                        kg_in = find(row, lambda n: n.has('lkg'))
                        if not ex and kg_in is None:
                            continue
                        stype = 'gym'
                        hit = find(row, lambda n: n.has('lhitbox'))
                        kg = to_float(kg_in.attrs.get('value')) if kg_in is not None else None
                        sets_.append({
                            'date': date, 'week': wk, 'session': title, 'category': cat,
                            'exercise': ex,
                            'prescription': clean(text_of(find(row, lambda n: n.has('lrx')))),
                            'kg': kg if kg is not None else '',
                            'hit': hit is not None and 'checked' in hit.attrs,
                            'session_done': done,
                            'logged': kg is not None,
                            'archived': kind == 'archived',
                        })

            sessions.append({
                'date': date, 'week': wk, 'range': rng, 'title': title,
                'category': cat, 'start': start, 'type': stype, 'done': done,
                'archived': kind == 'archived',
            })

    return {'source': os.path.basename(path), 'live_week': live_wk,
            'sessions': sessions, 'runs': runs, 'sets': sets_}


def write_csv(path, rows, cols):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in cols})


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='*', default=None,
                    help='HTML snapshot(s) to read (default: live-snapshot.html)')
    ap.add_argument('--out', default='data', help='output directory (default: data)')
    ap.add_argument('--only-logged', action='store_true',
                    help='drop rows with no number recorded')
    args = ap.parse_args()

    files = args.files or ['live-snapshot.html']
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        sys.exit(f'not found: {", ".join(missing)}\n'
                 f'(the nightly routine writes live-snapshot.html; '
                 f'run from the repo root)')

    runs, sets_, sessions = [], [], []
    for path in files:
        d = extract(path)
        runs += d['runs']
        sets_ += d['sets']
        sessions += d['sessions']

    if args.only_logged:
        runs = [r for r in runs if r['logged']]
        sets_ = [s for s in sets_ if s['logged']]

    write_csv(os.path.join(args.out, 'runs.csv'), runs,
              ['date', 'week', 'title', 'planned', 'done', 'km', 'time',
               'time_s', 'pace_s_per_km', 'pace', 'logged', 'archived'])
    write_csv(os.path.join(args.out, 'sets.csv'), sets_,
              ['date', 'week', 'session', 'exercise', 'prescription', 'kg',
               'hit', 'session_done', 'logged', 'archived'])
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, 'sessions.json'), 'w', encoding='utf-8') as f:
        json.dump({'sessions': sessions, 'runs': runs, 'sets': sets_}, f,
                  indent=2, ensure_ascii=False)

    logged_runs = [r for r in runs if r['logged']]
    logged_sets = [s for s in sets_ if s['logged']]
    weeks = sorted({s['week'] for s in sessions if s['week']})
    km = sum(r['km'] for r in logged_runs if isinstance(r['km'], float))

    print(f'read      : {", ".join(files)}')
    print(f'weeks     : {len(weeks)}  ({", ".join(weeks) if weeks else "none"})')
    print(f'sessions  : {len(sessions)}  ({sum(1 for s in sessions if s["done"])} done)')
    print(f'run slots : {len(runs)}  ({len(logged_runs)} with a number)')
    print(f'gym sets  : {len(sets_)}  ({len(logged_sets)} with a weight)')
    print(f'total km  : {km:.1f}')
    print(f'wrote     : {args.out}/runs.csv, {args.out}/sets.csv, {args.out}/sessions.json')
    if not logged_runs and not logged_sets:
        print('\nNothing logged yet — fill in kg / km / time in the ledger and '
              'the nightly snapshot will carry them here.')


if __name__ == '__main__':
    main()
