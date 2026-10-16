#!/usr/bin/env python3
"""Scrape Global TV's Survivor 51 Fantasy Tribe results and build a static points table.

Each episode's points are published as an image whose alt text lists every
castaway's points ("Alexis total points: 1; An total points: 11; ...").
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

URL = "https://www.globaltv.com/survivor-51-fantasy-tribe/"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")


class ResultsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_results = False
        self.episode = None
        self.text = ""
        self.episodes = {}  # episode number -> {name: points}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "results":
            self.in_results = True
        if self.in_results and tag == "img" and self.episode is not None:
            scores = {}
            for name, pts in re.findall(r"([^;:]+?)\s+total points:\s*(-?\d+)", attrs.get("alt", "")):
                scores[name.strip()] = int(pts)
            if scores:
                self.episodes[self.episode] = scores
                self.episode = None

    def handle_data(self, data):
        if not self.in_results:
            return
        m = re.search(r"EPISODE\s+(\d+)\s+POINTS", data, re.I)
        if m:
            self.episode = int(m.group(1))


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (survivor-fantasy-table)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def build(episodes):
    eps = sorted(episodes)
    names = sorted({n for e in eps for n in episodes[e]})
    rows = []
    for n in names:
        pts = [episodes[e].get(n) for e in eps]
        rows.append({"name": n, "points": pts, "total": sum(p or 0 for p in pts)})
    rows.sort(key=lambda r: (-r["total"], r["name"]))
    return eps, rows


def castaway_table(eps, rows):
    e = html.escape
    head = "".join(f'<th class="num" data-sort="num">Ep {n}</th>' for n in eps)
    body = []
    for i, r in enumerate(rows, 1):
        cells = "".join(
            f'<td class="num">{p}</td>' if p is not None else '<td class="num out" title="Not listed">–</td>'
            for p in r["points"]
        )
        body.append(
            f'<tr><td class="num rank">{i}</td><td class="name">{e(r["name"])}</td>{cells}'
            f'<td class="num total">{r["total"]}</td></tr>'
        )
    return (
        '<table id="t"><thead><tr><th class="num" data-sort="num">#</th><th data-sort="text">Survivor</th>'
        f'{head}<th class="num" data-sort="num">Total Points</th></tr></thead><tbody>\n'
        + "\n".join(body) + "\n</tbody></table>"
    )


def tribe_grid(players, castaways, points, label):
    """Spreadsheet-style grid: rows = castaways, columns = fantasy players.

    points: {castaway: int or None}. Black = not on that player's tribe, yellow = MVP.
    """
    e = html.escape
    totals = {p["name"]: sum(points.get(c) or 0 for c in p["picks"]) for p in players}
    ranked = sorted(totals.values(), reverse=True)
    head = "".join(f"<th>{e(p['name'])}</th>" for p in players)
    body = []
    for c in castaways:
        cells = []
        for p in players:
            if c not in p["picks"]:
                cells.append('<td class="off"></td>')
                continue
            v = points.get(c)
            cls = "mvp" if c == p["mvp"] else "on"
            title = f"{p['name']}: {c}" + (" (MVP)" if c == p["mvp"] else "")
            cells.append(f'<td class="{cls}" title="{e(title)}">{"–" if v is None else v}</td>')
        body.append(f'<tr><th class="name">{e(c)}</th>{"".join(cells)}</tr>')
    tot = "".join(f'<td class="gtotal">{totals[p["name"]]}</td>' for p in players)
    rank = "".join(f'<td class="grank">{ranked.index(totals[p["name"]]) + 1}</td>' for p in players)
    return (
        f'<table class="grid" aria-label="{e(label)}"><thead><tr><th class="name">Castaway</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody>'
        f'<tfoot><tr><th class="name">{e(label)} total</th>{tot}</tr><tr><th class="name">Rank</th>{rank}</tr></tfoot></table>'
    )


def render(episodes, eps, rows, picks, updated):
    e = html.escape
    players = picks["players"]
    # Castaway row order follows the picks sheet; anyone new from the results goes at the end.
    order = {c: i for i, c in enumerate(picks.get("castaway_order", []))}
    picked = {c for p in players for c in p["picks"]}
    castaways = sorted(picked | {r["name"] for r in rows}, key=lambda c: (order.get(c, len(order)), c))
    overall = {r["name"]: r["total"] for r in rows}
    ep_buttons = "".join(
        f'<button type="button" data-ep="{n}" aria-pressed="{str(n == eps[-1]).lower()}">Episode {n}</button>'
        for n in eps
    )
    ep_tables = "".join(
        f'<div class="ep" data-ep="{n}"{"" if n == eps[-1] else " hidden"}>'
        + tribe_grid(players, castaways, episodes[n], f"Episode {n}") + "</div>"
        for n in eps
    )
    tpl = (Path(__file__).parent / "template.html").read_text()
    return (
        tpl.replace("{{OVERALL}}", tribe_grid(players, castaways, overall, "Overall"))
        .replace("{{EP_BUTTONS}}", ep_buttons)
        .replace("{{EP_TABLES}}", ep_tables)
        .replace("{{CASTAWAYS}}", castaway_table(eps, rows))
        .replace("{{UPDATED}}", e(updated))
        .replace("{{SOURCE}}", e(URL + "#results"))
    )


def main():
    p = ResultsParser()
    p.feed(fetch())
    if not p.episodes:
        sys.exit("No episode results found - page layout may have changed.")
    for ep, fixes in json.loads(Path(__file__).with_name("corrections.json").read_text()).items():
        if ep.isdigit() and int(ep) in p.episodes:
            for name, pts in fixes.items():
                if p.episodes[int(ep)].get(name) == pts:
                    print(f"Correction for {name} ep {ep} now matches the source; it can be removed.")
                p.episodes[int(ep)][name] = pts
    eps, rows = build(p.episodes)
    picks = json.loads(Path(__file__).with_name("picks.json").read_text())
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render(p.episodes, eps, rows, picks, updated))
    (OUT / "data.json").write_text(json.dumps(
        {"updated": updated, "source": URL, "episodes": {str(k): p.episodes[k] for k in eps}}, indent=2))
    print(f"Episodes {eps}; {len(rows)} castaways -> {OUT}/index.html")


if __name__ == "__main__":
    main()
