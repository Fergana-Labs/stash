import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AutosaveTextarea from "./AutosaveTextarea";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
const tick = () => act(async () => { await vi.advanceTimersByTimeAsync(500); });

it("keeps newer typing while an earlier save is in flight, then saves it in order", async () => {
  let finish!: () => void;
  const save = vi.fn().mockImplementationOnce(() => new Promise<void>((r) => { finish = r; })).mockResolvedValue(undefined);
  const onSaved = vi.fn();
  const { rerender } = render(<AutosaveTextarea value="Original" label="Instructions" save={save} onSaved={onSaved} />);
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: "First edit" } });
  await tick();
  expect(save).toHaveBeenCalledExactlyOnceWith("First edit");
  fireEvent.change(input, { target: { value: "Latest edit" } });
  rerender(<AutosaveTextarea value="First edit" label="Instructions" save={save} onSaved={onSaved} />);
  expect(input).toHaveValue("Latest edit");
  await act(async () => finish());
  expect(save.mock.calls.map(([value]) => value)).toEqual(["First edit", "Latest edit"]);
  expect(screen.getByRole("status")).toHaveTextContent("Saved");
});

it("retains a failed edit and retries explicitly", async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error("Connection lost")).mockResolvedValue(undefined);
  render(<AutosaveTextarea value="Old" label="Feedback" save={save} onSaved={vi.fn()} />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Keep this reason" } });
  await tick();
  expect(screen.getByRole("alert")).toHaveTextContent("Connection lost");
  expect(screen.getByRole("textbox")).toHaveValue("Keep this reason");
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Retry save" })));
  expect(save).toHaveBeenLastCalledWith("Keep this reason");
  expect(screen.getByRole("status")).toHaveTextContent("Saved");
});

it("flushes a pending edit when its inspector closes before the debounce", async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  const { unmount } = render(<AutosaveTextarea value="Old" label="Feedback" save={save} onSaved={vi.fn()} />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Final reason" } });
  await act(async () => unmount());
  expect(save).toHaveBeenCalledExactlyOnceWith("Final reason");
});
