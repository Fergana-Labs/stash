/** The Minecraft hopper the feature is named after: a wide open mouth, walls
 *  tapering in, and a spout underneath. Drawn to lucide's conventions (24-unit
 *  grid, 1.5 stroke, currentColor) so it sits correctly beside the rail's
 *  other icons. */
export default function HopperIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* One continuous silhouette — wide mouth, shoulders angling in, square
          spout. Drawn as a single outline rather than stacked boxes: at 18px
          the internal edges of separate shapes merge into mush. */}
      <path d="M3 4h18v6h-3l-3.5 4v4h-5v-4L6 10H3z" />
      {/* the lip, which makes the top read as an open container */}
      <path d="M3 10h18" />
    </svg>
  );
}
