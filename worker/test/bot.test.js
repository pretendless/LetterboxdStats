import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { ABOUT, BOT_COMMANDS, DESCRIPTION } from "../bot_profile.mjs";
import { handle, tg2tmEnv } from "../src/index.js";
import {
  loginChatIds,
  notifyLoginChatsOfUpload,
  uploadZipCaption,
} from "../src/letterboxd.js";
import { letterboxdActiveKey, letterboxdPromptText } from "../../vm/letterboxd_genres.js";

function memoryKv() {
  const store = new Map();
  return {
    store,
    async get(key) {
      return store.has(key) ? store.get(key) : null;
    },
    async put(key, value) {
      store.set(key, value);
    },
    async delete(key) {
      store.delete(key);
    },
  };
}

function envWith() {
  return {
    BOT_KV: memoryKv(),
    WEBHOOK_SECRET: "webhook-secret",
    LEBXDBOT_TOKEN: "bot-token",
    GHLEBXD_DISPATCH_TOKEN: "dispatch-token",
    TG2TM_TOKEN: "tg2tm-token",
    GHTG2TM_DISPATCH_TOKEN: "tg2tm-dispatch",
    GH_REPO: "pretendless/LetterboxdStats",
  };
}

function telegramRequest(chatId, text) {
  return new Request("https://t2t-box.example/lebxd", {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": "webhook-secret", "content-type": "application/json" },
    body: JSON.stringify({ message: { chat: { id: chatId }, text } }),
  });
}

function documentRequest(chatId, document, from) {
  const message = { chat: { id: chatId }, document };
  if (from) message.from = from;
  return new Request("https://t2t-box.example/lebxd", {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": "webhook-secret", "content-type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

function callbackRequest(chatId, data, id = "cb-1") {
  return new Request("https://t2t-box.example/lebxd", {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": "webhook-secret", "content-type": "application/json" },
    body: JSON.stringify({
      callback_query: {
        id,
        data,
        message: { message_id: 42, chat: { id: chatId } },
      },
    }),
  });
}

const ZIP = {
  file_name: "letterboxd-2026.zip",
  mime_type: "application/zip",
  file_id: "BQACAgIAAxkBAAI1234567890abcd",
};

function githubFetch(calls, { runId = 99, createdAt = new Date().toISOString() } = {}) {
  return async (url, init = {}) => {
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push({ url: String(url), method: init.method || "GET", body });
    if (String(url).endsWith("/cancel")) return new Response(null, { status: 202 });
    if (String(url).includes("/workflows/") && String(url).includes("/runs")) {
      return {
        status: 200,
        json: async () => ({
          workflow_runs: [
            {
              id: runId,
              created_at: createdAt,
              html_url: `https://github.com/pretendless/LetterboxdStats/actions/runs/${runId}`,
            },
          ],
        }),
      };
    }
    return new Response(null, { status: 204 });
  };
}

test("webhook rejects a missing secret and serves health", async () => {
  const env = envWith();
  const denied = await handle(
    new Request("https://t2t-box.example/lebxd", { method: "POST", body: "{}" }),
    env,
    {},
  );
  assert.equal(denied.status, 401);
  const health = await handle(new Request("https://t2t-box.example/health"), env, {});
  assert.equal(health.status, 200);
});

test("/start asks for a ZIP and /letterboxd does not", async () => {
  const env = envWith();
  const sent = [];
  const sendMessage = async (_env, chatId, text) => {
    sent.push({ chatId, text });
    return { message_id: sent.length };
  };
  await handle(telegramRequest(7, "/start"), env, { sendMessage });
  assert.match(sent[0].text, /Letterboxd export ZIP/);
  assert.ok(env.BOT_KV.store.get("lebxd:await:7"));

  sent.length = 0;
  await handle(telegramRequest(7, "/start letterboxd"), env, { sendMessage });
  assert.match(sent[0].text, /Letterboxd export ZIP/);

  sent.length = 0;
  await handle(telegramRequest(7, "/start other"), env, { sendMessage });
  assert.match(sent[0].text, /\/start letterboxd/);

  sent.length = 0;
  await handle(telegramRequest(8, "/letterboxd"), env, { sendMessage });
  assert.equal(sent.length, 0);
  assert.equal(env.BOT_KV.store.get("lebxd:await:8"), undefined);
});

test("/stop clears the wizard and says when there is nothing to cancel", async () => {
  const env = envWith();
  const sent = [];
  const sendMessage = async (_env, chatId, text) => {
    sent.push({ chatId, text });
    return { message_id: sent.length };
  };
  await handle(telegramRequest(7, "/start"), env, { sendMessage });
  await handle(
    documentRequest(7, { file_name: "notes.txt", mime_type: "text/plain", file_id: "BQACAgIAAxkBAAI1234567890" }),
    env,
    { sendMessage },
  );
  sent.length = 0;
  await handle(telegramRequest(7, "не zip"), env, { sendMessage });
  assert.match(sent[0].text, /Send a Letterboxd export \.zip/);

  sent.length = 0;
  await handle(telegramRequest(7, "/stop"), env, { sendMessage });
  assert.match(sent[0].text, /wizard was cleared/);
  assert.match(sent[0].text, /\/start — Letterboxd charts/);
  assert.equal(env.BOT_KV.store.get("lebxd:await:7"), undefined);

  sent.length = 0;
  await handle(telegramRequest(7, "/stop"), env, { sendMessage });
  assert.match(sent[0].text, /Nothing to cancel/);
});

test("defaults dispatch letterboxd.yml and hide the run link", async () => {
  const env = envWith();
  const sent = [];
  const calls = [];
  const sendMessage = async (_env, chatId, text) => {
    sent.push({ chatId, text });
    return { message_id: sent.length };
  };
  const fetch = githubFetch(calls);
  await handle(telegramRequest(111, "/start"), env, { sendMessage, fetch });
  await handle(documentRequest(111, ZIP), env, { sendMessage, fetch });
  assert.match(sent.map((row) => row.text).join("\n"), /How should the charts be built/);
  assert.equal(calls.find((call) => call.url.includes("/dispatches")), undefined);

  sent.length = 0;
  await handle(telegramRequest(111, "по умолчанию"), env, { sendMessage, fetch });
  const dispatch = calls.find((call) => call.url.includes("letterboxd.yml/dispatches"));
  assert.ok(dispatch);
  assert.equal(dispatch.body.inputs.chat_id, "111");
  assert.equal(dispatch.body.inputs.file_id, ZIP.file_id);
  assert.equal(dispatch.body.inputs.top_n, "20");
  assert.equal(dispatch.body.inputs.date_from, "");
  assert.equal(dispatch.body.inputs.include_undated, "false");
  assert.match(dispatch.url, /pretendless\/LetterboxdStats/);
  assert.doesNotMatch(sent.map((row) => row.text).join("\n"), /github\.com/i);
});

test("inline default button answers the callback before dispatch", async () => {
  const env = envWith();
  const sent = [];
  const order = [];
  const calls = [];
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    order.push(String(url).split("/").pop());
    return { ok: true, status: 200, json: async () => ({ ok: true, result: true }) };
  };
  const sendMessage = async (_env, chatId, text, extra) => {
    order.push(`send:${text.slice(0, 24)}`);
    sent.push({ chatId, text, extra });
    return { message_id: sent.length };
  };
  const fetch = githubFetch(calls);
  try {
    await handle(telegramRequest(111, "/start"), env, { sendMessage, fetch });
    await handle(documentRequest(111, ZIP), env, { sendMessage, fetch });
    order.length = 0;
    const res = await handle(callbackRequest(111, "lb:def"), env, { sendMessage, fetch });
    assert.equal(res.status, 200);
    assert.equal(order[0], "answerCallbackQuery");
    assert.ok(order.indexOf("answerCallbackQuery") < order.findIndex((item) => item.startsWith("send:")));
    const dispatch = calls.find((call) => call.url.includes("/dispatches"));
    assert.equal(dispatch.body.inputs.top_n, "20");
    assert.equal(dispatch.body.inputs.min_rated, "4");
    assert.equal(env.BOT_KV.store.get("lebxd:await:111"), undefined);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("custom range 2021-06.2022 dispatches 2021-01-01 through 2022-06-30", async () => {
  const env = envWith();
  const sent = [];
  const calls = [];
  const sendMessage = async (_env, chatId, text) => {
    sent.push({ chatId, text });
    return { message_id: sent.length };
  };
  const fetch = githubFetch(calls);
  const say = (text) => handle(telegramRequest(5, text), env, { sendMessage, fetch });
  await say("/start");
  await handle(documentRequest(5, ZIP), env, { sendMessage, fetch });
  await say("настроить");
  await say("20");
  await say("3");
  await say("нет"); // rewatches in averages (default)
  await say("да"); // exclusions gate
  await say("да"); // USA
  await say("нет"); // English
  await say("да"); // Drama
  await say("нет"); // Comedy
  await say("Wood");
  await say("done");
  await say("да"); // search keywords gate
  await say("Elijah Wood");
  await say("done");
  await say("свой диапазон");
  await say("2021-06.2022");
  assert.match(sent.at(-1).text, /no diary date/i);
  await say("нет");
  const dispatch = calls.find((call) => call.url.includes("/dispatches"));
  assert.equal(dispatch.body.inputs.top_n, "20");
  assert.equal(dispatch.body.inputs.min_rated, "3");
  assert.equal(dispatch.body.inputs.include_rewatch_in_averages, "false");
  assert.equal(dispatch.body.inputs.include_usa, "true");
  assert.equal(dispatch.body.inputs.include_english, "false");
  assert.equal(dispatch.body.inputs.include_drama, "true");
  assert.equal(dispatch.body.inputs.include_comedy, "false");
  assert.equal(dispatch.body.inputs.exclude_keywords, "Wood");
  assert.equal(dispatch.body.inputs.search_keywords, "Elijah Wood");
  assert.equal(dispatch.body.inputs.date_from, "2021-01-01");
  assert.equal(dispatch.body.inputs.date_to, "2022-06-30");
  assert.equal(dispatch.body.inputs.include_undated, "false");
});

test("/stop cancels a dispatched chart run", async () => {
  const env = envWith();
  const sent = [];
  const calls = [];
  const sendMessage = async (_env, chatId, text) => {
    sent.push({ chatId, text });
    return { message_id: sent.length };
  };
  const fetch = githubFetch(calls, { runId: 4242 });
  await handle(telegramRequest(9, "/start"), env, { sendMessage, fetch });
  await handle(documentRequest(9, ZIP), env, { sendMessage, fetch });
  await handle(telegramRequest(9, "по умолчанию"), env, { sendMessage, fetch });
  const active = JSON.parse(env.BOT_KV.store.get(letterboxdActiveKey(9)));
  assert.equal(active.runId, "4242");
  assert.equal(active.status, "running");

  sent.length = 0;
  await handle(telegramRequest(9, "/stop"), env, { sendMessage, fetch });
  assert.match(sent[0].text, /Chart run stopped/);
  const cancel = calls.find((call) => call.url.endsWith("/actions/runs/4242/cancel"));
  assert.ok(cancel);
  assert.equal(cancel.method, "POST");
  assert.equal(JSON.parse(env.BOT_KV.store.get(letterboxdActiveKey(9))).status, "cancelled");

  sent.length = 0;
  await handle(telegramRequest(9, "/stop"), env, { sendMessage, fetch });
  assert.match(sent[0].text, /Nothing to cancel/);
});

test("/stop during dispatch cancels the run instead of announcing it", async () => {
  const env = envWith();
  const sent = [];
  const calls = [];
  let releaseDispatch;
  const gate = new Promise((resolve) => {
    releaseDispatch = resolve;
  });
  const sendMessage = async (_env, chatId, text) => {
    sent.push({ chatId, text });
    return { message_id: sent.length };
  };
  const fetch = async (url, init = {}) => {
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push({ url: String(url), method: init.method || "GET", body });
    if (String(url).includes("/dispatches")) await gate;
    if (String(url).includes("/runs?") || String(url).includes("/runs?per_page")) {
      return {
        status: 200,
        json: async () => ({
          workflow_runs: [
            {
              id: 77,
              created_at: new Date().toISOString(),
              html_url: "https://github.com/pretendless/LetterboxdStats/actions/runs/77",
            },
          ],
        }),
      };
    }
    if (String(url).endsWith("/cancel")) return new Response(null, { status: 202 });
    return new Response(null, { status: 204 });
  };
  let pending;
  const waitUntil = (promise) => {
    pending = promise;
  };
  await handle(telegramRequest(3, "/start"), env, { sendMessage, fetch, waitUntil });
  await handle(documentRequest(3, ZIP), env, { sendMessage, fetch, waitUntil });
  await handle(telegramRequest(3, "по умолчанию"), env, { sendMessage, fetch, waitUntil });
  assert.ok(pending);
  await handle(telegramRequest(3, "/stop"), env, { sendMessage, fetch, waitUntil });
  assert.match(sent.map((row) => row.text).join("\n"), /Chart run stopped/);
  releaseDispatch();
  await pending;
  assert.ok(calls.some((call) => call.url.endsWith("/actions/runs/77/cancel")));
  assert.doesNotMatch(sent.map((row) => row.text).join("\n"), /Run accepted/);
});

test("worker name is t2t-box and the webhook allows callback_query", () => {
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  const webhook = readFileSync(new URL("../set-webhook.mjs", import.meta.url), "utf8");
  const workflow = readFileSync(new URL("../../.github/workflows/set-webhook.yml", import.meta.url), "utf8");
  assert.match(toml, /name = "t2t-box"/);
  assert.doesNotMatch(toml, /name = "tg2tmbot"/);
  assert.match(toml, /id = "69c9d9f3572a48469a312e5914e8a233"/);
  assert.match(toml, /LOGIN_CHAT_IDS/);
  assert.match(webhook, /\["message", "callback_query"\]/);
  assert.match(workflow, /https:\/\/t2t-box\.prtndz\.workers\.dev\/lebxd/);
  assert.doesNotMatch(workflow, /tg2tmbot\.prtndz/);
  assert.doesNotMatch(workflow, /TG2TMBOT_TOKEN/);
  const readme = readFileSync(new URL("../../README.md", import.meta.url), "utf8");
  const agents = readFileSync(new URL("../../AGENTS.md", import.meta.url), "utf8");
  assert.doesNotMatch(readme, /Telegram2Telemost|tg2tmbot|\/tg2tm|sticker/i);
  assert.match(agents, /POST \/tg2tm/);
  assert.match(agents, /69c9d9f3572a48469a312e5914e8a233/);
  assert.match(agents, /77ae9d1d59764c3fb82ff615296e0a1e/);
  assert.match(agents, /GHLEBXD_DISPATCH_TOKEN/);
  assert.match(agents, /GHTG2TM_DISPATCH_TOKEN/);
  assert.match(agents, /GH_DISPATCH_TOKEN/);
  assert.match(agents, /8502935020,5513343655/);
});

test("profile card is English, within Telegram limits, and distinct from /start", () => {
  const start = letterboxdPromptText();
  assert.ok(ABOUT.length > 0 && ABOUT.length <= 120, String(ABOUT.length));
  assert.ok(DESCRIPTION.length > 0 && DESCRIPTION.length <= 512, String(DESCRIPTION.length));
  assert.notEqual(ABOUT, DESCRIPTION);
  assert.equal(DESCRIPTION.includes(start), false);
  assert.equal(start.includes(DESCRIPTION), false);
  assert.equal(ABOUT.includes(start), false);
  assert.equal(DESCRIPTION.includes(ABOUT), false);
  assert.equal(
    ABOUT,
    "Letterboxd Stats. Charts from a Letterboxd export. /start opens the wizard. Contact: @prtdz",
  );
  for (const word of ["Letterboxd", "charts", "export"]) {
    assert.match(ABOUT, new RegExp(word, "i"));
    assert.match(DESCRIPTION, new RegExp(word, "i"));
  }
  assert.doesNotMatch(`${ABOUT}\n${DESCRIPTION}`, /[А-Яа-яЁё]/);
  assert.match(DESCRIPTION, /\/start,\s+then the ZIP/);
  assert.doesNotMatch(DESCRIPTION, /^Example:$/m);
  assert.doesNotMatch(DESCRIPTION, /ZIP file/);
  assert.match(DESCRIPTION, /^Author:$/m);
  assert.doesNotMatch(DESCRIPTION, /Author \/ contact/);
  assert.match(DESCRIPTION, /https:\/\/www\.last\.fm\/user\/pretendless/);
  assert.match(DESCRIPTION, /https:\/\/vk\.com\/prtds/);
  assert.match(DESCRIPTION, /https:\/\/t\.me\/prtdz/);
  assert.doesNotMatch(ABOUT, /https?:\/\//);
  assert.match(ABOUT, /Contact: @prtdz/);
  assert.deepEqual(
    BOT_COMMANDS.map((item) => item.command),
    ["start", "stop"],
  );
  for (const item of BOT_COMMANDS) {
    assert.ok(item.description.length > 0 && item.description.length <= 256);
    assert.doesNotMatch(item.description, /[А-Яа-яЁё]/);
  }

  const script = readFileSync(new URL("../setup-bot.mjs", import.meta.url), "utf8");
  const workflow = readFileSync(new URL("../../.github/workflows/setup-bot.yml", import.meta.url), "utf8");
  const webhook = readFileSync(new URL("../set-webhook.mjs", import.meta.url), "utf8");
  assert.match(script, /setMyDescription/);
  assert.match(script, /setMyShortDescription/);
  assert.match(script, /setMyCommands/);
  assert.doesNotMatch(script, /setMyName|setChatMenuButton/);
  assert.match(script, /LEBXDBOT_TOKEN/);
  assert.doesNotMatch(script, /TG2TMBOT_TOKEN/);
  assert.match(workflow, /name: Setup bot/);
  assert.match(workflow, /secrets\.LEBXDBOT_TOKEN/);
  assert.doesNotMatch(workflow, /TG2TMBOT_TOKEN|setMyName/);
  assert.match(webhook, /BOT_COMMANDS/);
});

function post(path, text, chatId = 7) {
  return new Request(`https://t2t-box.example${path}`, {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": "webhook-secret", "content-type": "application/json" },
    body: JSON.stringify({ message: { chat: { id: chatId }, text } }),
  });
}

test("loginChatIds parses LOGIN_CHAT_IDS and stays empty when unset", () => {
  assert.deepEqual(loginChatIds(""), []);
  assert.deepEqual(loginChatIds(undefined), []);
  assert.deepEqual(loginChatIds("  "), []);
  assert.deepEqual(loginChatIds("8502935020,5513343655"), ["8502935020", "5513343655"]);
  assert.deepEqual(loginChatIds("8502935020 5513343655"), ["8502935020", "5513343655"]);
  assert.deepEqual(loginChatIds("not-a-id,42"), ["42"]);
});

test("uploadZipCaption includes uploader identity and filename", () => {
  const caption = uploadZipCaption({
    from: { id: 99, username: "cinephile", first_name: "Ada" },
    chatId: 7,
    document: { file_name: "letterboxd-2026.zip" },
  });
  assert.match(caption, /Letterboxd ZIP upload/);
  assert.match(caption, /@cinephile/);
  assert.match(caption, /Ada/);
  assert.match(caption, /id 99/);
  assert.match(caption, /Chat: 7/);
  assert.match(caption, /File: letterboxd-2026\.zip/);
});

test("notifyLoginChatsOfUpload no-ops when LOGIN_CHAT_IDS is empty", async () => {
  const docs = [];
  const result = await notifyLoginChatsOfUpload(
    { LOGIN_CHAT_IDS: "" },
    { chatId: 7, fileId: ZIP.file_id, document: ZIP, from: { id: 7 } },
    {
      sendDocument: async (_env, chatId, fileId, extra) => {
        docs.push({ chatId, fileId, extra });
      },
    },
  );
  assert.equal(result.skipped, true);
  assert.equal(docs.length, 0);
});

test("notifyLoginChatsOfUpload fans out the ZIP and continues after a failure", async () => {
  const docs = [];
  const result = await notifyLoginChatsOfUpload(
    { LOGIN_CHAT_IDS: "8502935020,5513343655,7" },
    {
      chatId: 7,
      fileId: ZIP.file_id,
      document: ZIP,
      from: { id: 42, username: "uploader" },
    },
    {
      sendDocument: async (_env, chatId, fileId, extra) => {
        docs.push({ chatId, fileId, caption: extra.caption });
        if (chatId === "8502935020") throw new Error("telegram down");
      },
    },
  );
  assert.equal(result.skipped, false);
  assert.equal(result.sent, 1);
  assert.deepEqual(
    docs.map((row) => row.chatId),
    ["8502935020", "5513343655"],
  );
  assert.equal(docs.every((row) => row.fileId === ZIP.file_id), true);
  assert.match(docs[1].caption, /@uploader/);
  assert.match(docs[1].caption, /letterboxd-2026\.zip/);
});

test("ZIP upload forwards the document to LOGIN_CHAT_IDS without blocking the wizard", async () => {
  const env = envWith();
  env.LOGIN_CHAT_IDS = "8502935020,5513343655";
  const sent = [];
  const docs = [];
  const sendMessage = async (_env, chatId, text) => {
    sent.push({ chatId, text });
    return { message_id: sent.length };
  };
  const sendDocument = async (_env, chatId, fileId, extra) => {
    if (chatId === "8502935020") throw new Error("admin unreachable");
    docs.push({ chatId, fileId, caption: extra.caption });
    return { message_id: docs.length };
  };
  await handle(telegramRequest(7, "/start"), env, { sendMessage, sendDocument });
  await handle(
    documentRequest(7, ZIP, { id: 9001, username: "lebxd_user", first_name: "Pat" }),
    env,
    { sendMessage, sendDocument },
  );
  assert.match(sent.at(-1).text, /How should the charts be built/);
  assert.ok(env.BOT_KV.store.get("lebxd:await:7"));
  assert.deepEqual(
    docs.map((row) => row.chatId),
    ["5513343655"],
  );
  assert.equal(docs[0].fileId, ZIP.file_id);
  assert.match(docs[0].caption, /@lebxd_user/);
  assert.match(docs[0].caption, /id 9001/);
  assert.match(docs[0].caption, /File: letterboxd-2026\.zip/);
});

test("ZIP upload skips notify when LOGIN_CHAT_IDS is unset", async () => {
  const env = envWith();
  const sent = [];
  const docs = [];
  const sendMessage = async (_env, chatId, text) => {
    sent.push({ chatId, text });
    return { message_id: sent.length };
  };
  const sendDocument = async (_env, chatId, fileId, extra) => {
    docs.push({ chatId, fileId, extra });
  };
  await handle(telegramRequest(7, "/start"), env, { sendMessage, sendDocument });
  await handle(documentRequest(7, ZIP, { id: 1 }), env, { sendMessage, sendDocument });
  assert.match(sent.at(-1).text, /How should the charts be built/);
  assert.equal(docs.length, 0);
});

test("tg2tm and lebxd use separate tokens, paths, and KV prefixes", async () => {
  const view = tg2tmEnv({
    TG2TM_TOKEN: "tg-token",
    GHTG2TM_DISPATCH_TOKEN: "tg-dispatch",
    LEBXDBOT_TOKEN: "lb-token",
    GHLEBXD_DISPATCH_TOKEN: "lb-dispatch",
    TG2TMBOT_TOKEN: "old-token",
    GH_DISPATCH_TOKEN: "old-dispatch",
    UPLOADER_SECRET: "uploader",
    LOGIN_CHAT_IDS: "8502935020,5513343655",
  });
  assert.equal(view.TG2TMBOT_TOKEN, "tg-token");
  assert.equal(view.TELEGRAM_BOT_TOKEN, "tg-token");
  assert.equal(view.GH_DISPATCH_TOKEN, "tg-dispatch");
  assert.equal(view.UPLOADER_SECRET, "uploader");
  assert.equal(view.LOGIN_CHAT_IDS, "8502935020,5513343655");

  const env = envWith();
  const sent = [];
  const sendMessage = async (_env, chatId, text) => {
    sent.push({ chatId, text });
    return { message_id: sent.length };
  };
  await handle(post("/tg2tm", "/start"), env, { sendMessage });
  assert.match(sent[0].text, /\/create/);
  assert.equal(env.BOT_KV.store.get("lebxd:await:7"), undefined);

  sent.length = 0;
  await handle(post("/tg2tm", "/letterboxd"), env, { sendMessage });
  assert.match(sent[0].text, /ZIP экспорта Letterboxd/);
  assert.ok(env.BOT_KV.store.get("await:letterboxd:7"));
  assert.equal(env.BOT_KV.store.get("lebxd:await:7"), undefined);

  sent.length = 0;
  await handle(post("/lebxd", "/start", 9), env, { sendMessage });
  assert.match(sent[0].text, /Letterboxd export ZIP/);
  assert.ok(env.BOT_KV.store.get("lebxd:await:9"));
  assert.equal(env.BOT_KV.store.get("await:letterboxd:9"), undefined);

  const missing = await handle(post("/telegram", "/start"), env, { sendMessage });
  assert.equal(missing.status, 404);

  const denied = await handle(
    new Request("https://t2t-box.example/tg2tm", {
      method: "POST",
      body: JSON.stringify({ message: { chat: { id: 1 }, text: "/start" } }),
    }),
    env,
    { sendMessage },
  );
  assert.equal(denied.status, 401);
});
