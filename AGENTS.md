# Agent notes

This file is for Cursor agents working in this repository. It is not user-facing. User-facing copy and `README.md` stay English and do not mention Telegram2Telemost. This file names the shared route and secrets so an agent does not break them. Names and locations only — never secret values.

## @lebxdbot

- Bot: `@lebxdbot`
- Commands: `/start` and `/stop`
- Webhook: `POST https://t2t-box.prtndz.workers.dev/lebxd`
- Workflow **Set webhook** registers that URL
- Workflow **Setup bot** writes the English description (empty-chat card), short description (profile), and `/start` `/stop` menu. It does not set the webhook, the display name, or the Start button. The Start button is Telegram's own control on an empty chat; a tap sends `/start`.
- Description copy lives in `worker/bot_profile.mjs`. `DESCRIPTION` (≤ 512) is the empty-chat / “What can this bot do?” card and ends with an `Author:` block of full https links (not labeled contact). `ABOUT` (≤ 120) is the short profile / share line: product sentence plus `Contact: @prtdz` only. After merge, the user must run **Setup bot** for Telegram to pick up the text.

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

One palette, `palette_color` in `scripts/letterboxd_palette.py`. It is a smooth piecewise-linear interpolation in OKLab `(L, a, b)` through five knots:

- 0 deep purple `#5922BF` = RGB (89, 34, 191)
- 0.15 blue `#3FB7EB` = RGB (63, 183, 235)
- 0.35 green `#03E53E` = RGB (3, 229, 62)
- 0.8 orange `#FC7A02` = RGB (252, 122, 2)
- 1 deep burgundy `#890E3A` = RGB (137, 14, 58)

The three middle knots are the measured logo circles (median sRGB of each non-overlapping interior: 12px erosion, then a center disk). Their positions are `LOGO_BLUE_T`, `LOGO_GREEN_T`, `LOGO_ORANGE_T`; the uneven spacing is deliberate so the scale is not homogeneous. The ends are `END_PURPLE_RGB` and `END_BURGUNDY_RGB`: darker than the logo colors (OKLab L 0.44 and 0.41) but still at least 2.2:1 on black. A knot returns those bytes exactly. Each segment is the straight OKLab line between its knots, so lightness does not jump.

Never use hue bands, hard cuts, holds, or easing.

A rating maps with `t = 1 − (rating − 0.5) / 4.5` (`RATING_VMIN = 0.5`, `RATING_VMAX = 5.0`), clamped to 0–1. So 5 is deep purple, 0.5 is deep burgundy, 4.325 is logo blue, 3.425 is green, and 1.4 is logo orange. This reversal is only the rating map. Discrete series below still start at the purple side.

Discrete ordered series (watch years, ranked genres), earliest or lowest first, use `categorical_positions`. This is the permanent rule:

- N = 1 → `[0.35]`, exact logo green
- N = 2 → `[0.15, 0.8]`, exact logo blue and orange
- N = 3 → `[0.15, 0.35, 0.8]`, the three logo colors
- N ≥ 4 → even bin midpoints `t_i = (i + 0.5) / N` for `i = 0 .. N−1`

Four or more values sample the full 0–1 palette. There is no quadratic bend and no snap onto the logo knots. N = 4 is `[0.125, 0.375, 0.625, 0.875]`. N = 7 is `[0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5] / 7`.

Genre-name colors (decade×genre / genre×year stacks and any other chart that colors by genre label): one run-wide map from `genre_spectrum_color_map` over the stable union of filtered genre names (`stable_genre_names`, casefold). Assign reversed `categorical_colors` so the spectrum reads burgundy/red → purple/violet. Same genre name → same hex everywhere in the run; a chart’s top-N subset keeps those global colors (unused slots omit). Stack bottom→top and legend rows follow `genres_in_spectrum_order` among genres present. Do not rebuild the map from each chart’s top-N alone. Horizontal **watches by genre** bars stay watch-year colored (`watch_year_palette`), not genre-name colored.

In-plot inset panels (**Most reviewed years**, genre swatch legends): top-left, panel bottom at the tallest-bar shelf, raise only to clear bars/tips (slight ylim / figure pad only as needed). Keep 5 rows per column with last-two rebalance (`inset_panel_column_sizes`). Multi-column mark lines size columns from measured text width, reserving at least 5 count digits so large ≡ / ♥ totals do not overlap the next column.

Watch-year stacks: dated years alone feed `categorical_positions` via `watch_year_palette`. `UNDATED_WATCH_YEAR` / **No date** is the logo-background charcoal gradient (`UNDATED_LOGO_TOP_HEX` `#2C3440` → `UNDATED_LOGO_BOTTOM_HEX` `#14181C`) — not a colormap slot and not solid white. Fill orientation follows the bar: **vertical** columns keep the logo axis (top→bottom); **horizontal** bars rotate 90° (left→right). Legend swatches always use the logo-native **vertical** gradient with `UNDATED_LEGEND_EDGE` on black.

## Rewatch averages toggle

Wizard / Actions / `ChartOptions.include_rewatch_in_averages` (env `LETTERBOXD_INCLUDE_REWATCH_IN_AVERAGES`). Default **false**: `merged_film_ratings` (one Name+Year). **true**: each rated diary row contributes via `ratings_for_averages` / `diary_rated_views_plus_gaps`. Threshold gates and `(n)` unique-film counts stay on unique rated films. Most often in the diary and search-keyword lists ignore this flag. Do not edit the vendored `tg2tm/` wizard for this.

## Likes / reviews display toggles

Wizard / Actions / `ChartOptions.show_likes` / `show_reviews` (env `LETTERBOXD_SHOW_LIKES` / `LETTERBOXD_SHOW_REVIEWS`). Both default **true**. When false, that mark is omitted everywhere (tips, titles, Most liked / Most reviewed, search lines, inside-bar labels) by clearing liked / reviewed keys before chart and search builders. Reviews off also skips the Top review wizard step and forces `show_top_review=false`. Settings summary: `Likes: yes/no.`; when Top review is off, `Reviews: yes/no.` (no Top review line). Paste accepts them (missing → yes).

## Top review panel

Wizard / Actions / `ChartOptions.show_top_review` (env `LETTERBOXD_SHOW_TOP_REVIEW`). Default **true**. Only offered when Reviews is on. Customize can turn it off. When true, listed ranking charts get an in-plot panel: film title (year), optional ♥ when that film is in likes/films.csv, optional pick-rating stars (`★` × floor + `½` when fractional; omit when unrated), review text truncated to `TOP_REVIEW_MAX_CHARS` (280) with ellipsis, and review Date. Corner: **bottom-right** on watches/count / Most often / higher-rating; **top-right** on lower-rating (raise on bar/tip overlap like other top insets). Walk drawn ranks (1, 2, …) to the first row with a qualifying review; omit only if none in the top have one. Among that row’s reviews: watches/count / Most often and higher-rating charts → highest `reviews.csv` Rating (else merged film rating); lower-rating → lowest. When every candidate is unrated, prefer liked films (`likes/films.csv`). After rating (or the all-unrated liked boost), ties → latest review Date, then Name/Year. Exclude hiding the true count-top suppresses the panel. Also forces lower-rating charts to emit (lifts full-slate gate). Settings summary: Top review on → only `Top review: yes.` (implies reviews); off → only `Reviews: yes/no.`; never both. Paste: `Top review: yes` ⇒ both on; `Reviews: no` ⇒ both off; legacy dual lines still parse.

## Non-date quantitative count charts

Unit for bar lengths when the category is release metadata or person/genre/studio/language/country (not watch time): **catalog hits** = every diary row + one row per watched-only film already in the period-scoped catalog (`include_undated` still gates whether watched-only enter that catalog). Dated rows stack by watch year; undated rows use the `No date` segment (`UNDATED_WATCH_YEAR` in `letterboxd_palette.py`), painted with the logo charcoal gradient along the bar axis (not on the year colormap). Same unit as `genre_summary` count lists. The extra-stats **Rating distribution** bottom panel also stacks undated rated catalog entries (ratings.csv / watched-only rated) under **No date**; tip `%` / count / ♥ include them. Do **not** invent watch years for watched-only on watch-year / weekday / month / pace / most-often-in-diary charts (those stay diary-dated only).

## Rating-bar labels

In `chart_rating_hbar` (`scripts/letterboxd_top_charts.py`), `SHORT_BAR_NAME_CHARS` is 15.

- A bar that holds at least 15 name characters keeps the name inside. The name is ellipsized only when the full name does not fit.
- A shorter bar shows the first 15 characters and an ellipsis, and that label runs past the bar tip.
- The bold rating sits 0.14 data units past a normal bar tip (`mean_after_bar`).
- After an overflowing label, the rating keeps at least that same gap past the label: the pixel width of the 0.14 offset, and never under 12 px, plus half the name stroke so the halo is not part of the gap.
