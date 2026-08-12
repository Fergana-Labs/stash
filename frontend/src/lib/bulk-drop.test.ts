import { describe, expect, it, vi } from "vitest";
import { filesFromPicker, runPool } from "./bulk-drop";

function pickedFile(name: string, relativePath?: string): File {
  const file = new File(["x"], name);
  if (relativePath) {
    Object.defineProperty(file, "webkitRelativePath", { value: relativePath });
  }
  return file;
}

// A dropped folder is the one destination we never have to guess at: it is the
// user's own filing. Losing the path would dump a structured backlog into one
// flat pile.
describe("filesFromPicker", () => {
  it("keeps the folder path a directory picker reports", () => {
    const picked = filesFromPicker([
      pickedFile("brakes.pdf", "catalogs/meritor/brakes.pdf"),
      pickedFile("loose.pdf"),
    ]);
    expect(picked[0].path).toEqual(["catalogs", "meritor"]);
    expect(picked[1].path).toEqual([]);
  });

  it("drops tooling residue rather than stashing it", () => {
    const picked = filesFromPicker([
      pickedFile(".DS_Store", "catalogs/.DS_Store"),
      pickedFile("real.pdf", "catalogs/.git/real.pdf"),
    ]);
    expect(picked).toHaveLength(1);
    // The file survives, but the dot-directory never becomes a folder.
    expect(picked[0].path).toEqual(["catalogs"]);
  });
});

describe("runPool", () => {
  it("runs at most `limit` workers at once", async () => {
    let running = 0;
    let peak = 0;
    const items = Array.from({ length: 20 }, (_, i) => i);

    await runPool(items, 5, async () => {
      running += 1;
      peak = Math.max(peak, running);
      await new Promise((r) => setTimeout(r, 1));
      running -= 1;
    });

    expect(peak).toBe(5);
  });

  it("keeps going when one item fails, and reports which", async () => {
    const results = await runPool([1, 2, 3], 2, async (n) => {
      if (n === 2) throw new Error("bad file");
      return n * 10;
    });

    expect(results[0]).toEqual({ ok: true, value: 10 });
    expect(results[1]).toMatchObject({ ok: false });
    expect(results[2]).toEqual({ ok: true, value: 30 });
  });

  it("stops starting work once cancelled", async () => {
    const controller = new AbortController();
    const worker = vi.fn(async (n: number) => {
      if (n === 0) controller.abort();
      return n;
    });

    const results = await runPool([0, 1, 2, 3], 1, worker, { signal: controller.signal });

    expect(worker).toHaveBeenCalledTimes(1);
    expect(results.slice(1).every((r) => r.ok === "skipped")).toBe(true);
  });
});
