import {
  MessagesSquare,
  Folder,
  FileText,
  File,
  Table,
  Clock,
  Compass,
  CircleHelp,
  Settings,
  Bell,
  User,
  Trash2,
  X,
  Pin,
  Search,
  type LucideIcon,
} from "lucide-react";

type IconProps = {
  className?: string;
};

function iconClass(className?: string) {
  return ["inline-block shrink-0", className].filter(Boolean).join(" ");
}

/** Render a lucide icon sized to the current font-size (1em) by default, so it
 *  behaves like the outlined MUI icons it replaced. A `className` with an
 *  explicit size (e.g. `w-4 h-4`) still overrides via CSS. */
function Icon({ icon: LucideGlyph, className }: IconProps & { icon: LucideIcon }) {
  return (
    <LucideGlyph aria-hidden="true" className={iconClass(className)} width="1em" height="1em" />
  );
}

function LowResOctopusIcon({ className }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      className={iconClass(className)}
      width="1em"
      height="1em"
      viewBox="0 0 24 24"
      shapeRendering="crispEdges"
    >
      <g fill="currentColor">
        <rect x="8" y="4" width="8" height="2" />
        <rect x="6" y="6" width="12" height="8" />
        <rect x="4" y="9" width="2" height="5" />
        <rect x="18" y="9" width="2" height="5" />
        <rect x="5" y="14" width="3" height="3" />
        <rect x="10" y="14" width="2" height="5" />
        <rect x="14" y="14" width="2" height="5" />
        <rect x="17" y="14" width="3" height="3" />
      </g>
      <g fill="var(--bg-base)">
        <rect x="9" y="8" width="2" height="2" />
        <rect x="13" y="8" width="2" height="2" />
      </g>
    </svg>
  );
}

export function SkillIcon(props: IconProps) {
  return <LowResOctopusIcon {...props} />;
}

/** The brand mark — the same octopus as the favicon and the landing page
 *  (public/octopus.svg), inlined so it sizes with text like every icon here.
 *  Full-color on purpose: this is the logo, not a themed glyph. */
export function StashIcon({ className }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      className={iconClass(className)}
      width="1em"
      height="1em"
      viewBox="0 0 64 72"
    >
      <ellipse cx="32" cy="24" rx="22" ry="18" fill="#F97316" />
      <circle cx="25" cy="22" r="4" fill="#fff" />
      <circle cx="39" cy="22" r="4" fill="#fff" />
      <circle cx="26" cy="22" r="2" fill="#0F172A" />
      <circle cx="40" cy="22" r="2" fill="#0F172A" />
      <path d="M12 38 Q8 52 4 60" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M20 40 Q18 54 14 62" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M32 42 Q32 56 32 64" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M44 40 Q46 54 50 62" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M52 38 Q56 52 60 60" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
    </svg>
  );
}

export function SessionsIcon(props: IconProps) {
  return <Icon icon={MessagesSquare} {...props} />;
}

export function FolderIcon(props: IconProps) {
  return <Icon icon={Folder} {...props} />;
}

export function PageIcon(props: IconProps) {
  return <Icon icon={FileText} {...props} />;
}

export function FileIcon(props: IconProps) {
  return <Icon icon={File} {...props} />;
}

export function TableIcon(props: IconProps) {
  return <Icon icon={Table} {...props} />;
}

export function ActivityIcon(props: IconProps) {
  return <Icon icon={Clock} {...props} />;
}

export function DiscoverIcon(props: IconProps) {
  return <Icon icon={Compass} {...props} />;
}

export function HelpIcon(props: IconProps) {
  return <Icon icon={CircleHelp} {...props} />;
}

export function SettingsIcon(props: IconProps) {
  return <Icon icon={Settings} {...props} />;
}

export function NotificationsIcon(props: IconProps) {
  return <Icon icon={Bell} {...props} />;
}

export function PersonIcon(props: IconProps) {
  return <Icon icon={User} {...props} />;
}

export function TrashIcon(props: IconProps) {
  return <Icon icon={Trash2} {...props} />;
}

export function CloseIcon(props: IconProps) {
  return <Icon icon={X} {...props} />;
}

export function PinIcon(props: IconProps) {
  return <Icon icon={Pin} {...props} />;
}

export function SearchIcon(props: IconProps) {
  return <Icon icon={Search} {...props} />;
}
