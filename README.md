# LetterboxdStats

[@lebxdbot](https://t.me/lebxdbot) строит графики по ZIP-экспорту Letterboxd. Это отдельный бот и отдельный Cloudflare Worker. Воркер стикеров `tg2tmbot` (@tg2tmbot) здесь не деплоится и не переименовывается. Его webhook не меняется.

Worker script name: `t2t-box`. Display name: T2T-Box. Адрес: `https://t2t-box.prtndz.workers.dev`. Webhook: `POST https://t2t-box.prtndz.workers.dev/telegram`.

## Команды

Только две:

| Команда | Что делает |
| --- | --- |
| `/start` | Тот же мастер, что `/letterboxd` у @tg2tmbot: просит ZIP, затем «по умолчанию» или «настроить» (топ 1–100, минимум оценённых фильмов, USA, английский, период, фильмы без даты). `2021-06.2022` — это 2021-01-01 … 2022-06-30. |
| `/start letterboxd` | То же самое. Так открывается `https://t.me/lebxdbot?start=letterboxd`. |
| `/stop` | Сбрасывает мастер. Если графики уже ушли в GitHub Actions, останавливает этот запуск. |

Других команд @tg2tmbot здесь нет.

Кнопки мастера — `callback_query`. Workflow **Set webhook** передаёт `allowed_updates`: `message` и `callback_query`.

## Из чего состоит

- `worker/` — webhook, мастер, `workflow_dispatch` на `letterboxd.yml`.
- `vm/letterboxd_genres.js` — шаги мастера и разбор дат.
- `scripts/` — те же календарные и TMDB-графики, что у @tg2tmbot. Job шлёт PNG в чат токеном @lebxdbot.

Проверка без Cloudflare и без токенов, Node 22:

```bash
cd worker
npm ci
npm test
```

## Выкладка

Три ручных workflow, черновик до слития в `main`:

1. **Deploy worker** — `npx wrangler deploy` в `worker/`. Нужны секреты репозитория `CLOUDFLARE_API_TOKEN` и `CLOUDFLARE_ACCOUNT_ID`.
2. **Set webhook** — `setWebhook` на `https://t2t-box.prtndz.workers.dev/telegram` и меню `/start`, `/stop`.
3. **Letterboxd** — графики. Его вызывает воркер, не человек.

KV уже отдельный: namespace с названием `t2t-box-BOT_KV`, binding `BOT_KV`. Это не namespace воркера `tg2tmbot`. Id записан в `worker/wrangler.toml`.

Секреты воркера (значения в git не класть):

```bash
npx wrangler secret put LEBXDBOT_TOKEN
npx wrangler secret put WEBHOOK_SECRET
npx wrangler secret put GH_DISPATCH_TOKEN
npx wrangler deploy
```

Команды выполняются для worker `t2t-box` (`name` в `wrangler.toml`). Не запускать их в каталоге воркера `tg2tmbot`.

## Секреты

Значения не придумывать и не копировать токен @tg2tmbot в этот бот.

| Имя | Куда | Что это |
| --- | --- | --- |
| `LEBXDBOT_TOKEN` | GitHub → pretendless/LetterboxdStats → Settings → Secrets and variables → Actions | Токен BotFather для @lebxdbot. Не `TG2TMBOT_TOKEN`. |
| `LEBXDBOT_TOKEN` | Cloudflare worker `t2t-box`: `npx wrangler secret put LEBXDBOT_TOKEN` | То же значение. Им воркер отвечает в Telegram, им job скачивает ZIP. |
| `WEBHOOK_SECRET` | Тот же GitHub Actions secret и `npx wrangler secret put WEBHOOK_SECRET` на `t2t-box` | Новый секрет только для @lebxdbot. Одинаковое значение в обоих местах. Не секрет webhook `tg2tmbot`. |
| `TMDB_BEARER_TOKEN` | GitHub Actions secret на pretendless/LetterboxdStats | Read Access Token TMDB для job графиков. Скопировать существующее значение из репозитория @tg2tmbot самостоятельно. На воркер не класть. |
| `CLOUDFLARE_API_TOKEN` | GitHub Actions secret на pretendless/LetterboxdStats | Тот же аккаунт Cloudflare. Право Workers Scripts Edit и Workers KV Storage Edit. |
| `CLOUDFLARE_ACCOUNT_ID` | GitHub Actions secret на pretendless/LetterboxdStats | Id того же аккаунта. |
| `GH_DISPATCH_TOKEN` | Уже есть: секрет Cloudflare на воркере `tg2tmbot` | Fine-grained PAT только на репозиторий Telegram2Telemost (`pretendless/tg2tm`), Actions: Read and write. Его не переносить: он не имеет права на LetterboxdStats. |
| `GH_DISPATCH_TOKEN` | Новый: `npx wrangler secret put GH_DISPATCH_TOKEN` на воркере `t2t-box` | Новый fine-grained PAT только на `pretendless/LetterboxdStats`, Actions: Read and write. Им воркер вызывает и отменяет `letterboxd.yml`. В GitHub Actions secrets репозитория этот PAT не класть. |

`TG2TMBOT_TOKEN` этот репозиторий не использует.

## Cutover

В этом PR @tg2tmbot не меняется: `/letterboxd` там по-прежнему строит отчёт.

Когда @lebxdbot выложен и проверен, отдельный PR в Telegram2Telemost заменит `/letterboxd` короткой карточкой со ссылкой `https://t.me/lebxdbot?start=letterboxd`. Текст карточки ещё не выбран.
