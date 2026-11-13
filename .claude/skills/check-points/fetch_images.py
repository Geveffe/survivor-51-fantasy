#!/usr/bin/env python3
"""Download each episode's points image from Global TV and split it into readable pieces.

Usage: python3 .claude/skills/check-points/fetch_images.py <output dir>
Writes <dir>/ep<N>_<i>.png pieces and <dir>/alt.json ({episode: {castaway: points}} from the alt text),
and prints any differences between the alt text and docs/data.json (which includes corrections.json).
"""
import json
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo))
import scrape  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
p = scrape.ResultsParser()
p.feed(scrape.fetch())
site = json.loads((repo / "docs/data.json").read_text())["episodes"]
alt = {}
for ep in sorted(p.episodes):
    req = urllib.request.Request(p.images[ep], headers={"User-Agent": "Mozilla/5.0"})
    im = Image.open(BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert("RGB")
    w, h = im.size
    n = (h + 749) // 750
    for i in range(n):
        im.crop((0, i * h // n, w, (i + 1) * h // n)).save(out / f"ep{ep}_{i}.png")
    alt[str(ep)] = p.episodes[ep]
    print(f"Episode {ep}: {len(p.episodes[ep])} castaways, {n} pieces")
    print("  alt text:", ", ".join(f"{c} {v}" for c, v in p.episodes[ep].items()))
(out / "alt.json").write_text(json.dumps(alt, indent=2))
diffs = [(e, c, alt[e][c], site.get(e, {}).get(c)) for e in alt for c in alt[e] if alt[e][c] != site.get(e, {}).get(c)]
print("Alt text vs site data differences (expected only where corrections.json applies):")
for e, c, a, s in diffs:
    print(f"  ep {e} {c}: alt {a}, site {s}")
print("  none" if not diffs else "")
