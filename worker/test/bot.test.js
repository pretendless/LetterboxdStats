import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { handle } from "../src/index.js";
import { letterboxdActiveKey } from "../../vm/letterboxd_genres.js";

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
    GH_DISPATCH_TOKEN: "dispatch-token",
    GH_REPO: "pretendless/LetterboxdStats",
  };
}

function telegramRequest(chatId, text) {
  return new Request("https://t2t-box.example/telegram", {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": "webhook-secret", "content-type": "application/json" },
    body: JSON.stringify({ message: { chat: { id: chatId }, text } }),
  });
}

function documentRequest(chatId, document) {
  return new Request("https://t2t-box.example/telegram", {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": "webhook-secret", "content-type": "application/json" },
    body: JSON.stringify({ message: { chat: { id: chatId }, document } }),
  });
}

function callbackRequest(chatId, data, id = "cb-1") {
  return new Request("https://t2t-box.example/telegram", {
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
    new Request("https://t2t-box.example/telegram", { method: "POST", body: "{}" }),
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
  assert.match(sent[0].text, /ZIP экспорта Letterboxd/);
  assert.ok(env.BOT_KV.store.get("await:letterboxd:7"));

  sent.length = 0;
  await handle(telegramRequest(7, "/start letterboxd"), env, { sendMessage });
  assert.match(sent[0].text, /ZIP экспорта Letterboxd/);

  sent.length = 0;
  await handle(telegramRequest(7, "/start other"), env, { sendMessage });
  assert.match(sent[0].text, /\/start letterboxd/);

  sent.length = 0;
  await handle(telegramRequest(8, "/letterboxd"), env, { sendMessage });
  assert.equal(sent.length, 0);
  assert.equal(env.BOT_KV.store.get("await:letterboxd:8"), undefined);
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
  assert.match(sent[0].text, /Нужен файл \.zip/);

  sent.length = 0;
  await handle(telegramRequest(7, "/stop"), env, { sendMessage });
  assert.match(sent[0].text, /ожидание Letterboxd сброшено/);
  assert.match(sent[0].text, /\/start — графики Letterboxd/);
  assert.equal(env.BOT_KV.store.get("await:letterboxd:7"), undefined);

  sent.length = 0;
  await handle(telegramRequest(7, "/stop"), env, { sendMessage });
  assert.match(sent[0].text, /нечего прерывать/);
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
  assert.match(sent.map((row) => row.text).join("\n"), /Как строим графики/);
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
    assert.equal(dispatch.body.inputs.min_rated, "3");
    assert.equal(env.BOT_KV.store.get("await:letterboxd:111"), undefined);
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
  await say("да");
  await say("нет");
  await say("свой диапазон");
  await say("2021-06.2022");
  assert.match(sent.at(-1).text, /без даты/i);
  await say("нет");
  const dispatch = calls.find((call) => call.url.includes("/dispatches"));
  assert.equal(dispatch.body.inputs.top_n, "20");
  assert.equal(dispatch.body.inputs.min_rated, "3");
  assert.equal(dispatch.body.inputs.include_usa, "true");
  assert.equal(dispatch.body.inputs.include_english, "false");
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
  assert.match(sent[0].text, /Запуск графиков остановлен/);
  const cancel = calls.find((call) => call.url.endsWith("/actions/runs/4242/cancel"));
  assert.ok(cancel);
  assert.equal(cancel.method, "POST");
  assert.equal(JSON.parse(env.BOT_KV.store.get(letterboxdActiveKey(9))).status, "cancelled");

  sent.length = 0;
  await handle(telegramRequest(9, "/stop"), env, { sendMessage, fetch });
  assert.match(sent[0].text, /нечего прерывать/);
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
  assert.match(sent.map((row) => row.text).join("\n"), /Запуск графиков остановлен/);
  releaseDispatch();
  await pending;
  assert.ok(calls.some((call) => call.url.endsWith("/actions/runs/77/cancel")));
  assert.doesNotMatch(sent.map((row) => row.text).join("\n"), /Запуск принят/);
});

test("worker name is t2t-box and the webhook allows callback_query", () => {
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  const webhook = readFileSync(new URL("../set-webhook.mjs", import.meta.url), "utf8");
  const workflow = readFileSync(new URL("../../.github/workflows/set-webhook.yml", import.meta.url), "utf8");
  assert.match(toml, /name = "t2t-box"/);
  assert.doesNotMatch(toml, /name = "tg2tmbot"/);
  assert.match(webhook, /\["message", "callback_query"\]/);
  assert.match(workflow, /https:\/\/t2t-box\.prtndz\.workers\.dev\/telegram/);
  assert.doesNotMatch(workflow, /tg2tmbot\.prtndz/);
  assert.doesNotMatch(workflow, /TG2TMBOT_TOKEN/);
});
