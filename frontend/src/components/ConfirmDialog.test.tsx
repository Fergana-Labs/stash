import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { ConfirmDialogProvider, useConfirm } from "./ConfirmDialog";

// Exercises the dialog the way call sites use it: await confirm(...) gates
// a destructive action, so the resolved boolean must match the user's choice.
function Harness() {
  const confirm = useConfirm();
  const [result, setResult] = useState<string>("pending");

  const ask = async () => {
    const ok = await confirm({
      title: "Delete this column?",
      body: "This cannot be undone.",
      confirmLabel: "Delete",
    });
    setResult(ok ? "confirmed" : "cancelled");
  };

  return (
    <div>
      <button onClick={() => void ask()}>ask</button>
      <output>{result}</output>
    </div>
  );
}

function renderHarness() {
  return render(
    <ConfirmDialogProvider>
      <Harness />
    </ConfirmDialogProvider>
  );
}

afterEach(cleanup);

describe("ConfirmDialogProvider", () => {
  it("resolves true when the user confirms", async () => {
    renderHarness();
    fireEvent.click(screen.getByText("ask"));

    expect(screen.getByRole("alertdialog")).toBeTruthy();
    expect(screen.getByText("This cannot be undone.")).toBeTruthy();

    fireEvent.click(screen.getByText("Delete"));
    expect(await screen.findByText("confirmed")).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("resolves false when the user cancels", async () => {
    renderHarness();
    fireEvent.click(screen.getByText("ask"));

    fireEvent.click(screen.getByText("Cancel"));
    expect(await screen.findByText("cancelled")).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("resolves false on Escape", async () => {
    renderHarness();
    fireEvent.click(screen.getByText("ask"));

    fireEvent.keyDown(document, { key: "Escape" });
    expect(await screen.findByText("cancelled")).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});
