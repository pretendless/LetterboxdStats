# Agent notes

This file is for Cursor agents working in this repository. It is not user-facing. User-facing copy and `README.md` stay English and do not mention Telegram2Telemost. This file names the shared route and secrets so an agent does not break them. Names and locations only — never secret values.

## @lebxdbot

- Bot: `@lebxdbot`
- Commands: `/start` and `/stop`
- Webhook: `POST https://t2t-box.prtndz.workers.dev/lebxd`
- Workflow **Set webhook** registers that URL
- Workflow **Setup bot** fills the English BotFather profile (short description, description, and the command menu). It does not set the webhook.

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
