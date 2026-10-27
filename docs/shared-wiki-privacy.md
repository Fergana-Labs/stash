# Shared wiki publication

The customer VFS serves only shared Markdown pages whose complete current title
and body match a server-owned review for the current policy, workspace and
folder. Deploying migration 0254 does not approve existing pages: they remain
quarantined from customer retrieval until reviewed. Developer console access and
private customer wikis retain their existing access rules.

Each shared curator write, including a small edit, checks the full candidate for
identifiers and asks a separate, tool-free model for privacy review. Failure,
uncertainty or contradictory approval blocks publication. Provider errors abort
the run without advancing its checkpoint. Human edits invalidate the previous
approval too. Customer reads recheck current scope and approval after listing;
they never invoke a model. Unreviewed shared attachments, folder names, HTML and
page metadata are not exposed. Approved shared pages are mounted directly under
`/memory`; private folder paths are unchanged.

Reusable technical facts and public manufacturer/part identifiers may be shared.
Customer identities, transaction records, inventory, pricing, personal contacts,
VINs/serials and raw session citations must remain private. Opt-in and test-account
labels do not exempt identifying content. Pattern checks and model review are
defenses, not a mathematical guarantee of anonymity; investigate reported misses
and raise the policy version to invalidate older approvals when necessary.

## Operator cleanup

Use `python -m backend.scripts.review_shared_wiki --workspace UUID --owner UUID
--root UUID` on the deployed worker to produce a bounded plan. It reads only that
workspace's current shared root and prints a manifest hash and page count. Inspect
the private source snapshot and confirm the intended workspace before applying.
Add `--apply --manifest-sha256 HASH --expected-code-sha256 CODE_HASH` to apply that exact plan and verified release (default maximum 300
pages, hard maximum 1000). Model concurrency defaults to three, with a hard maximum of four. One workspace cleanup may run at a time. Each page gets
at most one rewrite and one independent privacy/fidelity review, each bounded to
90 seconds; the command does not automatically retry failures.

The cleanup rechecks workspace generation and the exact original before saving.
It archives the original title, body, metadata and provenance in the private
`shared_wiki_originals` table in the same transaction as replacement. This table
has no customer API, search index or VFS mount. Replacements clear stale embeddings
and metadata, mark embeddings for rebuilding, record an edit, and approve only the
reviewed title/body. Existing rejected pages remain quarantined, preserving their
original content for operator inspection. A changed source requires a fresh plan;
never blindly repeat a failed job. Private wikis, consent flags, curation cursors
and global run allowances are not modified.

Validate customer listings, body reads, index links and representative technical
lessons after cleanup. Keep inspection artifacts private. Separately investigate
any historical copies in private wikis or already-returned client context; this
gate cannot retract data a customer already retrieved. Developer credentials
still represent the developer and retain console/API access to raw workspace
data; customer identity is asserted by the developer's backend through the VFS.

Do not roll back to the previous unfiltered customer read path to resolve an
incident. Keep the gate or quarantine active while repairing it. Archived originals
must never be restored to customer publication without a new review.
