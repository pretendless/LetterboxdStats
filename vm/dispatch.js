// GitHub Actions dispatch helpers for the @lebxdbot chart workflow.
// No Node builtins: the Cloudflare Worker imports this file.

export const DEFAULT_REPO = "pretendless/LetterboxdStats";
export const DEFAULT_REF = "main";

export function dispatchUrl(repo, workflow) {
  const parts = String(repo || "").split("/");
  if (parts.length !== 2) throw new Error("repo");
  const [owner, name] = parts;
  if (!/^[A-Za-z0-9_.-]+$/.test(owner) || !/^[A-Za-z0-9_.-]+$/.test(name)) throw new Error("repo");
  if (!/^[A-Za-z0-9_.-]+\.ya?ml$/.test(workflow || "")) throw new Error("workflow");
  return `https://api.github.com/repos/${owner}/${name}/actions/workflows/${workflow}/dispatches`;
}

export function assertRef(ref) {
  const value = String(ref || "");
  if (!/^[A-Za-z0-9._/-]{1,200}$/.test(value) || value.includes("..") || value.startsWith("-")) {
    throw new Error("ref");
  }
  return value;
}

export function githubHeaders(token) {
  return {
    authorization: `Bearer ${token}`,
    accept: "application/vnd.github+json",
    "content-type": "application/json",
    "user-agent": "lebxdbot",
    "x-github-api-version": "2022-11-28",
  };
}

export function workflowRunsUrl(repo, workflow) {
  return dispatchUrl(repo, workflow).replace(/\/dispatches$/, "/runs?per_page=20");
}

export function cancelRunUrl(repo, runId) {
  if (!/^[0-9]{1,12}$/.test(String(runId))) throw new Error("run");
  const [owner, name] = String(repo || "").split("/");
  return `https://api.github.com/repos/${owner}/${name}/actions/runs/${runId}/cancel`;
}
