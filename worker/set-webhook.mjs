// Points @lebxdbot at the t2t-box Worker. Do not run while another process is
// calling getUpdates for this bot: Telegram delivers each update to only one of them.
//
//   CONFIRM_STOP_POLLING=1 LEBXDBOT_TOKEN=... WEBHOOK_SECRET=... \
//     LEBXD_WEBHOOK_URL=https://t2t-box.prtndz.workers.dev/telegram node set-webhook.mjs

import { telegramFetch } from "./telegram_fetch.mjs";

if (process.env.CONFIRM_STOP_POLLING !== "1") {
  console.error("Polling must be stopped first. Set CONFIRM_STOP_POLLING=1 only after that.");
  process.exit(1);
}

const token = process.env.LEBXDBOT_TOKEN;
const secret = process.env.WEBHOOK_SECRET;
const url = process.env.LEBXD_WEBHOOK_URL;
if (!token || !secret || !url) {
  console.error("Need LEBXDBOT_TOKEN, WEBHOOK_SECRET and LEBXD_WEBHOOK_URL.");
  process.exit(1);
}

const body = new URLSearchParams({
  url,
  secret_token: secret,
  // callback_query is required for the Letterboxd inline wizard. An explicit
  // list that omits it makes button taps flash and never reach the worker.
  allowed_updates: JSON.stringify(["message", "callback_query"]),
});
const res = await telegramFetch(`https://api.telegram.org/bot${token}/setWebhook`, { method: "POST", body });
const json = await res.json();
if (!json.ok) {
  console.error(json.description || "setWebhook failed");
  process.exit(1);
}
console.log("webhook set");

const commands = [
  { command: "start", description: "Графики Letterboxd" },
  { command: "stop", description: "Прервать ввод или запуск" },
];
const menu = await telegramFetch(`https://api.telegram.org/bot${token}/setMyCommands`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ commands }),
});
const menuJson = await menu.json();
if (!menuJson.ok) {
  console.error(menuJson.description || "setMyCommands failed");
  process.exit(1);
}
console.log("commands set");
