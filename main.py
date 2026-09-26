"""API Client entry point: ``python main.py [backend-folder]``."""

import sys

from app.bootstrap import run

if __name__ == "__main__":
    sys.exit(run())
