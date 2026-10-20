// t2t-box: one Cloudflare Worker for @tg2tmbot and @lebxdbot.
// Do not rename or deploy over the live tg2tmbot worker.
//
// POST /tg2tm  — existing Telegram2Telemost behavior
//                TG2TM_TOKEN + GHTG2TM_DISPATCH_TOKEN
// POST /lebxd  — Letterboxd /start and /stop
//                LEBXDBOT_TOKEN + GHLEBXD_DISPATCH_TOKEN
// Both webhooks use WEBHOOK_SECRET.
// Uploader routes keep UPLOADER_SECRET and LOGIN_CHAT_IDS.
import { handle as handleTg2tm } from "../../tg2tm/worker/src/index.js";
import { handle as handleLebxd } from "./lebxd.js";

const UPLOADER_PATHS = new Set([
  "/progress",
  "/session-started",
  "/queue/claim",
  "/queue/plan",
  "/queue/drain-complete",
  "/session-ended",
  "/project/prompt",
  "/project/reply",
]);

export function tg2tmEnv(env) {
  return new Proxy(env, {
    get(target, prop) {
      if (prop === "TG2TMBOT_TOKEN" || prop === "TELEGRAM_BOT_TOKEN") return target.TG2TM_TOKEN || "";
      if (prop === "GH_DISPATCH_TOKEN") return target.GHTG2TM_DISPATCH_TOKEN || "";
      return target[prop];
    },
  });
}

function rewritePath(request, pathname) {
  const url = new URL(request.url);
  url.pathname = pathname;
  return new Request(url, request);
}

export async function handle(request, env, deps = {}) {
  const url = new URL(request.url);
  if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
    return handleTg2tm(request, tg2tmEnv(env), deps);
  }
  if (request.method === "POST" && url.pathname === "/lebxd") return handleLebxd(request, env, deps);
  if (request.method === "POST" && url.pathname === "/tg2tm") {
    return handleTg2tm(rewritePath(request, "/telegram"), tg2tmEnv(env), deps);
  }
  if (UPLOADER_PATHS.has(url.pathname)) return handleTg2tm(request, tg2tmEnv(env), deps);
  return new Response("not found", { status: 404 });
}

export default {
  fetch(request, env, ctx) {
    const waitUntil = ctx && typeof ctx.waitUntil === "function" ? (promise) => ctx.waitUntil(promise) : null;
    return handle(request, env, waitUntil ? { waitUntil } : {});
  },
};
