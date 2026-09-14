"""Hosted MCP servers that ship with curated skills.

A skill can bring tools: one `mcp: <name> <url>` line in its SKILL.md points
at a server we host, and the config writers (the sprite's .mcp.json, `stash
skills sync`) put it in front of the harness. This package is the hosting
side — bearer auth, an exact route at /mcp/<name>, the transport's lifespan —
shared by every such server. A new bundled skill with tools adds a builder
to `registry.SERVERS`; it does not touch the CLI, the plugin, or the API.
"""
