# Use past sessions in the eval wizard

Tell the wizard what to find, for example:

> Use my past Codex sessions about website design. Find cases where I asked for
> changes, show me the relevant outputs and feedback, and propose examples.

The wizard searches recorded sessions and traces already in the signed-in
account. A connected local computer can also search Codex sessions that have
never been recorded to Stash. Neither path requires exporting files or importing
a history corpus. Existing unfinished wizard conversations receive the tools;
there is no need to recreate the conversation.

## Connect local history

Using a CLI signed into the same Stash account as the wizard:

```sh
stash history-bridge
```

Keep it running while using the wizard. It makes outbound authenticated requests
to Stash using the existing CLI login, so it also works with a hosted backend.
It opens no inbound port and creates no new access credential. Read-only CLI
keys can use the connector without acquiring permission to modify evals.

The connector reads Codex's `~/.codex/sessions` and `~/.codex/archived_sessions`
directories. It accepts searches and discovered session IDs, never arbitrary
paths or shell commands. System messages and private reasoning are excluded.
Resumed histories are reconstructed from available base pages inside those
directories; unresolved bases are explicitly marked as partial. Source files
are never changed. Only requested previews and excerpts are returned.

One local connector can be active per account. Stop it with Ctrl-C; an offline
connection expires within 45 seconds. A disconnected or timed-out connector is
reported separately from a search with no matches. Recorded history remains
searchable when the local connection is unavailable. No settings or credentials
are silently copied between demo, personal, or workspace accounts.

## Search, inspect, review

- `search_history` finds recorded sessions/traces and/or local Codex sessions.
  Short queries work best. Empty queries browse recent sessions. Local searches
  scan in bounded batches; continue with the returned `next_offset` and
  `next_event_offset`, using `source: local`. Recorded pagination uses
  `recorded_next_offset` with `source: recorded`.
- `read_history` retrieves an event window around the result's `match_offset`.
  The response includes total events, the next offset, and truncation flags.
  Large messages may be excerpted; a preview is never presented as a full trace.
- `add_history_examples` copies selected real excerpts into the current eval and
  opens its labeler. Repeated identical selections are skipped. Suggested labels
  remain `needs_review`; the user confirms or changes them before training.

Sources are checked again when read or added. Recorded search honors session
permissions and deletion, and includes the user's own sessions in accessible
workspace scopes. Local requests and results are bound to the authenticated
account and its connector. Redis holds only short-lived request/result records;
normal wizard conversation persistence and explicitly selected eval examples
retain the excerpts the user is working with.

For visual website judgments, session text may identify relevant work and human
feedback but does not establish what the final rendered website looked like.
Use stored screenshots or other available visual evidence for that judgment.
