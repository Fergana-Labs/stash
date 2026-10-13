import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import EvalInput from "./EvalInput";
import { evalReadFile } from "@/lib/intuition-api";

vi.mock("@/lib/intuition-api", () => ({ evalReadFile: vi.fn() }));

it("preloads the selected output into the editable field and preserves it when the active source is clicked", () => {
  const change = vi.fn(); render(<EvalInput initialItem="A concrete next step" onChange={change} />);
  const field = screen.getByRole("textbox", { name: "Example output" });
  expect(field).toHaveValue("A concrete next step");
  fireEvent.click(screen.getByRole("button", { name: "Paste output" }));
  expect(field).toHaveValue("A concrete next step");
  expect(change).not.toHaveBeenCalled();
  fireEvent.change(field, { target: { value: "A different next step" } });
  expect(change).toHaveBeenLastCalledWith("A different next step");
  fireEvent.change(field, { target: { value: "" } });
  expect(change).toHaveBeenLastCalledWith(null);
});

it("preloads structured examples as editable JSON while preserving their object input type", () => {
  const item = { reply: "A concrete next step", context: { task: "refund" } };
  const change = vi.fn(); render(<EvalInput initialItem={item} onChange={change} />);
  const field = screen.getByRole("textbox", { name: "Example output" });
  expect(field).toHaveValue(JSON.stringify(item, null, 2));
  fireEvent.change(field, { target: { value: '{"reply":"Revised reply","context":{"task":"refund"}}' } });
  expect(change).toHaveBeenLastCalledWith({ reply: "Revised reply", context: { task: "refund" } });
  fireEvent.change(field, { target: { value: '{"reply":' } });
  expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid JSON object");
  expect(change).toHaveBeenLastCalledWith(null);
});

it("does not leave an old file selected after an upload fails", async () => {
  vi.mocked(evalReadFile).mockResolvedValueOnce({ name: "notes.md", content: "Good means clear" }).mockRejectedValueOnce(new Error("Could not read this file"));
  const change = vi.fn(); render(<EvalInput onChange={change} />);
  fireEvent.click(screen.getByRole("button", { name: "Upload file" }));
  fireEvent.change(screen.getByLabelText("Upload eval input"), { target: { files: [new File(["notes"], "notes.md")] } });
  await waitFor(() => expect(change).toHaveBeenLastCalledWith({ name: "notes.md", content: "Good means clear" }));
  fireEvent.change(screen.getByLabelText("Upload eval input"), { target: { files: [new File(["bad"], "bad.pdf")] } });
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not read this file");
  expect(change).toHaveBeenLastCalledWith(null);
  expect(screen.queryByText("Good means clear")).not.toBeInTheDocument();
});
