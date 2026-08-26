/** The minimap exists so a person can see at a glance where the human spoke
 * in a long wall of agent work. If the role → tone mapping drifts — human
 * turns losing their accent, tool spam rendering as loud as prose — the strip
 * degrades into uniform noise, so the mapping is pinned here.
 */
import { describe, expect, it } from "vitest";
import { MINIMAP_MIN_TURNS, MINIMAP_TONE_CLASS, minimapTone } from "./minimap";

describe("minimapTone", () => {
  it("accents human turns — the landmarks the strip exists for", () => {
    expect(minimapTone({ who: "user", toolName: null })).toBe("human");
  });

  it("renders agent prose at the medium tone", () => {
    expect(minimapTone({ who: "assistant", toolName: null })).toBe("agent");
  });

  it("fades tool-use turns so tool spam does not drown the map", () => {
    expect(minimapTone({ who: "assistant", toolName: "Bash" })).toBe("faint");
  });

  it("fades the scheduled-run system prompt like tool noise", () => {
    expect(minimapTone({ who: "system", toolName: null })).toBe("faint");
  });
});

describe("tone classes", () => {
  it("keeps the three tones visually distinct", () => {
    expect(new Set(Object.values(MINIMAP_TONE_CLASS)).size).toBe(3);
  });

  it("colors human turns with the app's human accent token", () => {
    expect(MINIMAP_TONE_CLASS.human).toContain("--color-human");
  });
});

describe("MINIMAP_MIN_TURNS", () => {
  it("hides the strip for sessions short enough to just scroll", () => {
    expect(MINIMAP_MIN_TURNS).toBe(15);
  });
});
