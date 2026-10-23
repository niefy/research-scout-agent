from __future__ import annotations

from app.collectors.base import ChannelAdapter
from app.collectors.mock import MockAdapter
from app.collectors.sina import SinaAdapter
from app.collectors.wallstreetcn import WallStreetCNAdapter
from app.collectors.xueqiu import XueqiuAdapter

_ADAPTERS: dict[str, ChannelAdapter] = {}


def register(adapter: ChannelAdapter) -> ChannelAdapter:
    if adapter.key in _ADAPTERS:
        raise ValueError(f"adapter already registered: {adapter.key}")
    _ADAPTERS[adapter.key] = adapter
    return adapter


for _adapter in (SinaAdapter(), WallStreetCNAdapter(), XueqiuAdapter(), MockAdapter()):
    register(_adapter)


def get_adapter(key: str) -> ChannelAdapter:
    try:
        return _ADAPTERS[key]
    except KeyError as exc:
        raise KeyError(f"unknown channel adapter: {key}") from exc


def list_adapters() -> list[ChannelAdapter]:
    return list(_ADAPTERS.values())


def adapter_keys() -> list[str]:
    return sorted(_ADAPTERS)


__all__ = ["adapter_keys", "get_adapter", "list_adapters", "register"]
