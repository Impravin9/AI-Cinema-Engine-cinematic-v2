"""Story-driven hybrid cinematic pipeline (additive layer; legacy renderers are untouched).

Stages: story -> director -> characters/environment -> render -> audio -> assemble.
Every stage exchanges plain JSON-serialisable dicts so each can be cached or replaced.
"""
STAGES = ("story", "director", "characters", "environment", "render", "audio", "assemble")
