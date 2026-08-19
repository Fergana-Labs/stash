import { Folder, Inbox } from "lucide-react";

/** The Default folder reads as an inbox — it is where sessions land when the
 *  repo names no folder — and every other session folder as a plain folder. */
export default function SessionFolderIcon({
  folder,
  className,
}: {
  folder?: { is_default?: boolean } | null;
  className?: string;
}) {
  const Icon = folder?.is_default ? Inbox : Folder;
  return <Icon className={className} strokeWidth={1.75} />;
}
