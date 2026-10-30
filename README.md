# Survivor 51 Fantasy Points

Scrapes the [Global TV Survivor 51 Fantasy Tribe results](https://www.globaltv.com/survivor-51-fantasy-tribe/#results)
and publishes a table of points per castaway per episode, plus a total, to GitHub Pages.

Fantasy players' tribes (8 picks + 1 MVP each) live in `picks.json`; the site shows each player's points overall and per episode in the same grid layout as the picks sheet.

A GitHub Action re-scrapes several times a day: on its own 3-hour schedule, hourly via a laptop cron job that dispatches the workflow, and on demand from the site's Update Status page (`status.html`). Run locally with `python3 scrape.py _site`.

## Merge Pick

`merge.html` is an unlinked page where each player chooses a merge pick. Choosing only emails the player a confirmation link, and the pick is saved when they open it. The backend is a Google Apps Script web app in `apps-script/`:

1. At [script.google.com](https://script.google.com) create a project and paste in `MergePick.gs`, plus `Config.gs` (copy `Config.example.gs`, fill in each player's email; `Config.gs` is gitignored).
2. Deploy > New deployment > Web app, Execute as **Me**, access **Anyone**, and authorize it.
3. Put the web app URL in `API` in `static/merge.html` (and `docs/merge.html`).

Picks are saved in the script's Script Properties (`pick:<player>`).
