"use client";

/**
 * Legacy route — redirects to home.
 * Chats now live at /workspaces/[workspaceId] (chat selected within workspace view).
 * DMs live at /dms/[chatId].
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function LegacyRoomPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return (
    <div className="min-h-screen flex items-center justify-center text-muted">
      Redirecting...
    </div>
  );
}
