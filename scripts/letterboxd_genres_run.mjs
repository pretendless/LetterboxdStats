// GitHub Actions: download Letterboxd ZIP, rich HTML report + photos, then TMDB genres.
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";

// Genre PNGs: watches → higher rating → (lower rating) → release decade → watch year.
export const GENRE_PNGS = [
  "watches_by_genre.png",
  "average_rating_by_genre.png",
  "worst_average_rating_by_genre.png",
  "genre_by_release_decade.png",
  "genre_counts_by_viewing_year.png",
  "watches_by_country.png",
  "average_rating_by_country.png",
  "worst_average_rating_by_country.png",
  "watches_by_director.png",
  "average_rating_by_director.png",
  "worst_average_rating_by_director.png",
  "watches_by_actor.png",
  "average_rating_by_actor.png",
  "worst_average_rating_by_actor.png",
  "watches_by_language.png",
  "average_rating_by_language.png",
  "worst_average_rating_by_language.png",
  "watches_by_studio.png",
  "average_rating_by_studio.png",
  "worst_average_rating_by_studio.png",
];

const CALENDAR_PNGS = [
  "views_by_weekday_month.png",
  "views_by_year.png",
  "extra_stats_decade_rating.png",
  "average_rating_by_year.png",
  "average_rating_by_release_decade.png",
  "viewing_pace.png",
  "top_rewatches.png",
  "watches_by_release_year.png",
  "average_rating_by_release_year.png",
  "worst_average_rating_by_release_year.png",
];

export function calendarCaptions(summary) {
  const grain = summary && summary.watch_time_grain;
  const phrase = grain === "day" ? "by day" : grain === "month" ? "by month" : "by year";
  return {
    ...CALENDAR_CAPTIONS,
    "views_by_year.png": `Film watches ${phrase}`,
    "average_rating_by_year.png": `Average rating ${phrase}`,
    "viewing_pace.png": grain === "day" ? "Viewing pace by day" : "Viewing pace by month",
  };
}

const CALENDAR_CAPTIONS = {
  "views_by_weekday_month.png": "Watches by weekday — stacked by year",
  "views_by_year.png": "Film watches by year",
  "extra_stats_decade_rating.png": "Letterboxd extra stats",
  "average_rating_by_year.png": "Average rating by year",
  "average_rating_by_release_decade.png": "Average rating by release decade",
  "viewing_pace.png": "Viewing pace by month",
  "top_rewatches.png": "Most often in the diary",
  "watches_by_release_year.png": "Release years — more watches",
  "average_rating_by_release_year.png": "Release years — higher rating",
  "worst_average_rating_by_release_year.png": "Release years — lower rating",
};

const GENRE_CAPTIONS = {
  "genre_counts_by_viewing_year.png": "Genres by watch year",
  "watches_by_genre.png": "Genres — watches",
  "average_rating_by_genre.png": "Genres — higher rating",
  "worst_average_rating_by_genre.png": "Genres — lower rating",
  "genre_by_release_decade.png": "Genres by release decade",
  "watches_by_country.png": "Countries of origin (TMDB)",
  "average_rating_by_country.png": "Countries — higher rating",
  "worst_average_rating_by_country.png": "Countries — lower rating",
  "watches_by_director.png": "Directors — watches",
  "average_rating_by_director.png": "Directors — higher rating",
  "worst_average_rating_by_director.png": "Directors — lower rating",
  "watches_by_actor.png": "Actors — watches",
  "average_rating_by_actor.png": "Actors — higher rating",
  "worst_average_rating_by_actor.png": "Actors — lower rating",
  "watches_by_language.png": "Original language — watches",
  "average_rating_by_language.png": "Original language — higher rating",
  "worst_average_rating_by_language.png": "Original language — lower rating",
  "watches_by_studio.png": "Studios — watches",
  "average_rating_by_studio.png": "Studios — higher rating",
  "worst_average_rating_by_studio.png": "Studios — lower rating",
};

const __dirname = dirname(fileURLToPath(import.meta.url));
const GENRE_SCRIPT = join(__dirname, "letterboxd_genre_charts.py");
const CALENDAR_SCRIPT = join(__dirname, "letterboxd_calendar_charts.py");

function env(name) {
  return String(process.env[name] || "").trim();
}

function telegramApi(token, method) {
  return `https://api.telegram.org/bot${token}/${method}`;
}

/**
 * Expand bare "fetch failed" / undici errors into a readable string for Actions logs.
 * Includes cause chain (code, errno, syscall, address) when present.
 */
export function formatTelegramError(err) {
  if (err == null) return "unknown error";
  const parts = [];
  let cur = err;
  let depth = 0;
  while (cur && depth < 4) {
    if (typeof cur === "string") {
      parts.push(cur);
      break;
    }
    const msg = cur.message || String(cur);
    const bits = [msg];
    if (cur.name && cur.name !== "Error") bits.push(`name=${cur.name}`);
    if (cur.code) bits.push(`code=${cur.code}`);
    if (cur.errno != null) bits.push(`errno=${cur.errno}`);
    if (cur.syscall) bits.push(`syscall=${cur.syscall}`);
    if (cur.address) bits.push(`address=${cur.address}`);
    if (cur.port != null) bits.push(`port=${cur.port}`);
    parts.push(bits.join(" "));
    cur = cur.cause;
    depth += 1;
  }
  return parts.join(" | cause: ");
}

/** One-shot Bot API fetch; wraps failures with step label (no retries). */
export async function telegramFetch(url, options, meta = {}) {
  const label = meta.label || "telegram";
  try {
    return await fetch(url, options);
  } catch (err) {
    const detail = formatTelegramError(err);
    console.error(`[letterboxd] ${label} FAILED: ${detail}`);
    const wrapped = new Error(`${label}: ${detail}`);
    wrapped.cause = err;
    throw wrapped;
  }
}

/** Escape user/diary strings for Telegram HTML parse_mode. */
export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function readJsonFile(path) {
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

function fmtPct(share) {
  const n = Number(share);
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n * 100)}%`;
}

function fmtNum(n) {
  if (n == null || !Number.isFinite(Number(n))) return "—";
  return String(Number(n));
}

function fmtRating(n) {
  if (n == null || !Number.isFinite(Number(n))) return "—";
  const v = Number(n);
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "") || String(v);
}

/**
 * Calendar-section HTML report (parse_mode=HTML). Prefer HTML over MarkdownV2:
 * film titles only need &lt; &gt; &amp; escapes.
 */
export function buildCalendarReportHtml(summary) {
  const s = summary && typeof summary === "object" ? summary : {};
  const entries = fmtNum(s.entries);
  const films = fmtNum(s.unique_films);
  let years = "—";
  if (s.year_min != null && s.year_max != null) {
    years = s.year_min === s.year_max ? String(s.year_min) : `${s.year_min}–${s.year_max}`;
  }
  const lines = [
    "<b>Letterboxd</b>",
    `Diary: <b>${escapeHtml(entries)}</b> entries · <b>${escapeHtml(films)}</b> films · ${escapeHtml(years)}`,
  ];
  if (s.date_from && s.date_to) {
    lines.push(
      `Period: <b>${escapeHtml(String(s.date_from))}</b> — <b>${escapeHtml(String(s.date_to))}</b>`,
    );
    lines.push(
      s.include_undated
        ? "No diary date: in the catalog, not in the calendar."
        : "Diary dates inside the period only.",
    );
  }

  // Peak calendar day first (diary Watched Date row count).
  if (s.peak_day_label && s.peak_day_count != null) {
    lines.push(
      `Most watches in one day: <b>${escapeHtml(s.peak_day_label)}</b> (<b>${escapeHtml(fmtNum(s.peak_day_count))}</b>)`,
    );
  }

  if (s.peak_year != null) {
    lines.push(
      `Peak year: <b>${escapeHtml(s.peak_year)}</b> — <b>${escapeHtml(fmtNum(s.peak_year_count))}</b> watches`,
    );
  }
  if (s.favorite_weekday) {
    lines.push(
      `Day: <b>${escapeHtml(s.favorite_weekday)}</b> (${escapeHtml(fmtNum(s.favorite_weekday_count))})`,
    );
  }
  if (s.favorite_month) {
    lines.push(
      `Month: <b>${escapeHtml(s.favorite_month)}</b> (${escapeHtml(fmtNum(s.favorite_month_count))})`,
    );
  }
  if (s.films_per_month != null && Number.isFinite(Number(s.films_per_month))) {
    lines.push(
      `Pace: <b>${escapeHtml(fmtRating(s.films_per_month))}</b> films per month on average`,
    );
  }

  const ratedShare = fmtPct(s.rated_share);
  if (s.rated_count != null) {
    let ratingLine = `Ratings: <b>${escapeHtml(fmtNum(s.rated_count))}</b> (${escapeHtml(ratedShare)})`;
    if (s.rating_avg != null) {
      ratingLine += ` · average <b>${escapeHtml(fmtRating(s.rating_avg))}</b>`;
    }
    if (s.rating_mode != null) {
      ratingLine += ` · most often <b>${escapeHtml(fmtRating(s.rating_mode))}</b>`;
    }
    lines.push(ratingLine);
  }

  // Count / rating tops (rewatches, release years, …) ship as charts — no HTML lists.
  return lines.join("\n");
}

/**
 * Short TMDB blurb after enrichment — ranked tops are charts, not HTML bullets.
 * Returns one message (array for call-site compatibility).
 */
export function buildGenreReportMessages(summary, unmatchedFallback = 0) {
  const s = summary && typeof summary === "object" ? summary : {};
  const unmatched =
    s.unmatched != null && Number.isFinite(Number(s.unmatched))
      ? Number(s.unmatched)
      : Number(unmatchedFallback) || 0;
  const unique = s.unique_titles != null ? fmtNum(s.unique_titles) : null;
  const resolved = s.resolved != null ? fmtNum(s.resolved) : null;

  const lines = ["<b>Letterboxd · TMDB</b>"];
  if (unique != null && resolved != null) {
    lines.push(
      `Enriched <b>${escapeHtml(resolved)}</b> / <b>${escapeHtml(unique)}</b> films`,
    );
  } else {
    lines.push("TMDB details are ready — charts below.");
  }
  if (unmatched > 0) {
    lines.push(`No TMDB genres: <b>${escapeHtml(String(unmatched))}</b>`);
  }
  lines.push("<i>Tops are on the charts (watches / higher rating).</i>");
  return [lines.join("\n")];
}

/** Genre-section HTML after TMDB enrichment (single string; tests / simple callers). */
export function buildGenreReportHtml(summary, unmatchedFallback = 0) {
  return buildGenreReportMessages(summary, unmatchedFallback).join("\n\n");
}

const TELEGRAM_TEXT_LIMIT = 4096;

/** Fixed match-site section order (same as Python SEARCH_MATCH_FIELDS). */
export const SEARCH_MATCH_FIELDS = [
  "genre",
  "director",
  "actor",
  "studio",
  "country",
  "language",
  "year",
];

// U+2665 only for likes. Review mark: U+275D ❝ (same text dingbat rules as ♥; no VS15).
// Keep in sync with REVIEW_MARK in letterboxd_top_charts.py.
const LIKED_HEART = "\u2665";
const REVIEW_MARK = "\u275D";

/**
 * Format one film row under a match-site section:
 * `1. Name (Year) ♥ ❝: 5, —, 3.5` when liked/reviewed (marks after year).
 * Heart is U+2665 BLACK HEART SUIT only (never U+2764). Review mark is
 * U+275D ❝ (no VS15). Colon separates title from ratings; em dash `—` is only
 * for empty slots. Ratings: one value per watch (diary oldest→newest, or one
 * watched-only slot). Liked = likes/films.csv; reviewed = reviews.csv.
 */
function formatSearchFilmLine(film, index) {
  const name = escapeHtml(film && film.name != null ? film.name : "?");
  const year =
    film && film.year != null && Number.isFinite(Number(film.year))
      ? String(Number(film.year))
      : "?";
  const ratings = Array.isArray(film && film.ratings) ? film.ratings : [];
  const ratingText = ratings.length
    ? ratings.map((slot) => escapeHtml(slot == null || slot === "" ? "—" : slot)).join(", ")
    : "";
  const heart = film && film.liked ? ` ${LIKED_HEART}` : "";
  const review = film && film.reviewed && REVIEW_MARK ? ` ${REVIEW_MARK}` : "";
  const base = `${index}. ${name} (${escapeHtml(year)})${heart}${review}`;
  return ratingText ? `${base}: ${ratingText}` : base;
}

/**
 * Format one search-keyword film list as HTML message chunk(s).
 *
 * Structure: title + unique film count, then a bold section per match site
 * (genre → … → year). Under each header, numbered films that matched that
 * field; a film that hits multiple fields is repeated under each. Empty
 * sections are omitted. Line: `1. Name (Year) ♥: 5, —, 3.5` when liked.
 * Empty list → one short notice.
 */
export function buildSearchKeywordMessages(keyword, films) {
  const word = String(keyword || "").trim();
  if (!word) return [];
  const header = `<b>Search keyword: ${escapeHtml(word)}</b>`;
  const rows = Array.isArray(films) ? films : [];
  if (!rows.length) {
    return [`${header}\n\nNo films matched in this catalog.`];
  }

  const bodyLines = [];
  for (const site of SEARCH_MATCH_FIELDS) {
    const inSection = rows.filter((film) => {
      const matched = Array.isArray(film && film.matched) ? film.matched : [];
      return matched.includes(site);
    });
    if (!inSection.length) continue;
    if (bodyLines.length) bodyLines.push(""); // blank line between sections
    bodyLines.push(`<b>${escapeHtml(site)}</b>`);
    inSection.forEach((film, i) => {
      bodyLines.push(formatSearchFilmLine(film, i + 1));
    });
  }

  const intro = `${header}\n${rows.length} film${rows.length === 1 ? "" : "s"}\n\n`;
  // No match-site labels on any film → still show title + count (no sections).
  if (!bodyLines.length) {
    return [intro.trimEnd()];
  }

  const chunks = [];
  let current = intro;
  for (const line of bodyLines) {
    const candidate = current === intro ? current + line : `${current}\n${line}`;
    if (candidate.length <= TELEGRAM_TEXT_LIMIT) {
      current = candidate;
      continue;
    }
    if (current && current !== intro) chunks.push(current);
    const continued = `${header} <i>(continued)</i>\n\n${line}`;
    if (continued.length <= TELEGRAM_TEXT_LIMIT) {
      current = continued;
    } else {
      // Extremely long single line — hard-split.
      chunks.push(continued.slice(0, TELEGRAM_TEXT_LIMIT));
      current = `${header} <i>(continued)</i>\n\n${continued.slice(TELEGRAM_TEXT_LIMIT)}`;
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

/** Read search_keyword_lists.json → flat list of HTML messages (one keyword after another). */
export function buildAllSearchKeywordMessages(payload) {
  const lists =
    payload && Array.isArray(payload.search_keywords) ? payload.search_keywords : [];
  const messages = [];
  for (const item of lists) {
    if (!item || !item.keyword) continue;
    messages.push(...buildSearchKeywordMessages(item.keyword, item.films));
  }
  return messages;
}

export function mapScriptError(stderr, stdout, status) {
  const text = `${stderr || ""}\n${stdout || ""}`;
  if (/TMDB_BEARER_TOKEN/i.test(text)) {
    return "TMDB_BEARER_TOKEN is not set (Read Access Token). Add the GitHub Actions secret TMDB_BEARER_TOKEN.";
  }
  if (/Watched Date/i.test(text)) {
    return "diary.csv has no Watched Date column. Send a full Letterboxd export.";
  }
  if (/missing columns|не хватает колонок/i.test(text)) {
    return "diary.csv is missing columns (Name, Year, Watched Date). Send a full Letterboxd export.";
  }
  if (/no watch dates|No diary entries|выбранном диапазоне нет записей/i.test(text)) {
    return "No diary entries with a watch date in the selected range.";
  }
  if (/BadZipFile|not a Letterboxd ZIP|не похож на ZIP/i.test(text)) {
    return "This file is not a Letterboxd ZIP.";
  }
  if (/diary\.csv/i.test(text)) {
    return "The ZIP has no diary.csv. Export: Letterboxd → Settings → Import & Export → Export Your Data.";
  }
  if (/401|unauthorized|invalid api/i.test(text)) {
    return "TMDB rejected the token. Check TMDB_BEARER_TOKEN (do not paste it in chat).";
  }
  if (status !== 0) {
    const line = text
      .split(/\r?\n/)
      .map((row) => row.trim())
      .filter(Boolean)
      .slice(-3)
      .join(" ");
    return line
      ? `Could not build the charts: ${line.slice(0, 350)}`
      : "Could not build the Letterboxd charts.";
  }
  return "";
}

export function unmatchedFromWorkdir(workdir, stdout = "") {
  const csvPath = join(workdir, "tmdb_unmatched.csv");
  if (existsSync(csvPath)) {
    const lines = readFileSync(csvPath, "utf8")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (lines.length > 1) return lines.length - 1;
  }
  const match = String(stdout || "").match(/(?:без найденных жанров|Films without TMDB genres):\s*(\d+)/i);
  if (match) return Number(match[1]);
  return 0;
}

export function existingPngs(workdir, names) {
  return names.filter((name) => {
    const path = join(workdir, name);
    return existsSync(path) && readFileSync(path).byteLength > 32;
  });
}

export function calendarReadyText() {
  return "Calendar charts are ready. Loading TMDB details next (genres, countries, directors, actors)…";
}

async function sendTelegramText(token, chatId, text, parseMode = "", label = "sendMessage") {
  const payload = {
    chat_id: chatId,
    text,
    link_preview_options: { is_disabled: true },
  };
  if (parseMode) payload.parse_mode = parseMode;
  const res = await telegramFetch(
    telegramApi(token, "sendMessage"),
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
    { label: `${label}${parseMode ? `/${parseMode}` : ""}` },
  );
  if (!res.ok) {
    console.error(`[letterboxd] ${label} HTTP ${res.status}${parseMode ? ` (${parseMode})` : ""}`);
  }
  return res.ok;
}

async function sendTelegramHtml(token, chatId, html, label = "sendMessage HTML") {
  return sendTelegramText(token, chatId, html, "HTML", label);
}

async function sendTelegramPhoto(token, chatId, filePath, filename, caption = "") {
  const bytes = readFileSync(filePath);
  const form = new FormData();
  form.set("chat_id", String(chatId));
  if (caption) {
    form.set("caption", caption);
    form.set("parse_mode", "HTML");
  }
  form.set("photo", new Blob([bytes], { type: "image/png" }), filename);
  const res = await telegramFetch(
    telegramApi(token, "sendPhoto"),
    { method: "POST", body: form },
    { label: `sendPhoto ${filename}` },
  );
  if (!res.ok) {
    console.error(`[letterboxd] sendPhoto ${filename} HTTP ${res.status}`);
    // Fallback: document keeps full resolution if photo reject (size/dimensions).
    return sendTelegramDocument(token, chatId, filePath, filename, caption);
  }
  return true;
}

async function sendTelegramDocument(token, chatId, filePath, filename, caption = "") {
  const bytes = readFileSync(filePath);
  const form = new FormData();
  form.set("chat_id", String(chatId));
  if (caption) {
    form.set("caption", caption);
    form.set("parse_mode", "HTML");
  }
  form.set("document", new Blob([bytes], { type: "image/png" }), filename);
  const res = await telegramFetch(
    telegramApi(token, "sendDocument"),
    { method: "POST", body: form },
    { label: `sendDocument ${filename}` },
  );
  if (!res.ok) console.error(`[letterboxd] sendDocument ${filename} HTTP ${res.status}`);
  return res.ok;
}

/**
 * Send charts one-by-one. On failure: log + notify that file, then continue
 * the rest of the batch (no retries — one ECONNRESET must not drop everything after).
 */
async function sendCaptionedPhotos(token, chatId, workdir, names, captions) {
  let sent = 0;
  const failed = [];
  for (const name of names) {
    const caption = captions[name] ? `<i>${escapeHtml(captions[name])}</i>` : "";
    try {
      const ok = await sendTelegramPhoto(token, chatId, join(workdir, name), name, caption);
      if (!ok) {
        failed.push(`${name} (HTTP reject)`);
        console.error(`[letterboxd] sendCaptionedPhotos CONTINUE after fail: ${name} HTTP reject`);
        try {
          await sendTelegramText(
            token,
            chatId,
            `Could not send ${name}.`,
            "",
            `notify fail ${name}`,
          );
        } catch (_) {
          /* ignore secondary notify failure */
        }
      } else {
        sent += 1;
      }
    } catch (err) {
      const detail = err && err.message ? err.message : String(err);
      failed.push(`${name}: ${detail}`);
      console.error(`[letterboxd] sendCaptionedPhotos CONTINUE after fail: ${name}: ${detail}`);
      try {
        await sendTelegramText(
          token,
          chatId,
          `Could not send ${name}: ${detail}`,
          "",
          `notify fail ${name}`,
        );
      } catch (_) {
        /* ignore secondary notify failure */
      }
    }
  }
  return { sent, failed, total: names.length };
}

async function downloadTelegramFile(token, fileId, destPath) {
  const metaRes = await telegramFetch(
    telegramApi(token, "getFile"),
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ file_id: fileId }),
    },
    { label: "getFile" },
  );
  if (!metaRes.ok) throw new Error(`getFile http ${metaRes.status}`);
  const meta = await metaRes.json();
  if (!meta.ok || !meta.result || !meta.result.file_path) {
    throw new Error("getFile missing path");
  }
  const filePath = String(meta.result.file_path);
  const fileRes = await telegramFetch(
    `https://api.telegram.org/file/bot${token}/${filePath}`,
    {},
    { label: "download ZIP" },
  );
  if (!fileRes.ok) throw new Error(`file download http ${fileRes.status}`);
  const buf = Buffer.from(await fileRes.arrayBuffer());
  writeFileSync(destPath, buf);
  return destPath;
}

/** Best-effort chat notice after a late failure (e.g. post-TMDB send). */
async function notifySendFailure(token, chatId, phase, err) {
  const detail = err && err.message ? err.message : String(err);
  console.error(`notifySendFailure [${phase}]:`, detail);
  try {
    await sendTelegramText(
      token,
      chatId,
      `Letterboxd: send failed after ${phase}: ${detail}`,
      "",
      `notify ${phase}`,
    );
  } catch (notifyErr) {
    console.error(
      "could not notify chat about send failure:",
      notifyErr && notifyErr.message ? notifyErr.message : notifyErr,
    );
  }
}

function runPython(script, zipPath, workdir) {
  const result = spawnSync("python3", [script, zipPath], {
    cwd: workdir,
    encoding: "utf8",
    env: {
      ...process.env,
      MPLBACKEND: "Agg",
    },
    timeout: 1000 * 60 * 45,
    maxBuffer: 8 * 1024 * 1024,
  });
  return {
    status: result.status ?? 1,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
    error: result.error,
  };
}

export async function main() {
  const token = env("LEBXDBOT_TOKEN");
  const chatId = env("CHAT_ID") || env("INPUT_CHAT_ID");
  const fileId = env("FILE_ID") || env("INPUT_FILE_ID");
  const jobId = env("JOB_ID") || env("INPUT_JOB_ID") || "lb";
  const bearer = env("TMDB_BEARER_TOKEN");

  if (!token) throw new Error("LEBXDBOT_TOKEN missing");
  if (!chatId) throw new Error("CHAT_ID missing");
  if (!fileId) throw new Error("FILE_ID missing");
  if (!bearer) {
    await sendTelegramText(
      token,
      chatId,
      "TMDB_BEARER_TOKEN is not set. Add a Read Access Token as a GitHub Actions secret (not an API Key).",
    );
    throw new Error("TMDB_BEARER_TOKEN missing");
  }

  const workdir = join(tmpdir(), `letterboxd-${jobId}`);
  mkdirSync(workdir, { recursive: true });
  const zipPath = join(workdir, "export.zip");

  try {
    await downloadTelegramFile(token, fileId, zipPath);
  } catch (err) {
    const msg = `Could not download the ZIP from Telegram: ${err && err.message ? err.message : err}`;
    await sendTelegramText(token, chatId, msg);
    throw err;
  }

  // 1) Light charts first (no TMDB) — summary + photos.
  const calendar = runPython(CALENDAR_SCRIPT, zipPath, workdir);
  if (calendar.stdout) process.stdout.write(calendar.stdout);
  if (calendar.stderr) process.stderr.write(calendar.stderr);

  const calendarPngs = existingPngs(workdir, CALENDAR_PNGS);
  if (!calendarPngs.length) {
    const mapped =
      mapScriptError(calendar.stderr, calendar.stdout, calendar.status) ||
      "Calendar charts were not created. Check diary.csv.";
    await sendTelegramText(token, chatId, mapped);
    throw new Error(mapped);
  }

  const diarySummary = readJsonFile(join(workdir, "diary_summary.json"));
  await sendTelegramHtml(token, chatId, buildCalendarReportHtml(diarySummary || {}));
  await sendCaptionedPhotos(token, chatId, workdir, calendarPngs, calendarCaptions(diarySummary || {}));
  await sendTelegramText(token, chatId, calendarReadyText());

  // 2) Slow TMDB genre enrichment — script edits one progress message, then genre report + PNGs.
  const genres = runPython(GENRE_SCRIPT, zipPath, workdir);
  if (genres.stdout) process.stdout.write(genres.stdout);
  if (genres.stderr) process.stderr.write(genres.stderr);

  const genrePngs = existingPngs(workdir, GENRE_PNGS);
  if (!genrePngs.length) {
    const mapped =
      mapScriptError(genres.stderr, genres.stdout, genres.status) ||
      "Genre charts were not created. Check TMDB_BEARER_TOKEN and diary.csv.";
    await sendTelegramText(token, chatId, mapped);
    throw new Error(mapped);
  }

  const unmatched = unmatchedFromWorkdir(workdir, genres.stdout);
  const genreSummary = readJsonFile(join(workdir, "genre_summary.json"));
  const tmdbMessages = buildGenreReportMessages(genreSummary || {}, unmatched);

  // TMDB work is done — send once each; mid-batch failures continue (no retries).
  const batchFailures = [];
  for (let i = 0; i < tmdbMessages.length; i++) {
    const label = `genre HTML part ${i + 1}/${tmdbMessages.length}`;
    try {
      const ok = await sendTelegramHtml(token, chatId, tmdbMessages[i], label);
      if (!ok) {
        batchFailures.push(`${label} rejected by Telegram`);
        console.error(`[letterboxd] CONTINUE after fail: ${label} HTTP reject`);
      }
    } catch (err) {
      const detail = err && err.message ? err.message : String(err);
      batchFailures.push(`${label}: ${detail}`);
      console.error(`[letterboxd] CONTINUE after fail: ${label}: ${detail}`);
    }
  }
  const photoResult = await sendCaptionedPhotos(
    token,
    chatId,
    workdir,
    genrePngs,
    GENRE_CAPTIONS,
  );
  if (photoResult.failed.length) {
    batchFailures.push(...photoResult.failed);
    console.error(
      `[letterboxd] genre PNGs sent ${photoResult.sent}/${photoResult.total}; failed: ${photoResult.failed.join("; ")}`,
    );
  }

  // Search-keyword film lists after every chart PNG (skip when none were requested).
  const searchPayload = readJsonFile(join(workdir, "search_keyword_lists.json"));
  const searchMessages = buildAllSearchKeywordMessages(searchPayload || {});
  for (let i = 0; i < searchMessages.length; i++) {
    const label = `search keyword HTML ${i + 1}/${searchMessages.length}`;
    try {
      const ok = await sendTelegramHtml(token, chatId, searchMessages[i], label);
      if (!ok) {
        batchFailures.push(`${label} rejected by Telegram`);
        console.error(`[letterboxd] CONTINUE after fail: ${label} HTTP reject`);
      }
    } catch (err) {
      const detail = err && err.message ? err.message : String(err);
      batchFailures.push(`${label}: ${detail}`);
      console.error(`[letterboxd] CONTINUE after fail: ${label}: ${detail}`);
    }
  }

  if (batchFailures.length) {
    const summary = batchFailures.join(" | ");
    await notifySendFailure(token, chatId, "TMDB HTML/PNG", new Error(summary));
    throw new Error(`TMDB send incomplete: ${summary}`);
  }

  console.log("calendar pngs", calendarPngs.join(","));
  console.log("genre pngs", genrePngs.join(","));
  console.log("search keyword messages", searchMessages.length);
  console.log("workdir files", readdirSync(workdir).join(","));
  console.log("unmatched", unmatched);
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((err) => {
    console.error(err && err.message ? err.message : err);
    process.exit(1);
  });
}
