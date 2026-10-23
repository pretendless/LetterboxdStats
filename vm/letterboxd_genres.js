// Telegram /letterboxd → wait for Letterboxd ZIP → GitHub Actions (Worker-safe).

import {
  assertRef,
  DEFAULT_REF,
  DEFAULT_REPO,
  dispatchUrl,
  githubHeaders,
  workflowRunsUrl,
} from "./dispatch.js";

export const LETTERBOXD_WORKFLOW = "letterboxd.yml";
/** @deprecated use LETTERBOXD_WORKFLOW */
export const LETTERBOXD_GENRES_WORKFLOW = LETTERBOXD_WORKFLOW;
export const AWAIT_LETTERBOXD_PREFIX = "lebxd:await:";
/** @deprecated use AWAIT_LETTERBOXD_PREFIX */
export const AWAIT_GENRES_PREFIX = AWAIT_LETTERBOXD_PREFIX;
export const LETTERBOXD_JOB_PREFIX = "lebxd:job:";
/** @deprecated use LETTERBOXD_JOB_PREFIX */
export const GENRES_JOB_PREFIX = LETTERBOXD_JOB_PREFIX;

const FILE_ID_RE = /^[A-Za-z0-9_-]{10,200}$/;

export function parseLetterboxdCommand(text) {
  const trimmed = String(text || "").trim();
  const match = trimmed.match(/^\/letterboxd(?:@[A-Za-z0-9_]+)?(?:\s+([\s\S]*))?$/i);
  if (!match) return null;
  const rest = (match[1] || "").trim();
  if (rest) return { error: "usage" };
  return { ok: true };
}

/** @lebxdbot entry. Bare /start and the deep link /start letterboxd. */
export function parseStartCommand(text) {
  const trimmed = String(text || "").trim();
  const match = trimmed.match(/^\/start(?:@[A-Za-z0-9_]+)?(?:\s+([\s\S]*))?$/i);
  if (!match) return null;
  const rest = (match[1] || "").trim();
  if (rest && rest.toLowerCase() !== "letterboxd") return { error: "usage" };
  return { ok: true };
}

/** @deprecated use parseLetterboxdCommand */
export const parseGenresCommand = parseLetterboxdCommand;

export function awaitLetterboxdKey(chatId) {
  return `${AWAIT_LETTERBOXD_PREFIX}${chatId}`;
}

/** @deprecated use awaitLetterboxdKey */
export const awaitGenresKey = awaitLetterboxdKey;

export function letterboxdJobKey(jobId) {
  return `${LETTERBOXD_JOB_PREFIX}${jobId}`;
}

export const LETTERBOXD_ACTIVE_PREFIX = "lebxd:active:";

export function letterboxdActiveKey(chatId) {
  return `${LETTERBOXD_ACTIVE_PREFIX}${chatId}`;
}

export function letterboxdCancelKey(jobId) {
  return `lebxd:cancel:${jobId}`;
}

export function encodeActiveLetterboxd(job) {
  return JSON.stringify({
    jobId: String(job.jobId || ""),
    chatId: String(job.chatId ?? ""),
    status: job.status || "pending",
    startedAt: Number(job.startedAt) || 0,
    runId: String(job.runId || ""),
  });
}

export function decodeActiveLetterboxd(raw) {
  if (raw == null || raw === "") return null;
  try {
    const parsed = JSON.parse(String(raw));
    if (!parsed || typeof parsed !== "object" || !parsed.jobId) return null;
    return {
      jobId: String(parsed.jobId),
      chatId: String(parsed.chatId ?? ""),
      status: String(parsed.status || "pending"),
      startedAt: Number(parsed.startedAt) || 0,
      runId: String(parsed.runId || ""),
    };
  } catch {
    return null;
  }
}

/** @deprecated use letterboxdJobKey */
export const genresJobKey = letterboxdJobKey;

export const LETTERBOXD_TOP_N_DEFAULT = 20;
export const LETTERBOXD_TOP_N_MIN = 1;
export const LETTERBOXD_TOP_N_MAX = 100;
export const LETTERBOXD_MIN_RATED_DEFAULT = 4;
export const LETTERBOXD_MIN_RATED_MIN = 1;
export const LETTERBOXD_MIN_RATED_MAX = 50;
export const LETTERBOXD_RATING_SCALE_DEFAULT = 5;
export const LETTERBOXD_RATING_SCALES = [5, 10, 100];
export const LETTERBOXD_EXCLUDE_KEYWORDS_MAX = 20;
export const LETTERBOXD_EXCLUDE_KEYWORD_MAX_LEN = 40;
export const LETTERBOXD_SEARCH_KEYWORDS_MAX = LETTERBOXD_EXCLUDE_KEYWORDS_MAX;
export const LETTERBOXD_SEARCH_KEYWORD_MAX_LEN = LETTERBOXD_EXCLUDE_KEYWORD_MAX_LEN;

export function defaultLetterboxdOptions() {
  return {
    topN: LETTERBOXD_TOP_N_DEFAULT,
    minRated: LETTERBOXD_MIN_RATED_DEFAULT,
    includeRewatchInAverages: false,
    showLikes: true,
    showReviews: true,
    showTopReview: true,
    ratingScale: LETTERBOXD_RATING_SCALE_DEFAULT,
    includeUSA: true,
    includeEnglish: true,
    includeDrama: true,
    includeComedy: true,
    excludeKeywords: [],
    searchKeywords: [],
    dateFrom: "",
    dateTo: "",
    includeUndated: false,
  };
}

function normalizeKeywordList(value, maxWords, maxLen) {
  const raw = Array.isArray(value)
    ? value
    : String(value || "")
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean);
  const out = [];
  const seen = new Set();
  for (const item of raw) {
    let word = String(item || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!word) continue;
    if (word.length > maxLen) {
      word = word.slice(0, maxLen).trimEnd();
    }
    const key = word.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(word);
    if (out.length >= maxWords) break;
  }
  return out;
}

export function normalizeExcludeKeywords(value) {
  return normalizeKeywordList(
    value,
    LETTERBOXD_EXCLUDE_KEYWORDS_MAX,
    LETTERBOXD_EXCLUDE_KEYWORD_MAX_LEN,
  );
}

export function normalizeSearchKeywords(value) {
  return normalizeKeywordList(
    value,
    LETTERBOXD_SEARCH_KEYWORDS_MAX,
    LETTERBOXD_SEARCH_KEYWORD_MAX_LEN,
  );
}

function clampInt(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isInteger(n)) return fallback;
  if (n < min || n > max) return fallback;
  return n;
}

function clampRatingScale(value, fallback = LETTERBOXD_RATING_SCALE_DEFAULT) {
  const n = Number(value);
  if (!Number.isInteger(n)) return fallback;
  if (!LETTERBOXD_RATING_SCALES.includes(n)) return fallback;
  return n;
}

export function normalizeLetterboxdOptions(options) {
  const src = options && typeof options === "object" ? options : {};
  const dateFrom = /^\d{4}-\d{2}-\d{2}$/.test(String(src.dateFrom || "")) ? String(src.dateFrom) : "";
  const dateTo = /^\d{4}-\d{2}-\d{2}$/.test(String(src.dateTo || "")) ? String(src.dateTo) : "";
  const windowOk = Boolean(dateFrom && dateTo && dateTo >= dateFrom);
  const showReviews = src.showReviews == null ? true : Boolean(src.showReviews);
  // Top review requires reviews on; clearing reviews also clears top review.
  // Default on when unset (Customize can disable).
  const showTopReview = showReviews
    ? src.showTopReview == null
      ? true
      : Boolean(src.showTopReview)
    : false;
  return {
    topN: clampInt(src.topN, LETTERBOXD_TOP_N_MIN, LETTERBOXD_TOP_N_MAX, LETTERBOXD_TOP_N_DEFAULT),
    minRated: clampInt(src.minRated, LETTERBOXD_MIN_RATED_MIN, LETTERBOXD_MIN_RATED_MAX, LETTERBOXD_MIN_RATED_DEFAULT),
    includeRewatchInAverages: src.includeRewatchInAverages == null ? false : Boolean(src.includeRewatchInAverages),
    showLikes: src.showLikes == null ? true : Boolean(src.showLikes),
    showReviews,
    showTopReview,
    ratingScale: clampRatingScale(src.ratingScale, LETTERBOXD_RATING_SCALE_DEFAULT),
    includeUSA: src.includeUSA == null ? true : Boolean(src.includeUSA),
    includeEnglish: src.includeEnglish == null ? true : Boolean(src.includeEnglish),
    includeDrama: src.includeDrama == null ? true : Boolean(src.includeDrama),
    includeComedy: src.includeComedy == null ? true : Boolean(src.includeComedy),
    excludeKeywords: normalizeExcludeKeywords(src.excludeKeywords),
    searchKeywords: normalizeSearchKeywords(src.searchKeywords),
    dateFrom: windowOk ? dateFrom : "",
    dateTo: windowOk ? dateTo : "",
    includeUndated: windowOk ? Boolean(src.includeUndated) : false,
  };
}

export function encodeAwaitLetterboxd(state = {}) {
  const out = {
    kind: "letterboxd",
    since: state.since || new Date().toISOString(),
    step: state.step || "zip",
  };
  if (state.fileId) out.fileId = String(state.fileId);
  if (state.topN != null) out.topN = state.topN;
  if (state.minRated != null) out.minRated = state.minRated;
  if (state.includeRewatchInAverages != null) {
    out.includeRewatchInAverages = Boolean(state.includeRewatchInAverages);
  }
  if (state.showLikes != null) out.showLikes = Boolean(state.showLikes);
  if (state.showReviews != null) out.showReviews = Boolean(state.showReviews);
  if (state.showTopReview != null) out.showTopReview = Boolean(state.showTopReview);
  if (state.ratingScale != null) out.ratingScale = clampRatingScale(state.ratingScale);
  if (state.promptMessageId != null) {
    const mid = Number(state.promptMessageId);
    if (Number.isFinite(mid) && mid > 0) out.promptMessageId = mid;
  }
  if (state.includeUSA != null) out.includeUSA = Boolean(state.includeUSA);
  if (state.includeEnglish != null) out.includeEnglish = Boolean(state.includeEnglish);
  if (state.includeDrama != null) out.includeDrama = Boolean(state.includeDrama);
  if (state.includeComedy != null) out.includeComedy = Boolean(state.includeComedy);
  if (Array.isArray(state.excludeKeywords) && state.excludeKeywords.length) {
    out.excludeKeywords = normalizeExcludeKeywords(state.excludeKeywords);
  }
  if (Array.isArray(state.searchKeywords) && state.searchKeywords.length) {
    out.searchKeywords = normalizeSearchKeywords(state.searchKeywords);
  }
  if (state.dateFrom) out.dateFrom = String(state.dateFrom);
  if (state.dateTo) out.dateTo = String(state.dateTo);
  if (state.includeUndated != null) out.includeUndated = Boolean(state.includeUndated);
  return JSON.stringify(out);
}

/** @deprecated use encodeAwaitLetterboxd */
export const encodeAwaitGenres = encodeAwaitLetterboxd;

export function decodeAwaitLetterboxd(raw) {
  if (raw == null || raw === "") return null;
  try {
    const parsed = JSON.parse(String(raw));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    // Accept legacy "genres" kind from older workers during rollout.
    if (parsed.kind !== "letterboxd" && parsed.kind !== "genres") return null;
    return {
      kind: "letterboxd",
      since: String(parsed.since || ""),
      step: parsed.step || "zip",
      fileId: String(parsed.fileId || ""),
      topN: parsed.topN == null ? null : parsed.topN,
      minRated: parsed.minRated == null ? null : parsed.minRated,
      includeRewatchInAverages:
        parsed.includeRewatchInAverages == null ? null : Boolean(parsed.includeRewatchInAverages),
      showLikes: parsed.showLikes == null ? null : Boolean(parsed.showLikes),
      showReviews: parsed.showReviews == null ? null : Boolean(parsed.showReviews),
      showTopReview: parsed.showTopReview == null ? null : Boolean(parsed.showTopReview),
      ratingScale: parsed.ratingScale == null ? null : clampRatingScale(parsed.ratingScale, null),
      promptMessageId: parsed.promptMessageId == null ? null : Number(parsed.promptMessageId) || null,
      includeUSA: parsed.includeUSA == null ? null : Boolean(parsed.includeUSA),
      includeEnglish: parsed.includeEnglish == null ? null : Boolean(parsed.includeEnglish),
      includeDrama: parsed.includeDrama == null ? null : Boolean(parsed.includeDrama),
      includeComedy: parsed.includeComedy == null ? null : Boolean(parsed.includeComedy),
      excludeKeywords: Array.isArray(parsed.excludeKeywords)
        ? normalizeExcludeKeywords(parsed.excludeKeywords)
        : [],
      searchKeywords: Array.isArray(parsed.searchKeywords)
        ? normalizeSearchKeywords(parsed.searchKeywords)
        : [],
      dateFrom: String(parsed.dateFrom || ""),
      dateTo: String(parsed.dateTo || ""),
      includeUndated: parsed.includeUndated == null ? null : Boolean(parsed.includeUndated),
    };
  } catch {
    return null;
  }
}

/** @deprecated use decodeAwaitLetterboxd */
export const decodeAwaitGenres = decodeAwaitLetterboxd;

export function newLetterboxdJobId(now = () => new Date()) {
  const stamp = now().toISOString().replace(/[:.]/g, "-");
  return `lb-${stamp}`.slice(0, 80);
}

/** @deprecated use newLetterboxdJobId */
export const newGenresJobId = newLetterboxdJobId;

export function isZipDocument(document) {
  if (!document || typeof document !== "object") return false;
  const name = String(document.file_name || document.fileName || "").toLowerCase();
  const mime = String(document.mime_type || document.mimeType || "").toLowerCase();
  if (name.endsWith(".zip")) return true;
  if (mime === "application/zip" || mime === "application/x-zip-compressed") return true;
  return false;
}

export function normalizeTelegramFileId(raw) {
  const id = String(raw || "").trim();
  if (!FILE_ID_RE.test(id)) return "";
  return id;
}

export function letterboxdPromptText() {
  return (
    "Send the Letterboxd export ZIP as one document.\n\n" +
    "Letterboxd → Settings → Import & Export → Export Your Data.\n" +
    "The archive must include diary.csv. watched.csv and ratings.csv are used for the catalog and averages when present. Cancel with /stop."
  );
}

/** @deprecated use letterboxdPromptText */
export const genresPromptText = letterboxdPromptText;

export function letterboxdNeedZipText() {
  return "Send a Letterboxd export .zip (a document in this chat). Cancel with /stop.";
}

/** @deprecated use letterboxdNeedZipText */
export const genresNeedZipText = letterboxdNeedZipText;

export function letterboxdInvalidZipText() {
  return "That is not a Letterboxd ZIP. Send the .zip from Settings → Export. Cancel with /stop.";
}

/** @deprecated use letterboxdInvalidZipText */
export const genresInvalidZipText = letterboxdInvalidZipText;

function formatKeywordSummaryList(words) {
  return words.length ? words.map((word) => `"${word}"`).join(", ") : "none";
}

/** Fixed-order count-top filters listed under Exclude when they are turned off. */
const EXCLUDE_SUMMARY_FLAGS = [
  { label: "USA", key: "includeUSA" },
  { label: "English", key: "includeEnglish" },
  { label: "Drama", key: "includeDrama" },
  { label: "Comedy", key: "includeComedy" },
];

const EXCLUDE_SUMMARY_FLAG_KEYS = Object.fromEntries(
  EXCLUDE_SUMMARY_FLAGS.map(({ label, key }) => [label.toLowerCase(), key]),
);

/**
 * Exclude clause value: omitted include-filters (USA/English/Drama/Comedy) then
 * quoted keywords. `none` when nothing is filtered out.
 */
function formatExcludeSummaryList(opts) {
  const parts = [];
  for (const { label, key } of EXCLUDE_SUMMARY_FLAGS) {
    if (!opts[key]) parts.push(label);
  }
  for (const word of opts.excludeKeywords) {
    parts.push(`"${word}"`);
  }
  return parts.length ? parts.join(", ") : "none";
}

/** Footnote under the Tops/…/Period paragraph (HTML italic; outside the `<pre>` block). */
export const LETTERBOXD_SETTINGS_SUMMARY_FOOTNOTE =
  "<i>Paste this into Paste settings on a later run.</i>";

/** Accept `Rewatches:` (current) or legacy `Rewatches in averages:`. */
const REWATCHES_SUMMARY_LABEL = String.raw`Rewatches(?: in averages)?:`;

function escapeTelegramHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Strip Telegram HTML wrappers/entities so paste can reuse an ack bubble. */
function plainTextForSettingsPaste(text) {
  let s = String(text || "");
  s = s.replace(/<\/?(?:pre|code|i|b|em|strong)(?:\s[^>]*)?>/gi, "");
  s = s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&");
  return s;
}

/** Plain Tops…Period (+ optional No diary date) for the copyable block. */
export function formatLetterboxdSettingsBody(options) {
  const opts = normalizeLetterboxdOptions(options);
  const period = opts.dateFrom ? `${opts.dateFrom} — ${opts.dateTo}` : "full";
  const undated = opts.dateFrom
    ? `\nNo diary date: ${opts.includeUndated ? "yes" : "no"}.`
    : "";
  // Top review on → only `Top review: yes.` (implies reviews on).
  // Top review off → only `Reviews: yes/no.` (never both lines).
  const reviewsOrTop = opts.showTopReview
    ? "Top review: yes. "
    : `Reviews: ${opts.showReviews ? "yes" : "no"}. `;
  return (
    `Tops: ${opts.topN}. Scale: ${opts.ratingScale}. Threshold: ${opts.minRated}. ` +
    `Rewatches: ${opts.includeRewatchInAverages ? "yes" : "no"}. ` +
    `Likes: ${opts.showLikes ? "yes" : "no"}. ` +
    reviewsOrTop +
    `Exclude: ${formatExcludeSummaryList(opts)}. ` +
    `Search: ${formatKeywordSummaryList(opts.searchKeywords)}. ` +
    `Period: ${period}.` +
    undated
  );
}

/** Compact settings block for the ZIP ack: `<pre>` copyable body + italic footnote. */
export function formatLetterboxdSettingsSummary(options) {
  const body = formatLetterboxdSettingsBody(options);
  return `<pre>${escapeTelegramHtml(body)}</pre>\n${LETTERBOXD_SETTINGS_SUMMARY_FOOTNOTE}`;
}

function ratingScaleFromTenPointField(raw) {
  // Legacy `10-point ratings: yes/no` — missing → 5 (old default off).
  if (raw == null) return 5;
  return String(raw).toLowerCase() === "yes" ? 10 : 5;
}

/** Prefer explicit Scale: 5|10|100 over legacy 10-point when both appear. */
function ratingScaleFromSummaryText(src, tenPointRaw) {
  const scaleMatch = String(src || "").match(/Scale:\s*(5|10|100)\./i);
  if (scaleMatch) return Number(scaleMatch[1]);
  return ratingScaleFromTenPointField(tenPointRaw);
}

/** True when a Scale: field is present but not 5, 10, or 100. */
export function letterboxdSettingsSummaryHasInvalidScale(text) {
  const m = plainTextForSettingsPaste(text).match(/Scale:\s*([^\s.]+)\./i);
  if (!m) return false;
  const n = Number(m[1]);
  return !(Number.isInteger(n) && LETTERBOXD_RATING_SCALES.includes(n));
}

const SCALE_AFTER_TOPS = String.raw`Tops:\s*(\d+)\.\s*Scale:\s*(5|10|100)\.\s*Threshold:\s*(\d+)\.\s*`;
const TOPS_THRESHOLD = String.raw`Tops:\s*(\d+)\.\s*Threshold:\s*(\d+)\.\s*`;
const TEN_POINT_SUMMARY_OPT = String.raw`(?:10-point ratings:\s*(yes|no)\.\s*)?`;
const EXCLUDE_SEARCH_PERIOD = String.raw`(?:Keyword exclusions|Exclude):\s*(none|(?:(?:"[^"]*"|USA|English|Drama|Comedy)(?:\s*,\s*(?:"[^"]*"|USA|English|Drama|Comedy))*))\.\s*(?:Search keywords|Search):\s*(none|(?:"[^"]*"(?:\s*,\s*"[^"]*")*))\.\s*Period:\s*(full|\d{4}-\d{2}-\d{2}\s*[—–-]\s*\d{4}-\d{2}-\d{2})\.`;

// Current emit: Tops + Scale + Threshold … Top review on.
// Optional trailing legacy `10-point ratings:` is ignored (Scale wins).
const SETTINGS_SUMMARY_SCALE_TOP_REVIEW_ON_RE = new RegExp(
  SCALE_AFTER_TOPS +
    REWATCHES_SUMMARY_LABEL +
    String.raw`\s*(yes|no)\.\s*Likes:\s*(yes|no)\.\s*Top review:\s*yes\.\s*` +
    TEN_POINT_SUMMARY_OPT +
    EXCLUDE_SEARCH_PERIOD,
  "i",
);

// Current emit: Tops + Scale + Threshold … Reviews only (Top review off).
const SETTINGS_SUMMARY_SCALE_RE = new RegExp(
  SCALE_AFTER_TOPS +
    REWATCHES_SUMMARY_LABEL +
    String.raw`\s*(yes|no)\.\s*Likes:\s*(yes|no)\.\s*Reviews:\s*(yes|no)\.\s*` +
    TEN_POINT_SUMMARY_OPT +
    EXCLUDE_SEARCH_PERIOD,
  "i",
);

// Legacy (pre-Scale): Threshold after Tops; optional 10-point ratings after reviews/top.
const SETTINGS_SUMMARY_TOP_REVIEW_ON_RE = new RegExp(
  TOPS_THRESHOLD +
    REWATCHES_SUMMARY_LABEL +
    String.raw`\s*(yes|no)\.\s*Likes:\s*(yes|no)\.\s*Top review:\s*yes\.\s*` +
    TEN_POINT_SUMMARY_OPT +
    EXCLUDE_SEARCH_PERIOD,
  "i",
);

const SETTINGS_SUMMARY_RE = new RegExp(
  TOPS_THRESHOLD +
    REWATCHES_SUMMARY_LABEL +
    String.raw`\s*(yes|no)\.\s*Likes:\s*(yes|no)\.\s*Reviews:\s*(yes|no)\.\s*` +
    TEN_POINT_SUMMARY_OPT +
    EXCLUDE_SEARCH_PERIOD,
  "i",
);

// Legacy dual lines: Reviews + Top review both present (PR #49 emit shape).
const SETTINGS_SUMMARY_LEGACY_BOTH_RE = new RegExp(
  TOPS_THRESHOLD +
    REWATCHES_SUMMARY_LABEL +
    String.raw`\s*(yes|no)\.\s*Likes:\s*(yes|no)\.\s*Reviews:\s*(yes|no)\.\s*Top review:\s*(yes|no)\.\s*` +
    TEN_POINT_SUMMARY_OPT +
    EXCLUDE_SEARCH_PERIOD,
  "i",
);

// Pre-Likes/Reviews: same Exclude shape, no Likes:/Reviews: fields (default likes/reviews/Top review yes).
const SETTINGS_SUMMARY_PRE_LIKES_RE = new RegExp(
  TOPS_THRESHOLD +
    REWATCHES_SUMMARY_LABEL +
    String.raw`\s*(yes|no)\.\s*(?:Keyword exclusions|Exclude):\s*(none|(?:(?:"[^"]*"|USA|English|Drama|Comedy)(?:\s*,\s*(?:"[^"]*"|USA|English|Drama|Comedy))*))\.\s*(?:Search keywords|Search):\s*(none|(?:"[^"]*"(?:\s*,\s*"[^"]*")*))\.\s*Period:\s*(full|\d{4}-\d{2}-\d{2}\s*[—–-]\s*\d{4}-\d{2}-\d{2})\.`,
  "i",
);

// Legacy: separate USA/English/Drama/Comedy yes/no fields + keyword-only Exclude.
const SETTINGS_SUMMARY_LEGACY_RE = new RegExp(
  TOPS_THRESHOLD +
    REWATCHES_SUMMARY_LABEL +
    String.raw`\s*(yes|no)\.\s*USA:\s*(yes|no)\.\s*English:\s*(yes|no)\.\s*Drama:\s*(yes|no)\.\s*Comedy:\s*(yes|no)\.\s*(?:Keyword exclusions|Exclude):\s*(none|(?:"[^"]*"(?:\s*,\s*"[^"]*")*))\.\s*(?:Search keywords|Search):\s*(none|(?:"[^"]*"(?:\s*,\s*"[^"]*")*))\.\s*Period:\s*(full|\d{4}-\d{2}-\d{2}\s*[—–-]\s*\d{4}-\d{2}-\d{2})\.`,
  "i",
);

const NO_DIARY_DATE_RE = /No diary date:\s*(yes|no)\./i;

function parseQuotedKeywordList(raw) {
  const value = String(raw || "").trim();
  if (!value || /^none$/i.test(value)) return [];
  const words = [];
  const re = /"([^"]*)"/g;
  let match;
  while ((match = re.exec(value))) {
    words.push(match[1]);
  }
  return words;
}

/**
 * Parse Exclude value: bare USA/English/Drama/Comedy mean those include-flags
 * are off; quoted tokens are exclude keywords. `none` → all includes on, no keywords.
 */
function parseExcludeSummaryList(raw) {
  const value = String(raw || "").trim();
  const out = {
    includeUSA: true,
    includeEnglish: true,
    includeDrama: true,
    includeComedy: true,
    excludeKeywords: [],
  };
  if (!value || /^none$/i.test(value)) return out;
  // Consume optional commas between tokens so quoted keywords keep their quotes.
  const re = /\s*(?:"([^"]*)"|([^,",]+))\s*(?:,|$)/g;
  let match;
  while ((match = re.exec(value))) {
    if (match[1] != null) {
      if (match[1]) out.excludeKeywords.push(match[1]);
      continue;
    }
    const token = String(match[2] || "").trim();
    if (!token) continue;
    const flagKey = EXCLUDE_SUMMARY_FLAG_KEYS[token.toLowerCase()];
    if (flagKey) {
      out[flagKey] = false;
    } else {
      out.excludeKeywords.push(token);
    }
  }
  out.excludeKeywords = normalizeExcludeKeywords(out.excludeKeywords);
  return out;
}

function parsePeriodAndUndated(src, match, periodGroupIndex, yesNo) {
  const periodRaw = String(match[periodGroupIndex] || "").trim();
  let dateFrom = "";
  let dateTo = "";
  let includeUndated = false;
  if (!/^full$/i.test(periodRaw)) {
    const dates = periodRaw.match(/(\d{4}-\d{2}-\d{2})\s*[—–-]\s*(\d{4}-\d{2}-\d{2})/);
    if (!dates || dates[2] < dates[1]) return null;
    dateFrom = dates[1];
    dateTo = dates[2];
    const afterPeriod = src.slice((match.index || 0) + match[0].length);
    const undated = afterPeriod.match(NO_DIARY_DATE_RE);
    if (undated) includeUndated = yesNo(undated[1]);
  }
  return { dateFrom, dateTo, includeUndated };
}

/**
 * Locate and parse a settings summary paragraph (from formatLetterboxdSettingsSummary)
 * inside arbitrary surrounding text. Returns normalized options, or null.
 * Accepts current Tops/Scale/… shape, legacy 10-point ratings, and older forms.
 */
export function parseLetterboxdSettingsSummary(text) {
  const src = plainTextForSettingsPaste(text);
  const yesNo = (value) => String(value).toLowerCase() === "yes";

  // Current: Tops + Scale + Threshold … Top review: yes.
  // Groups: 1 topN 2 scale 3 minRated 4 rewatch 5 likes 6 tenPoint? 7 exclude 8 search 9 period
  const scaleTopOn = src.match(SETTINGS_SUMMARY_SCALE_TOP_REVIEW_ON_RE);
  if (scaleTopOn) {
    const topN = Number(scaleTopOn[1]);
    const ratingScale = Number(scaleTopOn[2]);
    const minRated = Number(scaleTopOn[3]);
    if (!Number.isInteger(topN) || !Number.isInteger(minRated)) return null;
    if (topN < LETTERBOXD_TOP_N_MIN || topN > LETTERBOXD_TOP_N_MAX) return null;
    if (minRated < LETTERBOXD_MIN_RATED_MIN || minRated > LETTERBOXD_MIN_RATED_MAX) return null;
    if (![5, 10, 100].includes(ratingScale)) return null;
    const period = parsePeriodAndUndated(src, scaleTopOn, 9, yesNo);
    if (!period) return null;
    const exclude = parseExcludeSummaryList(scaleTopOn[7]);
    return normalizeLetterboxdOptions({
      topN,
      ratingScale,
      minRated,
      includeRewatchInAverages: yesNo(scaleTopOn[4]),
      showLikes: yesNo(scaleTopOn[5]),
      showReviews: true,
      showTopReview: true,
      includeUSA: exclude.includeUSA,
      includeEnglish: exclude.includeEnglish,
      includeDrama: exclude.includeDrama,
      includeComedy: exclude.includeComedy,
      excludeKeywords: exclude.excludeKeywords,
      searchKeywords: parseQuotedKeywordList(scaleTopOn[8]),
      ...period,
    });
  }

  // Current: Tops + Scale + Threshold … Reviews only.
  // Groups: 1 topN 2 scale 3 minRated 4 rewatch 5 likes 6 reviews 7 tenPoint? 8 exclude 9 search 10 period
  const scaleCurrent = src.match(SETTINGS_SUMMARY_SCALE_RE);
  if (scaleCurrent) {
    const topN = Number(scaleCurrent[1]);
    const ratingScale = Number(scaleCurrent[2]);
    const minRated = Number(scaleCurrent[3]);
    if (!Number.isInteger(topN) || !Number.isInteger(minRated)) return null;
    if (topN < LETTERBOXD_TOP_N_MIN || topN > LETTERBOXD_TOP_N_MAX) return null;
    if (minRated < LETTERBOXD_MIN_RATED_MIN || minRated > LETTERBOXD_MIN_RATED_MAX) return null;
    if (![5, 10, 100].includes(ratingScale)) return null;
    const period = parsePeriodAndUndated(src, scaleCurrent, 10, yesNo);
    if (!period) return null;
    const exclude = parseExcludeSummaryList(scaleCurrent[8]);
    const reviewsOn = yesNo(scaleCurrent[6]);
    return normalizeLetterboxdOptions({
      topN,
      ratingScale,
      minRated,
      includeRewatchInAverages: yesNo(scaleCurrent[4]),
      showLikes: yesNo(scaleCurrent[5]),
      showReviews: reviewsOn,
      showTopReview: false,
      includeUSA: exclude.includeUSA,
      includeEnglish: exclude.includeEnglish,
      includeDrama: exclude.includeDrama,
      includeComedy: exclude.includeComedy,
      excludeKeywords: exclude.excludeKeywords,
      searchKeywords: parseQuotedKeywordList(scaleCurrent[9]),
      ...period,
    });
  }

  // Legacy dual lines (Reviews + Top review) before single-field shapes.
  // Groups: 1 topN 2 minRated 3 rewatch 4 likes 5 reviews 6 top 7 tenPoint?
  //         8 exclude 9 search 10 period
  const legacyBoth = src.match(SETTINGS_SUMMARY_LEGACY_BOTH_RE);
  if (legacyBoth) {
    const topN = Number(legacyBoth[1]);
    const minRated = Number(legacyBoth[2]);
    if (!Number.isInteger(topN) || !Number.isInteger(minRated)) return null;
    if (topN < LETTERBOXD_TOP_N_MIN || topN > LETTERBOXD_TOP_N_MAX) return null;
    if (minRated < LETTERBOXD_MIN_RATED_MIN || minRated > LETTERBOXD_MIN_RATED_MAX) return null;
    const period = parsePeriodAndUndated(src, legacyBoth, 10, yesNo);
    if (!period) return null;
    const exclude = parseExcludeSummaryList(legacyBoth[8]);
    const reviewsOn = yesNo(legacyBoth[5]);
    const topOn = reviewsOn && yesNo(legacyBoth[6]);
    return normalizeLetterboxdOptions({
      topN,
      minRated,
      includeRewatchInAverages: yesNo(legacyBoth[3]),
      showLikes: yesNo(legacyBoth[4]),
      showReviews: reviewsOn || topOn,
      showTopReview: topOn,
      ratingScale: ratingScaleFromSummaryText(src, legacyBoth[7]),
      includeUSA: exclude.includeUSA,
      includeEnglish: exclude.includeEnglish,
      includeDrama: exclude.includeDrama,
      includeComedy: exclude.includeComedy,
      excludeKeywords: exclude.excludeKeywords,
      searchKeywords: parseQuotedKeywordList(legacyBoth[9]),
      ...period,
    });
  }

  // Legacy Top review: yes alone (optional 10-point ratings).
  // Groups: 1 topN 2 minRated 3 rewatch 4 likes 5 tenPoint? 6 exclude 7 search 8 period
  const topReviewOn = src.match(SETTINGS_SUMMARY_TOP_REVIEW_ON_RE);
  if (topReviewOn) {
    const topN = Number(topReviewOn[1]);
    const minRated = Number(topReviewOn[2]);
    if (!Number.isInteger(topN) || !Number.isInteger(minRated)) return null;
    if (topN < LETTERBOXD_TOP_N_MIN || topN > LETTERBOXD_TOP_N_MAX) return null;
    if (minRated < LETTERBOXD_MIN_RATED_MIN || minRated > LETTERBOXD_MIN_RATED_MAX) return null;
    const period = parsePeriodAndUndated(src, topReviewOn, 8, yesNo);
    if (!period) return null;
    const exclude = parseExcludeSummaryList(topReviewOn[6]);
    return normalizeLetterboxdOptions({
      topN,
      minRated,
      includeRewatchInAverages: yesNo(topReviewOn[3]),
      showLikes: yesNo(topReviewOn[4]),
      showReviews: true,
      showTopReview: true,
      ratingScale: ratingScaleFromSummaryText(src, topReviewOn[5]),
      includeUSA: exclude.includeUSA,
      includeEnglish: exclude.includeEnglish,
      includeDrama: exclude.includeDrama,
      includeComedy: exclude.includeComedy,
      excludeKeywords: exclude.excludeKeywords,
      searchKeywords: parseQuotedKeywordList(topReviewOn[7]),
      ...period,
    });
  }

  // Legacy Reviews only (optional 10-point ratings).
  // Groups: 1 topN 2 minRated 3 rewatch 4 likes 5 reviews 6 tenPoint? 7 exclude 8 search 9 period
  const current = src.match(SETTINGS_SUMMARY_RE);
  if (current) {
    const topN = Number(current[1]);
    const minRated = Number(current[2]);
    if (!Number.isInteger(topN) || !Number.isInteger(minRated)) return null;
    if (topN < LETTERBOXD_TOP_N_MIN || topN > LETTERBOXD_TOP_N_MAX) return null;
    if (minRated < LETTERBOXD_MIN_RATED_MIN || minRated > LETTERBOXD_MIN_RATED_MAX) return null;
    const period = parsePeriodAndUndated(src, current, 9, yesNo);
    if (!period) return null;
    const exclude = parseExcludeSummaryList(current[7]);
    const reviewsOn = yesNo(current[5]);
    return normalizeLetterboxdOptions({
      topN,
      minRated,
      includeRewatchInAverages: yesNo(current[3]),
      showLikes: yesNo(current[4]),
      showReviews: reviewsOn,
      showTopReview: false,
      ratingScale: ratingScaleFromSummaryText(src, current[6]),
      includeUSA: exclude.includeUSA,
      includeEnglish: exclude.includeEnglish,
      includeDrama: exclude.includeDrama,
      includeComedy: exclude.includeComedy,
      excludeKeywords: exclude.excludeKeywords,
      searchKeywords: parseQuotedKeywordList(current[8]),
      ...period,
    });
  }

  const preLikes = src.match(SETTINGS_SUMMARY_PRE_LIKES_RE);
  if (preLikes) {
    const topN = Number(preLikes[1]);
    const minRated = Number(preLikes[2]);
    if (!Number.isInteger(topN) || !Number.isInteger(minRated)) return null;
    if (topN < LETTERBOXD_TOP_N_MIN || topN > LETTERBOXD_TOP_N_MAX) return null;
    if (minRated < LETTERBOXD_MIN_RATED_MIN || minRated > LETTERBOXD_MIN_RATED_MAX) return null;
    const period = parsePeriodAndUndated(src, preLikes, 6, yesNo);
    if (!period) return null;
    const exclude = parseExcludeSummaryList(preLikes[4]);
    return normalizeLetterboxdOptions({
      topN,
      minRated,
      includeRewatchInAverages: yesNo(preLikes[3]),
      showLikes: true,
      showReviews: true,
      showTopReview: true,
      ratingScale: ratingScaleFromSummaryText(src, null),
      includeUSA: exclude.includeUSA,
      includeEnglish: exclude.includeEnglish,
      includeDrama: exclude.includeDrama,
      includeComedy: exclude.includeComedy,
      excludeKeywords: exclude.excludeKeywords,
      searchKeywords: parseQuotedKeywordList(preLikes[5]),
      ...period,
    });
  }

  const legacy = src.match(SETTINGS_SUMMARY_LEGACY_RE);
  if (!legacy) return null;
  const topN = Number(legacy[1]);
  const minRated = Number(legacy[2]);
  if (!Number.isInteger(topN) || !Number.isInteger(minRated)) return null;
  if (topN < LETTERBOXD_TOP_N_MIN || topN > LETTERBOXD_TOP_N_MAX) return null;
  if (minRated < LETTERBOXD_MIN_RATED_MIN || minRated > LETTERBOXD_MIN_RATED_MAX) return null;
  const period = parsePeriodAndUndated(src, legacy, 10, yesNo);
  if (!period) return null;

  return normalizeLetterboxdOptions({
    topN,
    minRated,
    includeRewatchInAverages: yesNo(legacy[3]),
    showLikes: true,
    showReviews: true,
    showTopReview: true,
    ratingScale: ratingScaleFromSummaryText(src, null),
    includeUSA: yesNo(legacy[4]),
    includeEnglish: yesNo(legacy[5]),
    includeDrama: yesNo(legacy[6]),
    includeComedy: yesNo(legacy[7]),
    excludeKeywords: parseQuotedKeywordList(legacy[8]),
    searchKeywords: parseQuotedKeywordList(legacy[9]),
    ...period,
  });
}

export const LETTERBOXD_PASTE_SETTINGS_RETRY =
  "Could not parse that settings summary. Paste the Tops: … Period: paragraph (include Scale: 5, 10, or 100). Charts have not started.";

export const LETTERBOXD_PASTE_SCALE_RETRY =
  "Scale must be 5, 10, or 100. Paste the Tops: … Period: paragraph. Charts have not started.";

export function letterboxdAckText(jobId, options) {
  return (
    "ZIP received. Building charts — PNGs will arrive here (calendar, extra stats, genres).\n\n" +
    formatLetterboxdSettingsSummary(options) +
    `\n\nid: ${jobId}`
  );
}

/** @deprecated use letterboxdAckText */
export const genresAckText = letterboxdAckText;

export function letterboxdStartingText() {
  return "⏳ Starting Letterboxd…";
}

/** @deprecated use letterboxdStartingText */
export const genresStartingText = letterboxdStartingText;

export function letterboxdDispatchedText({ jobId, runUrl }) {
  if (runUrl) {
    return `✅ Run accepted.\n\n${runUrl}\n\nid: ${jobId}`;
  }
  return `✅ Run accepted. Charts will arrive as separate messages.\n\nid: ${jobId}`;
}

/** @deprecated use letterboxdDispatchedText */
export const genresDispatchedText = letterboxdDispatchedText;

export function letterboxdDispatchFailText(status) {
  return `Could not start Letterboxd: GitHub replied ${status}. Check GHLEBXD_DISPATCH_TOKEN and the letterboxd.yml workflow on main.`;
}

/** @deprecated use letterboxdDispatchFailText */
export const genresDispatchFailText = letterboxdDispatchFailText;

export function letterboxdUsageText() {
  return "Command: /start — then send a Letterboxd export ZIP. A link from another chat opens the same wizard: /start letterboxd.";
}

/** @deprecated use letterboxdUsageText */
export const genresUsageText = letterboxdUsageText;

export function letterboxdStopClearedHead() {
  return "Input cancelled. The Letterboxd wizard was cleared.";
}

export function letterboxdStopJobHead() {
  return "Chart run stopped.";
}

export function letterboxdStopIdleHead() {
  return "Nothing to cancel right now.";
}

export function letterboxdStopFailText(status) {
  return `Could not stop the run: GitHub replied ${status}.`;
}

export function letterboxdCommandList() {
  return "/start — Letterboxd charts\n/stop — cancel input";
}

export function letterboxdStopText({ wizard = false, job = false, failStatus = "" } = {}) {
  const lines = [];
  if (wizard) lines.push(letterboxdStopClearedHead());
  if (failStatus) lines.push(letterboxdStopFailText(failStatus));
  else if (job) lines.push(letterboxdStopJobHead());
  if (!lines.length) lines.push(letterboxdStopIdleHead());
  return `${lines.join("\n")}\n\n${letterboxdCommandList()}`;
}

/** @deprecated use letterboxdStopClearedHead */
export const genresStopClearedHead = letterboxdStopClearedHead;

function normReply(text) {
  return String(text || "")
    .trim()
    .toLowerCase()
    .replace(/[.!?]+$/g, "")
    .replace(/\s+/g, " ");
}

const RU_MONTHS = {
  январь: 1,
  янв: 1,
  февраль: 2,
  фев: 2,
  март: 3,
  мар: 3,
  апрель: 4,
  апр: 4,
  май: 5,
  июнь: 6,
  июн: 6,
  июль: 7,
  июл: 7,
  август: 8,
  авг: 8,
  сентябрь: 9,
  сен: 9,
  октябрь: 10,
  окт: 10,
  ноябрь: 11,
  ноя: 11,
  декабрь: 12,
  дек: 12,
};

const EN_MONTHS = {
  january: 1,
  jan: 1,
  february: 2,
  feb: 2,
  march: 3,
  mar: 3,
  april: 4,
  apr: 4,
  may: 5,
  june: 6,
  jun: 6,
  july: 7,
  jul: 7,
  august: 8,
  aug: 8,
  september: 9,
  sep: 9,
  sept: 9,
  october: 10,
  oct: 10,
  november: 11,
  nov: 11,
  december: 12,
  dec: 12,
};

function isoDate(year, month, day) {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function daysInMonth(year, month) {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function yearOk(year) {
  return year >= 1900 && year <= 2100;
}

export const LETTERBOXD_DATE_RETRY =
  "Could not read that date. Year: 2012. Month: 06-2012. Day: 15-06-2012 or 15.06.2012. Two edges: 2018 2020 or 2021-06.2022. The report has not started.";

/**
 * One typed bound → inclusive YYYY-MM-DD edge.
 * Month is always before year: MM-YYYY, MM.YYYY, "March 2012", «март 2012».
 * Day is day-month-year: DD-MM-YYYY or DD.MM.YYYY.
 * Year-first forms (2012-06, 2012-06-15) are rejected.
 * edge "start" is the first day of that period; "end" is the last day.
 */
export function parseWatchBound(text, edge = "start") {
  const raw = String(text || "").trim().toLowerCase().replace(/\s+/g, " ");
  const end = edge === "end";
  const emit = (year, month, day, precision) => {
    if (!yearOk(year) || month < 1 || month > 12) return "";
    if (precision === "year") return end ? isoDate(year, 12, 31) : isoDate(year, 1, 1);
    if (precision === "month") {
      return end ? isoDate(year, month, daysInMonth(year, month)) : isoDate(year, month, 1);
    }
    if (day < 1 || day > daysInMonth(year, month)) return "";
    return isoDate(year, month, day);
  };

  let match = raw.match(/^(\d{4})$/);
  if (match) return emit(Number(match[1]), 1, 1, "year");

  match = raw.match(/^(\d{2})[-.](\d{4})$/);
  if (match) return emit(Number(match[2]), Number(match[1]), 1, "month");

  match = raw.match(/^([a-zа-яё]+)\s+(\d{4})$/);
  if (match) {
    const month = RU_MONTHS[match[1]] || EN_MONTHS[match[1]];
    if (month) return emit(Number(match[2]), month, 1, "month");
  }

  match = raw.match(/^(\d{2})[-.](\d{2})[-.](\d{4})$/);
  if (match) return emit(Number(match[3]), Number(match[2]), Number(match[1]), "day");

  return "";
}

function pairWatchBounds(left, right) {
  const dateFrom = parseWatchBound(left, "start");
  const dateTo = parseWatchBound(right, "end");
  if (!dateFrom || !dateTo) return null;
  return { dateFrom, dateTo };
}

/**
 * One value is the whole interval. Two bounds are an explicit start–end.
 * A hyphen, dash, or space splits the bounds. A dot or hyphen inside one
 * bound stays part of that date (06.2022, 15-06-2022). The first split
 * where both sides are valid month-before-year bounds wins.
 * Year-before-month (2021-06, 2021.06) is not a bound.
 */
export function parseWatchInterval(text) {
  const raw = String(text || "").trim().replace(/\s+/g, " ");
  if (!raw) return null;
  if (parseWatchBound(raw, "start")) {
    return { dateFrom: parseWatchBound(raw, "start"), dateTo: parseWatchBound(raw, "end") };
  }
  for (let i = 0; i < raw.length; i += 1) {
    const ch = raw[i];
    if (ch !== "-" && ch !== "–" && ch !== "—") continue;
    const found = pairWatchBounds(raw.slice(0, i), raw.slice(i + 1));
    if (found) return found;
  }
  const bits = raw.split(" ");
  if (bits.length === 2) return pairWatchBounds(bits[0], bits[1]);
  return null;
}

export function utcDateStamp(date) {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function shiftUtcYears(date, deltaYears) {
  const year = date.getUTCFullYear() + deltaYears;
  const month = date.getUTCMonth();
  const day = date.getUTCDate();
  const dim = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(day, dim)));
}

export function presetWatchRange(years, now = new Date()) {
  return {
    dateFrom: utcDateStamp(shiftUtcYears(now, -years)),
    dateTo: utcDateStamp(now),
  };
}

function button(text, data) {
  return { text, callback_data: data };
}

function withDefaultButton(rows, label, data) {
  return { inline_keyboard: [...rows, [button(label, data)]] };
}

/** Neutral object/symbol emojis only — no hand or face glyphs.
 *  Numeric choices (tops, threshold, years, Last N years) stay numbers/labels only.
 */
export const WIZARD_EMOJI_YES = "✅";
export const WIZARD_EMOJI_NO = "❌";
export const WIZARD_EMOJI_DEFAULT_MODE = "✅";
export const WIZARD_EMOJI_CUSTOMIZE = "⚙️";
export const WIZARD_EMOJI_PASTE = "📋";
export const WIZARD_EMOJI_FULL_PERIOD = "📅";
export const WIZARD_EMOJI_CUSTOM_RANGE = "✏️";
export const WIZARD_EMOJI_DONE = "✔️";
export const WIZARD_EMOJI_NONE = "🚫";

/** Default button: emoji of the default choice, or bare ``Default (N)`` when numeric. */
function defaultButtonLabel(emojiOrEmpty, detail = "") {
  if (!emojiOrEmpty) {
    return detail ? `Default (${detail})` : "Default";
  }
  const tail = detail ? ` (${detail})` : "";
  return `Default ${emojiOrEmpty}${tail}`;
}

export function letterboxdModeKeyboard() {
  return withDefaultButton(
    [[
      button(`${WIZARD_EMOJI_CUSTOMIZE} Customize`, "lb:cus"),
      button(`${WIZARD_EMOJI_PASTE} Paste settings`, "lb:paste"),
    ]],
    defaultButtonLabel(WIZARD_EMOJI_DEFAULT_MODE),
    "lb:def",
  );
}

export function letterboxdTopKeyboard() {
  return withDefaultButton(
    [[
      button("10", "lb:n:10"),
      button("20", "lb:n:20"),
      button("30", "lb:n:30"),
      button("50", "lb:n:50"),
    ]],
    defaultButtonLabel("", "20"),
    "lb:n:20",
  );
}

export function letterboxdMinKeyboard() {
  return withDefaultButton(
    [[
      button("1", "lb:m:1"),
      button("3", "lb:m:3"),
      button("5", "lb:m:5"),
    ]],
    defaultButtonLabel("", "4"),
    "lb:m:4",
  );
}

export function letterboxdScaleKeyboard() {
  return withDefaultButton(
    [[
      button("5", "lb:scale:5"),
      button("10", "lb:scale:10"),
      button("100", "lb:scale:100"),
    ]],
    defaultButtonLabel("", "5"),
    "lb:scale:5",
  );
}

export function letterboxdYesNoKeyboard(prefix, fallback = "yes") {
  const no = fallback === "no" || fallback === "нет";
  const data = no ? `${prefix}:0` : `${prefix}:1`;
  return withDefaultButton(
    [[
      button(`${WIZARD_EMOJI_YES} Yes`, `${prefix}:1`),
      button(`${WIZARD_EMOJI_NO} No`, `${prefix}:0`),
    ]],
    defaultButtonLabel(no ? WIZARD_EMOJI_NO : WIZARD_EMOJI_YES),
    data,
  );
}

export function letterboxdPeriodKeyboard() {
  return withDefaultButton(
    [[
      button(`${WIZARD_EMOJI_FULL_PERIOD} Full period`, "lb:span"),
      button(`${WIZARD_EMOJI_CUSTOM_RANGE} Custom range`, "lb:rng"),
    ]],
    defaultButtonLabel(WIZARD_EMOJI_FULL_PERIOD, "full"),
    "lb:span",
  );
}

export function recentWatchYears(now = new Date(), count = 5) {
  const year = now.getUTCFullYear();
  const years = [];
  for (let i = 0; i < count; i += 1) years.push(year - i);
  return years;
}

export function letterboxdRangeKeyboard(now = new Date()) {
  // Calendar years and Last N years are numeric/plain labels — no emoji.
  const years = recentWatchYears(now, 5).map((year) =>
    button(String(year), `lb:yr:${year}`),
  );
  return {
    inline_keyboard: [
      years.slice(0, 3),
      years.slice(3),
      [
        button("Last 3 years", "lb:y:3"),
        button("Last 5 years", "lb:y:5"),
      ],
      [button(defaultButtonLabel(WIZARD_EMOJI_FULL_PERIOD, "full"), "lb:full")],
    ],
  };
}

export function letterboxdUndatedKeyboard() {
  return withDefaultButton(
    [[
      button(`${WIZARD_EMOJI_NO} No`, "lb:und:0"),
      button(`${WIZARD_EMOJI_YES} Yes`, "lb:und:1"),
    ]],
    defaultButtonLabel(WIZARD_EMOJI_NO),
    "lb:und:0",
  );
}

export function letterboxdKeywordsKeyboard(hasWords = false) {
  const rows = [[button(`${WIZARD_EMOJI_DONE} Done`, "lb:kw:done")]];
  if (!hasWords) {
    rows.push([button(defaultButtonLabel(WIZARD_EMOJI_NONE, "none"), "lb:kw:done")]);
  }
  return { inline_keyboard: rows };
}

export function letterboxdSearchKeywordsKeyboard(hasWords = false) {
  const rows = [[button(`${WIZARD_EMOJI_DONE} Done`, "lb:sk:done")]];
  if (!hasWords) {
    rows.push([button(defaultButtonLabel(WIZARD_EMOJI_NONE, "none"), "lb:sk:done")]);
  }
  return { inline_keyboard: rows };
}

function htmlEscape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function wizardPrompt(heading, body, example, fallback) {
  return [`<b>${heading}</b>`, "", body, "", `For example: ${example}`, "", `Default: ${fallback}`].join("\n");
}

function choicePrompt(heading, body) {
  return [`<b>${heading}</b>`, "", body].join("\n");
}

export function letterboxdModePrompt() {
  return {
    text: [
      "<b>How should the charts be built?</b>",
      "",
      "ZIP received. Default runs the usual charts now. Customize walks through size, threshold, likes, reviews, filters, and dates. Paste settings reuses a previous Tops: … Period: summary.",
      "",
      "Tap a button, or reply with text. Cancel with /stop.",
    ].join("\n"),
    reply_markup: letterboxdModeKeyboard(),
  };
}

export function letterboxdPasteSettingsPrompt() {
  return {
    text: [
      "<b>Paste your settings summary</b>",
      "",
      "Paste a Tops: … Period: paragraph from a previous run (include No diary date: when you used a date range). Extra text around it is fine.",
      "",
      "Cancel with /stop.",
    ].join("\n"),
  };
}

function promptFor(step, state, now = new Date()) {
  if (step === "mode") return letterboxdModePrompt();
  if (step === "paste_settings") return letterboxdPasteSettingsPrompt();
  if (step === "top_n") {
    return {
      text: wizardPrompt(
        "How many rows in each top?",
        "Rows per ranking chart. Tap a button, or type a number from 1 to 100.",
        "20, 7, 100",
        "20",
      ),
      reply_markup: letterboxdTopKeyboard(),
    };
  }
  if (step === "scale") {
    return {
      text: wizardPrompt(
        "Scale",
        "Displayed rating and average numbers use this scale (Letterboxd 0.5–5 × scale/5). Colors and ranking stay the same. Tap a button, or type 5, 10, or 100.",
        "5, 10, 100",
        "5",
      ),
      reply_markup: letterboxdScaleKeyboard(),
    };
  }
  if (step === "min_rated") {
    return {
      text: wizardPrompt(
        "Threshold",
        "Minimum rated films (or catalog hits) before a row appears on average-rating and people/studio watch-count charts. At 4, a director with only three rated films is skipped. Tap a button, or type 1–50.",
        "1, 3, 5",
        "4",
      ),
      reply_markup: letterboxdMinKeyboard(),
    };
  }
  if (step === "rewatch_avg") {
    return {
      text: choicePrompt(
        "Count rewatches in averages?",
        "Off: each film’s last rating only. On: every rated diary entry counts. Default is off.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:rew", "no"),
    };
  }
  if (step === "show_likes") {
    return {
      text: choicePrompt(
        "Show likes (♥)?",
        "Orange ♥ on tips, titles, Most liked lists, and search lines. Default is on.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:likes"),
    };
  }
  if (step === "show_reviews") {
    return {
      text: choicePrompt(
        "Show reviews (≡)?",
        "Blue ≡ on tips, titles, Most reviewed lists, and search lines. Off also skips Top review. Default is on.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:revs"),
    };
  }
  if (step === "show_top_review") {
    return {
      text: choicePrompt(
        "Show top review?",
        "When on, ranking charts show a small review panel: film title (♥ if liked), up to 280 characters, and the date. Picks the highest-ranked film that has a review — highest rating on count/higher charts, lowest on lower charts; if none are rated, prefer liked, then the newest date. Also unlocks lower-rating charts when there aren’t enough films for a full top. Default is on.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:toprev", "yes"),
    };
  }
  if (step === "exclusions") {
    return {
      text: choicePrompt(
        "Exclude some rows from watch-count tops?",
        "Yes asks about USA, English, Drama, Comedy, and custom keywords (count charts only). No keeps every row. Default is no.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:excl", "no"),
    };
  }
  if (step === "usa") {
    return {
      text: choicePrompt(
        "Show USA in the country top?",
        "No hides USA from the country chart. Default is on.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:usa"),
    };
  }
  if (step === "english") {
    return {
      text: choicePrompt(
        "Show English in the language top?",
        "No hides English from the language chart. Default is on.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:en"),
    };
  }
  if (step === "drama") {
    return {
      text: choicePrompt(
        "Show Drama in the genre tops?",
        "No hides Drama from genre charts. Default is on.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:drama"),
    };
  }
  if (step === "comedy") {
    return {
      text: choicePrompt(
        "Show Comedy in the genre tops?",
        "No hides Comedy from genre charts. Default is on.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:com"),
    };
  }
  if (step === "keywords") {
    const words = normalizeExcludeKeywords(state.excludeKeywords);
    const listed = words.length
      ? `Added (${words.length}/${LETTERBOXD_EXCLUDE_KEYWORDS_MAX}): ${words
          .map((word) => htmlEscape(word))
          .join(", ")}.`
      : `None yet. Up to ${LETTERBOXD_EXCLUDE_KEYWORDS_MAX} words, ${LETTERBOXD_EXCLUDE_KEYWORD_MAX_LEN} characters each.`;
    return {
      text: [
        "<b>Exclude keywords</b>",
        "",
        "Send one word per message (actor, director, studio, genre, language, country, or year). Case-insensitive match on chart row names. Count charts only.",
        "",
        listed,
        "",
        'Tap Done when finished, or send "done".',
      ].join("\n"),
      reply_markup: letterboxdKeywordsKeyboard(words.length > 0),
    };
  }
  if (step === "search") {
    return {
      text: choicePrompt(
        "Add search keywords?",
        "Optional text lists after the charts — films whose metadata match each keyword. Default is off.",
      ),
      reply_markup: letterboxdYesNoKeyboard("lb:search", "no"),
    };
  }
  if (step === "search_keywords") {
    const words = normalizeSearchKeywords(state.searchKeywords);
    const listed = words.length
      ? `Added (${words.length}/${LETTERBOXD_SEARCH_KEYWORDS_MAX}): ${words
          .map((word) => htmlEscape(word))
          .join(", ")}.`
      : `None yet. Up to ${LETTERBOXD_SEARCH_KEYWORDS_MAX} words, ${LETTERBOXD_SEARCH_KEYWORD_MAX_LEN} characters each.`;
    return {
      text: [
        "<b>Search keywords</b>",
        "",
        "Send one word per message (actor, director, studio, genre, language, country, or year). Matches film metadata; lists arrive after every chart PNG.",
        "",
        listed,
        "",
        'Tap Done when finished, or send "done".',
      ].join("\n"),
      reply_markup: letterboxdSearchKeywordsKeyboard(words.length > 0),
    };
  }
  if (step === "period") {
    return {
      text: choicePrompt(
        "Full period or a custom range?",
        "Full: first watch through last. Custom: only the dates you pick (inclusive). Default is full.",
      ),
      reply_markup: letterboxdPeriodKeyboard(),
    };
  }
  if (step === "range_start") {
    return {
      text: wizardPrompt(
        "Which period?",
        "Type inclusive dates (month before year), or tap a ready-made range. One value = that whole slice; two values = start and end.",
        "2012, 06-2012, 15-06-2012, 2021-06.2022, 15.06.2021 - 20.08.2022",
        "full period",
      ),
      reply_markup: letterboxdRangeKeyboard(now),
    };
  }
  if (step === "range_end") {
    return {
      text: wizardPrompt(
        "End of the range",
        `Start is ${htmlEscape(state.dateFrom)}. End is inclusive (year, month, or day).`,
        "2012, 06-2012, 15-06-2012",
        "full period",
      ),
      reply_markup: {
        inline_keyboard: [[
          button(defaultButtonLabel(WIZARD_EMOJI_FULL_PERIOD, "full"), "lb:endfull"),
        ]],
      },
    };
  }
  if (step === "undated") {
    return {
      text: choicePrompt(
        "Add films with no diary date?",
        "No: only dated diary rows in the period. Yes: also undated watched/ratings films (not on calendar charts). Default is no.",
      ),
      reply_markup: letterboxdUndatedKeyboard(),
    };
  }
  return letterboxdModePrompt();
}

function withText(step, state, text, now = new Date()) {
  const base = promptFor(step, state, now);
  return { text, reply_markup: base.reply_markup };
}

export function parseLetterboxdCallback(data) {
  const raw = String(data || "");
  if (raw === "lb:def") return { step: "mode", choice: "defaults" };
  if (raw === "lb:cus") return { step: "mode", choice: "custom" };
  if (raw === "lb:paste") return { step: "mode", choice: "paste" };
  let match = raw.match(/^lb:n:(10|20|30|50)$/);
  if (match) return { step: "top_n", value: Number(match[1]) };
  match = raw.match(/^lb:m:(1|3|4|5)$/);
  if (match) return { step: "min_rated", value: Number(match[1]) };
  if (raw === "lb:rew:1" || raw === "lb:rew:0") return { step: "rewatch_avg", value: raw.endsWith("1") };
  if (raw === "lb:likes:1" || raw === "lb:likes:0") return { step: "show_likes", value: raw.endsWith("1") };
  if (raw === "lb:revs:1" || raw === "lb:revs:0") return { step: "show_reviews", value: raw.endsWith("1") };
  if (raw === "lb:toprev:1" || raw === "lb:toprev:0") return { step: "show_top_review", value: raw.endsWith("1") };
  match = raw.match(/^lb:scale:(5|10|100)$/);
  if (match) return { step: "scale", value: Number(match[1]) };
  if (raw === "lb:excl:1" || raw === "lb:excl:0") return { step: "exclusions", value: raw.endsWith("1") };
  if (raw === "lb:usa:1" || raw === "lb:usa:0") return { step: "usa", value: raw.endsWith("1") };
  if (raw === "lb:en:1" || raw === "lb:en:0") return { step: "english", value: raw.endsWith("1") };
  if (raw === "lb:drama:1" || raw === "lb:drama:0") return { step: "drama", value: raw.endsWith("1") };
  if (raw === "lb:com:1" || raw === "lb:com:0") return { step: "comedy", value: raw.endsWith("1") };
  if (raw === "lb:kw:done") return { step: "keywords", choice: "done" };
  if (raw === "lb:search:1" || raw === "lb:search:0") return { step: "search", value: raw.endsWith("1") };
  if (raw === "lb:sk:done") return { step: "search_keywords", choice: "done" };
  if (raw === "lb:span") return { step: "period", choice: "full" };
  if (raw === "lb:rng") return { step: "period", choice: "custom" };
  if (raw === "lb:y:1" || raw === "lb:y:3" || raw === "lb:y:5") {
    return { step: "range_start", preset: Number(raw.slice(5)) };
  }
  match = raw.match(/^lb:yr:(19\d{2}|20\d{2})$/);
  if (match) return { step: "range_start", year: Number(match[1]) };
  if (raw === "lb:full") return { step: "range_start", choice: "full" };
  if (raw === "lb:endfull") return { step: "range_end", choice: "full" };
  if (raw === "lb:und:1" || raw === "lb:und:0") return { step: "undated", value: raw.endsWith("1") };
  return null;
}

function parseModeText(text) {
  const t = normReply(text);
  if (["по умолчанию", "умолчанию", "default", "defaults"].includes(t)) return "defaults";
  if (["настроить", "настройка", "customize", "custom"].includes(t)) return "custom";
  if (["paste settings", "paste", "from summary", "paste summary"].includes(t)) return "paste";
  return "";
}

function parseYesNoText(text) {
  const t = normReply(text);
  if (["да", "yes", "y"].includes(t)) return true;
  if (["нет", "no", "n"].includes(t)) return false;
  return null;
}

function parsePeriodText(text) {
  const t = normReply(text);
  if (["весь период", "весь", "все", "полный", "full", "full period"].includes(t)) return "full";
  if (["свой диапазон", "свой", "диапазон", "custom", "custom range"].includes(t)) return "custom";
  return "";
}

function parsePresetYears(text) {
  const t = normReply(text);
  if (["последний год", "за год", "last year", "1"].includes(t)) return 1;
  if (["последние 3 года", "3 года", "last 3 years", "3"].includes(t)) return 3;
  if (["последние 5 лет", "5 лет", "last 5 years", "5"].includes(t)) return 5;
  return 0;
}

function parseBounded(text, min, max) {
  const t = String(text || "").trim();
  if (!/^\d{1,3}$/.test(t)) return null;
  const n = Number(t);
  if (n < min || n > max) return null;
  return n;
}

function go(state, step, now = new Date()) {
  return { state: { ...state, step }, messages: [promptFor(step, { ...state, step }, now)] };
}

function retry(state, text, now = new Date()) {
  return { state, messages: [withText(state.step, state, text, now)] };
}

function finish(state, patch) {
  const merged = { ...state, ...patch };
  return {
    clear: true,
    dispatch: {
      fileId: merged.fileId,
      options: normalizeLetterboxdOptions(merged),
    },
    messages: [],
  };
}

/**
 * One wizard step. Returns { state, messages, clear?, dispatch?, stale? }.
 * Invalid input stays on the step and does not dispatch.
 */
export function advanceLetterboxdWizard(state, input, now = new Date()) {
  const step = state.step || "zip";
  const kind = input && input.kind;
  if (kind === "callback" && input.step !== step) {
    return { state, messages: [], stale: true };
  }
  if (step === "mode") {
    const choice = kind === "callback" ? input.choice : parseModeText(input.text);
    if (choice === "defaults") return finish(state, defaultLetterboxdOptions());
    if (choice === "custom") return go(state, "top_n", now);
    if (choice === "paste") return go(state, "paste_settings", now);
    return retry(state, 'Need "default", "customize", or "paste settings". The report has not started.');
  }
  if (step === "paste_settings") {
    if (kind === "callback") {
      return retry(state, LETTERBOXD_PASTE_SETTINGS_RETRY, now);
    }
    if (letterboxdSettingsSummaryHasInvalidScale(input.text)) {
      return retry(state, LETTERBOXD_PASTE_SCALE_RETRY, now);
    }
    const parsed = parseLetterboxdSettingsSummary(input.text);
    if (!parsed) return retry(state, LETTERBOXD_PASTE_SETTINGS_RETRY, now);
    return finish(state, parsed);
  }
  if (step === "top_n") {
    const value = kind === "callback" ? input.value : parseBounded(input.text, LETTERBOXD_TOP_N_MIN, LETTERBOXD_TOP_N_MAX);
    if (value == null) return retry(state, "Need a number from 1 to 100. Buttons: 10, 20, 30, 50. The report has not started.");
    return go({ ...state, topN: value }, "scale", now);
  }
  if (step === "scale") {
    const value = kind === "callback"
      ? input.value
      : (() => {
          const n = parseBounded(input.text, 5, 100);
          return n != null && LETTERBOXD_RATING_SCALES.includes(n) ? n : null;
        })();
    if (value == null) return retry(state, "Need 5, 10, or 100. The report has not started.");
    return go({ ...state, ratingScale: value }, "min_rated", now);
  }
  if (step === "min_rated") {
    const value = kind === "callback" ? input.value : parseBounded(input.text, LETTERBOXD_MIN_RATED_MIN, LETTERBOXD_MIN_RATED_MAX);
    if (value == null) return retry(state, "Need a number from 1 to 50. Buttons: 1, 3, 5. The report has not started.");
    return go({ ...state, minRated: value }, "rewatch_avg", now);
  }
  if (step === "rewatch_avg") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    return go({ ...state, includeRewatchInAverages: value }, "show_likes", now);
  }
  if (step === "show_likes") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    return go({ ...state, showLikes: value }, "show_reviews", now);
  }
  if (step === "show_reviews") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    // Top review only when Reviews is on; otherwise force off and skip the question.
    if (!value) {
      return go({ ...state, showReviews: false, showTopReview: false }, "exclusions", now);
    }
    return go({ ...state, showReviews: true }, "show_top_review", now);
  }
  if (step === "show_top_review") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    // Reviews must stay on for Top review; a stray answer with reviews off clears it.
    if (state.showReviews === false) {
      return go({ ...state, showTopReview: false }, "exclusions", now);
    }
    return go({ ...state, showTopReview: value }, "exclusions", now);
  }
  if (step === "exclusions") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    if (!value) {
      // No = keep everything: include toggles stay yes, no custom exclude keywords.
      return go(
        {
          ...state,
          includeUSA: true,
          includeEnglish: true,
          includeDrama: true,
          includeComedy: true,
          excludeKeywords: [],
        },
        "search",
        now,
      );
    }
    return go({ ...state, excludeKeywords: normalizeExcludeKeywords(state.excludeKeywords) }, "usa", now);
  }
  if (step === "usa") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    return go({ ...state, includeUSA: value }, "english", now);
  }
  if (step === "english") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    return go({ ...state, includeEnglish: value }, "drama", now);
  }
  if (step === "drama") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    return go({ ...state, includeDrama: value }, "comedy", now);
  }
  if (step === "comedy") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    return go({ ...state, includeComedy: value, excludeKeywords: normalizeExcludeKeywords(state.excludeKeywords) }, "keywords", now);
  }
  if (step === "keywords") {
    const done =
      (kind === "callback" && input.choice === "done") ||
      (kind === "text" && ["done", "готово", "достаточно"].includes(normReply(input.text)));
    if (done) {
      return go(
        { ...state, excludeKeywords: normalizeExcludeKeywords(state.excludeKeywords) },
        "search",
        now,
      );
    }
    if (kind === "callback") {
      return retry(state, 'Need a keyword, or tap Done. The report has not started.', now);
    }
    const word = String(input.text || "").replace(/\s+/g, " ").trim();
    if (!word) {
      return retry(state, "Send a keyword, or tap Done. The report has not started.", now);
    }
    if (word.length > LETTERBOXD_EXCLUDE_KEYWORD_MAX_LEN) {
      return retry(
        state,
        `Each keyword is at most ${LETTERBOXD_EXCLUDE_KEYWORD_MAX_LEN} characters. Shorten it, or tap Done.`,
        now,
      );
    }
    const current = normalizeExcludeKeywords(state.excludeKeywords);
    if (current.length >= LETTERBOXD_EXCLUDE_KEYWORDS_MAX) {
      return retry(
        state,
        `At most ${LETTERBOXD_EXCLUDE_KEYWORDS_MAX} keywords. Tap Done to continue.`,
        now,
      );
    }
    const next = normalizeExcludeKeywords([...current, word]);
    if (next.length === current.length) {
      return retry(state, "That keyword is already on the list. Send another, or tap Done.", now);
    }
    return go({ ...state, excludeKeywords: next }, "keywords", now);
  }
  if (step === "search") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    if (!value) {
      return go({ ...state, searchKeywords: [] }, "period", now);
    }
    return go({ ...state, searchKeywords: normalizeSearchKeywords(state.searchKeywords) }, "search_keywords", now);
  }
  if (step === "search_keywords") {
    const done =
      (kind === "callback" && input.choice === "done") ||
      (kind === "text" && ["done", "готово", "достаточно"].includes(normReply(input.text)));
    if (done) {
      return go(
        { ...state, searchKeywords: normalizeSearchKeywords(state.searchKeywords) },
        "period",
        now,
      );
    }
    if (kind === "callback") {
      return retry(state, 'Need a search keyword, or tap Done. The report has not started.', now);
    }
    const word = String(input.text || "").replace(/\s+/g, " ").trim();
    if (!word) {
      return retry(state, "Send a search keyword, or tap Done. The report has not started.", now);
    }
    if (word.length > LETTERBOXD_SEARCH_KEYWORD_MAX_LEN) {
      return retry(
        state,
        `Each search keyword is at most ${LETTERBOXD_SEARCH_KEYWORD_MAX_LEN} characters. Shorten it, or tap Done.`,
        now,
      );
    }
    const current = normalizeSearchKeywords(state.searchKeywords);
    if (current.length >= LETTERBOXD_SEARCH_KEYWORDS_MAX) {
      return retry(
        state,
        `At most ${LETTERBOXD_SEARCH_KEYWORDS_MAX} search keywords. Tap Done to continue.`,
        now,
      );
    }
    const next = normalizeSearchKeywords([...current, word]);
    if (next.length === current.length) {
      return retry(state, "That search keyword is already on the list. Send another, or tap Done.", now);
    }
    return go({ ...state, searchKeywords: next }, "search_keywords", now);
  }
  if (step === "period") {
    const choice = kind === "callback" ? input.choice : parsePeriodText(input.text);
    if (choice === "full") {
      return finish(state, { dateFrom: "", dateTo: "", includeUndated: false });
    }
    if (choice === "custom") return go(state, "range_start", now);
    return retry(state, "Need \"full period\" or \"custom range\". The report has not started.");
  }
  if (step === "range_start") {
    const full = kind === "callback" ? input.choice === "full" : parsePeriodText(input.text) === "full";
    if (full) return finish(state, { dateFrom: "", dateTo: "", includeUndated: false });
    if (kind === "callback" && input.year) {
      const year = input.year;
      return go({ ...state, dateFrom: `${year}-01-01`, dateTo: `${year}-12-31` }, "undated", now);
    }
    const preset = kind === "callback" ? input.preset : parsePresetYears(input.text);
    if (preset === 1 || preset === 3 || preset === 5) {
      const range = presetWatchRange(preset, now);
      return go({ ...state, dateFrom: range.dateFrom, dateTo: range.dateTo }, "undated", now);
    }
    if (kind === "callback") return retry(state, "This step is no longer about period buttons. The report has not started.", now);
    const interval = parseWatchInterval(input.text);
    if (!interval) return retry(state, LETTERBOXD_DATE_RETRY, now);
    if (interval.dateTo < interval.dateFrom) {
      return retry(state, `End ${interval.dateTo} is before start ${interval.dateFrom}. Type the period again.`, now);
    }
    return go({ ...state, dateFrom: interval.dateFrom, dateTo: interval.dateTo }, "undated", now);
  }
  if (step === "range_end") {
    if (kind === "callback" && input.choice === "full") {
      return finish(state, { dateFrom: "", dateTo: "", includeUndated: false });
    }
    if (kind === "callback") return retry(state, LETTERBOXD_DATE_RETRY, now);
    const interval = parseWatchInterval(input.text);
    if (!interval) return retry(state, LETTERBOXD_DATE_RETRY);
    if (interval.dateTo < interval.dateFrom) {
      return retry(state, `End ${interval.dateTo} is before start ${interval.dateFrom}. Type the period again.`);
    }
    return go({ ...state, dateFrom: interval.dateFrom, dateTo: interval.dateTo }, "undated", now);
  }
  if (step === "undated") {
    const value = kind === "callback" ? input.value : parseYesNoText(input.text);
    if (value == null) return retry(state, "Need yes or no. The report has not started.");
    return finish(state, { includeUndated: value });
  }
  return { state, messages: [] };
}

export function buildLetterboxdDispatch({ repo, workflow, ref, jobId, chatId, fileId, options }) {
  const id = String(jobId || "").trim();
  const chat = String(chatId ?? "").trim();
  const file = normalizeTelegramFileId(fileId);
  if (!id || id.length > 80) throw new Error("jobId");
  if (!chat || !/^-?[0-9]{1,16}$/.test(chat)) throw new Error("chatId");
  if (!file) throw new Error("fileId");
  const opts = normalizeLetterboxdOptions(options);
  return {
    url: dispatchUrl(repo, workflow || LETTERBOXD_WORKFLOW),
    body: {
      ref: assertRef(ref || DEFAULT_REF),
      inputs: {
        job_id: id,
        chat_id: chat,
        file_id: file,
        top_n: String(opts.topN),
        min_rated: String(opts.minRated),
        include_rewatch_in_averages: opts.includeRewatchInAverages ? "true" : "false",
        show_likes: opts.showLikes ? "true" : "false",
        show_reviews: opts.showReviews ? "true" : "false",
        show_top_review: opts.showTopReview ? "true" : "false",
        rating_scale: String(opts.ratingScale),
        include_usa: opts.includeUSA ? "true" : "false",
        include_english: opts.includeEnglish ? "true" : "false",
        include_drama: opts.includeDrama ? "true" : "false",
        include_comedy: opts.includeComedy ? "true" : "false",
        exclude_keywords: opts.excludeKeywords.join(","),
        search_keywords: opts.searchKeywords.join(","),
        date_from: opts.dateFrom,
        date_to: opts.dateTo,
        include_undated: opts.includeUndated ? "true" : "false",
      },
    },
  };
}

/** @deprecated use buildLetterboxdDispatch */
export const buildGenresDispatch = buildLetterboxdDispatch;

export async function dispatchLetterboxdWorkflow(fetchImpl, { token, repo, workflow, ref, jobId, chatId, fileId, options }) {
  const built = buildLetterboxdDispatch({ repo, workflow, ref, jobId, chatId, fileId, options });
  const res = await fetchImpl(built.url, {
    method: "POST",
    headers: githubHeaders(token),
    body: JSON.stringify(built.body),
  });
  return { ok: res.status === 204, status: res.status };
}

/** @deprecated use dispatchLetterboxdWorkflow */
export const dispatchGenresWorkflow = dispatchLetterboxdWorkflow;

async function readJsonBody(response) {
  if (!response || typeof response.json !== "function") return {};
  try {
    return await response.json();
  } catch {
    return {};
  }
}

export async function findLetterboxdRun(
  fetchImpl,
  { token, repo, workflow, startedAt, sleep, attempts = 5 },
) {
  const headers = githubHeaders(token);
  const listUrl = workflowRunsUrl(repo, workflow || LETTERBOXD_WORKFLOW);
  const since = typeof startedAt === "number" ? startedAt : Date.now();
  for (let attempt = 0; attempt < attempts; attempt++) {
    if (sleep && attempt) await sleep(800);
    const res = await fetchImpl(listUrl, { headers });
    if (res.status !== 200) continue;
    const body = await readJsonBody(res);
    const runs = (body.workflow_runs || []).filter((run) => run && run.html_url);
    const fresh = runs.find((run) => Date.parse(run.created_at) >= since - 20_000);
    if (fresh) return { id: String(fresh.id || ""), url: fresh.html_url };
  }
  return { id: "", url: "" };
}

export async function findLetterboxdRunUrl(fetchImpl, options) {
  const found = await findLetterboxdRun(fetchImpl, options);
  return found.url;
}

/** @deprecated use findLetterboxdRunUrl */
export const findGenresRunUrl = findLetterboxdRunUrl;

export { DEFAULT_REF, DEFAULT_REPO };
