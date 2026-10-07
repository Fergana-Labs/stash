import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { wbEditChange, wbInstructionReleases, wbReleaseChange, type WorkbenchChange } from "@/lib/workbench-api";
import ChangeEditor from "./ChangeEditor";

vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/workbench-api", async (original) => ({ ...await original<typeof import("@/lib/workbench-api")>(), wbEditChange: vi.fn(), wbInstructionReleases: vi.fn(), wbReleaseChange: vi.fn() }));

const change: WorkbenchChange = { id: "change-1", kind: "instruction", status: "checked", title: "Report failing tests", feedback_id: "feedback-1", grader_id: "grader-1", content: { text: "Inspect the recorded exit code before reporting that tests pass." }, check_report: { passed: true, quality_measured: false }, created_at: "2026-10-06T12:00:00Z", released_at: null };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(wbInstructionReleases).mockResolvedValue([]); });

it("prevents release of edits that have not passed their own check", async () => {
  vi.mocked(wbEditChange).mockResolvedValue({ ...change, status: "draft" });
  const onChanged = vi.fn().mockResolvedValue(undefined);
  render(<ChangeEditor change={change} onChanged={onChanged} />);
  expect(screen.getByRole("button", { name: "Release for agent use" })).toBeEnabled();
  fireEvent.change(screen.getByRole("textbox", { name: /Exact agent instructions/ }), { target: { value: "Name failures before reporting the test result." } });
  expect(screen.getByRole("button", { name: "Release for agent use" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Check saved change" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => expect(wbEditChange).toHaveBeenCalledWith("change-1", { text: "Name failures before reporting the test result." }));
  expect(wbReleaseChange).not.toHaveBeenCalled();
});

it("does not enable release when independent quality checks are unavailable", () => {
  render(<ChangeEditor change={{ ...change, kind: "grader", check_report: { passed: false, quality_measured: false, total: 0, message: "Quality check unavailable: no independent reviewed examples" } }} onChanged={vi.fn()} />);
  expect(screen.getByText(/Quality check unavailable/, { selector: "p" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Release grader version" })).toBeDisabled();
});

it("does not describe offered instructions as loaded and links captured receipts to the event", () => {
  render(<ChangeEditor change={{ ...change, status: "released", delivery_records: [{ id: "offer", grader_id: "grader-1", release_id: "release-1", change_id: "change-1", session_id: "session-1", source_format: "codex", repository: "/stash", content: "Check results", content_sha256: "hash", status: "offered", trace_id: null, step_id: null, offered_at: "2026-10-06T12:00:00Z", captured_at: null }, { id: "receipt", grader_id: "grader-1", release_id: "release-1", change_id: "change-1", session_id: "session-2", source_format: "codex", repository: "/stash", content: "Check results", content_sha256: "hash", status: "captured", trace_id: "trace-2", step_id: "instructions", offered_at: "2026-10-06T12:00:00Z", captured_at: "2026-10-06T12:01:00Z" }] }} onChanged={vi.fn()} />);
  expect(screen.getByText(/Loading into the agent’s context is unconfirmed/)).toBeVisible();
  expect(screen.getByRole("link", { name: "Open captured run" })).toHaveAttribute("href", "/reward-models/traces/trace-2#step-instructions");
  expect(screen.getByText(/no improvement is established by delivery alone/)).toBeVisible();
});

it("requires explicit unmeasured-new-requirement acceptance when the server permits it", async () => {
  vi.mocked(wbReleaseChange).mockResolvedValue({ ...change, status: "released" });
  render(<ChangeEditor change={{ ...change, kind: "grader", check_report: { passed: false, quality_measured: false, can_accept_unmeasured: true } }} onChanged={vi.fn().mockResolvedValue(undefined)} />);
  const release = screen.getByRole("button", { name: "Activate new requirement (unmeasured)" });
  expect(release).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: /I confirm this is a new requirement/ }));
  fireEvent.click(release);
  await waitFor(() => expect(wbReleaseChange).toHaveBeenCalledWith("change-1", true));
});

it("retains partial comparison results without displaying missing judgments as errors", () => {
  render(<ChangeEditor change={{ ...change, kind: "grader", status: "failed", error: "Candidate provider timed out", check_report: { passed: false, running: true, cases: [{ assessment_id: "case-1", trace_id: "trace-1", label: "violates", current_verdict: "violates", current_correct: true }] } }} onChanged={vi.fn()} />);
  expect(screen.getByRole("cell", { name: "Not completed" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "violates ✓" })).toBeVisible();
  expect(screen.getByRole("alert")).toHaveTextContent("Candidate provider timed out");
  expect(screen.getByRole("button", { name: "Release grader version" })).toBeDisabled();
});
