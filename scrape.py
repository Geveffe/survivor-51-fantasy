#!/usr/bin/env python3
"""Scrape Global TV's Survivor 51 Fantasy Tribe results and build a static points table.

Each episode's points are published as an image whose alt text lists every
castaway's points ("Alexis total points: 1; An total points: 11; ...").
"""
import html
import json
import re
import shutil
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


def rank(values):
    """Competition ranking (1, 2, 2, 4) for a {key: score} dict."""
    ordered = sorted(values.values(), reverse=True)
    return {k: ordered.index(v) + 1 for k, v in values.items()}


def build(episodes, picks):
    eps = sorted(episodes)
    order = {c: i for i, c in enumerate(picks.get("castaway_order", []))}
    players = picks["players"]
    picked = {c for p in players for c in p["picks"]}
    listed = {c for e in eps for c in episodes[e]}
    names = sorted(picked | listed, key=lambda c: (order.get(c, len(order)), c))
    tribe_of = {c: t for t, info in picks.get("tribes", {}).items() for c in info["members"]}

    castaways = []
    for c in names:
        pts = [episodes[e].get(c) for e in eps]
        castaways.append({
            "name": c,
            "tribe": tribe_of.get(c),
            "points": pts,
            "total": sum(x or 0 for x in pts),
            "picked_by": sum(c in p["picks"] for p in players),
        })
    cast_total = {c["name"]: c["total"] for c in castaways}

    def tribe_score(p, upto):
        return sum(episodes[e].get(c) or 0 for e in eps[:upto] for c in p["picks"])

    totals = {p["name"]: tribe_score(p, len(eps)) for p in players}
    ranks = rank(totals)
    prev = rank({p["name"]: tribe_score(p, len(eps) - 1) for p in players}) if len(eps) > 1 else ranks
    standings = []
    for p in players:
        n = p["name"]
        standings.append({
            "name": n,
            "picks": p["picks"],
            "mvp": p["mvp"],
            "total": totals[n],
            "rank": ranks[n],
            "move": prev[n] - ranks[n],
            "last": sum(episodes[eps[-1]].get(c) or 0 for c in p["picks"]),
        })
    standings.sort(key=lambda s: (s["rank"], s["name"]))
    return {"eps": eps, "episodes": episodes, "castaways": castaways, "cast_total": cast_total,
            "players": players, "standings": standings, "totals": totals, "ranks": ranks,
            "tribes": picks.get("tribes", {})}


e = html.escape


def tribe_dot(d, c):
    t = next((t for t, info in d["tribes"].items() if c in info["members"]), None)
    if not t:
        return ""
    return f'<i class="dot" style="--c:{d["tribes"][t]["color"]}" title="{e(t)}"></i>'


def move_badge(m):
    if m > 0:
        return f'<span class="move up" title="Up {m} since last episode">▲{m}</span>'
    if m < 0:
        return f'<span class="move down" title="Down {-m} since last episode">▼{-m}</span>'
    return '<span class="move same" title="No change">–</span>'


def podium(d):
    last = d["eps"][-1]
    cards = []
    for s in d["standings"][:3]:
        chips = "".join(
            f'<li class="{"mvp" if c == s["mvp"] else ""}">{tribe_dot(d, c)}{e(c)}</li>'
            for c in sorted(s["picks"], key=lambda c: -d["cast_total"].get(c, 0))
        )
        cards.append(f'''<article class="podium-card place-{s["rank"]}">
  <div class="medal">{s["rank"]}</div>
  <h3>{e(s["name"])}</h3>
  <div class="score"><b>{s["total"]}</b><span>pts</span></div>
  <p class="sub">+{s["last"]} in Ep {last} {move_badge(s["move"])}</p>
  <ul class="chips">{chips}</ul>
</article>''')
    return "\n".join(cards)


def leaderboard(d):
    """Everyone below the podium, split into two columns that each carry a header."""
    rest = d["standings"][3:]
    half = (len(rest) + 1) // 2
    head = (
        '<div class="board-head" aria-hidden="true"><span>#</span><span>Player</span><span>Move</span>'
        f'<span>Ep {d["eps"][-1]}</span><span>Total</span></div>'
    )
    cols = []
    for chunk in (rest[:half], rest[half:]):
        if not chunk:
            continue
        rows = []
        for s in chunk:
            title = "Tribe: " + ", ".join(s["picks"]) + f' · MVP: {s["mvp"]}'
            rows.append(
                f'<li title="{e(title)}"><span class="rk">{s["rank"]}</span><span class="nm">{e(s["name"])}</span>'
                f'{move_badge(s["move"])}<span class="ep">+{s["last"]}</span><span class="tot">{s["total"]}</span></li>'
            )
        cols.append(f'<div>{head}<ol class="board">{"".join(rows)}</ol></div>')
    return "\n".join(cols)


def tribe_grid(d, points, label):
    """Spreadsheet-style grid: rows = castaways, columns = fantasy players.

    Black = not on that player's tribe, yellow = MVP, red = castaway not listed.
    """
    players = d["players"]
    totals = {p["name"]: sum(points.get(c) or 0 for c in p["picks"]) for p in players}
    ranks = rank(totals)
    head = "".join(f'<th class="pl" scope="col"><span>{e(p["name"])}</span></th>' for p in players)
    body = []
    for c in d["castaways"]:
        cells = []
        for p in players:
            if c["name"] not in p["picks"]:
                cells.append("<td class=off></td>")
                continue
            v = points.get(c["name"])
            cls = "gone" if v is None else "on"
            if c["name"] == p["mvp"]:
                cls += " mvp"
            title = f'{p["name"]} · {c["name"]}' + (" (MVP)" if c["name"] == p["mvp"] else "")
            title += " · not listed" if v is None else f" · {v} pts"
            cells.append(f'<td class="{cls}" title="{e(title)}">{"" if v is None else v}</td>')
        body.append(f'<tr><th class="cn" scope="row">{tribe_dot(d, c["name"])}{e(c["name"])}</th>{"".join(cells)}</tr>')
    tot = "".join(f"<td>{totals[p['name']]}</td>" for p in players)
    rk = "".join(f"<td>{ranks[p['name']]}</td>" for p in players)
    return (
        f'<table class="grid" aria-label="{e(label)} points by player">'
        f'<thead><tr><th class="cn corner" scope="col">Castaway</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody>'
        f'<tfoot><tr class="t-total"><th class="cn" scope="row">Total</th>{tot}</tr>'
        f'<tr class="t-rank"><th class="cn" scope="row">Rank</th>{rk}</tr></tfoot></table>'
    )


def castaway_table(d):
    eps = d["eps"]
    head = "".join(f'<th class="num" data-sort="num" scope="col">Ep {n}</th>' for n in eps)
    rows = sorted(d["castaways"], key=lambda c: (-c["total"], c["name"]))
    most = max(c["picked_by"] for c in rows) or 1
    body = []
    for c in rows:
        cells = "".join(
            f'<td class="num">{x}</td>' if x is not None else '<td class="gone" title="Not listed"></td>'
            for x in c["points"]
        )
        bar = f'<span class="bar"><i style="width:{100 * c["picked_by"] / most:.0f}%"></i></span>'
        body.append(
            f'<tr><th class="cn" scope="row">{tribe_dot(d, c["name"])}{e(c["name"])}</th>{cells}'
            f'<td class="num tot">{c["total"]}</td><td class="num pick">{bar}<span class="n">{c["picked_by"]}</span></td></tr>'
        )
    return (
        '<table id="castaways-table" class="sortable"><thead><tr><th data-sort="text" scope="col">Castaway</th>'
        f'{head}<th class="num" data-sort="num" scope="col">Total</th>'
        '<th class="num" data-sort="num" scope="col">Picked by</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )


def render(d, updated):
    eps = d["eps"]
    last = eps[-1]
    overall = {c["name"]: c["total"] for c in d["castaways"]}
    views = [("overall", "Season", overall)] + [(f"ep{n}", f"Ep {n}", d["episodes"][n]) for n in eps]
    buttons = "".join(
        f'<button type="button" data-view="{k}" aria-pressed="{str(i == 0).lower()}">{label}</button>'
        for i, (k, label, _) in enumerate(views)
    )
    grids = "".join(
        f'<div class="view" data-view="{k}"{"" if i == 0 else " hidden"}>{tribe_grid(d, pts, label)}</div>'
        for i, (k, label, pts) in enumerate(views)
    )
    legend_tribes = "".join(
        f'<span><i class="dot" style="--c:{info["color"]}"></i>{e(t)}</span>' for t, info in d["tribes"].items()
    )
    leader = d["standings"][0]
    hot = max(d["castaways"], key=lambda c: c["total"])
    best_ep = max(d["standings"], key=lambda s: s["last"])
    climber = max(d["standings"], key=lambda s: s["move"])
    fill = {
        "PODIUM": podium(d),
        "LEADERBOARD": leaderboard(d),
        "VIEW_BUTTONS": buttons,
        "GRIDS": grids,
        "CASTAWAYS": castaway_table(d),
        "LEGEND_TRIBES": legend_tribes,
        "LAST_EP": str(last),
        "CLIMBER": e(climber["name"]) if climber["move"] > 0 else "No movement",
        "CLIMB": f"▲{climber['move']}" if climber["move"] > 0 else "",
        "LEADER": e(leader["name"]),
        "LEADER_PTS": str(leader["total"]),
        "HOT": e(hot["name"]),
        "HOT_PTS": str(hot["total"]),
        "BEST_EP": e(best_ep["name"]),
        "BEST_EP_PTS": str(best_ep["last"]),
        "UPDATED": e(updated),
        "SOURCE": e(URL + "#results"),
    }
    out = (Path(__file__).parent / "template.html").read_text()
    for k, v in fill.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def main():
    p = ResultsParser()
    p.feed(fetch())
    if not p.episodes:
        sys.exit("No episode results found - page layout may have changed.")
    here = Path(__file__).parent
    for ep, fixes in json.loads((here / "corrections.json").read_text()).items():
        if ep.isdigit() and int(ep) in p.episodes:
            for name, pts in fixes.items():
                if p.episodes[int(ep)].get(name) == pts:
                    print(f"Correction for {name} ep {ep} now matches the source; it can be removed.")
                p.episodes[int(ep)][name] = pts
    picks = json.loads((here / "picks.json").read_text())
    d = build(p.episodes, picks)
    now = datetime.now(timezone.utc)
    updated = now.strftime("%b %-d, %Y · %-I:%M %p UTC")
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(here / "static", OUT, dirs_exist_ok=True)
    (OUT / "index.html").write_text(render(d, updated))
    (OUT / "data.json").write_text(json.dumps(
        {"updated": now.strftime("%Y-%m-%d %H:%M UTC"), "source": URL,
         "episodes": {str(k): p.episodes[k] for k in d["eps"]}}, indent=2))
    print(f"Episodes {d['eps']}; {len(d['castaways'])} castaways, {len(d['players'])} players -> {OUT}/index.html")


if __name__ == "__main__":
    main()
