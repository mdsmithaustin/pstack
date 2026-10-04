import type { Repository } from "./types.ts";

export function parseRemote(value: string): Repository | null {
  let normalized = value.trim();
  if (/[\s\\%?#]/.test(normalized)) return null;
  const scp = normalized.includes("://")
    ? null
    : /^git@([^:/]+):([^:]+)$/.exec(normalized);
  if (scp) normalized = `https://${scp[1]}/${scp[2]}`;
  const path = /^(?:https:\/\/[^/:@]+|ssh:\/\/git@[^/:@]+)(\/.*)$/i
    .exec(normalized)?.[1];
  if (!path || !/^\/[a-z\d_.-]+\/[a-z\d_.-]+\/?$/i.test(path))
    return null;
  try {
    const url = new URL(normalized);
    const parts = url.pathname
      .replace(/\/$/, "")
      .replace(/\.git$/, "")
      .split("/")
      .slice(1);
    if (
      !/^[a-z\d](?:[a-z\d.-]*[a-z\d])?$/i.test(url.hostname) ||
      (url.protocol === "ssh:" && url.username !== "git") ||
      url.pathname !== path ||
      parts.some((part) => !part || part === "." || part === "..")
    )
      return null;
    return { host: url.hostname, owner: parts[0], repo: parts[1] };
  } catch {
    return null;
  }
}
