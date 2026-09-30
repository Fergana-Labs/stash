import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { rmImportTraces, rmListFormats } from "@/lib/api";
import ImportTracesDialog from "./ImportTracesDialog";

vi.mock("@/lib/api", () => ({ rmImportTraces: vi.fn(), rmListFormats: vi.fn() }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(rmListFormats).mockResolvedValue([]);
});

function file(path: string, text: string) {
  return Object.assign(new File([text], path.split("/").at(-1)!), {
    webkitRelativePath: path, text: async () => text,
  });
}

it("offers a real folder picker and imports a bundle without sending its support files", async () => {
  vi.mocked(rmImportTraces).mockResolvedValue({ imported: 13, format: "stash", trace_ids: [] });
  const refresh = vi.fn();
  render(<ImportTracesDialog onImported={refresh} />);
  fireEvent.click(screen.getByRole("button", { name: "Import traces" }));
  const input = screen.getByLabelText("Trace folder");
  expect(input).toHaveAttribute("webkitdirectory");
  fireEvent.change(input, { target: { files: [file("bundle/traces.jsonl", "traces"), file("bundle/manifest.json", "metadata"), file("bundle/START-HERE.md", "guide")] } });
  fireEvent.click(screen.getByRole("button", { name: "Import" }));
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(rmImportTraces).toHaveBeenCalledExactlyOnceWith("auto", "traces");
  expect(screen.getByRole("status")).toHaveTextContent("Imported 13 traces.");
  expect(screen.getByText(/Skipped supporting files:/)).toHaveTextContent("bundle/manifest.json, bundle/START-HERE.md");
  expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
});

it("retries failed files without replacing traces from the successful part of the batch", async () => {
  vi.mocked(rmImportTraces)
    .mockResolvedValueOnce({ imported: 1, format: "stash", trace_ids: [] })
    .mockRejectedValueOnce(new Error("Network error"))
    .mockResolvedValueOnce({ imported: 1, format: "stash", trace_ids: [] });
  render(<ImportTracesDialog onImported={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Import traces" }));
  fireEvent.change(screen.getByLabelText("Trace folder"), { target: { files: [file("bundle/one.json", "one"), file("bundle/two.json", "two")] } });
  fireEvent.click(screen.getByRole("button", { name: "Import" }));
  await screen.findByRole("alert");
  expect(screen.getByText("1 file selected")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Import" }));
  await waitFor(() => expect(rmImportTraces).toHaveBeenCalledTimes(3));
  expect(vi.mocked(rmImportTraces).mock.calls.map((call) => call[1])).toEqual(["one", "two", "two"]);
});

it("explains an empty folder instead of enabling an import that cannot upload anything", async () => {
  render(<ImportTracesDialog onImported={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Import traces" }));
  fireEvent.change(screen.getByLabelText("Trace folder"), { target: { files: [] } });
  expect(await screen.findByText("The selected folder is empty.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
  expect(rmImportTraces).not.toHaveBeenCalled();
});
