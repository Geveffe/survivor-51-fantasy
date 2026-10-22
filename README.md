# Survivor 51 Fantasy Points

Scrapes the [Global TV Survivor 51 Fantasy Tribe results](https://www.globaltv.com/survivor-51-fantasy-tribe/#results)
and publishes a table of points per castaway per episode, plus a total, to GitHub Pages.

Fantasy players' tribes (8 picks + 1 MVP each) live in `picks.json`; the site shows each player's points overall and per episode in the same grid layout as the picks sheet.

A GitHub Action re-scrapes several times a day: on its own 3-hour schedule, hourly via a laptop cron job that dispatches the workflow, and on demand from the site's Update Status page (`status.html`). Run locally with `python3 scrape.py _site`.
