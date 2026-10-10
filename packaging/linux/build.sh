#!/usr/bin/env bash
# Builds the Linux release archive: venv -> PyInstaller bundle -> tar.gz.
#
#   packaging/linux/build.sh
#
# Produces dist_installer/api-client-linux-x86_64.tar.gz, which unpacks to api-client/
# with the self-contained app (no Python needed on the target machine) and its own
# install.sh. Requires Python 3.12+ and libxcb-cursor0. Build on the oldest distro you want to support:
# the bundle only runs on systems with the same or a newer glibc.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ARCH="$(uname -m)"
ARCHIVE="dist_installer/api-client-linux-$ARCH.tar.gz"
STAGE="build/linux-release/api-client"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
    || fail "Python 3.12 or newer is required (set PYTHON=/path/to/python3.12)."

info "Virtual environment and dependencies"
[[ -x .venv/bin/python ]] || "$PYTHON" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet --upgrade -r requirements.txt -r requirements-dev.txt

info "Running PyInstaller"
rm -rf build dist
.venv/bin/python -m PyInstaller --noconfirm api_client.spec
[[ -x dist/api-client/api-client ]] || fail "PyInstaller did not produce dist/api-client/api-client"

# Qt 6.5+ needs libxcb-cursor to open a window on X11/XWayland and many distros do not
# ship it, so it must travel inside the bundle (PyInstaller copies it from the build host).
compgen -G "dist/api-client/_internal/libxcb-cursor.so*" >/dev/null \
    || fail "libxcb-cursor is not in the bundle; install libxcb-cursor0 (or xcb-util-cursor) and rebuild."

info "Smoke test"
dist/api-client/api-client --help >/dev/null || fail "The bundled binary does not start."

info "Packing $ARCHIVE"
mkdir -p "$STAGE" dist_installer
cp -a dist/api-client "$STAGE/app"
cp packaging/linux/install.sh "$STAGE/install.sh"
cp assets/api-client.svg "$STAGE/api-client.svg"
chmod +x "$STAGE/install.sh"
tar -C "$(dirname "$STAGE")" -czf "$ARCHIVE" api-client

printf '\n\033[1;32m✓\033[0m Done: %s\n' "$ARCHIVE"
