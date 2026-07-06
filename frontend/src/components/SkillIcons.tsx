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

export function StashIcon(props: IconProps) {
  return <LowResOctopusIcon {...props} />;
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
