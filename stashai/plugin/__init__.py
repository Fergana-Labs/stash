"""Shared core for Stash plugins across all coding agents.

Ships as part of the `stashai` PyPI package. Every per-agent plugin imports
from `stashai.plugin.*`; `pip install stashai` puts this on PYTHONPATH so
the plugin dir can stay thin (only stdin adapter + manifest + hook scripts).
"""
