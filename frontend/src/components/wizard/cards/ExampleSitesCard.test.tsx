import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { WizardProvider } from "../wizard-ui";
import WebsiteEvalCard from "./WebsiteEvalCard";

const add = vi.hoisted(() => vi.fn());
vi.mock("@/lib/taste-api", () => ({ tasteGet: vi.fn(), tasteAddExamples: add }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const page = (name: string, body = "<html></html>") => new File([body], name, { type: "text/html" });

function setup() {
  const send = vi.fn();
  render(
    <WizardProvider value={{ modelId: null, send, refresh: vi.fn(), version: 0, busy: false, sessionId: "s1", adoptModel: vi.fn() }}>
      <WebsiteEvalCard section="sources" />
    </WizardProvider>,
  );
  return { send };
}

it("uploads pages, then lets the user mark each one good or bad", async () => {
  add.mockResolvedValue({ model_id: "eval-1", added: { liked: 2, disliked: 2 }, job_id: null });
  const { send } = setup();
  expect(screen.getByText("Show it example sites")).toBeTruthy();
  const names = ["render.html", "neon.html", "gpumode.html", "treehacks.html", "notes.html"];
  fireEvent.change(screen.getByLabelText("Choose example pages"), { target: { files: names.map((n) => page(n, `<html>${n}</html>`)) } });
  await screen.findByLabelText("Mark render.html good");
  const use = () => screen.getByRole("button", { name: /Use these/ });
  expect(use()).toBeDisabled();
  for (const n of ["render.html", "neon.html"]) fireEvent.click(screen.getByLabelText(`Mark ${n} good`));
  for (const n of ["gpumode.html", "treehacks.html"]) fireEvent.click(screen.getByLabelText(`Mark ${n} bad`));
  expect(screen.getByText(/2 good · 2 bad · 1 not marked/)).toBeTruthy();
  fireEvent.click(use());
  await waitFor(() => expect(send).toHaveBeenCalledWith("Added 2 good examples and 2 bad.", "event"));
  expect(add.mock.calls[0][1].map((f: { name: string; label: string }) => [f.label, f.name])).toEqual([
    ["liked", "render.html"], ["liked", "neon.html"], ["disliked", "gpumode.html"], ["disliked", "treehacks.html"],
  ]);
  expect(add.mock.calls[0][1][0].content).toBe("<html>render.html</html>");
});

it("toggles a mark off and removes a page", async () => {
  setup();
  fireEvent.change(screen.getByLabelText("Choose example pages"), { target: { files: [page("a.html"), page("b.html")] } });
  await screen.findByLabelText("Mark a.html good");
  fireEvent.click(screen.getByLabelText("Mark a.html good"));
  expect(screen.getByLabelText("Mark a.html good")).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByLabelText("Mark a.html good"));
  expect(screen.getByLabelText("Mark a.html good")).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(screen.getByLabelText("Remove b.html"));
  expect(screen.queryByLabelText("Mark b.html good")).toBeNull();
});
