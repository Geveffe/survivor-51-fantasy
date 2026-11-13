---
name: check-points
description: Compare Global TV's episode points images against their alt text / metadata for every episode and fix mismatches (the image wins). Use whenever the user asks to compare, check, verify or match the images and text/metadata for points, "games", episodes or scores — e.g. "compare the images and text for points", "check the images and metadata match", "are the points right".
---

# Check episode points images against their text

Global TV posts one image per episode on its results page. `scrape.py` reads each castaway's points from the
image's alt text, but the alt text is sometimes wrong. **The image is always right.**

1. Run the helper with a fresh output dir in the session scratchpad:
   `python3 .claude/skills/check-points/fetch_images.py <scratchpad>/points-check`
   It prints each episode's alt-text points, saves image pieces `ep<N>_<i>.png`, and lists where the alt text
   differs from `docs/data.json` (those should only be existing `corrections.json` entries).
2. Read **every** piece with the Read tool. For each castaway, compare the big total number with the alt text,
   and check the "Points Breakdown" lines add up to that total. Don't skip episodes that checked out before.
3. Where the image differs from the alt text, add the image's value to `corrections.json`
   (`{"<episode>": {"<Castaway>": points}}`). If an existing correction now matches the alt text, it can be removed.
4. If `corrections.json` changed, commit and push it (message like "Correct X's episode N points (alt text says A,
   image says B)"), then refresh the site: ask the user to run `! ~/.local/bin/survivor-dispatch.sh`.
5. Report per episode: matches, or which castaways differ (alt vs image) and what you changed.
   Mention which episodes the page has (episode 1 isn't posted).
