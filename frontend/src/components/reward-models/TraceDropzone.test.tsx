import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { rmImportTraces } from "@/lib/api";
import TraceDropzone from "./TraceDropzone";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/lib/api", () => ({ rmImportTraces: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

function file(name: string, data: string) {
  return Object.assign(new File([data], name), { text: async () => data });
}

function transfer(files: File[]) {
  return {
    types: ["Files"],
    items: files.map((file) => ({
      kind: "file",
      webkitGetAsEntry: () => ({
        isFile: true, fullPath: `/${file.name}`,
        file: (resolve: (file: File) => void) => resolve(file),
      }),
    })),
  };
}

it("imports every dropped file once, detects each format, and refreshes the list", async () => {
  vi.mocked(rmImportTraces).mockResolvedValue({ imported: 2, format: "stash", trace_ids: [] });
  const refresh = vi.fn();
  render(<TraceDropzone onImported={refresh}>Existing trace list</TraceDropzone>);
  fireEvent.drop(screen.getByRole("region"), {
    dataTransfer: transfer([file("one.jsonl", "first"), file("two.json", "second")]),
  });
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(rmImportTraces).toHaveBeenNthCalledWith(1, "auto", "first");
  expect(rmImportTraces).toHaveBeenNthCalledWith(2, "auto", "second");
  expect(toast.success).toHaveBeenCalledWith("Imported 4 traces");
  expect(screen.getByRole("region")).toHaveAttribute("aria-busy", "false");
});

it("identifies failed files without hiding successful imports in the same drop", async () => {
  vi.mocked(rmImportTraces)
    .mockRejectedValueOnce(new Error("Invalid trace payload"))
    .mockResolvedValueOnce({ imported: 1, format: "stash", trace_ids: [] });
  const refresh = vi.fn();
  render(<TraceDropzone onImported={refresh}>Traces</TraceDropzone>);
  fireEvent.drop(screen.getByRole("region"), {
    dataTransfer: transfer([file("bundle.zip", "zip"), file("broken.json", "bad"), file("valid.jsonl", "valid")]),
  });
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(toast.error).toHaveBeenCalledWith("bundle.zip: Unzip this archive, then import the folder inside.");
  expect(toast.error).toHaveBeenCalledWith("broken.json: Invalid trace payload");
  expect(toast.success).toHaveBeenCalledWith("Imported 1 trace");
  expect(rmImportTraces).toHaveBeenCalledTimes(2);
});

it("keeps the drop target steady across child elements and ignores dragged text", () => {
  render(<TraceDropzone onImported={vi.fn()}><p>Traces</p></TraceDropzone>);
  const region = screen.getByRole("region");
  const child = screen.getByText("Traces");
  const dataTransfer = { types: ["Files"], files: [] };
  fireEvent.dragEnter(region, { dataTransfer });
  fireEvent.dragEnter(child, { dataTransfer });
  fireEvent.dragLeave(child, { dataTransfer });
  expect(screen.getByRole("status")).toHaveTextContent("Drop files or folders to import traces");
  fireEvent.dragLeave(region, { dataTransfer });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  fireEvent.drop(region, { dataTransfer: { types: ["text/plain"], files: [] } });
  expect(rmImportTraces).not.toHaveBeenCalled();
});

it("blocks a second drop while importing so an impatient retry cannot duplicate traces", async () => {
  let finish!: (value: { imported: number; format: string; trace_ids: string[] }) => void;
  vi.mocked(rmImportTraces).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  const refresh = vi.fn();
  render(<TraceDropzone onImported={refresh}>Traces</TraceDropzone>);
  const dataTransfer = transfer([file("trace.jsonl", "trace")]);
  fireEvent.drop(screen.getByRole("region"), { dataTransfer });
  await waitFor(() => expect(rmImportTraces).toHaveBeenCalledOnce());
  fireEvent.drop(screen.getByRole("region"), { dataTransfer });
  expect(toast.error).toHaveBeenCalledWith("Wait for the current import to finish before dropping more files.");
  finish({ imported: 1, format: "stash", trace_ids: [] });
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(rmImportTraces).toHaveBeenCalledOnce();
});
