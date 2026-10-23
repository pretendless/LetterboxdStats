// @lebxdbot webhook on the shared t2t-box worker. Path: POST /lebxd.
// Token: LEBXDBOT_TOKEN. Dispatch: GHLEBXD_DISPATCH_TOKEN. Same WEBHOOK_SECRET as /tg2tm.
import {
  awaitLetterboxdKey,
  decodeAwaitLetterboxd,
  letterboxdNeedZipText,
  letterboxdStopText,
} from "../../vm/letterboxd_genres.js";
import {
  cancelDispatchedLetterboxd,
  clearLetterboxdAwait,
  handleLetterboxdCallback,
  handleLetterboxdCommand,
  handleLetterboxdDocument,
  handleLetterboxdText,
} from "./letterboxd.js";

export function botToken(env) {
  return env.LEBXDBOT_TOKEN || "";
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function timingSafeEqual(a, b) {
  const left = String(a);
  const right = String(b);
  const length = Math.max(left.length, right.length);
  let mismatch = left.length === right.length ? 0 : 1;
  for (let i = 0; i < length; i++) mismatch |= (left.charCodeAt(i) || 0) ^ (right.charCodeAt(i) || 0);
  return mismatch === 0;
}

function commandOf(text) {
  if (!String(text || "").startsWith("/")) return "";
  return String(text).split(/\s/)[0].split("@")[0].toLowerCase();
}

function telegramParseMode(text) {
  const value = String(text ?? "");
  // Wizard prompts use <b>; ZIP ack uses <pre> settings + <i> footnote.
  if (
    /<b>[\s\S]*<\/b>/.test(value) ||
    /<i>[\s\S]*<\/i>/.test(value) ||
    /<pre>[\s\S]*<\/pre>/.test(value) ||
    /<code>[\s\S]*<\/code>/.test(value)
  ) {
    return "HTML";
  }
  return undefined;
}

async function telegram(env, method, params) {
  const token = botToken(env);
  if (!token) throw new Error("no bot token");
  const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(params),
  });
  let body;
  try {
    body = await res.json();
  } catch {
    throw new Error(`telegram ${method} http ${res.status}`);
  }
  if (!body.ok) throw new Error(body.description || `telegram ${method}`);
  return body.result;
}

function outgoingText(text) {
  const value = String(text ?? "");
  const parseMode = telegramParseMode(value);
  if (parseMode) return { text: value, parse_mode: parseMode };
  return { text: value };
}

async function defaultSend(env, chatId, text, extra) {
  const body = outgoingText(text);
  const payload = {
    chat_id: chatId,
    text: body.text,
    link_preview_options: { is_disabled: true },
  };
  if (body.parse_mode) payload.parse_mode = body.parse_mode;
  if (extra && extra.reply_markup) payload.reply_markup = extra.reply_markup;
  return telegram(env, "sendMessage", payload);
}

async function defaultEdit(env, chatId, messageId, text, extra) {
  const body = outgoingText(text);
  const payload = {
    chat_id: chatId,
    message_id: messageId,
    text: body.text,
    link_preview_options: { is_disabled: true },
  };
  if (body.parse_mode) payload.parse_mode = body.parse_mode;
  if (extra && extra.reply_markup !== undefined) payload.reply_markup = extra.reply_markup;
  return telegram(env, "editMessageText", payload);
}

async function defaultSendDocument(env, chatId, fileId, extra = {}) {
  const payload = {
    chat_id: chatId,
    document: fileId,
  };
  if (extra.caption) payload.caption = String(extra.caption).slice(0, 1024);
  return telegram(env, "sendDocument", payload);
}

async function defaultAnswerCallback(env, id, text) {
  const payload = { callback_query_id: id };
  if (text) payload.text = String(text).slice(0, 200);
  return telegram(env, "answerCallbackQuery", payload);
}

async function defaultClearKeyboard(env, chatId, messageId) {
  try {
    await telegram(env, "editMessageReplyMarkup", {
      chat_id: chatId,
      message_id: messageId,
      reply_markup: { inline_keyboard: [] },
    });
  } catch (err) {
    console.error("clear letterboxd keyboard", err && err.message);
  }
}

const NEED_START = "Send /start first, then the Letterboxd export ZIP. Cancel with /stop.";

async function answer(env, update, send, deps = {}) {
  if (update && update.callback_query) {
    await handleLetterboxdCallback(env, update.callback_query, {
      send,
      edit: deps.editMessage || defaultEdit,
      fetch: deps.fetch,
      now: deps.now,
      waitUntil: deps.waitUntil,
      sleep: deps.sleep,
      answerCallback: deps.answerCallback || ((target, id, text) => defaultAnswerCallback(target, id, text)),
    });
    return;
  }
  const message = update && update.message;
  if (!message) return;
  const text = typeof message.text === "string" ? message.text : "";
  const document = message.document && typeof message.document === "object" ? message.document : null;
  if (!text && !document) return;
  const chatId = message.chat && message.chat.id;
  if (!Number.isSafeInteger(chatId) && typeof chatId !== "number") return;
  const cmd = text ? commandOf(text) : "";

  if (cmd === "/start") {
    await handleLetterboxdCommand(env, message, {
      send,
      fetch: deps.fetch,
      now: deps.now,
      waitUntil: deps.waitUntil,
      sleep: deps.sleep,
    });
    return;
  }
  if (cmd === "/stop") {
    const wizard = await clearLetterboxdAwait(env.BOT_KV, chatId);
    const job = await cancelDispatchedLetterboxd(env, chatId, deps);
    const failStatus = job.status != null && job.cancelled === false && !job.pending ? String(job.status) : "";
    await send(env, chatId, letterboxdStopText({
      wizard,
      job: Boolean(job.cancelled || job.pending),
      failStatus,
    }));
    return;
  }
  if (cmd) return;

  if (document) {
    const handled = await handleLetterboxdDocument(env, message, {
      send,
      sendDocument: deps.sendDocument || defaultSendDocument,
      fetch: deps.fetch,
      now: deps.now,
      waitUntil: deps.waitUntil,
      sleep: deps.sleep,
    });
    if (!handled) await send(env, chatId, NEED_START);
    return;
  }

  const awaiting = decodeAwaitLetterboxd(await env.BOT_KV.get(awaitLetterboxdKey(chatId)));
  if (awaiting && awaiting.step !== "zip") {
    await handleLetterboxdText(env, message, {
      send,
      edit: deps.editMessage || defaultEdit,
      fetch: deps.fetch,
      now: deps.now,
      waitUntil: deps.waitUntil,
      sleep: deps.sleep,
    });
    return;
  }
  await send(env, chatId, awaiting ? letterboxdNeedZipText() : NEED_START);
}

async function handleTelegram(request, env, send, deps) {
  const secret = env.WEBHOOK_SECRET || "";
  const got = request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
  if (!secret || !timingSafeEqual(got, secret)) return new Response("unauthorized", { status: 401 });
  let update;
  try {
    update = await request.json();
  } catch {
    return new Response("bad json", { status: 400 });
  }
  try {
    await answer(env, update, send, deps);
  } catch (err) {
    console.error("reply failed", err && err.message);
  }
  return new Response("ok");
}

export async function handle(request, env, deps = {}) {
  const send = deps.sendMessage || defaultSend;
  const sendDocument = deps.sendDocument || defaultSendDocument;
  const editMessage = deps.editMessage || defaultEdit;
  const url = new URL(request.url);
  if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) return json({ ok: true });
  if (request.method === "POST" && url.pathname === "/lebxd") {
    return handleTelegram(request, env, send, { ...deps, sendDocument, editMessage });
  }
  return new Response("not found", { status: 404 });
}

export default {
  fetch(request, env, ctx) {
    const waitUntil = ctx && typeof ctx.waitUntil === "function" ? (promise) => ctx.waitUntil(promise) : null;
    return handle(request, env, waitUntil ? { waitUntil } : {});
  },
};
