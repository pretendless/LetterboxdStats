# LetterboxdStats

[@lebxdbot](https://t.me/lebxdbot) строит графики по ZIP-экспорту Letterboxd. Код живёт здесь. Исполняет его один Cloudflare Worker `t2t-box` (display name T2T-Box), общий для @tg2tmbot, @lebxdbot и следующих ботов.

`tg2tmbot` пока живой и отдельно. Этот репозиторий его не переименовывает и не деплоит. Webhook @tg2tmbot остаётся `https://tg2tmbot.prtndz.workers.dev/telegram`, пока общий воркер не обслуживает оба бота.

Адрес `t2t-box`: `https://t2t-box.prtndz.workers.dev`.

| Путь | Бот | Секреты |
| --- | --- | --- |
| `POST /tg2tm` | текущее поведение @tg2tmbot, включая `/letterboxd` | `TG2TM_TOKEN`, `GHTG2TM_DISPATCH_TOKEN` |
| `POST /lebxd` | только `/start` и `/stop` (@lebxdbot) | `LEBXDBOT_TOKEN`, `GHLEBXD_DISPATCH_TOKEN` |

Оба пути проверяют один `WEBHOOK_SECRET`. Кнопки: `allowed_updates` включает `message` и `callback_query`.

Загрузчик Телемоста по-прежнему ходит в `/progress`, `/queue/claim` и соседние пути с `UPLOADER_SECRET`. Чаты администратора — переменная `LOGIN_CHAT_IDS`.

KV binding `BOT_KV` — существующий namespace `tg2tmbot`, id `69c9d9f3572a48469a312e5914e8a233`. Ключи @lebxdbot начинаются с `lebxd:`, чтобы делить этот namespace и не попасть в пустой `t2t-box-BOT_KV`. Пустой namespace не используется.

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
2. **Set webhook** — только @lebxdbot, `setWebhook` на `https://t2t-box.prtndz.workers.dev/lebxd` и меню `/start`, `/stop`. Webhook @tg2tmbot этим workflow не меняется.
3. **Letterboxd** — графики. Его вызывает воркер, не человек.

`worker/wrangler.toml` уже указывает `BOT_KV` на namespace `69c9d9f3572a48469a312e5914e8a233`. На живом `t2t-box` binding пока ещё пустой namespace `t2t-box-BOT_KV`. Этот toml на воркер не выкладывался: деплой `t2t-box` с этим файлом переключит KV, но не трогает скрипт `tg2tmbot`.

Секреты воркера (значения в git не класть):

Секреты воркера `t2t-box` (не каталог `tg2tmbot`):

```bash
npx wrangler secret put LEBXDBOT_TOKEN
npx wrangler secret put TG2TM_TOKEN
npx wrangler secret put GHLEBXD_DISPATCH_TOKEN
npx wrangler secret put GHTG2TM_DISPATCH_TOKEN
npx wrangler secret put WEBHOOK_SECRET
npx wrangler secret put UPLOADER_SECRET
```

`npx wrangler deploy` выкладывает только скрипт `t2t-box`. Не запускать wrangler в каталоге живого `tg2tmbot`.

## Секреты

| Имя | Куда | Что это |
| --- | --- | --- |
| `LEBXDBOT_TOKEN` | Уже секрет Production на worker `t2t-box`. Тот же токен — GitHub Actions secret на pretendless/LetterboxdStats | BotFather для @lebxdbot. Не `TG2TMBOT_TOKEN`. Job графиков скачивает ZIP им. |
| `TG2TM_TOKEN` | Уже секрет Production на worker `t2t-box` | Токен @tg2tmbot для пути `/tg2tm`. На живом `tg2tmbot` секрет до сих пор называется `TG2TMBOT_TOKEN`. |
| `GHLEBXD_DISPATCH_TOKEN` | Уже секрет Production на worker `t2t-box` | PAT, которым `/lebxd` запускает и отменяет `letterboxd.yml` в LetterboxdStats. |
| `GHTG2TM_DISPATCH_TOKEN` | Уже секрет Production на worker `t2t-box`. На `tg2tmbot` секрет с тем же именем тоже есть | PAT для workflow @tg2tmbot. |
| `WEBHOOK_SECRET` | Уже секрет Production на worker `t2t-box`. Для workflow Set webhook — GitHub Actions secret с тем же значением | Один секрет на оба пути `/tg2tm` и `/lebxd`. |
| `UPLOADER_SECRET` | Ещё нет на `t2t-box`. Есть на `tg2tmbot`. `npx wrangler secret put UPLOADER_SECRET` на `t2t-box` | Bearer для `/progress` и очереди. Скопировать существующее значение самостоятельно. |
| `LOGIN_CHAT_IDS` | Уже plain-text var на `t2t-box`: `8502935020,5513343655`. То же в `wrangler.toml` | Не секрет. |
| `TMDB_BEARER_TOKEN` | GitHub Actions secret на pretendless/LetterboxdStats, не на воркере | Read Access Token для job графиков. Скопировать существующее значение самостоятельно. |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | GitHub Actions secrets на pretendless/LetterboxdStats | Деплой `t2t-box`. |

Код читает эти имена как есть: `LEBXDBOT_TOKEN`, `TG2TM_TOKEN`, `GHLEBXD_DISPATCH_TOKEN`, `GHTG2TM_DISPATCH_TOKEN`, `WEBHOOK_SECRET`, `UPLOADER_SECRET`, `LOGIN_CHAT_IDS`. Имена `TG2TMBOT_TOKEN` и `GH_DISPATCH_TOKEN` с окружения воркера не читаются.

## Cutover

В этом PR @tg2tmbot не меняется: `/letterboxd` там по-прежнему строит отчёт.

Когда @lebxdbot выложен и проверен, отдельный PR в Telegram2Telemost заменит `/letterboxd` короткой карточкой со ссылкой `https://t.me/lebxdbot?start=letterboxd`. Текст карточки ещё не выбран.
