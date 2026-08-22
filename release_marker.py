#!/usr/bin/env python3
"""Helpers for stable release identity markers embedded in the published site."""
from __future__ import annotations


def build_release_marker(source_commit: str) -> str:
    return f"insureai:{source_commit or 'unknown'}"
