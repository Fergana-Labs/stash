import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ExploreOutlinedIcon from "@mui/icons-material/ExploreOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import HelpOutlineOutlinedIcon from "@mui/icons-material/HelpOutlineOutlined";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import PersonOutlineOutlinedIcon from "@mui/icons-material/PersonOutlineOutlined";
import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import PushPinOutlinedIcon from "@mui/icons-material/PushPinOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import ScheduleOutlinedIcon from "@mui/icons-material/ScheduleOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import type { SvgIconProps } from "@mui/material/SvgIcon";
import type { ComponentType } from "react";

type IconProps = {
  className?: string;
};

function iconClass(className?: string) {
  return ["inline-block shrink-0", className].filter(Boolean).join(" ");
}

function MaterialIcon({
  icon: Icon,
  className,
}: IconProps & {
  icon: ComponentType<SvgIconProps>;
}) {
  return (
    <Icon
      aria-hidden="true"
      className={iconClass(className)}
      fontSize="inherit"
    />
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

export function StashIcon(props: IconProps) {
  return <LowResOctopusIcon {...props} />;
}

export function WorkspaceIcon(props: IconProps) {
  return <LowResOctopusIcon {...props} />;
}

export function SessionsIcon(props: IconProps) {
  return <MaterialIcon icon={ForumOutlinedIcon} {...props} />;
}

export function FolderIcon(props: IconProps) {
  return <MaterialIcon icon={FolderOutlinedIcon} {...props} />;
}

export function PageIcon(props: IconProps) {
  return <MaterialIcon icon={DescriptionOutlinedIcon} {...props} />;
}

export function FileIcon(props: IconProps) {
  return <MaterialIcon icon={InsertDriveFileOutlinedIcon} {...props} />;
}

export function TableIcon(props: IconProps) {
  return <MaterialIcon icon={TableChartOutlinedIcon} {...props} />;
}

export function ActivityIcon(props: IconProps) {
  return <MaterialIcon icon={ScheduleOutlinedIcon} {...props} />;
}

export function DiscoverIcon(props: IconProps) {
  return <MaterialIcon icon={ExploreOutlinedIcon} {...props} />;
}

export function HelpIcon(props: IconProps) {
  return <MaterialIcon icon={HelpOutlineOutlinedIcon} {...props} />;
}

export function SettingsIcon(props: IconProps) {
  return <MaterialIcon icon={SettingsOutlinedIcon} {...props} />;
}

export function NotificationsIcon(props: IconProps) {
  return <MaterialIcon icon={NotificationsNoneOutlinedIcon} {...props} />;
}

export function PersonIcon(props: IconProps) {
  return <MaterialIcon icon={PersonOutlineOutlinedIcon} {...props} />;
}

export function TrashIcon(props: IconProps) {
  return <MaterialIcon icon={DeleteOutlineOutlinedIcon} {...props} />;
}

export function CloseIcon(props: IconProps) {
  return <MaterialIcon icon={CloseOutlinedIcon} {...props} />;
}

export function PinIcon(props: IconProps) {
  return <MaterialIcon icon={PushPinOutlinedIcon} {...props} />;
}

export function SearchIcon(props: IconProps) {
  return <MaterialIcon icon={SearchOutlinedIcon} {...props} />;
}
