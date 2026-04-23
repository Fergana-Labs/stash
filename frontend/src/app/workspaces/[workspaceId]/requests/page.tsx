"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../../../components/AppShell";
import { useAuth } from "../../../../hooks/useAuth";
import {
  approveJoinRequest,
  denyJoinRequest,
  getWorkspace,
  listJoinRequests,
} from "../../../../lib/api";
import { JoinRequest, Workspace } from "../../../../lib/types";

export default function JoinRequestsPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading, logout } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [requests, setRequests] = useState<JoinRequest[]>([]);
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [ws, jr] = await Promise.all([
        getWorkspace(workspaceId),
        listJoinRequests(workspaceId),
      ]);
      setWorkspace(ws);
      setRequests(jr.requests);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, [workspaceId]);

  useEffect(() => {
    if (user) loadData();
  }, [user, loadData]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const handleApprove = async (requestId: string) => {
    setProcessing(requestId);
    try {
      await approveJoinRequest(workspaceId, requestId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve");
    }
    setProcessing(null);
  };

  const handleDeny = async (requestId: string) => {
    setProcessing(requestId);
    try {
      await denyJoinRequest(workspaceId, requestId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to deny");
    }
    setProcessing(null);
  };

  if (loading)
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Loading...
      </div>
    );
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-2xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <button
              onClick={() => router.push(`/workspaces/${workspaceId}`)}
              className="text-xs text-brand hover:text-brand-hover mb-1 inline-block"
            >
              &larr; Back to workspace
            </button>
            <h1 className="text-lg font-semibold text-foreground">
              Join Requests
            </h1>
            {workspace && (
              <p className="text-sm text-dim">{workspace.name}</p>
            )}
          </div>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-800 text-red-400 text-sm px-4 py-2 rounded mb-4">
            {error}
            <button
              onClick={() => setError("")}
              className="ml-2 text-red-500 hover:text-red-300"
            >
              &times;
            </button>
          </div>
        )}

        {requests.length === 0 ? (
          <div className="bg-surface border border-border rounded-xl px-6 py-10 text-center">
            <p className="text-dim">No pending join requests.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {requests.map((req) => (
              <div
                key={req.id}
                className="bg-surface border border-border rounded-xl px-5 py-4 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-human-muted text-human flex items-center justify-center text-sm font-bold">
                    {(
                      req.user_display_name ||
                      req.user_name ||
                      "?"
                    )
                      .charAt(0)
                      .toUpperCase()}
                  </div>
                  <div>
                    <div className="text-sm text-foreground font-medium">
                      {req.user_display_name || req.user_name}
                    </div>
                    {req.user_name && (
                      <div className="text-xs text-muted">
                        @{req.user_name}
                      </div>
                    )}
                    <div className="text-xs text-muted">
                      Requested{" "}
                      {new Date(req.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleApprove(req.id)}
                    disabled={processing === req.id}
                    className="text-xs bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => handleDeny(req.id)}
                    disabled={processing === req.id}
                    className="text-xs text-red-400 hover:text-red-300 border border-border hover:border-red-800 px-4 py-1.5 rounded disabled:opacity-50"
                  >
                    Deny
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
