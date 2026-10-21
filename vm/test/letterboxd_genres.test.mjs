import assert from "node:assert/strict";
import test from "node:test";
import {
  advanceLetterboxdWizard,
  buildLetterboxdDispatch,
  decodeAwaitLetterboxd,
  encodeAwaitLetterboxd,
  isZipDocument,
  letterboxdAckText,
  normalizeTelegramFileId,
  letterboxdMinKeyboard,
  letterboxdModeKeyboard,
  letterboxdModePrompt,
  letterboxdPeriodKeyboard,
  letterboxdTopKeyboard,
  letterboxdKeywordsKeyboard,
  letterboxdSearchKeywordsKeyboard,
  letterboxdUndatedKeyboard,
  letterboxdYesNoKeyboard,
  parseLetterboxdCallback,
  parseLetterboxdCommand,
  parseStartCommand,
  parseWatchBound,
  parseWatchInterval,
} from "../letterboxd_genres.js";
import {
  GENRE_PNGS,
  buildCalendarReportHtml,
  buildGenreReportHtml,
  buildGenreReportMessages,
  buildSearchKeywordMessages,
  buildAllSearchKeywordMessages,
  calendarCaptions,
  calendarReadyText,
  escapeHtml,
  formatTelegramError,
  mapScriptError,
  telegramFetch,
  unmatchedFromWorkdir,
} from "../../scripts/letterboxd_genres_run.mjs";
import { mkdtempSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

test("parseLetterboxdCommand", () => {
  assert.equal(parseLetterboxdCommand("/start"), null);
  assert.equal(parseLetterboxdCommand("/genres"), null);
  assert.deepEqual(parseLetterboxdCommand("/letterboxd"), { ok: true });
  assert.deepEqual(parseLetterboxdCommand("/letterboxd@tg2tmbot"), { ok: true });
  assert.deepEqual(parseLetterboxdCommand("/letterboxd extra"), { error: "usage" });
  assert.deepEqual(parseStartCommand("/start"), { ok: true });
  assert.deepEqual(parseStartCommand("/start@lebxdbot"), { ok: true });
  assert.deepEqual(parseStartCommand("/start letterboxd"), { ok: true });
  assert.deepEqual(parseStartCommand("/start other"), { error: "usage" });
  assert.equal(parseStartCommand("/letterboxd"), null);
});

test("await letterboxd encode/decode", () => {
  const raw = encodeAwaitLetterboxd({ since: "2026-10-17T00:00:00.000Z" });
  const decoded = decodeAwaitLetterboxd(raw);
  assert.equal(decoded.kind, "letterboxd");
  assert.equal(decoded.since, "2026-10-17T00:00:00.000Z");
  assert.equal(decoded.step, "zip");
  assert.equal(decodeAwaitLetterboxd('{"kind":"genres","since":"x"}').step, "zip");
  assert.equal(decodeAwaitLetterboxd(""), null);
  assert.equal(decodeAwaitLetterboxd('{"step":"name"}'), null);
});

test("watch bounds are month-before-year; one value is the whole interval", () => {
  assert.equal(parseWatchBound("2012", "start"), "2012-01-01");
  assert.equal(parseWatchBound("2012", "end"), "2012-12-31");
  assert.equal(parseWatchBound("06-2012", "start"), "2012-06-01");
  assert.equal(parseWatchBound("06-2012", "end"), "2012-06-30");
  assert.equal(parseWatchBound("06.2012", "end"), "2012-06-30");
  assert.equal(parseWatchBound("15-06-2012", "start"), "2012-06-15");
  assert.equal(parseWatchBound("15.06.2012", "end"), "2012-06-15");
  assert.equal(parseWatchBound("2012-06", "start"), "");
  assert.equal(parseWatchBound("2012-06-15", "start"), "");
  assert.deepEqual(parseWatchInterval("2012"), { dateFrom: "2012-01-01", dateTo: "2012-12-31" });
  assert.deepEqual(parseWatchInterval("06-2012"), { dateFrom: "2012-06-01", dateTo: "2012-06-30" });
  assert.deepEqual(parseWatchInterval("15-06-2012"), { dateFrom: "2012-06-15", dateTo: "2012-06-15" });
  assert.deepEqual(parseWatchInterval("2018 2020"), { dateFrom: "2018-01-01", dateTo: "2020-12-31" });
  assert.deepEqual(parseWatchInterval("01-2019 06-2019"), { dateFrom: "2019-01-01", dateTo: "2019-06-30" });
  assert.deepEqual(parseWatchInterval("15-01-2019-31-03-2019"), {
    dateFrom: "2019-01-15",
    dateTo: "2019-03-31",
  });
  assert.deepEqual(parseWatchInterval("15.01.2019-31.03.2019"), {
    dateFrom: "2019-01-15",
    dateTo: "2019-03-31",
  });
  assert.deepEqual(parseWatchInterval("06.2012"), { dateFrom: "2012-06-01", dateTo: "2012-06-30" });
  assert.deepEqual(parseWatchInterval("март 2012"), { dateFrom: "2012-03-01", dateTo: "2012-03-31" });
  assert.deepEqual(parseWatchInterval("March 2012"), { dateFrom: "2012-03-01", dateTo: "2012-03-31" });
  assert.equal(parseWatchInterval("2012-06"), null);
  assert.equal(parseWatchInterval("2012-06-15"), null);
  assert.equal(parseWatchInterval("2021.06"), null);
  assert.deepEqual(parseWatchInterval("2021-06.2022"), { dateFrom: "2021-01-01", dateTo: "2022-06-30" });
  assert.deepEqual(parseWatchInterval("06.2021-2022"), { dateFrom: "2021-06-01", dateTo: "2022-12-31" });
  assert.deepEqual(parseWatchInterval("15.06.2021 - 20.08.2022"), {
    dateFrom: "2021-06-15",
    dateTo: "2022-08-20",
  });
});

test("one typed period skips the second bound and asks about undated films", () => {
  const state = {
    step: "range_start",
    fileId: "BQACAgIAAxkBAAI1234567890",
    topN: 20,
    minRated: 3,
    includeUSA: true,
    includeEnglish: true,
    includeDrama: true,
    includeComedy: true,
  };
  const next = advanceLetterboxdWizard(state, { kind: "text", text: "2019" });
  assert.equal(next.state.step, "undated");
  assert.equal(next.state.dateFrom, "2019-01-01");
  assert.equal(next.state.dateTo, "2019-12-31");
  assert.equal(next.dispatch, undefined);
  const bad = advanceLetterboxdWizard(state, { kind: "text", text: "2012-06" });
  assert.equal(bad.state.step, "range_start");
  assert.equal(bad.dispatch, undefined);
  assert.match(bad.messages[0].text, /06-2012/);
  const backwards = advanceLetterboxdWizard(state, { kind: "text", text: "2020 2018" });
  assert.equal(backwards.state.step, "range_start");
  assert.equal(backwards.dispatch, undefined);
});

test("top size is any integer from 1 to 100", () => {
  const state = { step: "top_n", fileId: "BQACAgIAAxkBAAI1234567890" };
  const hundred = advanceLetterboxdWizard(state, { kind: "text", text: "100" });
  assert.equal(hundred.state.step, "min_rated");
  assert.equal(hundred.state.topN, 100);
  const one = advanceLetterboxdWizard(state, { kind: "text", text: "1" });
  assert.equal(one.state.topN, 1);
  const fifty = advanceLetterboxdWizard(state, { kind: "callback", step: "top_n", value: 50 });
  assert.equal(fifty.state.topN, 50);
  assert.equal(parseLetterboxdCallback("lb:n:50").value, 50);
  const bad = advanceLetterboxdWizard(state, { kind: "text", text: "9999" });
  assert.equal(bad.state.step, "top_n");
  assert.equal(bad.dispatch, undefined);
  assert.match(bad.messages[0].text, /from 1 to 100/);
  const zero = advanceLetterboxdWizard(state, { kind: "text", text: "0" });
  assert.equal(zero.state.step, "top_n");
  assert.match(zero.messages[0].text, /from 1 to 100/);
});

test("wizard prompts are html, with a default line and examples", () => {
  const mode = letterboxdModePrompt();
  assert.match(mode.text, /<b>How should the charts be built\?<\/b>/);
  assert.match(mode.text, /Default builds the usual set/);
  assert.match(mode.text, /Buttons below, or reply with text/);
  assert.doesNotMatch(mode.text, /For example:/);
  assert.doesNotMatch(mode.text, /Default: default/);
  assert.equal(mode.reply_markup.inline_keyboard[0][0].callback_data, "lb:def");
  assert.equal(mode.reply_markup.inline_keyboard[0][1].callback_data, "lb:cus");
  const now = new Date("2026-10-20T00:00:00Z");
  const range = advanceLetterboxdWizard(
    { step: "period", fileId: "BQACAgIAAxkBAAI1234567890" },
    { kind: "callback", step: "period", choice: "custom" },
    now,
  );
  assert.match(range.messages[0].text, /<b>Which period\?<\/b>/);
  assert.match(range.messages[0].text, /2021-06\.2022/);
  assert.match(range.messages[0].text, /15\.06\.2021 - 20\.08\.2022/);
  assert.match(range.messages[0].text, /Default: full period/);
  const labels = range.messages[0].reply_markup.inline_keyboard.flat().map((button) => button.text);
  assert.deepEqual(labels, [
    "2026",
    "2025",
    "2024",
    "2023",
    "2022",
    "Last 3 years",
    "Last 5 years",
    "Default: full period",
  ]);
  const top = advanceLetterboxdWizard(
    { step: "top_n", fileId: "BQACAgIAAxkBAAI1234567890" },
    { kind: "callback", step: "top_n", value: 20 },
    now,
  );
  assert.equal(top.state.topN, 20);
  assert.equal(top.state.step, "min_rated");
  assert.equal(top.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "✅ Default (3)");
  const minText = top.messages[0].text;
  assert.match(minText, /<b>Threshold<\/b>/);
  assert.match(minText, /unique rated films/);
  assert.match(minText, /a director with two rated films is left out/);
  assert.match(minText, /Director, actor, and studio watch-count charts/);
  assert.match(minText, /diary hits/);
  assert.doesNotMatch(minText, /Watch-count charts ignore this threshold/);
  assert.doesNotMatch(minText, /minimum ratings/i);
  assert.match(minText, /For example: 3, 5, 10/);
  assert.match(minText, /Default: 3/);
  const year = advanceLetterboxdWizard(
    range.state,
    { kind: "callback", step: "range_start", year: 2024 },
    now,
  );
  assert.equal(year.state.step, "undated");
  assert.equal(year.state.dateFrom, "2024-01-01");
  assert.equal(year.state.dateTo, "2024-12-31");
  assert.equal(year.dispatch, undefined);
  const trailing = advanceLetterboxdWizard(
    range.state,
    { kind: "callback", step: "range_start", preset: 3 },
    now,
  );
  assert.equal(trailing.state.dateFrom, "2023-10-20");
  assert.equal(trailing.state.dateTo, "2026-10-20");
  const full = advanceLetterboxdWizard(
    range.state,
    { kind: "callback", step: "range_start", choice: "full" },
    now,
  );
  assert.equal(full.dispatch.options.dateFrom, "");
  assert.equal(full.dispatch.options.dateTo, "");
});

test("binary steps keep the default button and drop the repeated lines", () => {
  const fileId = "BQACAgIAAxkBAAI1234567890";
  const rewatch = advanceLetterboxdWizard(
    { step: "min_rated", fileId },
    { kind: "callback", step: "min_rated", value: 3 },
  );
  const exclusions = advanceLetterboxdWizard(
    rewatch.state,
    { kind: "callback", step: "rewatch_avg", value: false },
  );
  const usa = advanceLetterboxdWizard(
    exclusions.state,
    { kind: "callback", step: "exclusions", value: true },
  );
  const english = advanceLetterboxdWizard(usa.state, { kind: "callback", step: "usa", value: true });
  const drama = advanceLetterboxdWizard(english.state, { kind: "callback", step: "english", value: true });
  const comedy = advanceLetterboxdWizard(drama.state, { kind: "callback", step: "drama", value: true });
  const keywords = advanceLetterboxdWizard(comedy.state, { kind: "callback", step: "comedy", value: true });
  const search = advanceLetterboxdWizard(
    keywords.state,
    { kind: "callback", step: "keywords", choice: "done" },
  );
  const period = advanceLetterboxdWizard(
    search.state,
    { kind: "callback", step: "search", value: false },
  );
  const skip = advanceLetterboxdWizard(
    { step: "exclusions", fileId, minRated: 3, includeRewatchInAverages: false },
    { kind: "callback", step: "exclusions", value: false },
  );
  const undated = advanceLetterboxdWizard(
    { step: "range_start", fileId, dateFrom: "2024-01-01", dateTo: "2024-12-31" },
    { kind: "callback", step: "range_start", year: 2024 },
  );
  for (const message of [rewatch, exclusions, usa, english, drama, comedy, search, period, skip, undated]) {
    assert.doesNotMatch(message.messages[0].text, /For example:/);
    assert.doesNotMatch(message.messages[0].text, /Default:/);
  }
  assert.equal(rewatch.state.step, "rewatch_avg");
  assert.match(rewatch.messages[0].text, /<b>Count previous watches in averages\?<\/b>/);
  assert.match(rewatch.messages[0].text, /Most often in the diary always counts rewatches/);
  assert.match(rewatch.messages[0].text, /clutter the statistics/);
  assert.equal(exclusions.state.includeRewatchInAverages, false);
  assert.match(exclusions.messages[0].text, /<b>Remove some rows from the watch-count tops\?<\/b>/);
  assert.match(usa.messages[0].text, /<b>Show USA in the country top\?<\/b>/);
  assert.match(english.messages[0].text, /<b>Show English in the language top\?<\/b>/);
  assert.match(drama.messages[0].text, /<b>Show Drama in the genre tops\?<\/b>/);
  assert.match(comedy.messages[0].text, /<b>Show Comedy in the genre tops\?<\/b>/);
  assert.match(keywords.messages[0].text, /<b>Exclude keywords from watch-count tops\?<\/b>/);
  assert.match(search.messages[0].text, /<b>Add search keywords\?<\/b>/);
  assert.match(period.messages[0].text, /<b>Full period or a custom range\?<\/b>/);
  assert.equal(skip.state.step, "search");
  assert.equal(skip.state.includeUSA, true);
  assert.equal(skip.state.includeEnglish, true);
  assert.equal(skip.state.includeDrama, true);
  assert.equal(skip.state.includeComedy, true);
  assert.deepEqual(skip.state.excludeKeywords, []);
  assert.match(undated.messages[0].text, /<b>Add films with no diary date\?<\/b>/);
  assert.equal(rewatch.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "Default: no");
  assert.equal(exclusions.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "Default: no");
  assert.equal(usa.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "Default: yes");
  assert.equal(english.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "Default: yes");
  assert.equal(drama.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "Default: yes");
  assert.equal(comedy.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "Default: yes");
  assert.equal(search.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "Default: no");
  assert.equal(period.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "Default: full period");
  assert.equal(undated.messages[0].reply_markup.inline_keyboard.at(-1)[0].text, "Default: no");
  assert.match(period.messages[0].text, /Full period runs from the first watch/);
  assert.equal(parseLetterboxdCallback("lb:rew:0").step, "rewatch_avg");
  assert.equal(parseLetterboxdCallback("lb:rew:0").value, false);
  assert.equal(parseLetterboxdCallback("lb:rew:1").value, true);
  assert.equal(parseLetterboxdCallback("lb:excl:0").step, "exclusions");
  assert.equal(parseLetterboxdCallback("lb:excl:0").value, false);
  assert.equal(parseLetterboxdCallback("lb:drama:0").step, "drama");
  assert.equal(parseLetterboxdCallback("lb:drama:0").value, false);
  assert.equal(parseLetterboxdCallback("lb:com:1").step, "comedy");
  assert.equal(parseLetterboxdCallback("lb:com:1").value, true);
  assert.equal(parseLetterboxdCallback("lb:kw:done").step, "keywords");
  assert.equal(parseLetterboxdCallback("lb:search:0").step, "search");
  assert.equal(parseLetterboxdCallback("lb:search:0").value, false);
  assert.equal(parseLetterboxdCallback("lb:sk:done").step, "search_keywords");
});

test("keyword step accumulates words until Done", () => {
  const fileId = "BQACAgIAAxkBAAI1234567890";
  const start = { step: "keywords", fileId, excludeKeywords: [] };
  const first = advanceLetterboxdWizard(start, { kind: "text", text: "Elijah Wood" });
  assert.equal(first.state.step, "keywords");
  assert.deepEqual(first.state.excludeKeywords, ["Elijah Wood"]);
  assert.match(first.messages[0].text, /Already added \(1\/20\): Elijah Wood/);
  const second = advanceLetterboxdWizard(first.state, { kind: "text", text: "2001" });
  assert.deepEqual(second.state.excludeKeywords, ["Elijah Wood", "2001"]);
  const done = advanceLetterboxdWizard(second.state, { kind: "callback", step: "keywords", choice: "done" });
  assert.equal(done.state.step, "search");
  assert.deepEqual(done.state.excludeKeywords, ["Elijah Wood", "2001"]);
});

test("search keyword step accumulates words until Done", () => {
  const fileId = "BQACAgIAAxkBAAI1234567890";
  const gate = advanceLetterboxdWizard(
    { step: "search", fileId, searchKeywords: [] },
    { kind: "callback", step: "search", value: true },
  );
  assert.equal(gate.state.step, "search_keywords");
  assert.match(gate.messages[0].text, /<b>Search keywords for film lists\?<\/b>/);
  const first = advanceLetterboxdWizard(gate.state, { kind: "text", text: "Elijah Wood" });
  assert.equal(first.state.step, "search_keywords");
  assert.deepEqual(first.state.searchKeywords, ["Elijah Wood"]);
  assert.match(first.messages[0].text, /Already added \(1\/20\): Elijah Wood/);
  const second = advanceLetterboxdWizard(first.state, { kind: "text", text: "2001" });
  assert.deepEqual(second.state.searchKeywords, ["Elijah Wood", "2001"]);
  const done = advanceLetterboxdWizard(
    second.state,
    { kind: "callback", step: "search_keywords", choice: "done" },
  );
  assert.equal(done.state.step, "period");
  assert.deepEqual(done.state.searchKeywords, ["Elijah Wood", "2001"]);
  const skip = advanceLetterboxdWizard(
    { step: "search", fileId },
    { kind: "callback", step: "search", value: false },
  );
  assert.equal(skip.state.step, "period");
  assert.deepEqual(skip.state.searchKeywords, []);
});

test("every wizard keyboard has a one-tap default button", () => {
  const last = (keyboard) => keyboard.inline_keyboard.at(-1)[0].text;
  assert.equal(letterboxdModeKeyboard().inline_keyboard[0][0].text, "✅ Default");
  assert.equal(last(letterboxdTopKeyboard()), "✅ Default (20)");
  assert.equal(last(letterboxdMinKeyboard()), "✅ Default (3)");
  assert.equal(last(letterboxdYesNoKeyboard("lb:rew", "no")), "Default: no");
  assert.equal(last(letterboxdYesNoKeyboard("lb:excl", "no")), "Default: no");
  assert.equal(last(letterboxdYesNoKeyboard("lb:usa")), "Default: yes");
  assert.equal(last(letterboxdYesNoKeyboard("lb:en")), "Default: yes");
  assert.equal(last(letterboxdYesNoKeyboard("lb:drama")), "Default: yes");
  assert.equal(last(letterboxdYesNoKeyboard("lb:com")), "Default: yes");
  assert.equal(last(letterboxdKeywordsKeyboard(false)), "Default: none");
  assert.equal(letterboxdKeywordsKeyboard(true).inline_keyboard[0][0].text, "Done");
  assert.equal(last(letterboxdYesNoKeyboard("lb:search", "no")), "Default: no");
  assert.equal(last(letterboxdSearchKeywordsKeyboard(false)), "Default: none");
  assert.equal(letterboxdSearchKeywordsKeyboard(true).inline_keyboard[0][0].text, "Done");
  assert.equal(last(letterboxdPeriodKeyboard()), "Default: full period");
  assert.equal(last(letterboxdUndatedKeyboard()), "Default: no");
  assert.equal(last(letterboxdYesNoKeyboard("lb:und", "нет")), "Default: no");
});

test("isZipDocument and file_id", () => {
  assert.equal(isZipDocument({ file_name: "export.zip", mime_type: "application/octet-stream" }), true);
  assert.equal(isZipDocument({ file_name: "diary.csv" }), false);
  assert.equal(isZipDocument({ mime_type: "application/zip" }), true);
  assert.equal(normalizeTelegramFileId("BQACAgIAAxkBAAI"), "BQACAgIAAxkBAAI");
  assert.equal(normalizeTelegramFileId("../x"), "");
});

test("ack summary lists rewatch averages USA English Drama Comedy exclude and search keywords", () => {
  const text = letterboxdAckText("lb-1", {
    topN: 20,
    minRated: 3,
    includeRewatchInAverages: true,
    includeUSA: true,
    includeEnglish: false,
    includeDrama: false,
    includeComedy: true,
    excludeKeywords: ["Wood", "2001"],
    searchKeywords: ["Elijah Wood"],
  });
  assert.match(text, /Rewatches in averages: yes/);
  assert.match(text, /USA: yes/);
  assert.match(text, /English: no/);
  assert.match(text, /Drama: no/);
  assert.match(text, /Comedy: yes/);
  assert.match(text, /Keyword exclusions: "Wood", "2001"/);
  assert.match(text, /Search keywords: "Elijah Wood"/);
  const defaults = letterboxdAckText("lb-2", {});
  assert.match(defaults, /Rewatches in averages: no/);
});

test("genre PNG send order puts watches before rating before decade before watch year", () => {
  const genreOnly = [
    "watches_by_genre.png",
    "average_rating_by_genre.png",
    "worst_average_rating_by_genre.png",
    "genre_by_release_decade.png",
    "genre_counts_by_viewing_year.png",
  ];
  assert.deepEqual(GENRE_PNGS.slice(0, genreOnly.length), genreOnly);
  assert.ok(GENRE_PNGS.indexOf("watches_by_genre.png") < GENRE_PNGS.indexOf("average_rating_by_genre.png"));
  assert.ok(
    GENRE_PNGS.indexOf("average_rating_by_genre.png") < GENRE_PNGS.indexOf("genre_by_release_decade.png"),
  );
  assert.ok(
    GENRE_PNGS.indexOf("genre_by_release_decade.png") < GENRE_PNGS.indexOf("genre_counts_by_viewing_year.png"),
  );
});

test("buildLetterboxdDispatch", () => {
  const built = buildLetterboxdDispatch({
    repo: "pretendless/Telegram2Telemost",
    workflow: "letterboxd.yml",
    ref: "main",
    jobId: "lb-1",
    chatId: "7",
    fileId: "BQACAgIAAxkBAAI1234567890",
  });
  assert.equal(
    built.url,
    "https://api.github.com/repos/pretendless/Telegram2Telemost/actions/workflows/letterboxd.yml/dispatches",
  );
  assert.deepEqual(built.body, {
    ref: "main",
    inputs: {
      job_id: "lb-1",
      chat_id: "7",
      file_id: "BQACAgIAAxkBAAI1234567890",
      top_n: "20",
      min_rated: "3",
      include_rewatch_in_averages: "false",
      include_usa: "true",
      include_english: "true",
      include_drama: "true",
      include_comedy: "true",
      exclude_keywords: "",
      search_keywords: "",
      date_from: "",
      date_to: "",
      include_undated: "false",
    },
  });
  const withSearch = buildLetterboxdDispatch({
    repo: "pretendless/Telegram2Telemost",
    workflow: "letterboxd.yml",
    ref: "main",
    jobId: "lb-2",
    chatId: "7",
    fileId: "BQACAgIAAxkBAAI1234567890",
    options: { searchKeywords: ["Elijah Wood", "2001"] },
  });
  assert.equal(withSearch.body.inputs.search_keywords, "Elijah Wood,2001");
});

test("search keyword HTML lists sections by match site with watch ratings", () => {
  const chunks = buildSearchKeywordMessages("Elijah Wood", [
    {
      name: "The Lord of the Rings: The Fellowship of the Ring",
      year: 2001,
      matched: ["actor"],
      ratings: ["5"],
    },
    {
      name: "Eternal Sunshine of the Spotless Mind",
      year: 2004,
      matched: ["actor", "genre"],
      ratings: ["5", "—"],
    },
  ]);
  assert.equal(chunks.length, 1);
  assert.match(chunks[0], /<b>Search keyword: Elijah Wood<\/b>/);
  assert.match(chunks[0], /2 films/);
  // Sections in fixed order; genre before actor. Eternal appears under both.
  assert.match(
    chunks[0],
    /<b>genre<\/b>\n1\. Eternal Sunshine of the Spotless Mind \(2004\): 5, —/,
  );
  assert.match(
    chunks[0],
    /<b>actor<\/b>\n1\. The Lord of the Rings: The Fellowship of the Ring \(2001\): 5\n2\. Eternal Sunshine of the Spotless Mind \(2004\): 5, —/,
  );
  // No inline match-site parentheses on film lines.
  assert.doesNotMatch(chunks[0], /\(2001\) \(actor\)/);
  assert.doesNotMatch(chunks[0], /\(2004\) \(actor/);
  // Empty sites (director, …) omitted.
  assert.doesNotMatch(chunks[0], /<b>director<\/b>/);
  assert.deepEqual(buildAllSearchKeywordMessages({ search_keywords: [] }), []);
  assert.match(
    buildSearchKeywordMessages("Nobody", [])[0],
    /No films matched in this catalog/,
  );
});

test("mapScriptError covers diary and bearer", () => {
  assert.match(mapScriptError("TMDB_BEARER_TOKEN is not set", "", 2), /TMDB_BEARER_TOKEN/);
  assert.match(mapScriptError("diary.csv was not found in the ZIP.", "", 1), /diary\.csv/);
  assert.match(
    mapScriptError("No diary entries with a watch date in the selected range.", "", 2),
    /selected range/,
  );
  assert.match(mapScriptError("diary.csv has no Watched Date column.", "", 1), /Watched Date/);
  assert.match(mapScriptError("diary.csv is missing columns: Name", "", 1), /missing columns/);
});

test("calendar captions name the watch-time grain", () => {
  const days = calendarCaptions({ watch_time_grain: "day" });
  assert.equal(days["views_by_year.png"], "Film watches by day");
  assert.equal(days["average_rating_by_year.png"], "Average rating by day");
  assert.equal(days["viewing_pace.png"], "Viewing pace by day");
  const months = calendarCaptions({ watch_time_grain: "month" });
  assert.equal(months["views_by_year.png"], "Film watches by month");
  assert.equal(months["viewing_pace.png"], "Viewing pace by month");
  const years = calendarCaptions({});
  assert.equal(years["views_by_year.png"], "Film watches by year");
  assert.equal(years["viewing_pace.png"], "Viewing pace by month");
});

test("formatTelegramError expands cause chain", () => {
  const cause = new Error("connect ECONNRESET");
  cause.code = "ECONNRESET";
  cause.syscall = "connect";
  cause.address = "1.2.3.4";
  const err = new Error("fetch failed");
  err.cause = cause;
  const text = formatTelegramError(err);
  assert.match(text, /fetch failed/);
  assert.match(text, /ECONNRESET/);
  assert.match(text, /cause:/);
});

test("telegramFetch is one-shot and labels failures", async () => {
  let calls = 0;
  const previous = globalThis.fetch;
  globalThis.fetch = async () => {
    calls += 1;
    throw new Error("fetch failed");
  };
  try {
    await assert.rejects(
      () =>
        telegramFetch("https://example.test/bot", { method: "POST" }, { label: "genre HTML part 1/2" }),
      (err) => {
        assert.match(String(err.message), /genre HTML part 1\/2/);
        assert.match(String(err.message), /fetch failed/);
        return true;
      },
    );
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = previous;
  }
});

test("unmatchedFromWorkdir reads csv", () => {
  const dir = mkdtempSync(join(tmpdir(), "lb-test-"));
  writeFileSync(join(dir, "tmdb_unmatched.csv"), "Name,Year\nA,2020\nB,2021\n");
  assert.equal(unmatchedFromWorkdir(dir), 2);
});

test("calendarReadyText announces TMDB details phase", () => {
  assert.match(calendarReadyText(), /Calendar charts are ready/);
  assert.match(calendarReadyText(), /TMDB/);
  assert.match(calendarReadyText(), /directors/);
});

test("escapeHtml for film titles", () => {
  assert.equal(escapeHtml('A & B <C> "D"'), "A &amp; B &lt;C&gt; \"D\"");
});

test("buildCalendarReportHtml keeps blurb, drops charted tops", () => {
  const html = buildCalendarReportHtml({
    entries: 100,
    unique_films: 80,
    year_min: 2020,
    year_max: 2024,
    peak_day: "2021-03-15",
    peak_day_label: "15 March 2021",
    peak_day_count: 7,
    peak_year: 2023,
    peak_year_count: 40,
    favorite_weekday: "Sat",
    favorite_weekday_count: 20,
    favorite_month: "Oct",
    favorite_month_count: 15,
    films_per_month: 4.2,
    rated_count: 70,
    rated_share: 0.7,
    rating_avg: 3.75,
    rating_mode: 4,
    rating_mode_count: 25,
    top_rewatches: [{ name: "Heat & Dust", year: 1995, count: 3 }],
    top_rated_release_years: [{ year: 1999, avg: 4.5, films: 8, rated: 8 }],
    top_release_years_by_count: [{ year: 2019, count: 22 }],
  });
  assert.match(html, /<b>Letterboxd<\/b>/);
  assert.match(html, /<b>100<\/b>/);
  assert.match(html, /Most watches in one day: <b>15 March 2021<\/b> \(<b>7<\/b>\)/);
  assert.match(html, /Pace: <b>4\.2<\/b> films per month on average/);
  assert.match(html, /average <b>3\.75<\/b>/);
  assert.doesNotMatch(html, /Heat/);
  assert.doesNotMatch(html, /Release years/);
  assert.doesNotMatch(html, /Most often in the diary/);
  assert.doesNotMatch(html, /parse_mode/);
});

test("buildGenreReportHtml is short blurb without ranked lists", () => {
  const html = buildGenreReportHtml(
    {
      unique_titles: 100,
      resolved: 98,
      top_genres: [
        { name: "Drama", count: 50, pct: 20.5 },
        { name: "Comedy <x>", count: 10, pct: 4.1 },
      ],
      unmatched: 2,
    },
    9,
  );
  assert.match(html, /Letterboxd · TMDB/);
  assert.match(html, /Enriched/);
  assert.match(html, /<b>2<\/b>/);
  assert.doesNotMatch(html, /Comedy/);
  assert.doesNotMatch(html, /Genres — higher rating/);
});

test("buildGenreReportMessages drops people/country bullet tops", () => {
  const msgs = buildGenreReportMessages({
    unique_titles: 50,
    resolved: 48,
    top_genres: [{ name: "Drama", count: 50, pct: 20 }],
    top_genres_by_rating: [{ name: "Drama", count: 50, avg: 4.1, rated: 40 }],
    unmatched: 1,
    countries: [{ name: "United States of America", count: 40, avg: 3.8 }],
    countries_by_rating: [{ name: "France", count: 10, avg: 4.5, rated: 8 }],
    directors: [{ name: "Nolan & Co", count: 5, avg: 4.2 }],
    directors_by_rating: [{ name: "Nolan & Co", count: 5, avg: 4.2, rated: 5 }],
    actors: [{ name: "Actor <X>", count: 4, avg: 3.5 }],
    actors_by_rating: [],
    languages: [{ name: "en", count: 30 }],
    languages_by_rating: [{ name: "en", count: 30, avg: 3.9, rated: 20 }],
    companies: [{ name: "A24", count: 6, avg: 4.0 }],
    companies_by_rating: [{ name: "A24", count: 6, avg: 4.0, rated: 6 }],
    min_person_count: 3,
  });
  assert.equal(msgs.length, 1);
  assert.match(msgs[0], /Letterboxd · TMDB/);
  assert.match(msgs[0], /charts/);
  assert.doesNotMatch(msgs[0], /Nolan/);
  assert.doesNotMatch(msgs[0], /Countries — higher rating/);
  assert.doesNotMatch(msgs[0], /Actors/);
  assert.doesNotMatch(msgs[0], /Studios/);
});
