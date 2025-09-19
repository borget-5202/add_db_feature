# app/games/core/store_registry.py
from __future__ import annotations
from typing import Callable, TypeVar
from flask import current_app

T = TypeVar("T")

def get_store(key: str, factory: Callable[[], T], load: bool = True) -> T:
    ext = getattr(current_app, "extensions", None)
    if ext is None:
        current_app.extensions = {}
        ext = current_app.extensions
    store: T | None = ext.get(key)
    if store is None:
        store = factory()
        ext[key] = store
    if load and hasattr(store, "load"):
        store.load(force=False)
    return store

def warmup_store(key: str, factory: Callable[[], T], force: bool = False) -> None:
    store = get_store(key, factory, load=False)
    if hasattr(store, "load"):
        store.load(force=force)

