"""Locate preserved historical fixtures without changing their frozen contents."""
from functools import lru_cache
import json
from pathlib import Path
from .config import PROJECT_ROOT


@lru_cache(maxsize=1)
def _mapping():
    return json.loads((PROJECT_ROOT/'evals/archive/layout-map.json').read_text(encoding='utf-8'))['files']


def reference_path(relative):
    key=Path(relative).as_posix()
    original=PROJECT_ROOT/key
    if original.is_file():
        return original
    entry=_mapping().get(key)
    if not entry:
        return original
    target=(PROJECT_ROOT/entry['path']).resolve()
    if not target.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError('Reference outside project')
    return target
