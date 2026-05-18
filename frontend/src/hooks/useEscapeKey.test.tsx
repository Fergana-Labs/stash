import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useEscapeKey } from "./useEscapeKey";

function EscapeTarget({
  active,
  label,
  onEscape,
}: {
  active: boolean;
  label: string;
  onEscape: () => void;
}) {
  useEscapeKey(active, onEscape);
  return <div>{label}</div>;
}

describe("useEscapeKey", () => {
  afterEach(() => {
    cleanup();
  });

  it("calls the active escape handler", () => {
    const onEscape = vi.fn();

    render(<EscapeTarget active={true} label="Dialog" onEscape={onEscape} />);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onEscape).toHaveBeenCalledTimes(1);
  });

  it("only calls the topmost active handler", () => {
    const first = vi.fn();
    const second = vi.fn();

    const { rerender } = render(
      <>
        <EscapeTarget active={true} label="First" onEscape={first} />
        <EscapeTarget active={true} label="Second" onEscape={second} />
      </>
    );

    fireEvent.keyDown(document, { key: "Escape" });

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);

    rerender(
      <>
        <EscapeTarget active={true} label="First" onEscape={first} />
        <EscapeTarget active={false} label="Second" onEscape={second} />
      </>
    );

    fireEvent.keyDown(document, { key: "Escape" });

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });
});
