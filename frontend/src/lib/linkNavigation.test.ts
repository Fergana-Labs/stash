import { describe, expect, it } from "vitest";
import { shouldOpenInNewTab } from "./linkNavigation";

describe("shouldOpenInNewTab", () => {
  it("opens command/control clicks in a new tab", () => {
    expect(shouldOpenInNewTab({ metaKey: true, ctrlKey: false, button: 0 })).toBe(true);
    expect(shouldOpenInNewTab({ metaKey: false, ctrlKey: true, button: 0 })).toBe(true);
  });

  it("opens middle clicks in a new tab", () => {
    expect(shouldOpenInNewTab({ metaKey: false, ctrlKey: false, button: 1 })).toBe(true);
  });

  it("keeps normal primary clicks in the current tab", () => {
    expect(shouldOpenInNewTab({ metaKey: false, ctrlKey: false, button: 0 })).toBe(false);
  });
});
