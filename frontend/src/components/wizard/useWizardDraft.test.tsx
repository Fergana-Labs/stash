import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useEffect } from "react";
import { useWizardDraft } from "./useWizardDraft";
const api = vi.hoisted(() => ({ save: vi.fn() }));
vi.mock("@/lib/wizard-api", () => ({ wzSaveDraft: api.save }));
function Editor({ remote = "" }: { remote?: string }) {
  const draft = useWizardDraft("s");
  const load = draft.load;
  useEffect(() => load(remote), [load, remote]);
  return <><textarea aria-label="Draft" value={draft.input} onChange={(e) => draft.setInput(e.target.value)} /><button onClick={() => void draft.flush()}>Save</button><span>{draft.status}</span></>;
}
beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); api.save.mockResolvedValue({ saved: true }); });
it("restores a server draft and saves pending typing when leaving the page", async () => {
  const view = render(<Editor remote="Review policy" />);
  expect(screen.getByRole("textbox")).toHaveValue("Review policy");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Review policy exceptions" } });
  await act(async () => view.unmount());
  expect(api.save).toHaveBeenCalledWith("s", "Review policy exceptions");
});
it("recovers unsaved local typing after a failed server save", async () => {
  api.save.mockRejectedValue(new Error("Offline"));
  const view = render(<Editor />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Keep this unfinished thought" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await screen.findByText("Saved on this device");
  view.unmount();
  render(<Editor />);
  expect(screen.getByRole("textbox")).toHaveValue("Keep this unfinished thought");
  api.save.mockResolvedValue({ saved: true });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(localStorage.getItem("stash-wizard-draft:s")).toBeNull());
});
