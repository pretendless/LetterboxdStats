// Fills the @lebxdbot BotFather profile: short description, description, and commands.
// Does not set the webhook and does not call setMyName.
//
//   LEBXDBOT_TOKEN=... node setup-bot.mjs

import { telegramFetch } from "./telegram_fetch.mjs";

const token = process.env.LEBXDBOT_TOKEN;
if (!token) {
  console.error("Need LEBXDBOT_TOKEN.");
  process.exit(1);
}

const PROFILE =
  "A Letterboxd ZIP becomes a dark-theme chart report in this chat. /start begins, /stop cancels.";

const commands = [
  { command: "start", description: "Start a Letterboxd chart report" },
  { command: "stop", description: "Cancel the wizard or a running report" },
];

async function call(method, body) {
  const res = await telegramFetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  if (!json.ok) {
    console.error(json.description || `${method} failed`);
    process.exit(1);
  }
  console.log(`${method} ok`);
}

await call("setMyShortDescription", { short_description: PROFILE });
await call("setMyDescription", { description: PROFILE });
await call("setMyCommands", { commands });
