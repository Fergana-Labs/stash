"""Shared core for Stash plugins across all coding agents.

Each per-agent plugin adds this dir to sys.path and imports from it.
Keeps per-agent plugins thin: only stdin adapter + manifest + hook scripts.
"""
