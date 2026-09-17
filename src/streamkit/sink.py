"""The Sink interface and its registry — the extension point every medium project plugs into."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .grid import Grid

REGISTRY: dict[str, type] = {}


@runtime_checkable
class Sink(Protocol):
    """Anything that can receive frames.

    ``open`` is called once with the grid dimensions the source will deliver; ``write`` once per
    frame; ``close`` exactly once, also on error paths (implementations must be idempotent).
    """

    name: str

    def open(self, width: int, height: int) -> None: ...

    def write(self, grid: Grid) -> None: ...

    def close(self) -> None: ...


def register(name: str):
    """Class decorator: make a sink buildable by name from the CLI."""

    def deco(cls):
        if name in REGISTRY:
            raise ValueError(f"sink {name!r} is already registered")
        cls.name = name
        REGISTRY[name] = cls
        return cls

    return deco


def registered_sinks() -> list[str]:
    return sorted(REGISTRY)


def build_sink(sink_name: str, **options) -> Sink:
    """Instantiate a registered sink by name, passing ``options`` to its constructor.

    The first parameter is deliberately NOT called ``name``: sinks take their own ``name``
    option (used for default output filenames), and passing both would collide.
    """
    try:
        cls = REGISTRY[sink_name]
    except KeyError:
        raise KeyError(
            f"unknown sink {sink_name!r}; registered sinks: "
            f"{', '.join(registered_sinks()) or 'none'}"
        ) from None
    return cls(**options)
