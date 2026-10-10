#!/usr/bin/env bash
# Install or update API Client from the Linux release archive (no Python needed).
#
#   ./install.sh              install, or update to the version in this folder
#   ./install.sh --uninstall  remove the app, the command and the menu entry
#
# Nothing is written outside your home folder and sudo is never used. Your projects and
# settings are kept on uninstall. To install from a git clone instead, use the install.sh
# at the root of the repository.
set -euo pipefail

APP_ID="api-client"
APP_NAME="API Client"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/lib/$APP_ID"
BIN_DIR="$HOME/.local/bin"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DESKTOP_FILE="$DATA_HOME/applications/$APP_ID.desktop"
ICON_FILE="$DATA_HOME/icons/hicolor/scalable/apps/$APP_ID.svg"
LAUNCHER="$BIN_DIR/$APP_ID"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m!\033[0m %s\n' "$*"; }
fail()  { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

refresh_desktop_caches() {
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$DATA_HOME/applications" || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" || true
}

uninstall() {
    info "Removing $APP_NAME"
    rm -rf "$INSTALL_DIR"
    rm -f "$LAUNCHER" "$DESKTOP_FILE" "$ICON_FILE"
    refresh_desktop_caches
    ok "Removed. Your projects and settings ($DATA_HOME/$APP_ID) were kept."
    exit 0
}

[[ "${1:-}" == "--uninstall" ]] && uninstall
[[ "$(uname -s)" == "Linux" ]] || fail "This installer is for Linux."
[[ -x "$SRC_DIR/app/$APP_ID" ]] || fail "Run this script from the unpacked release folder (app/$APP_ID is missing)."

# 1. App files -----------------------------------------------------------------
# Copy to a temporary folder first, then swap, so a failed copy never leaves a
# half-installed app behind.
info "Installing to $INSTALL_DIR"
mkdir -p "$(dirname "$INSTALL_DIR")"
rm -rf "$INSTALL_DIR.new"
cp -a "$SRC_DIR/app" "$INSTALL_DIR.new"
rm -rf "$INSTALL_DIR"
mv "$INSTALL_DIR.new" "$INSTALL_DIR"
ok "App files ready"

# 2. Command, icon and menu entry ----------------------------------------------
info "Installing launcher"
mkdir -p "$BIN_DIR" "$(dirname "$DESKTOP_FILE")" "$(dirname "$ICON_FILE")"
if [[ -e "$LAUNCHER" && ! -L "$LAUNCHER" ]]; then
    warn "Replacing the launcher created by the source install ($LAUNCHER)."
fi
ln -sfn "$INSTALL_DIR/$APP_ID" "$LAUNCHER"
cp "$SRC_DIR/$APP_ID.svg" "$ICON_FILE"

cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$APP_NAME
GenericName=REST Client
Comment=Lightweight REST client for backend developers
Exec=$INSTALL_DIR/$APP_ID %f
Icon=$APP_ID
Terminal=false
Categories=Development;WebDevelopment;
Keywords=api;rest;http;postman;spring;
StartupWMClass=$APP_ID
StartupNotify=true
DESKTOP
chmod +x "$DESKTOP_FILE"
refresh_desktop_caches
ok "Menu entry: $DESKTOP_FILE"
ok "Command:    $LAUNCHER"

# 3. PATH -----------------------------------------------------------------------
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR is not in your PATH; the menu entry works, but add it to run '$APP_ID' from a terminal." ;;
esac

echo
ok "$APP_NAME installed. Open it from your applications menu or run: $APP_ID [backend-folder]"
echo "   To update, download a newer release and run its install.sh."
