"""Entry point for ``python -m billcollector``."""

import sys

from billcollector.cli import main

if __name__ == "__main__":
    sys.exit(main())
