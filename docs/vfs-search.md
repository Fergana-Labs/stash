# Search coverage

`POST /api/v1/me/vfs` returns `searches` alongside stdout/stderr. Each entry
reports the requested roots, the current listing's file count, the range
attempted, successfully searched files, unreadable files, listing completeness,
and whether another scan page is available. `search_complete` is null for
commands without a document search, true for complete searches, and false if any
search is partial. Pipes and later commands preserve earlier coverage metadata.

Partial searches retain matches but exit 2, including when no matches were found.
Only a complete search with no matches exits 1. Never interpret a partial empty
result as evidence that the information is absent. Continue or narrow the search;
if that is not possible, disclose the incomplete coverage in the answer.

When `has_more` is true, run the returned `next_command` in a **new request** with
the same credential, `user_id`, and cwd. Each request retains the 400-document
read budget. A cursor is bound to the query and visible path listing, and is
rejected when that listing changes. It grants no access: every new request
reauthenticates and rebuilds the caller's scoped tree, and individual reads still
check current permission and shared-publication approval.

Continuation results explicitly describe only their range and remain partial as
standalone results, even on the last page. Combine all ranges, check for read or
listing errors, and stop when `has_more` is false. This is not a frozen snapshot;
document bodies can change between requests. A failed read requires a fresh,
narrower search; it is never silently counted as searched. Do not automatically
loop without an overall request/time budget.
