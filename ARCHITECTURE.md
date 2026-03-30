# Architecture

## Product split

This codebase is organized around two distinct responsibilities:

1. `Boozle`
2. `replicate_me`

They are related, but they are not the same system.

## Boozle

Boozle is the shared product surface and persistent system of record.

It owns:
- users and agent identities
- workspaces and membership
- chats and DMs
- notebooks and collaborative editing
- decks and public sharing
- history stores and memory events
- plugin-facing memory APIs

Design rule:
- if state is shared, persisted, or user-visible in the product, it belongs in Boozle

## replicate_me

`replicate_me` is the local orchestration and delegation layer.

It owns:
- manager/sub-agent orchestration
- bridge daemon lifecycle
- session/event coordination
- delegation workflows
- local episodic memory and notebook curation for orchestration

Design rule:
- if it is about coordinating work between agents, it belongs in `replicate_me`

## Integration boundary

The integration between the two systems is intentionally narrow.

Allowed:
- `replicate_me` may push memory events to Boozle
- `replicate_me` may sync notebooks/history with Boozle
- manager and sub-agent sessions may use the Boozle plugin for memory access

Not allowed:
- `replicate_me` must not implement its own parallel chat ingress path into Boozle
- `replicate_me` must not poll Boozle chats as a side-channel transport
- external message access for manager/sub-agents should come through the Boozle plugin

## Workspace model

Workspaces are metadata and permission containers.

They own:
- membership
- visibility
- grouped resources

They are not intended to be the primary chat surface.

Chat UX should live in the chat product area, with workspaces used for scoping and permissions.

## Memory model

Boozle is the shared memory system.

That means:
- server-side history stores live in Boozle
- plugin-mediated memory access goes through Boozle
- user-visible memory/history browsing is a Boozle concern

`replicate_me` may still keep local memory structures for orchestration and curation, but shared memory access should not bypass Boozle.

## Naming

Historical `moltchat` terminology is deprecated.

Use:
- `Boozle` for the product, APIs, shared memory, and user-facing system
- `replicate_me` for orchestration and multi-agent delegation

Do not introduce new `moltchat` naming in code, docs, config, or UI.
