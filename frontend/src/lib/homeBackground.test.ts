import { describe, expect, it } from "vitest";
import { homeBackgroundStyle } from "./homeBackground";

describe("homeBackgroundStyle", () => {
  it("renders a three-color gradient background", () => {
    expect(
      homeBackgroundStyle({
        kind: "gradient",
        gradient_start: "#111111",
        gradient_middle: "#222222",
        gradient_end: "#333333",
        image_url: null,
      })
    ).toEqual({
      background: "linear-gradient(90deg, #111111, #222222, #333333)",
    });
  });

  it("renders image backgrounds with cover positioning", () => {
    expect(
      homeBackgroundStyle({
        kind: "image",
        gradient_start: "#111111",
        gradient_middle: "#222222",
        gradient_end: "#333333",
        image_url: "https://example.com/cover.jpg",
      })
    ).toEqual({
      backgroundImage:
        'linear-gradient(90deg, rgba(55, 53, 47, 0.48), rgba(55, 53, 47, 0.12)), url("https://example.com/cover.jpg")',
      backgroundPosition: "center",
      backgroundSize: "cover",
    });
  });
});
