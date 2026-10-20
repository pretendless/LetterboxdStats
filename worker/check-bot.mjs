// Logs @lebxdbot identity and webhook state (no secrets).
import { telegramFetch } from "./telegram_fetch.mjs";

const token = process.env.LEBXDBOT_TOKEN;
if (!token) {
  console.error("Set LEBXDBOT_TOKEN.");
  process.exit(1);
}

async function call(method) {
  const res = await telegramFetch(`https://api.telegram.org/bot${token}/${method}`);
  const body = await res.json();
  if (!body.ok) throw new Error(body.description || method);
  return body.result;
}

const me = await call("getMe");
console.log(`bot username: @${me.username}`);

const wh = await call("getWebhookInfo");
const url = wh.url || "";
console.log(`webhook url: ${url || "(empty — polling or unset)"}`);
console.log(`pending_update_count: ${wh.pending_update_count ?? 0}`);
console.log(`allowed_updates: ${JSON.stringify(wh.allowed_updates ?? [])}`);
console.log(`last_error_message: ${wh.last_error_message ?? "(none)"}`);
if (wh.last_error_date) {
  console.log(
    `last_error_date: ${new Date(wh.last_error_date * 1000).toISOString()} (unix ${wh.last_error_date})`,
  );
} else {
  console.log("last_error_date: (none)");
}
