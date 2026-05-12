import type { CSSProperties } from "react";
import type { HomeBackground } from "./types";

export function homeBackgroundStyle(background: HomeBackground): CSSProperties {
  if (background.kind === "image") {
    return {
      backgroundImage: `linear-gradient(90deg, rgba(55, 53, 47, 0.48), rgba(55, 53, 47, 0.12)), url(${JSON.stringify(
        background.image_url
      )})`,
      backgroundPosition: "center",
      backgroundSize: "cover",
    };
  }

  return {
    background: `linear-gradient(90deg, ${background.gradient_start}, ${background.gradient_middle}, ${background.gradient_end})`,
  };
}
