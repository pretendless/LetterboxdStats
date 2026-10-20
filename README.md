# LetterboxdStats

[@lebxdbot](https://t.me/lebxdbot) turns a Letterboxd export ZIP into a dark-theme chart report in the chat. `/start` begins. `/stop` cancels.

Webhook: `POST https://t2t-box.prtndz.workers.dev/lebxd` on the Cloudflare worker `t2t-box`.

## What it produces

You send the ZIP from Letterboxd → Settings → Import & Export → Export Your Data. The bot asks a few questions, then posts a short summary and a series of PNG charts in the same chat. The images below come from synthetic data, not a real export.

![Bot message asking for the watch period, with year and preset buttons](docs/images/wizard-period-step.png)

*The wizard asks one question at a time. Tap a button or type a reply.*

![Bar chart of film watches per year, each bar labelled with its count and a bold colored average rating](docs/images/watches-by-year.png)

*Watches per year, with the count and the bold colored average rating above each bar. These five years run blue, green, green, yellow, red.*

![Weekday and month bar charts stacked by watch year](docs/images/weekday-month-by-year.png)

*When you watch: weekdays and months, stacked by watch year in the same year colors.*

![Horizontal bars of the best-rated release years with averages and rated-film counts](docs/images/release-years-higher-rating.png)

*Release years with the highest average rating, among years with at least 3 rated films. Bar color follows the rating scale on the left.*

![Directors with the lowest average rating; short bars show the first 15 letters of the name with an ellipsis](docs/images/directors-lower-rating.png)

*Directors with the lowest average rating. A bar too short for 15 letters shows the first 15 and an ellipsis.*

![Twenty directors from a 4.80 average down to 1.00, colored from burgundy through red, yellow, green, and blue](docs/images/directors-higher-rating-20.png)

*A top 20 across the rating scale: blues near 1–1.6, greens through 2.75, yellows up to logo orange at 3.9, reds above that, and burgundy at 4.8. The three shortest bars show 15 letters and an ellipsis past the bar, with the same gap before the rating as after a normal bar.*

![Line chart of average rating by month, with a colored dot on each month](docs/images/average-rating-by-month.png)

*Average rating over the watch months: a line, and a dot colored on the rating scale.*

![Line chart of films watched per month, with dots and a dashed mean](docs/images/viewing-pace.png)

*Viewing pace by month. The dashed line is the mean.*

![Two stacked bar charts: films by release decade, and how ratings are distributed](docs/images/extra-stats-decade-rating.png)

*Release decade and the rating distribution. Color is the watch year.*

![Horizontal bars of watches by genre, stacked by watch year](docs/images/watches-by-genre.png)

*Watches by genre, stacked by watch year.*

![Horizontal bars of films that appear more than once, stacked by watch year](docs/images/top-rewatches.png)

*Films logged more than once, stacked by watch year.*

## Commands

| Command | What it does |
| --- | --- |
| `/start` | Asks for the Letterboxd export ZIP, then builds the charts. Default uses the usual set. Customize sets the top size (1–100), the minimum number of rated films, whether USA and English stay in those tops, the watch period, and films with no diary date. |
| `/start letterboxd` | The same wizard. This is what `https://t.me/lebxdbot?start=letterboxd` opens. |
| `/stop` | Clears the wizard. If a chart run is already in GitHub Actions, it stops that run. |

Dates are month before year. `2021-06.2022` means 2021-01-01 through 2022-06-30. A year is that whole year. A month is `06-2012` or `June 2012`. A day is `15-06-2012` or `15.06.2012`.

## Charts

The report is a set of PNG charts in the chat: calendar (watches, pace, weekdays), extra stats, and TMDB tops for genres, countries of origin, directors, actors, original language, and studios. A rating bar ends with a bold colored average and a regular parenthetical count. A name stays inside its bar and is shortened with an ellipsis only when it does not fit. A bar too short for 15 characters shows the first 15 characters and an ellipsis, running past the end of the bar.

Every chart uses one palette. The anchors are the three logo circles, measured from the non-overlapping interior of each circle: blue `#3FB7EB` at 0.25, green `#03E53E` at 0.50, and orange `#FC7A02` at 0.75. The blend is piecewise-linear in OKLab lightness, chroma, and hue. Below 0.05 it stays purple (`#7729FF`). From 0.05 to 0.25 it runs through blue shades and lands on logo blue; then green shades through 0.50; then yellow shades through logo orange at 0.75; then a bent path of distinct reds through 0.95, not one ramp from orange to the end; and from 0.95 on, burgundy (`#A90048`). A rating uses the whole range: 0.5 maps to 0 and 5 maps to 1. An ordered series (watch years, ranked genres), earliest or lowest first, starts from rank `q = k / (N + 1)` and bends that rank with a quadratic inside each quarter: toward 0 below blue, toward green between blue and orange, and toward 1 above orange. The knots stay put, so three values are blue, green, and orange, and seven values put those colors on the 2nd, 4th, and 6th (`0.25`, `0.5`, `0.75`), with the 1st at `0.0625` and the 7th at `0.9375`. Two values are blue and orange. One value is green.

Example title: Studios — lower rating (at least 3 rated films).

## Bot profile

An empty chat shows the description below, with Telegram's own Start button under it. That button is part of the Telegram app. A tap sends `/start`, which opens the wizard.

**Setup bot** writes the description, the short description, and the `/start` and `/stop` menu. The display name stays whatever BotFather already has. Run **Setup bot** once after this is on `main`. It does not publish the worker and it does not register the webhook.

Description (empty chat, and “What can this bot do?”):

> Letterboxd Stats (@lebxdbot) builds charts from a Letterboxd export.
>
> /start, then the ZIP. Next, keep the usual chart set or choose your own: top size from 1 to 100, minimum rated films, USA, English, and a watch period. /stop leaves the questions. A chart run that has already started stops too.
>
> Example:
> /start
> ZIP file
> defaults

Short description (profile page, and the text sent with a shared link):

> Letterboxd Stats. Charts from a Letterboxd export. /start opens the wizard.

Commands: start — Start a Letterboxd chart report. stop — Cancel the wizard or a running report.

If the live chat still answers in Russian, also run **Deploy worker**. Those replies are already English on `main` and reach Telegram only after that deploy. **Set webhook** registers `https://t2t-box.prtndz.workers.dev/lebxd` and refreshes the same command menu.

## Configuration

GitHub Actions secrets on this repository:

| Secret | Used by |
| --- | --- |
| `LEBXDBOT_TOKEN` | Chart workflow `letterboxd.yml` (download the ZIP and send the PNGs) |
| `WEBHOOK_SECRET` | **Set webhook** |
| `TMDB_BEARER_TOKEN` | Chart workflow (TMDB Read Access Token, not an API key) |
| `CLOUDFLARE_API_TOKEN` | **Deploy worker** |
| `CLOUDFLARE_ACCOUNT_ID` | **Deploy worker** |

Cloudflare worker `t2t-box` secrets used by this bot:

| Secret | Role |
| --- | --- |
| `LEBXDBOT_TOKEN` | Telegram bot token |
| `WEBHOOK_SECRET` | Check on `POST /lebxd` |
| `GHLEBXD_DISPATCH_TOKEN` | Starts and cancels `letterboxd.yml` |

Do not put secret values in git.

## Develop

Checks without Cloudflare and without tokens, Node 22:

```bash
cd worker
npm ci
npm test
```

## Workflows

Manual workflows, after merge to `main`:

1. **Deploy worker** — publishes worker `t2t-box`. Needs `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
2. **Set webhook** — points @lebxdbot at `https://t2t-box.prtndz.workers.dev/lebxd`.
3. **Setup bot** — English BotFather profile and command menu. Run this after merge. It does not register the webhook.
4. **Letterboxd** — the chart job. The worker starts it.

Layout:

- `worker/` — webhook and wizard, then `workflow_dispatch` of `letterboxd.yml`.
- `vm/letterboxd_genres.js` — wizard steps and date parsing.
- `scripts/` — calendar charts and TMDB charts. The job sends PNGs with `LEBXDBOT_TOKEN`.
