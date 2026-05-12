import AnalyticsOutlinedIcon from "@mui/icons-material/AnalyticsOutlined";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ExploreOutlinedIcon from "@mui/icons-material/ExploreOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import HelpOutlineOutlinedIcon from "@mui/icons-material/HelpOutlineOutlined";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import PersonOutlineOutlinedIcon from "@mui/icons-material/PersonOutlineOutlined";
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

export function StashIcon(props: IconProps) {
  return <MaterialIcon icon={AnalyticsOutlinedIcon} {...props} />;
}

export function SessionsIcon(props: IconProps) {
  return <MaterialIcon icon={ChatOutlinedIcon} {...props} />;
}

export function WikiIcon(props: IconProps) {
  return <MaterialIcon icon={MenuBookOutlinedIcon} {...props} />;
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

export function PersonIcon(props: IconProps) {
  return <MaterialIcon icon={PersonOutlineOutlinedIcon} {...props} />;
}
