import { fireEvent, render, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useEscapeBack } from "./useEscapeBack";
function Page({ back }: { back: () => void }) { useEscapeBack(back); return <><input aria-label="Edit" /><div contentEditable aria-label="Editor" /></>; }
it("navigates on Escape and removes the listener when leaving", async () => {
  const back = vi.fn(); const { unmount } = render(<Page back={back} />);
  fireEvent.keyDown(document, { key: "Escape" });
  await waitFor(() => expect(back).toHaveBeenCalledTimes(1));
  unmount(); fireEvent.keyDown(document, { key: "Escape" });
  await Promise.resolve(); expect(back).toHaveBeenCalledTimes(1);
});
it("yields to inputs, overlays, and an Escape event already handled by another control", async () => {
  const back = vi.fn(); const { getByLabelText } = render(<Page back={back} />);
  fireEvent.keyDown(getByLabelText("Edit"), { key: "Escape" });
  fireEvent.keyDown(getByLabelText("Editor"), { key: "Escape" });
  const dialog = document.createElement("div"); dialog.setAttribute("role", "dialog"); document.body.append(dialog);
  fireEvent.keyDown(document, { key: "Escape" }); dialog.remove();
  const handled = new KeyboardEvent("keydown", { key: "Escape", cancelable: true }); handled.preventDefault(); document.dispatchEvent(handled);
  await Promise.resolve(); expect(back).not.toHaveBeenCalled();
});
