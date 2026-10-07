"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { EmptyState, RmPage } from "@/components/reward-models/rm-ui";
import { ErrorNotice, useWorkbenchLoad } from "@/components/workbench/workbench-ui";
import { wbFeedbackDetail, wbListFeedback } from "@/lib/workbench-api";

import FeedbackReview from "@/components/workbench/FeedbackReview";
import ReviewSamples from "@/components/workbench/ReviewSamples";

export default function ReviewPage() { return <Suspense><Review /></Suspense>; }

function Review() {
  useBreadcrumbs([{ label: "Review" }], "workbench-review");
  const feedbackId = useSearchParams().get("feedback");
  const loader = useCallback(async () => feedbackId ? [await wbFeedbackDetail(feedbackId)] : wbListFeedback(), [feedbackId]);
  const { data, loading, error, reload } = useWorkbenchLoad(loader, 5000);
  const [filter, setFilter] = useState(feedbackId ? "all" : "pending");
  const visible = data?.filter((item) => filter === "all" || item.review_status === filter) ?? [];
  return <RmPage title="Review" description="Review corrections and their proposed interpretation. Accepted feedback can prepare separate grader and agent-instruction changes; it does not release them.">
    <ErrorNotice error={error} onRetry={() => void reload()} />
    {feedbackId && <p className="text-[12px] text-muted-foreground">Viewing the source correction. <Link href="/reward-models/review" className="underline">Open all feedback</Link>.</p>}
    {!feedbackId && <ReviewSamples onLabeled={reload} />}
    <div className="mb-4 flex flex-wrap items-center gap-2">{["pending", "accepted", "rejected", "all"].map((status) => <Button key={status} variant={filter === status ? "secondary" : "ghost"} size="sm" aria-pressed={filter === status} onClick={() => setFilter(status)}>{status === "all" ? "All feedback" : status[0].toUpperCase() + status.slice(1)}{data ? ` (${data.filter((f) => status === "all" || f.review_status === status).length})` : ""}</Button>)}</div>
    {loading && <p className="text-[13px] text-muted-foreground">Loading feedback…</p>}
    {!loading && !error && visible.length === 0 && <EmptyState title={filter === "pending" ? "No corrections awaiting review" : "No matching feedback"}>Open an assessment in <Link href="/reward-models" className="underline">Traces</Link> to correct its verdict or the agent’s behavior.</EmptyState>}
    <div className="space-y-4">{visible.map((item) => <FeedbackReview key={`${item.id}-${item.review_status}-${item.status}-${item.updated_at ?? ""}`} feedback={item} onReviewed={reload} />)}</div>
  </RmPage>;
}
