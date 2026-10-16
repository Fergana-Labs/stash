import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WizardProvider } from "../wizard-ui";
import { labelFor } from "./ExampleSites";
import WebsiteEvalCard from "./WebsiteEvalCard";

const add = vi.hoisted(() => vi.fn());
vi.mock("@/lib/taste-api", () => ({ tasteGet: vi.fn(), tasteAddExamples: add }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const page = (path: string, body = "<html></html>") => {
  const file = new File([body], path.split("/").pop()!, { type: "text/html" });
  Object.defineProperty(file, "webkitRelativePath", { value: path });
  return file;
};

describe("labelFor", () => {
  it("labels files by the nearest good or bad folder", () => {
    expect(labelFor("examples/good/render.html")).toBe("liked");
    expect(labelFor("examples/bad/old/gpumode.html")).toBe("disliked");
    expect(labelFor("examples/Dislike/x.png")).toBe("disliked");
    expect(labelFor("examples/notes.html")).toBeNull();
  });
});

it("uploads one folder of good and bad pages, labeled by subfolder", async () => {
  add.mockResolvedValue({ model_id: "eval-1", added: { liked: 2, disliked: 2 }, job_id: null });
  const send = vi.fn();
  render(
    <WizardProvider value={{ modelId: null, send, refresh: vi.fn(), version: 0, busy: false, sessionId: "s1", adoptModel: vi.fn() }}>
      <WebsiteEvalCard section="sources" />
    </WizardProvider>,
  );
  expect(screen.getByText("Show it example sites")).toBeTruthy();
  const files = [page("ex/good/render.html", "<html>render</html>"), page("ex/good/neon.html"), page("ex/bad/gpumode.html"), page("ex/bad/treehacks.html"), page("ex/README.md")];
  fireEvent.change(screen.getByLabelText("Choose a folder of examples"), { target: { files } });
  expect(screen.getByText("Good · 2")).toBeTruthy();
  expect(screen.getByText("Skipped 1 file outside good/ and bad/.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Use these 4 examples/ }));
  await waitFor(() => expect(send).toHaveBeenCalledWith("Added 2 good examples and 2 bad.", "event"));
  expect(add.mock.calls[0][1].map((f: { name: string; label: string }) => [f.label, f.name])).toEqual([
    ["liked", "render.html"], ["liked", "neon.html"], ["disliked", "gpumode.html"], ["disliked", "treehacks.html"],
  ]);
  expect(add.mock.calls[0][1][0].content).toBe("<html>render</html>");
});

it("adds good/ and bad/ picked one after the other", () => {
  render(
    <WizardProvider value={{ modelId: null, send: vi.fn(), refresh: vi.fn(), version: 0, busy: false, sessionId: "s1" }}>
      <WebsiteEvalCard section="sources" />
    </WizardProvider>,
  );
  const input = screen.getByLabelText("Choose a folder of examples");
  fireEvent.change(input, { target: { files: [page("good/render.html"), page("good/neon.html")] } });
  expect(screen.getByText("Now add your bad/ folder (at least two).")).toBeTruthy();
  fireEvent.change(input, { target: { files: [page("bad/gpumode.html"), page("bad/treehacks.html")] } });
  expect(screen.getByText("Good · 2")).toBeTruthy();
  expect(screen.getByText("Bad · 2")).toBeTruthy();
  expect(screen.getByRole("button", { name: /Use these 4 examples/ })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
  expect(screen.queryByText("Good · 2")).toBeNull();
});
