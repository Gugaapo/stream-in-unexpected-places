"""``python -m stream_in_novel`` entry point."""

from __future__ import annotations

import sys

LIBRARY_HINT = (
    "error: the streamkit library is not installed.\n"
    "From the repository root:  python -m pip install -e .\n"
    "then, in this script's directory:  python -m pip install -e ."
)


def main(argv: list[str] | None = None) -> int:
    try:
        from .cli import main as cli_main
    except ModuleNotFoundError as exc:  # friendlier than a bare traceback
        if (exc.name or "").split(".")[0] == "streamkit":
            print(LIBRARY_HINT, file=sys.stderr)
            return 2
        raise
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
