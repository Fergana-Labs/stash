import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import EvalWorkspace from "./EvalWorkspace";
import CreateEval from "./CreateEval";

const api = vi.hoisted(() => ({ imGet: vi.fn(), imExamples: vi.fn(), imEditDraft: vi.fn(), evalPrepare: vi.fn(), imDraftRubric: vi.fn(), imGrade: vi.fn(), imFit: vi.fn(), imPromote: vi.fn(), evalAddExamples: vi.fn(), evalAddTrace: vi.fn(), imEditExample: vi.fn(), imPredict: vi.fn(), imPredictions: vi.fn(), imReview: vi.fn(), imCreate: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);
vi.mock("./EvalInput", () => ({ default: ({ initialItem, onChange }: { initialItem?: string; onChange: (item: string) => void }) => <textarea aria-label="Example output" defaultValue={initialItem ?? ""} onChange={(event) => onChange(event.target.value)} /> }));

const version = { id: "draft", status: "draft", number: 1, description: "Be helpful", labels: [{ id: "good" }, { id: "bad" }], rubric: [], head: null, head_stale: true, metrics: null, gate: null };
const detail = { model: { id: "eval", name: "Replies", output_type: "choice" }, draft: version, active: null, judge: { configured: true }, versions: [], counts: {} };

beforeEach(() => {
  vi.clearAllMocks(); api.imGet.mockResolvedValue(detail); api.imExamples.mockResolvedValue([]);
  api.imGrade.mockResolvedValue({ graded: 5, remaining: 0, failed: 0 });
  api.imDraftRubric.mockResolvedValue({ rubric: [{ id: "helpful", prompt: "Is it helpful?" }] });
  api.imPredictions.mockResolvedValue([]);
  api.imEditDraft.mockResolvedValue(undefined); api.imPromote.mockResolvedValue(detail);
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

it("prepares the held-out split before drafting criteria and fits only calibration data", async () => {
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Save" }));
  await waitFor(() => expect(api.imFit).toHaveBeenCalledWith("eval", { train_on: "train", calibrate: true }));
  expect(api.evalPrepare.mock.invocationCallOrder[0]).toBeLessThan(api.imDraftRubric.mock.invocationCallOrder[0]);
  expect(api.imGrade.mock.invocationCallOrder[0]).toBeLessThan(api.imFit.mock.invocationCallOrder[0]);
  await waitFor(() => expect(api.imPromote).toHaveBeenCalledWith("eval", true));
  expect(api.imFit.mock.invocationCallOrder[0]).toBeLessThan(api.imPromote.mock.invocationCallOrder[0]);
  expect(api.imDraftRubric).toHaveBeenCalledWith("eval", {});
});

it("shows failed grading and does not calibrate or activate partial results", async () => {
  api.imGrade.mockResolvedValue({ graded: 2, remaining: 1, failed: 1, errors: ["Judge unavailable"] });
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Judge unavailable");
  expect(api.imFit).not.toHaveBeenCalled(); expect(api.imPromote).not.toHaveBeenCalled();
});

it("keeps limited-data checks visible without a separate activation step", async () => {
  api.imGet.mockResolvedValue({ ...detail, draft: null, active: { ...version, id: "active", status: "active", head: {}, head_stale: false, rubric: [{ id: "helpful", prompt: "Is it helpful?" }], metrics: { eval: { n: 1, accuracy: 0, rows: [{ example_id: "held", label: "good", predicted: "bad", p_true: 0.3 }] } }, gate: { passed: false, checks: [{ name: "held_out_size", passed: false, detail: "1 held-out example; need 4" }] } } });
  api.imExamples.mockResolvedValue([{ id: "held", item: "A held-out slide", label: "good", split: "eval", note: "" }]);
  render(<EvalWorkspace id="eval" />);
  expect(await screen.findByText("0 of 1 labels matched")).toBeVisible();
  expect(screen.getByText("Probability of your label: 30%")).toBeVisible();
  const checks = screen.getByRole("region", { name: "Held-out checks" });
  expect(within(checks).getByText("Limited data")).toBeVisible();
  expect(within(checks).queryByText("Is it helpful?")).not.toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Evaluation criteria" })).getByText("Is it helpful?")).toBeVisible();
  expect(screen.queryByRole("button", { name: /Activate/ })).not.toBeInTheDocument();
  expect(screen.queryByText("Draft")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(api.imPromote).toHaveBeenCalledWith("eval", true));
  expect(await screen.findByRole("status", { name: "Save status" })).toHaveTextContent("Eval saved");
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
  expect(await screen.findByText("Correction added. Save the eval to include it.")).toBeVisible();
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


it("shows immediate progress beside the build button, hides old results, then offers a test action", async () => {
  api.imGet.mockResolvedValue({ ...detail, draft: null, active: { ...version, id: "active", status: "active", head: {}, head_stale: false, metrics: { eval: { n: 1, accuracy: 1, rows: [] } } } });
  let finishDraft!: (value: unknown) => void;
  api.imDraftRubric.mockReturnValueOnce(new Promise((resolve) => { finishDraft = resolve; }));
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Save" }));
  expect(screen.queryByText("1 of 1 labels matched")).not.toBeInTheDocument();
  const running = screen.getByRole("button", { name: "Saving…" });
  expect(running).toBeDisabled();
  expect(await screen.findByRole("status", { name: "Save status" })).toHaveTextContent("Creating evaluation criteria");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  await act(async () => { finishDraft({ rubric: [{ id: "helpful", prompt: "Is it helpful?" }] }); });
  expect(await screen.findByRole("button", { name: "Open sandbox" })).toBeVisible();
  expect(screen.getByRole("status", { name: "Save status" })).toHaveTextContent("Eval saved");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "4");
  fireEvent.click(screen.getByRole("button", { name: "Open sandbox" }));
  expect(screen.getByRole("button", { name: "Run eval" })).toBeVisible();
});

it("shows a failed build at the button and makes retry available without fitting partial grades", async () => {
  api.imGrade.mockResolvedValueOnce({ graded: 1, remaining: 1, failed: 1, errors: ["Judge unavailable"] });
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Save" }));
  expect(await screen.findByRole("button", { name: "Save" })).toBeEnabled();
  expect(screen.getByRole("status", { name: "Save status" })).toHaveTextContent("Could not save the eval");
  expect(screen.getByRole("alert")).toHaveTextContent("Judge unavailable");
  expect(api.imFit).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Open sandbox" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("button", { name: "Open sandbox" })).toBeVisible();
  expect(api.imFit).toHaveBeenCalledOnce();
});


it("opens a compact example row for feedback and tests the selected content", async () => {
  api.imGet.mockResolvedValue({ ...detail, draft: null, active: { ...version, id: "active", status: "active", head: {}, head_stale: false } });
  api.imExamples.mockResolvedValue([{ id: "row", item: "A concrete next step", label: "good", note: "Useful", split: "train" }]);
  api.imPredict.mockResolvedValue({ label: "good", confidence: 0.9, probabilities: { good: 0.9, bad: 0.1 }, version: 1, rubric: {} });
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect example 1" }));
  const form = within(await screen.findByRole("region", { name: "Example 1" }));
  fireEvent.change(form.getByRole("textbox", { name: "Feedback for example row" }), { target: { value: "Use a concrete timeline" } });
  fireEvent.click(form.getByRole("button", { name: "Save feedback" }));
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


it("saves the latest instructions only when Save is clicked and applies them after successful scoring", async () => {
  render(<EvalWorkspace id="eval" />);
  const field = await screen.findByRole("textbox", { name: "Eval instructions" });
  fireEvent.change(field, { target: { value: "Latest instructions" } });
  fireEvent.blur(field);
  expect(api.imEditDraft).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Save instructions" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(api.imPromote).toHaveBeenCalledWith("eval", true));
  expect(api.imEditDraft).toHaveBeenNthCalledWith(1, "eval", { description: "Latest instructions" });
  expect(api.imEditDraft.mock.invocationCallOrder[0]).toBeLessThan(api.evalPrepare.mock.invocationCallOrder[0]);
  expect(api.imFit.mock.invocationCallOrder[0]).toBeLessThan(api.imPromote.mock.invocationCallOrder[0]);
});

it("keeps failed saves retryable without reporting success", async () => {
  api.imPromote.mockRejectedValueOnce(new Error("Could not persist eval"));
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not persist eval");
  expect(screen.getByRole("status", { name: "Save status" })).toHaveTextContent("Could not save the eval");
  expect(screen.queryByRole("button", { name: "Open sandbox" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("button", { name: "Open sandbox" })).toBeVisible();
  expect(screen.getByRole("status", { name: "Save status" })).toHaveTextContent("Eval saved");
});

it("tests the saved evaluator even while edits exist, and uses the updated one after Save", async () => {
  const active = { ...version, id: "active", status: "active", head: {}, head_stale: false };
  const edited = { ...version, number: 2, head: {}, head_stale: false };
  const current = { ...detail, active, draft: edited };
  api.imGet.mockResolvedValue(current);
  api.imPromote.mockImplementation(async () => {
    api.imGet.mockResolvedValue({ ...detail, active: { ...edited, id: "updated", status: "active" }, draft: null });
  });
  api.imPredict.mockResolvedValue({ label: "good", confidence: 0.9, probabilities: { good: 0.9, bad: 0.1 }, version: 1, rubric: {} });
  render(<EvalWorkspace id="eval" />);
  fireEvent.click(await screen.findByRole("button", { name: "Sandbox" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Example output" }), { target: { value: "A reply" } });
  fireEvent.click(screen.getByRole("button", { name: "Run eval" }));
  expect(await screen.findByText("90% confidence · v1")).toBeVisible();
  expect(api.imPredict).toHaveBeenLastCalledWith("eval", "A reply", "active");
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("button", { name: "Open sandbox" })).toBeVisible();
  api.imPredict.mockResolvedValue({ label: "good", confidence: 0.9, probabilities: { good: 0.9, bad: 0.1 }, version: 2, rubric: {} });
  fireEvent.click(screen.getByRole("button", { name: "Run eval" }));
  expect(await screen.findByText("90% confidence · v2")).toBeVisible();
  expect(api.imPredict).toHaveBeenLastCalledWith("eval", "A reply", "active");
});
