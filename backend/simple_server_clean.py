"""Legacy entrypoint kept for compatibility. Use backend/run.py instead."""
from __future__ import annotations

from .app import create_app

app = create_app("development")


def main() -> None:
    """Run development server."""
    app.run(host="0.0.0.0", port=5001)


if __name__ == "__main__":
    main()
