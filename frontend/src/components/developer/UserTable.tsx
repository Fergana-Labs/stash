"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { Code } from "@/components/developer/DocsPrimitives";
import WikiToggle from "@/components/developer/WikiToggle";
import type { EndUser } from "@/lib/types";

export default function UserTable({ users, onChanged }: { users: EndUser[]; onChanged: () => void }) {
  if (users.length === 0) {
    return (
      <p className="rounded border border-dashed border-border px-6 py-10 text-center text-[15px] leading-7 text-muted-foreground">
        No users yet. Users appear automatically the first time your backend uploads a session
        with a new <Code>user_id</Code>.
      </p>
    );
  }
  return (
    <div className="overflow-hidden rounded border border-border bg-surface">
      {users.map((user) => (
        <Link
          key={user.id}
          href={`/developer/users/${user.id}`}
          className="flex items-center gap-4 border-b border-border px-5 py-4 transition-colors last:border-b-0 hover:bg-raised"
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[15px] font-medium text-foreground">
              {user.name}
            </span>
            <span className="mt-0.5 block truncate font-mono text-[12px] text-muted-foreground">
              {user.external_id} · {user.session_count} session
              {user.session_count === 1 ? "" : "s"}
              {user.last_session_at &&
                ` · last ${new Date(user.last_session_at).toLocaleDateString()}`}
            </span>
          </span>
          <WikiToggle user={user} onChanged={onChanged} />
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        </Link>
      ))}
    </div>
  );
}
