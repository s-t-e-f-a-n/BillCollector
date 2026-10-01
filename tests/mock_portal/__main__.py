# -*- coding: utf-8 -*-
"""Run the mock portal from the repo root:

    python3 -m tests.mock_portal [--port 8787]
"""

import argparse

import uvicorn

from tests.scenarios import PORT_DEFAULT
from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="BillCollector mock portal")
    parser.add_argument("--port", type=int, default=PORT_DEFAULT,
                        help=f"listen port (default {PORT_DEFAULT})")
    args = parser.parse_args()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
