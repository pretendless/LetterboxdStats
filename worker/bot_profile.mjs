// @lebxdbot BotFather profile. Setup bot writes these. The display name is set in BotFather.
// The empty-chat Start button is Telegram's own control. Nothing here sets it.
// Description and /start use different sentences. Search words: Letterboxd, charts, export.

export const ABOUT =
  "Letterboxd Stats. Charts from a Letterboxd export. /start opens the wizard.";

export const DESCRIPTION =
  "Letterboxd Stats (@lebxdbot) builds charts from a Letterboxd export.\n" +
  "\n" +
  "/start, then the ZIP. Next, keep the usual chart set or choose your own: " +
  "top size from 1 to 100, a rating-count threshold for average tops, USA, English, and a watch period. " +
  "/stop leaves the questions. A chart run that has already started stops too.\n" +
  "\n" +
  "Example:\n" +
  "/start\n" +
  "ZIP file\n" +
  "defaults";

export const BOT_COMMANDS = [
  { command: "start", description: "Start a Letterboxd chart report" },
  { command: "stop", description: "Cancel the wizard or a running report" },
];
