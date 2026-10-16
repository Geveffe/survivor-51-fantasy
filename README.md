# Survivor 51 Fantasy Points

Scrapes the [Global TV Survivor 51 Fantasy Tribe results](https://www.globaltv.com/survivor-51-fantasy-tribe/#results)
and publishes a table of points per castaway per episode, plus a total, to GitHub Pages.

Fantasy players' tribes (8 picks + 1 MVP each) live in `picks.json`; the site shows each player's points overall and per episode in the same grid layout as the picks sheet.

A GitHub Action re-scrapes every 3 hours (and on push / manual run). Run locally with `python3 scrape.py _site`.
