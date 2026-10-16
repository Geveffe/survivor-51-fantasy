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


def render(eps, rows, updated):
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
    tpl = (Path(__file__).parent / "template.html").read_text()
    return (
        tpl.replace("{{HEAD}}", head)
        .replace("{{BODY}}", "\n".join(body))
        .replace("{{UPDATED}}", e(updated))
        .replace("{{SOURCE}}", e(URL + "#results"))
    )


def main():
    p = ResultsParser()
    p.feed(fetch())
    if not p.episodes:
        sys.exit("No episode results found - page layout may have changed.")
    eps, rows = build(p.episodes)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render(eps, rows, updated))
    (OUT / "data.json").write_text(json.dumps(
        {"updated": updated, "source": URL, "episodes": {str(k): p.episodes[k] for k in eps}}, indent=2))
    print(f"Episodes {eps}; {len(rows)} castaways -> {OUT}/index.html")


if __name__ == "__main__":
    main()
