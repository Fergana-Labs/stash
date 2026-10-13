import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import EvalInput from "./EvalInput";
import { evalReadFile } from "@/lib/intuition-api";

vi.mock("@/lib/intuition-api", () => ({ evalReadFile: vi.fn() }));

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
