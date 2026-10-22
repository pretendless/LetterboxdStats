// @lebxdbot BotFather profile. Setup bot writes these. The display name is set in BotFather.
// The empty-chat Start button is Telegram's own control. Nothing here sets it.
// DESCRIPTION (≤512) is what Telegram shows on an unused/empty chat card ("What can this bot do?").
// ABOUT (≤120) is the short profile / share line (product sentence + one Telegram contact; full https URLs are in DESCRIPTION).
// Description and /start use different sentences. Search words: Letterboxd, charts, export.

export const ABOUT =
  "Letterboxd Stats. Charts from a Letterboxd export ZIP. /start opens the wizard. Contact: @prtdz";

export const DESCRIPTION =
  "Letterboxd Stats (@lebxdbot) builds charts from a Letterboxd export ZIP.\n" +
  "\n" +
  "/start, then the ZIP. Default, Customize, or paste settings. Customize: tops 1–100, " +
  "threshold, rewatches in averages, likes (♥), reviews (≡), Top review (on by default; " +
  "panel from highest reviewed rank; unlocks lower-rating charts), Exclude on count tops, " +
  "Search keywords, watch period. /stop leaves the questions. A started chart run stops too.\n" +
  "\n" +
  "Author:\n" +
  "https://www.last.fm/user/pretendless\n" +
  "https://vk.com/prtds\n" +
  "https://t.me/prtdz";

export const BOT_COMMANDS = [
  { command: "start", description: "Start a Letterboxd chart report" },
  { command: "stop", description: "Cancel the wizard or a running report" },
];
