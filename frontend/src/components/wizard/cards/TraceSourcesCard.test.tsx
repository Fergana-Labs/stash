import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { WizardProvider } from "../wizard-ui";
import WebsiteEvalCard from "./WebsiteEvalCard";

const upload = vi.hoisted(() => vi.fn());
vi.mock("@/lib/taste-api", () => ({ tasteGet: vi.fn(), tasteUploadTraces: upload }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

function setup() {
  const send = vi.fn();
  const adoptModel = vi.fn();
  render(
    <WizardProvider value={{ modelId: null, send, refresh: vi.fn(), version: 0, busy: false, sessionId: "s1", adoptModel }}>
      <WebsiteEvalCard section="sources" />
    </WizardProvider>,
  );
  return { send, adoptModel };
}

it("uploads past sessions from the first website-eval card and tells the wizard to continue", async () => {
  upload.mockResolvedValue({ session_id: "s1", model_id: "eval-1", job_id: "job-1" });
  const { send, adoptModel } = setup();
  expect(screen.getByText("Add your past sessions")).toBeTruthy();
  const input = document.querySelector('input[type="file"][accept=".jsonl"]') as HTMLInputElement;
  const session = new File(['{"type":"user"}'], "session.jsonl");
  fireEvent.change(input, { target: { files: [session, new File(["x"], "notes.md")] } });
  await waitFor(() => expect(send).toHaveBeenCalled());
  expect(upload).toHaveBeenCalledWith("s1", [{ name: "session.jsonl", content: '{"type":"user"}' }]);
  expect(adoptModel).toHaveBeenCalledWith("eval-1");
  expect(send.mock.calls[0][0]).toContain("job-1");
  expect(send.mock.calls[0][1]).toBe("event");
  expect(screen.getByText(/Uploaded 1 session · skipped 1 other file/)).toBeTruthy();
});

it("lets the user search connected history instead", () => {
  const { send } = setup();
  fireEvent.click(screen.getByRole("button", { name: /Search my connected history instead/ }));
  expect(send).toHaveBeenCalledWith("Search my connected history instead of uploading.");
});
