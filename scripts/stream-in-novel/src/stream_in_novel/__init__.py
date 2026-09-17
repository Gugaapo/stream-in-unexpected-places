"""stream-in-novel — the stream narrated as prose.

The medium lives here; the plumbing (sources, Grid, sink registry, describer seam, chat, PNG encoder,
pipeline) comes from :mod:`streamkit`.

    stream-in-novel --source twitch:oMeiaUm --size 640x360 --fps 2 --sink novel --seconds 180
"""

from __future__ import annotations

__version__ = "0.1.0"
