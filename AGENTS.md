# Agent notes

This file is for Cursor agents working in this repository. It is not user-facing. User-facing copy and `README.md` stay English and do not mention Telegram2Telemost. This file names the shared route and secrets so an agent does not break them. Names and locations only — never secret values.

## @lebxdbot

- Bot: `@lebxdbot`
- Commands: `/start` and `/stop`
- Webhook: `POST https://t2t-box.prtndz.workers.dev/lebxd`
- Workflow **Set webhook** registers that URL
- Workflow **Setup bot** writes the English description (empty-chat card), short description (profile), and `/start` `/stop` menu. It does not set the webhook, the display name, or the Start button. The Start button is Telegram's own control on an empty chat; a tap sends `/start`.

## Cloudflare worker

- Worker name: `t2t-box` (display name T2T-Box)
- Account worker URL: `https://t2t-box.prtndz.workers.dev`
- This one worker also serves `POST /tg2tm` for `@tg2tmbot`
- Do not remove the `/tg2tm` route
- Do not rename the worker
- Do not point `@tg2tmbot` at this worker until a separate cutover

## KV

- Binding: `BOT_KV`
- Namespace id must stay `69c9d9f3572a48469a312e5914e8a233` (the live tg2tm data)
- Letterboxd keys use the `lebxd:` prefix
- Do not switch back to the empty namespace `t2t-box-BOT_KV` (`77ae9d1d59764c3fb82ff615296e0a1e`)

## Worker secrets

On worker `t2t-box`:

- `LEBXDBOT_TOKEN`
- `TG2TM_TOKEN`
- `GHLEBXD_DISPATCH_TOKEN` — LetterboxdStats Actions read/write only
- `GHTG2TM_DISPATCH_TOKEN`
- `WEBHOOK_SECRET` — shared by both webhook paths
- `UPLOADER_SECRET`

Var `LOGIN_CHAT_IDS` = `8502935020,5513343655`.

## GitHub Actions

Repository: `pretendless/LetterboxdStats`.

Secrets:

- `LEBXDBOT_TOKEN`
- `WEBHOOK_SECRET`
- `TMDB_BEARER_TOKEN`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Chart workflow: `letterboxd.yml`. **Deploy worker** publishes `t2t-box`.

## Dispatch tokens

The live tg2tmbot worker must keep `GH_DISPATCH_TOKEN` until its webhook moves. Do not copy that token onto `t2t-box` under the old name.

## Dates

Month before year. `2021-06.2022` means 2021-01-01 through 2022-06-30.

## Copy

Leave the vendored `tg2tm/` wizard as it is until a separate cutover. Do not remove `POST /tg2tm`. Do not put the shared route, `@tg2tmbot`, or Telegram2Telemost into `README.md` or new user-facing chat copy.

## Chart palette

One palette, `palette_color` in `scripts/letterboxd_palette.py`. Do not add turbo, viridis, coolwarm, or a second rating colormap.

Logo anchors are the median sRGB of each circle's non-overlapping interior (12px erosion, then a center disk; both middle samples of each channel matched):

- 0.25 blue `#3FB7EB` = RGB (63, 183, 235)
- 0.50 green `#03E53E` = RGB (3, 229, 62)
- 0.75 orange `#FC7A02` = RGB (252, 122, 2)

`palette_color(t)` is piecewise-linear in OKLab through those anchors. `t = 0` and `t = 1` extend the blue←green and green→orange chords by one anchor step (`2B − G`, `2O − G`) and scale chroma into sRGB (deeper blue-violet, then red). Ratings use the full 0..1 range: `t = (rating − 0.5) / 4.5`.

Discrete ordered series, earliest or lowest first. Raw rank `q = (i+1)/(N+1)`, then `bend_rank`:

- N = 1 → `[0.5]`
- N = 2 → `[0.25, 0.75]`
- N ≥ 3 → piecewise quadratic on `q`, knots fixed:
  - `[0, 0.25]`: `u = q/0.25`, `t = 0.25 u²` (pull toward 0)
  - `[0.25, 0.5]`: `u = (q−0.25)/0.25`, `t = 0.25 + 0.25 (1−(1−u)²)` (pull toward green)
  - `[0.5, 0.75]`: `u = (q−0.5)/0.25`, `t = 0.5 + 0.25 u²` (pull toward green)
  - `[0.75, 1]`: `u = (q−0.75)/0.25`, `t = 1 − 0.25 (1−u)²` (pull toward 1)

N = 3 is blue, green, orange. N = 7 is `[0.0625, 0.25, 0.4375, 0.5, 0.5625, 0.75, 0.9375]` (items 2, 4, 6 are the logo colors).
