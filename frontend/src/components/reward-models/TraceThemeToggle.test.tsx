import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import TraceThemeToggle from "./TraceThemeToggle";

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); delete document.documentElement.dataset.theme; });
it("uses saved theme, toggles tokens, and keeps the choice when remounted", async () => {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  localStorage.setItem("stash-theme", "dark");
  const view = render(<TraceThemeToggle />);
  expect(document.documentElement.dataset.theme).toBe("dark");
  fireEvent.click(await screen.findByRole("button", { name: "Switch to light mode" }));
  await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
  expect(localStorage.getItem("stash-theme")).toBe("light");
  view.unmount();
  render(<TraceThemeToggle />);
  expect(await screen.findByRole("button", { name: "Switch to dark mode" })).toBeVisible();
});
