import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import BulkExamples, { droppedFiles } from "./BulkExamples";

const api = vi.hoisted(() => ({ evalReadFile: vi.fn(), evalAddExamples: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);
beforeEach(() => { vi.clearAllMocks(); api.evalReadFile.mockImplementation(async (file: File) => ({ name: file.name, content: "File output" })); api.evalAddExamples.mockResolvedValue([]); });

it("imports multiple files as unlabeled examples in one batch", async () => {
  const added = vi.fn().mockResolvedValue(undefined);
  render(<BulkExamples id="eval" onAdded={added} />);
  fireEvent.change(screen.getByLabelText("Bulk files"), { target: { files: [new File(["one"], "one.txt"), new File(["two"], "two.txt")] } });
  expect(await screen.findByText("2 examples added")).toBeVisible();
  expect(api.evalAddExamples).toHaveBeenCalledWith("eval", [
    { item: { name: "one.txt", content: "File output" }, label: null, needs_review: true, note: "" },
    { item: { name: "two.txt", content: "File output" }, label: null, needs_review: true, note: "" },
  ]);
  expect(added).toHaveBeenCalledTimes(1);
});

it("adds readable files while retaining failed files for retry without duplicating successes", async () => {
  api.evalReadFile.mockResolvedValueOnce({ content: "First file" }).mockRejectedValueOnce(new Error("Cannot parse"));
  render(<BulkExamples id="eval" onAdded={vi.fn().mockResolvedValue(undefined)} />);
  fireEvent.change(screen.getByLabelText("Bulk files"), { target: { files: [new File(["one"], "one.txt"), new File(["bad"], "bad.pdf")] } });
  expect(await screen.findByRole("alert")).toHaveTextContent("bad.pdf: Cannot parse");
  expect(api.evalAddExamples.mock.calls[0][1]).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Retry failed files" }));
  await waitFor(() => expect(api.evalReadFile).toHaveBeenCalledTimes(3));
  expect(api.evalReadFile.mock.calls[2][0].name).toBe("bad.pdf");
  await waitFor(() => expect(api.evalAddExamples).toHaveBeenCalledTimes(2));
});

it("rejects excessive batches before reading files", async () => {
  render(<BulkExamples id="eval" onAdded={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Bulk files"), { target: { files: Array.from({ length: 101 }, (_, i) => new File(["x"], `${i}.txt`)) } });
  expect(await screen.findByRole("alert")).toHaveTextContent("100 files");
  expect(api.evalReadFile).not.toHaveBeenCalled();
});

it("traverses nested folders and reads every directory batch, excluding hidden entries", async () => {
  const file = (name: string) => ({ name, isFile: true, file: (done: (file: File) => void) => done(new File([name], name)) });
  const folder = (name: string, batches: unknown[][]) => ({ name, isDirectory: true, createReader: () => { let index = 0; return { readEntries: (done: (entries: unknown[]) => void) => done(batches[index++] ?? []) }; } });
  const entry = folder("examples", [[file("one.txt"), folder("nested", [[file("two.txt")]])], [file("three.txt"), file(".DS_Store")]]);
  const files = await droppedFiles({ items: [{ webkitGetAsEntry: () => entry, getAsFile: () => null }], files: [] } as unknown as DataTransfer);
  expect(files.map((file) => file.name)).toEqual(["one.txt", "two.txt", "three.txt"]);
});


it("accepts drops on the existing examples area", async () => {
  render(<BulkExamples id="eval" onAdded={vi.fn().mockResolvedValue(undefined)}><div>Existing examples</div></BulkExamples>);
  fireEvent.drop(screen.getByText("Existing examples"), { dataTransfer: { types: ["Files"], files: [new File(["Output"], "reply.txt")] } });
  expect(await screen.findByText("1 example added")).toBeVisible();
  expect(api.evalReadFile).toHaveBeenCalledTimes(1);
});
