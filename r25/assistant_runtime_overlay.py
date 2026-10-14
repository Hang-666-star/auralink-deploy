"""Finite overlay of the recorded closed Critic wrapper, no process execution."""
from __future__ import annotations
import hashlib
from pathlib import Path
import re

BASE_SHA256 = '0d87dc494914c147b34e0032c0631a89cb84159862882fc5f24fdfa26908d972'
ANCHOR = '''    return {
        "PATH": SAFE_PATH,'''
RETURN_END = '''        "AURALINK_CRITIC_EXECUTION_POLICY": execution_policy,
    }
'''


def render(before):
    if hashlib.sha256(before).hexdigest()!=BASE_SHA256:
        raise ValueError('assistant_wrapper_baseline_hash')
    text=before.decode()
    if text.count(ANCHOR)!=1 or text.count(RETURN_END)!=1:
        raise ValueError('assistant_wrapper_anchor')
    text=text.replace(ANCHOR,'''    child = {
        "PATH": SAFE_PATH,''').replace(RETURN_END,RETURN_END+'''    # Assistant loader contains its own failure boundary; malformed/absent
    # Assistant settings must not prevent existing Critic startup or health.
    # Forward exactly two private references, never generic env/provider keys.
    for key in ("AURALINK_ASSISTANT_CONFIG_FILE", "AURALINK_ASSISTANT_INTERNAL_TOKEN_FILE"):
        value = values.get(key, "").strip()
        if value and value.startswith("/") and not any(c in value for c in ("\\\\", "\\x00", "\\r", "\\n")):
            child[key] = value
    return child
''')
    return text.encode()
