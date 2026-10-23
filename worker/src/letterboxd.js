import { cancelRunUrl, githubHeaders } from "../../vm/dispatch.js";
import {
  DEFAULT_REF,
  DEFAULT_REPO,
  awaitLetterboxdKey,
  decodeActiveLetterboxd,
  decodeAwaitLetterboxd,
  dispatchLetterboxdWorkflow,
  encodeActiveLetterboxd,
  encodeAwaitLetterboxd,
  findLetterboxdRun,
  advanceLetterboxdWizard,
  letterboxdAckText,
  letterboxdActiveKey,
  letterboxdCancelKey,
  letterboxdDispatchFailText,
  letterboxdDispatchedText,
  letterboxdInvalidZipText,
  letterboxdJobKey,
  letterboxdModePrompt,
  letterboxdNeedZipText,
  letterboxdPromptText,
  letterboxdStartingText,
  letterboxdUsageText,
  isZipDocument,
  LETTERBOXD_WORKFLOW,
  newLetterboxdJobId,
  normalizeTelegramFileId,
  parseLetterboxdCallback,
  parseStartCommand,
} from "../../vm/letterboxd_genres.js";

function isAdminChat(chatId, raw) {
  return loginChatIds(raw).includes(String(chatId));
}

/** Numeric chat ids from LOGIN_CHAT_IDS. Empty/unset → [] (no invented fallback). */
export function loginChatIds(raw) {
  return String(raw || "")
    .split(/[\s,]+/)
    .filter((id) => /^[0-9]{1,16}$/.test(id));
}

export function uploadZipCaption({ from, chatId, document } = {}) {
  const user = from && typeof from === "object" ? from : {};
  const userId = user.id != null ? String(user.id) : "";
  const username = typeof user.username === "string" && user.username.trim() ? user.username.trim() : "";
  const nameBits = [user.first_name, user.last_name]
    .map((part) => (typeof part === "string" ? part.trim() : ""))
    .filter(Boolean);
  const displayName = nameBits.join(" ");
  const fileName =
    (document && (document.file_name || document.fileName)) ||
    "";
  const lines = ["Letterboxd ZIP upload"];
  if (userId || username || displayName) {
    const who = [];
    if (username) who.push(`@${username}`);
    if (displayName) who.push(displayName);
    if (userId) who.push(`id ${userId}`);
    lines.push(`From: ${who.join(" · ")}`);
  }
  if (chatId != null && chatId !== "") lines.push(`Chat: ${chatId}`);
  if (fileName) lines.push(`File: ${fileName}`);
  return lines.join("\n");
}

/**
 * Forward the uploaded ZIP (by file_id) to every LOGIN_CHAT_IDS chat.
 * Failures are logged only — never thrown to the caller.
 */
export async function notifyLoginChatsOfUpload(env, { chatId, from, document, fileId }, deps = {}) {
  const ids = loginChatIds(env && env.LOGIN_CHAT_IDS);
  if (!ids.length || !fileId) return { sent: 0, skipped: true };
  const sendDocument = deps.sendDocument;
  if (!sendDocument) {
    console.error("letterboxd zip notify: sendDocument missing");
    return { sent: 0, skipped: true };
  }
  const caption = uploadZipCaption({ from, chatId, document });
  const source = String(chatId);
  let sent = 0;
  for (const id of ids) {
    if (id === source) continue;
    try {
      await sendDocument(env, id, fileId, {
        caption,
        file_name: (document && (document.file_name || document.fileName)) || undefined,
      });
      sent += 1;
    } catch (err) {
      console.error("letterboxd zip notify failed", id, err && err.message);
    }
  }
  return { sent, skipped: false };
}

function repoOf(env) {
  return env.GH_REPO || DEFAULT_REPO;
}

function workflowOf(env) {
  return env.LETTERBOXD_WORKFLOW || LETTERBOXD_WORKFLOW;
}

async function cancelRun(fetchImpl, env, runId) {
  if (!runId || !env.GHLEBXD_DISPATCH_TOKEN) return 0;
  const res = await fetchImpl(cancelRunUrl(repoOf(env), runId), {
    method: "POST",
    headers: githubHeaders(env.GHLEBXD_DISPATCH_TOKEN),
  });
  return res.status;
}

async function jobCancelled(env, jobId) {
  if (!env.BOT_KV || !jobId) return false;
  const flag = await env.BOT_KV.get(letterboxdCancelKey(jobId));
  return flag != null && flag !== "";
}

export async function finishLetterboxdDispatch(env, { jobId, chatId, fileId, options, startedAt, deps = {} }) {
  const send = deps.send;
  const fetchImpl = deps.fetch || fetch;
  const repo = repoOf(env);
  const workflow = workflowOf(env);
  const ref = env.LETTERBOXD_REF || env.GH_GHRUN_REF || DEFAULT_REF;
  const when = typeof startedAt === "number" ? startedAt : Date.now();
  if (await jobCancelled(env, jobId)) return { ok: false, cancelled: true };

  let dispatched;
  try {
    dispatched = await dispatchLetterboxdWorkflow(fetchImpl, {
      token: env.GHLEBXD_DISPATCH_TOKEN,
      repo,
      workflow,
      ref,
      jobId,
      chatId,
      fileId,
      options,
    });
  } catch (err) {
    console.error("letterboxd dispatch failed", err && err.message);
    dispatched = { ok: false, status: 0 };
  }
  if (!dispatched.ok) {
    if (!(await jobCancelled(env, jobId)) && send) {
      await send(env, chatId, letterboxdDispatchFailText(dispatched.status || "error"));
    }
    return { ok: false };
  }

  let run = { id: "", url: "" };
  try {
    run = await findLetterboxdRun(fetchImpl, {
      token: env.GHLEBXD_DISPATCH_TOKEN,
      repo,
      workflow,
      startedAt: when,
      sleep: deps.sleep,
    });
  } catch (err) {
    console.error("letterboxd run lookup failed", err && err.message);
  }

  if (env.BOT_KV && run.id) {
    const current = decodeActiveLetterboxd(await env.BOT_KV.get(letterboxdActiveKey(chatId)));
    if (current && current.jobId === jobId && current.status !== "cancelled") {
      await env.BOT_KV.put(
        letterboxdActiveKey(chatId),
        encodeActiveLetterboxd({ ...current, runId: run.id, status: "running" }),
      );
    }
  }

  if (await jobCancelled(env, jobId)) {
    if (run.id) {
      try {
        await cancelRun(fetchImpl, env, run.id);
      } catch (err) {
        console.error("letterboxd cancel failed", err && err.message);
      }
    }
    if (env.BOT_KV) {
      const current = decodeActiveLetterboxd(await env.BOT_KV.get(letterboxdActiveKey(chatId)));
      if (current && current.jobId === jobId) {
        await env.BOT_KV.put(
          letterboxdActiveKey(chatId),
          encodeActiveLetterboxd({ ...current, runId: run.id || current.runId, status: "cancelled" }),
        );
      }
    }
    return { ok: true, cancelled: true };
  }

  if (send) {
    const admin = isAdminChat(chatId, env.LOGIN_CHAT_IDS);
    await send(env, chatId, letterboxdDispatchedText({ jobId, runUrl: admin ? run.url : "" }));
  }
  return { ok: true, runUrl: run.url, runId: run.id };
}

export async function handleLetterboxdCommand(env, message, deps = {}) {
  const parsed = parseStartCommand(message && message.text);
  if (!parsed) return false;
  const send = deps.send;
  if (!send) throw new Error("send");
  const chatId = message.chat && message.chat.id;
  if (parsed.error) {
    await send(env, chatId, letterboxdUsageText());
    return true;
  }
  const kv = env.BOT_KV;
  if (!kv) {
    await send(env, chatId, "KV is unavailable — cannot wait for a ZIP.");
    return true;
  }
  await kv.put(awaitLetterboxdKey(chatId), encodeAwaitLetterboxd({ since: new Date().toISOString() }));
  await send(env, chatId, letterboxdPromptText());
  return true;
}

export async function handleLetterboxdDocument(env, message, deps = {}) {
  const send = deps.send;
  if (!send) throw new Error("send");
  const chatId = message.chat && message.chat.id;
  const kv = env.BOT_KV;
  if (!kv) return false;
  const awaiting = decodeAwaitLetterboxd(await kv.get(awaitLetterboxdKey(chatId)));
  if (!awaiting) return false;

  const document = message.document;
  if (!isZipDocument(document)) {
    await send(env, chatId, letterboxdInvalidZipText());
    return true;
  }
  const fileId = normalizeTelegramFileId(document.file_id || document.fileId);
  if (!fileId) {
    await send(env, chatId, letterboxdNeedZipText());
    return true;
  }
  if (!env.GHLEBXD_DISPATCH_TOKEN) {
    await send(env, chatId, "Run is not configured: missing secret GHLEBXD_DISPATCH_TOKEN.");
    return true;
  }

  const prompt = letterboxdModePrompt();
  const sent = await send(env, chatId, prompt.text, { reply_markup: prompt.reply_markup });
  const promptMessageId = sent && sent.message_id != null ? Number(sent.message_id) : null;
  await kv.put(
    awaitLetterboxdKey(chatId),
    encodeAwaitLetterboxd({
      since: awaiting.since,
      step: "mode",
      fileId,
      promptMessageId: Number.isFinite(promptMessageId) && promptMessageId > 0 ? promptMessageId : null,
    }),
  );

  const notify = () =>
    notifyLoginChatsOfUpload(
      env,
      { chatId, from: message.from, document, fileId },
      deps,
    ).catch((err) => {
      console.error("letterboxd zip notify", err && err.message);
    });
  if (deps.waitUntil) deps.waitUntil(notify());
  else await notify();
  return true;
}

async function beginLetterboxdJob(env, chatId, fileId, options, deps, promptMessageId = null) {
  const send = deps.send;
  const edit = deps.edit;
  const kv = env.BOT_KV;
  const jobId = newLetterboxdJobId(deps.now);
  const createdAt = typeof deps.now === "function" ? deps.now().toISOString() : new Date().toISOString();
  const startedAt = typeof deps.now === "function" ? deps.now().getTime() : Date.now();
  await kv.put(
    letterboxdJobKey(jobId),
    JSON.stringify({
      id: jobId,
      chatId: String(chatId),
      fileId,
      status: "pending",
      createdAt,
      options,
    }),
  );
  await kv.put(
    letterboxdActiveKey(chatId),
    encodeActiveLetterboxd({
      jobId,
      chatId,
      status: "pending",
      startedAt,
      runId: "",
    }),
  );
  await kv.delete(awaitLetterboxdKey(chatId));
  if (await jobCancelled(env, jobId)) return;
  const ack = letterboxdAckText(jobId, options);
  // Prefer editing the wizard bubble into the ack so step prompts leave no trail.
  let ackEdited = false;
  if (edit && promptMessageId) {
    try {
      await edit(env, chatId, promptMessageId, ack, { reply_markup: { inline_keyboard: [] } });
      ackEdited = true;
    } catch (err) {
      console.error("letterboxd ack edit", err && err.message);
    }
  }
  if (!ackEdited) await send(env, chatId, ack);
  await send(env, chatId, letterboxdStartingText());
  const background = async () => {
    if (await jobCancelled(env, jobId)) return;
    await finishLetterboxdDispatch(env, {
      jobId,
      chatId,
      fileId,
      options,
      startedAt,
      deps: { ...deps, send },
    });
  };
  if (deps.waitUntil) deps.waitUntil(background());
  else await background();
}

async function deliverWizardMessage(env, chatId, msg, promptMessageId, deps) {
  const send = deps.send;
  const edit = deps.edit;
  const extra = msg.reply_markup
    ? { reply_markup: msg.reply_markup }
    : { reply_markup: { inline_keyboard: [] } };
  if (edit && promptMessageId) {
    try {
      await edit(env, chatId, promptMessageId, msg.text, extra);
      return promptMessageId;
    } catch (err) {
      console.error("letterboxd wizard edit", err && err.message);
    }
  }
  const sent = await send(env, chatId, msg.text, msg.reply_markup ? { reply_markup: msg.reply_markup } : undefined);
  const mid = sent && sent.message_id != null ? Number(sent.message_id) : null;
  return Number.isFinite(mid) && mid > 0 ? mid : promptMessageId;
}

async function applyLetterboxdWizard(env, chatId, outcome, deps) {
  const kv = env.BOT_KV;
  let promptMessageId =
    outcome.state && outcome.state.promptMessageId != null
      ? Number(outcome.state.promptMessageId)
      : deps.promptMessageId != null
        ? Number(deps.promptMessageId)
        : null;
  if (!Number.isFinite(promptMessageId) || promptMessageId <= 0) promptMessageId = null;

  for (const msg of outcome.messages || []) {
    promptMessageId = await deliverWizardMessage(env, chatId, msg, promptMessageId, deps);
  }

  if (outcome.state && !outcome.clear) {
    const next = { ...outcome.state };
    if (promptMessageId) next.promptMessageId = promptMessageId;
    await kv.put(awaitLetterboxdKey(chatId), encodeAwaitLetterboxd(next));
  }
  if (outcome.dispatch) {
    await beginLetterboxdJob(
      env,
      chatId,
      outcome.dispatch.fileId,
      outcome.dispatch.options,
      deps,
      promptMessageId,
    );
  } else if (outcome.clear) {
    await kv.delete(awaitLetterboxdKey(chatId));
  }
}

export async function handleLetterboxdText(env, message, deps = {}) {
  const send = deps.send;
  if (!send) throw new Error("send");
  const chatId = message.chat && message.chat.id;
  const kv = env.BOT_KV;
  if (!kv) return false;
  const state = decodeAwaitLetterboxd(await kv.get(awaitLetterboxdKey(chatId)));
  if (!state || state.step === "zip") return false;
  const now = typeof deps.now === "function" ? deps.now() : new Date();
  const outcome = advanceLetterboxdWizard(state, { kind: "text", text: message.text }, now);
  await applyLetterboxdWizard(env, chatId, outcome, {
    ...deps,
    promptMessageId: state.promptMessageId,
  });
  return true;
}

async function replyCallback(answer, env, id, text) {
  if (!answer) return;
  try {
    await answer(env, id, text || "");
  } catch (err) {
    console.error("answerCallbackQuery", err && err.message);
  }
}

export async function handleLetterboxdCallback(env, callback, deps = {}) {
  const answer = deps.answerCallback;
  const callbackId = callback && callback.id;
  const parsed = parseLetterboxdCallback(callback && callback.data);
  const message = callback && callback.message;
  const chatId = message && message.chat && message.chat.id;
  if (!parsed || chatId == null) {
    await replyCallback(answer, env, callbackId, "");
    return false;
  }
  const kv = env.BOT_KV;
  const state = kv ? decodeAwaitLetterboxd(await kv.get(awaitLetterboxdKey(chatId))) : null;
  if (!state) {
    await replyCallback(answer, env, callbackId, "The Letterboxd wizard was already cleared.");
    return true;
  }
  if (parsed.step !== state.step) {
    await replyCallback(answer, env, callbackId, "That step is already done.");
    return true;
  }
  await replyCallback(answer, env, callbackId, "");
  // Edit the same wizard message in place — do not clear markup then send a new bubble.
  const callbackMessageId = message && message.message_id != null ? Number(message.message_id) : null;
  const now = typeof deps.now === "function" ? deps.now() : new Date();
  const outcome = advanceLetterboxdWizard(state, { kind: "callback", ...parsed }, now);
  if (
    outcome.state &&
    !outcome.clear &&
    Number.isFinite(callbackMessageId) &&
    callbackMessageId > 0 &&
    outcome.state.promptMessageId == null
  ) {
    outcome.state = { ...outcome.state, promptMessageId: callbackMessageId };
  }
  await applyLetterboxdWizard(env, chatId, outcome, {
    ...deps,
    promptMessageId: state.promptMessageId || callbackMessageId,
  });
  return true;
}

export async function clearLetterboxdAwait(kv, chatId) {
  if (!kv) return false;
  const key = awaitLetterboxdKey(chatId);
  const pending = decodeAwaitLetterboxd(await kv.get(key));
  if (!pending) return false;
  await kv.delete(key);
  return true;
}

export async function cancelDispatchedLetterboxd(env, chatId, deps = {}) {
  const kv = env.BOT_KV;
  if (!kv) return { cancelled: false };
  const active = decodeActiveLetterboxd(await kv.get(letterboxdActiveKey(chatId)));
  if (!active || !active.jobId || active.status === "cancelled") return { cancelled: false };
  await kv.put(letterboxdCancelKey(active.jobId), "1");
  await kv.put(
    letterboxdActiveKey(chatId),
    encodeActiveLetterboxd({ ...active, status: "cancelled" }),
  );
  if (!active.runId) return { cancelled: true, pending: true };
  const fetchImpl = deps.fetch || fetch;
  try {
    const status = await cancelRun(fetchImpl, env, active.runId);
    const ok = status === 202 || status === 204 || status === 409;
    return { cancelled: ok, pending: false, status };
  } catch (err) {
    console.error("letterboxd cancel failed", err && err.message);
    return { cancelled: false, pending: false, status: 0 };
  }
}
