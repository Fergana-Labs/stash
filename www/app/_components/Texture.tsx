// The brand's reusable surface motif: a sparse warm dot-field with a soft
// radial fade. Used behind the hero and at section seams. Decorative only —
// always aria-hidden and pointer-events-none so it never blocks the page.
export default function Texture({
  className = "",
  fade = "top",
}: {
  className?: string;
  fade?: "top" | "center" | "none";
}) {
  const mask =
    fade === "center"
      ? "radial-gradient(ellipse 70% 70% at 50% 40%, black, transparent 75%)"
      : fade === "top"
        ? "linear-gradient(to bottom, black, transparent 80%)"
        : undefined;
  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-0 z-0 ${className}`}
      style={{
        backgroundImage: "var(--dot-field)",
        backgroundSize: "var(--dot-field-size)",
        WebkitMaskImage: mask,
        maskImage: mask,
      }}
    />
  );
}
