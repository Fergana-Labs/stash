import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import EvalWorkspace from "./EvalWorkspace";
import CreateEval from "./CreateEval";

const api = vi.hoisted(() => ({ imGet: vi.fn(), imExamples: vi.fn(), imEditDraft: vi.fn(), evalEnableUpdates: vi.fn(), evalUpdateStatus: vi.fn(), evalRetryUpdate: vi.fn(), evalPrepare: vi.fn(), imDraftRubric: vi.fn(), imGrade: vi.fn(), imFit: vi.fn(), imPromote: vi.fn(), evalAddExamples: vi.fn(), evalAddTrace: vi.fn(), imEditExample: vi.fn(), imPredict: vi.fn(), imPredictions: vi.fn(), imReview: vi.fn(), imCreate: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);
vi.mock("./EvalInput", () => ({ default: ({ initialItem, onChange }: { initialItem?: string; onChange: (item: string) => void }) => <textarea aria-label="Example output" defaultValue={initialItem ?? ""} onChange={(event) => onChange(event.target.value)} /> }));

const version = { id: "draft", status: "draft", number: 1, description: "Be helpful", labels: [{ id: "good" }, { id: "bad" }], rubric: [], head: null, head_stale: true, metrics: null, gate: null };
const detail = { model: { id: "eval", name: "Replies", output_type: "choice" }, draft: version, active: null, judge: { configured: true }, versions: [], counts: {} };

beforeEach(() => {
  vi.clearAllMocks(); api.imGet.mockResolvedValue(detail); api.imExamples.mockResolvedValue([]);
  api.imGrade.mockResolvedValue({ graded: 5, remaining: 0, failed: 0 });
  api.imDraftRubric.mockResolvedValue({ rubric: [{ id: "helpful", prompt: "Is it helpful?", criteria: { true: "Helpful", false: "Unhelpful" } }] });
  api.imPredictions.mockResolvedValue([]);
  api.imEditDraft.mockResolvedValue(undefined); api.imPromote.mockResolvedValue(detail);
  api.evalEnableUpdates.mockResolvedValue({ state: "idle", revision: 1, completed_revision: 1 });
  api.evalUpdateStatus.mockResolvedValue({ state: "idle", revision: 1, completed_revision: 1 });
});

it("creates an eval from user criteria without trace-training settings", async () => {
  api.imCreate.mockResolvedValue({ model: { id: "created" } });
  const created = vi.fn(); render(<CreateEval onCreated={created} />);
  fireEvent.change(screen.getByRole("textbox", { name: "Name" }), { target: { value: "Slides" } });
  fireEvent.change(screen.getByRole("textbox", { name: "What does good look like?" }), { target: { value: "Readable and concise" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue to examples" }));
  await waitFor(() => expect(created).toHaveBeenCalledWith("created"));
  expect(api.imCreate).toHaveBeenCalledWith({ name: "Slides", description: "Readable and concise", output_type: "choice", labels: [{ id: "good", description: "Meets the user's expectations" }, { id: "bad", description: "Needs correction" }] });
  expect(screen.queryByRole("combobox", { name: /Base model|Epochs/ })).not.toBeInTheDocument();
});

it("keeps limited-data checks visible without a separate activation step", async () => {
  api.imGet.mockResolvedValue({ ...detail, draft: null, active: { ...version, id: "active", status: "active", head: {}, head_stale: false, rubric: [{ id: "helpful", prompt: "Is it helpful?", criteria: { true: "Helpful", false: "Unhelpful" } }], metrics: { eval: { n: 1, accuracy: 0, rows: [{ example_id: "held", label: "good", predicted: "bad", p_true: 0.3 }] } }, gate: { passed: false, checks: [{ name: "held_out_size", passed: false, detail: "1 held-out example; need 4" }] } } });
  api.imExamples.mockResolvedValue([{ id: "held", item: "A held-out slide", label: "good", split: "eval", note: "" }]);
  render(<EvalWorkspace id="eval" />);
  expect(await screen.findByText("0 of 1 labels matched")).toBeVisible();
  expect(screen.getByText("Probability of your label: 30%")).toBeVisible();
  const checks = screen.getByRole("region", { name: "Held-out checks" });
  expect(within(checks).getByText("Limited data")).toBeVisible();
  expect(within(checks).queryByText("Is it helpful?")).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Evaluation criteria" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Implementation" }));
  expect(within(screen.getByRole("region", { name: "Evaluation criteria" })).getByText(/Is it helpful\?/)).toBeVisible();
  expect(screen.getByText("Helpful", { exact: true })).toBeVisible();
  expect(screen.getByText("Unhelpful", { exact: true })).toBeVisible();
  expect(screen.queryByRole("button", { name: /Activate/ })).not.toBeInTheDocument();
  expect(screen.queryByText("Draft")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
});

it("logs test calls through the prediction API and saves human corrections", async () => {
  api.imGet.mockResolvedValue({ ...detail, draft: null, active: { ...version, id: "active", status: "active", head: {}, head_stale: false } });
  api.imPredict.mockResolvedValue({ prediction_id: "call", label: "good", confidence: 0.8, probabilities: { good: 0.8, bad: 0.2 }, version: 1, rubric: {} });
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Sandbox" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Example output" }), { target: { value: "A reply" } });
  fireEvent.click(screen.getByRole("button", { name: "Run eval" }));
  expect(await screen.findByText("80% confidence · v1")).toBeVisible();
  expect(api.imPredict).toHaveBeenCalledWith("eval", "A reply", "active");
  fireEvent.change(screen.getByRole("textbox", { name: "Score correction feedback" }), { target: { value: "Too vague" } });
  fireEvent.click(screen.getByRole("button", { name: "Mark bad" }));
  await waitFor(() => expect(api.imReview).toHaveBeenCalledWith("eval", "call", { label: "bad", note: "Too vague" }));
  expect(await screen.findByText("Correction added. The eval will update automatically.")).toBeVisible();
});


it("shows the endpoint directly, keeps Connect out of the menu, and expands request examples inline", async () => {
  render(<EvalWorkspace id="eval" />);
  const endpoint = await screen.findByRole("region", { name: "API endpoint" });
  expect(endpoint).toHaveTextContent(`${window.location.origin}/api/v1/intuitions/eval/predict`);
  fireEvent.keyDown(screen.getByRole("button", { name: "Eval options" }), { key: "ArrowDown" });
  const menu = await screen.findByRole("menu", { name: "Eval options" });
  expect(within(menu).queryByRole("menuitem", { name: "Connect" })).not.toBeInTheDocument();
  fireEvent.keyDown(menu, { key: "Escape" });
  fireEvent.click(screen.getByRole("button", { name: "API request details" }));
  const panel = await screen.findByRole("region", { name: "API request" });
  expect(panel).toHaveTextContent("Authorization: Bearer $STASH_API_KEY");
  expect(panel).toHaveTextContent("steps");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.keyDown(panel, { key: "Escape" });
  expect(screen.queryByRole("region", { name: "API request" })).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "API endpoint" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Sandbox" }));
  expect(screen.queryByRole("region", { name: "API endpoint" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Usage & corrections" }));
  expect(screen.queryByRole("region", { name: "API endpoint" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Build eval" }));
  expect(screen.getByRole("region", { name: "API endpoint" })).toBeVisible();
});

it("shows calls from external agents in usage and saves corrections against those calls", async () => {
  api.imPredictions.mockResolvedValue([{ id: "external-call", kind: "predict", caller: "refund-agent", version: 1, created_at: "2026-10-12T12:00:00Z", status: "unreviewed", input: { item: { steps: [{ role: "user", content: "Check the refund" }, { role: "assistant", content: "Please send your order number" }] } }, output: { label: "good", probabilities: { good: 0.8, bad: 0.2 } } }]);
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Usage & corrections" }));
  const caller = await screen.findByText("refund-agent");
  expect(api.imPredictions).toHaveBeenCalledWith("eval", "all");
  fireEvent.click(caller);
  expect(screen.getByText(/Check the refund/)).toBeVisible();
  expect(screen.getByText(/Please send your order number/)).toBeVisible();
  fireEvent.change(screen.getByRole("textbox", { name: "Feedback for usage external-call" }), { target: { value: "Missing context" } });
  fireEvent.click(screen.getByRole("button", { name: "Mark bad" }));
  await waitFor(() => expect(api.imReview).toHaveBeenCalledWith("eval", "external-call", { label: "bad", note: "Missing context" }));
});


it("downloads saved definitions, fitted heads, frozen seeds, and examples for this eval", async () => {
  const active = { ...version, id: "active", status: "active", head: { weights: [[1, 2]] }, seed_snapshot: [{ item: "Frozen seed", label: "good" }] };
  const examples = [{ id: "example", item: "A reply", label: "bad", note: "Needs specifics" }];
  api.imGet.mockResolvedValue({ ...detail, active }); api.imExamples.mockResolvedValue(examples);
  const create = vi.fn((blob: Blob) => { expect(blob.type).toBe("application/json"); return "blob:eval"; });
  const oldCreate = URL.createObjectURL, oldRevoke = URL.revokeObjectURL;
  URL.createObjectURL = create; URL.revokeObjectURL = vi.fn();
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  try {
    render(<EvalWorkspace id="eval" />);
    fireEvent.keyDown(await screen.findByRole("button", { name: "Eval options" }), { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Download" }));
    expect(click).toHaveBeenCalledOnce();
    const link = click.mock.instances[0] as HTMLAnchorElement;
    expect(link.download).toBe("Replies.json");
    const exported = await new Promise<string>((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(create.mock.calls[0][0]); });
    expect(JSON.parse(exported)).toMatchObject({ format: "stash-eval", format_version: 1, model: detail.model, active, examples });
  } finally { click.mockRestore(); URL.createObjectURL = oldCreate; URL.revokeObjectURL = oldRevoke; }
});


it("adds a labeled example into the single Examples collection", async () => {
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Add example" }));
  const dialog = await screen.findByRole("region", { name: "Add example" });
  const form = within(dialog);
  expect(form.getByRole("button", { name: "Add example" })).toBeDisabled();
  fireEvent.change(form.getByRole("textbox", { name: "Example output" }), { target: { value: "A concrete next step" } });
  fireEvent.change(form.getByRole("textbox", { name: "Example feedback" }), { target: { value: "Useful and concise" } });
  api.imExamples.mockResolvedValue([{ id: "new", item: "A concrete next step", label: "good", note: "Useful and concise", split: "train" }]);
  fireEvent.click(form.getByRole("button", { name: "Add example" }));
  await waitFor(() => expect(api.evalAddExamples).toHaveBeenCalledWith("eval", [{ item: "A concrete next step", label: "good", note: "Useful and concise" }]));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Add example" })).not.toBeInTheDocument());
  expect(within(screen.getByRole("region", { name: "Examples (1)" })).getByText("A concrete next step")).toBeVisible();
});

it("keeps failed submissions editable and clears canceled input", async () => {
  api.evalAddExamples.mockRejectedValueOnce(new Error("Could not save"));
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Add example" }));
  const form = within(await screen.findByRole("region", { name: "Add example" }));
  fireEvent.change(form.getByRole("textbox", { name: "Example output" }), { target: { value: "Keep this draft" } });
  fireEvent.click(form.getByRole("button", { name: "Add example" }));
  expect(await form.findByRole("alert")).toHaveTextContent("Could not save");
  expect(form.getByRole("textbox", { name: "Example output" })).toHaveValue("Keep this draft");
  fireEvent.click(form.getByRole("button", { name: "Cancel" }));
  fireEvent.click(screen.getByRole("button", { name: "Add example" }));
  expect(within(await screen.findByRole("region", { name: "Add example" })).getByRole("button", { name: "Add example" })).toBeDisabled();
  expect(screen.getByRole("textbox", { name: "Example output" })).toHaveValue("");
});


it("opens a compact example row for feedback and tests the selected content", async () => {
  api.imGet.mockResolvedValue({ ...detail, draft: null, active: { ...version, id: "active", status: "active", head: {}, head_stale: false } });
  api.imExamples.mockResolvedValue([{ id: "row", item: "A concrete next step", label: "good", note: "Useful", split: "train" }]);
  api.imPredict.mockResolvedValue({ label: "good", confidence: 0.9, probabilities: { good: 0.9, bad: 0.1 }, version: 1, rubric: {} });
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect example 1" }));
  const form = within(await screen.findByRole("region", { name: "Example 1" }));
  fireEvent.change(form.getByRole("textbox", { name: "Feedback for example row" }), { target: { value: "Use a concrete timeline" } });
  fireEvent.blur(form.getByRole("textbox", { name: "Feedback for example row" }));
  await waitFor(() => expect(api.imEditExample).toHaveBeenCalledWith("eval", "row", { note: "Use a concrete timeline" }));
  await waitFor(() => expect(form.getByRole("button", { name: "Open in sandbox" })).toBeEnabled());
  fireEvent.click(form.getByRole("button", { name: "Open in sandbox" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Example output" })).toHaveValue("A concrete next step");
  expect(api.imPredict).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Run eval" }));
  await waitFor(() => expect(api.imPredict).toHaveBeenCalledWith("eval", "A concrete next step", "active"));
  fireEvent.change(screen.getByRole("textbox", { name: "Example output" }), { target: { value: "Edited output" } });
  fireEvent.click(screen.getByRole("button", { name: "Run eval" }));
  await waitFor(() => expect(api.imPredict).toHaveBeenLastCalledWith("eval", "Edited output", "active"));
});


it("expands details directly after a clicked row and collapses on a second click", async () => {
  api.imExamples.mockResolvedValue([{ id: "first", item: "First reply", label: "good", note: "Clear", split: "train" }, { id: "second", item: "Second reply", label: "bad", note: "Vague", split: "train" }]);
  render(<EvalWorkspace id="eval" />);
  const trigger = await screen.findByRole("button", { name: "Inspect example 1" });
  fireEvent.click(trigger);
  const panel = screen.getByRole("region", { name: "Example 1" });
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(trigger.closest("tr")?.nextElementSibling).toContainElement(panel);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(trigger);
  expect(screen.queryByRole("region", { name: "Example 1" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("cell", { name: "Vague" }));
  expect(screen.getByRole("region", { name: "Example 2" })).toBeVisible();
  expect(screen.queryByRole("region", { name: "Example 1" })).not.toBeInTheDocument();
});


it("autosaves instructions without a manual save or training trigger", async () => {
  render(<EvalWorkspace id="eval" />);
  const field = await screen.findByRole("textbox", { name: "Eval instructions" });
  fireEvent.change(field, { target: { value: "Latest instructions" } });
  expect(api.imEditDraft).not.toHaveBeenCalled();
  await waitFor(() => expect(api.imEditDraft).toHaveBeenCalledWith("eval", { description: "Latest instructions" }));
  expect(api.evalEnableUpdates).toHaveBeenCalledWith("eval");
  expect(api.imFit).not.toHaveBeenCalled();
  expect(api.imPromote).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
});

it("shows scheduled progress and a failed update with retry", async () => {
  api.evalEnableUpdates.mockResolvedValue({ state: "failed", revision: 2, completed_revision: 1, error: "Judge unavailable" });
  api.evalRetryUpdate.mockResolvedValue({ state: "pending", revision: 3, completed_revision: 1 });
  render(<EvalWorkspace id="eval" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Judge unavailable");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.getByRole("status", { name: "Eval update status" })).toHaveTextContent("Update scheduled"));
  expect(api.evalRetryUpdate).toHaveBeenCalledWith("eval");
});


it("refreshes implementation after the background update completes", async () => {
  const first = { ...detail, draft: null, active: { ...version, head: {}, head_stale: false, rubric: [{ id: "help", prompt: "Old criterion", criteria: { true: "Yes", false: "No" } }] } };
  api.imGet.mockResolvedValue(first);
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Implementation" }));
  expect(screen.getByText(/Old criterion/)).toBeVisible();
  api.imGet.mockResolvedValue({ ...first, active: { ...first.active, rubric: [{ id: "help", prompt: "Updated criterion", criteria: { true: "Yes", false: "No" } }] } });
  api.evalUpdateStatus.mockResolvedValue({ state: "idle", revision: 2, completed_revision: 2 });
  expect(await screen.findByText(/Updated criterion/, {}, { timeout: 4500 })).toBeVisible();
  expect(api.imGet).toHaveBeenCalledTimes(2);
});

it("retains failed instruction edits and retries the same text", async () => {
  api.imEditDraft.mockRejectedValueOnce(new Error("Cannot persist changes")).mockResolvedValue(undefined);
  render(<EvalWorkspace id="eval" />);
  const field = await screen.findByRole("textbox", { name: "Eval instructions" });
  fireEvent.change(field, { target: { value: "Keep this text" } });
  fireEvent.blur(field);
  expect(await screen.findByRole("alert")).toHaveTextContent("Cannot persist changes");
  expect(field).toHaveValue("Keep this text");
  fireEvent.click(screen.getByRole("button", { name: "Retry changes" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(api.imEditDraft).toHaveBeenLastCalledWith("eval", { description: "Keep this text" });
});


it("autosaves example feedback and retains changes on failure", async () => {
  api.imExamples.mockResolvedValue([{ id: "example", item: "A reply", label: "good", split: "train", note: "Original" }]);
  api.imEditExample.mockRejectedValueOnce(new Error("Could not save feedback")).mockResolvedValue(undefined);
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect example 1" }));
  const field = screen.getByRole("textbox", { name: "Feedback for example example" });
  fireEvent.change(field, { target: { value: "More precise feedback" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save feedback");
  expect(field).toHaveValue("More precise feedback");
  fireEvent.click(screen.getByRole("button", { name: "Retry feedback" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(api.imEditExample).toHaveBeenLastCalledWith("eval", "example", { note: "More precise feedback" });
  expect(screen.queryByRole("button", { name: "Save feedback" })).not.toBeInTheDocument();
});
