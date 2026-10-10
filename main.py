"""API Client entry point.

``python main.py [backend-folder]`` opens the desktop app; ``python main.py <command> ...``
runs the command line (see ``python main.py --help``) without loading Qt.
"""

import sys

from app.cli import is_cli_invocation

if __name__ == "__main__":
    if is_cli_invocation(sys.argv[1:]):
        from app.cli import main

        sys.exit(main())

    from app.bootstrap import run

    sys.exit(run())
