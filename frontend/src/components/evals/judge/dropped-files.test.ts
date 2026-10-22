import { expect, it } from "vitest";
import { droppedFiles } from "./dropped-files";

const file = (name: string) => ({ name, isFile: true, isDirectory: false, file: (ok: (f: File) => void) => ok(new File(["x"], name)) });
function folder(name: string, children: unknown[], batch = 2) {
  return { name, isFile: false, isDirectory: true, createReader: () => {
    let at = 0;
    return { readEntries: (ok: (e: unknown[]) => void) => { ok(children.slice(at, at + batch)); at += batch; } };
  } };
}
const drop = (entries: unknown[], files: File[] = []) =>
  ({ items: entries.map((entry) => ({ kind: "file", webkitGetAsEntry: () => entry })), files } as unknown as DataTransfer);

it("opens dropped folders, including nested ones read in batches, and skips hidden files", async () => {
  const dropped = drop([
    folder("drawings", [file("a.png"), file(".DS_Store"), file("b.png"), folder("more", [file("c.pdf")])]),
    file("d.txt"),
  ]);
  expect((await droppedFiles(dropped)).map((f) => f.name).sort()).toEqual(["a.png", "b.png", "c.pdf", "d.txt"]);
});

it("falls back to the plain file list when the browser gives no entries", async () => {
  const plain = new File(["x"], "e.png");
  expect(await droppedFiles({ items: [], files: [plain] } as unknown as DataTransfer)).toEqual([plain]);
});
