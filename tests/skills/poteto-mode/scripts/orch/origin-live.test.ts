import { afterEach, describe, expect, it } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  openStore,
  type Store,
} from "../../../../../skills/poteto-mode/scripts/orch/store.ts";

const repo = process.env.PSTACK_ORIGIN_LIVE_REPO;
const live = Bun.which("origin") !== null && repo !== undefined && repo !== "";
if (!live) {
  console.warn(
    "origin-live skipped: needs the origin CLI on PATH and PSTACK_ORIGIN_LIVE_REPO naming a checkout of a disposable Origin-hosted repo whose current branch heads a stack"
  );
}

const directories: string[] = [];
const handles: Store[] = [];

afterEach(async () => {
  for (const store of handles.splice(0).reverse()) {
    await store.close();
  }
  for (const directory of directories.splice(0)) {
    await rm(directory, { recursive: true, force: true });
  }
});

function git(args: readonly string[]): string {
  const result = Bun.spawnSync(["git", "-C", repo ?? ".", ...args]);
  if (result.exitCode !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${result.stderr.toString()}`);
  }
  return result.stdout.toString().trim();
}

describe("Origin frontier against a live forge", () => {
  it.skipIf(!live)(
    "walks the live stack through the current branch",
    async () => {
      const directory = await mkdtemp(join(tmpdir(), "orch-origin-live-"));
      directories.push(directory);
      const store = openStore(directory);
      handles.push(store);
      await store.init();

      const frontier = await store.frontier.set({
        repo: repo ?? ".",
        forge: "origin",
      });

      expect(frontier.generation).toBe(1);
      expect(frontier.prs.length).toBeGreaterThan(0);
      expect(new Set(frontier.prs.map((row) => row.pr)).size).toBe(
        frontier.prs.length
      );
      expect(frontier.prs.map((row) => row.branches)).toContain(
        git(["branch", "--show-current"])
      );
      for (const row of frontier.prs) {
        expect(Number.isSafeInteger(row.pr) && row.pr > 0).toBe(true);
        expect(["OPEN", "MERGED", "CLOSED"]).toContain(row.state);
        if (row.state === "OPEN") {
          expect(row.sha).toBe(
            git(["rev-parse", "--verify", `refs/heads/${row.branches}^{commit}`])
          );
        } else {
          expect(row.sha === "" || /^[0-9a-f]{40,64}$/i.test(row.sha)).toBe(true);
        }
      }
      expect(frontier.lowestUnmerged).toBe(
        frontier.prs.find((row) => row.state === "OPEN")?.pr ?? null
      );
      expect(await store.frontier.show()).toEqual(frontier);
    },
    60_000
  );
});
