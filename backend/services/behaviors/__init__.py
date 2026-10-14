"""Behaviors: named patterns tagged on exact step windows of production traces.

A behavior names something worth watching: what the user does, what the agent
does, or what the environment hands back. Detectors tag the windows where it
happens (`behavior_hits`), monitors trend the hits and alert, search finds
windows by meaning, and confirmed hits become eval examples.
"""
