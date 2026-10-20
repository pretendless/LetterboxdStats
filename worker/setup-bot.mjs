// Sets @lebxdbot description, short description and command list.
// Display name is set manually in BotFather, not by this script.
// Token: LEBXDBOT_TOKEN.
// The empty-chat Start button is Telegram's own control. This script does not set it.
import { ABOUT, BOT_COMMANDS, DESCRIPTION } from "./bot_profile.mjs";
import { telegramFetch } from "./telegram_fetch.mjs";

const token = process.env.LEBXDBOT_TOKEN;
if (!token) {
  console.error("Set LEBXDBOT_TOKEN.");
  process.exit(1);
}

async function call(method, params) {
  const res = await telegramFetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(params),
  });
  const body = await res.json();
  if (!body.ok) throw new Error(body.description || method);
}

await call("setMyDescription", { description: DESCRIPTION });
await call("setMyShortDescription", { short_description: ABOUT });
await call("setMyCommands", { commands: BOT_COMMANDS });

console.log(`description, about text and commands set (${BOT_COMMANDS.length} commands)`);
