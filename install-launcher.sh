#!/usr/bin/env bash

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

chmod +x "$APP_DIR/yank-launcher.sh"
mkdir -p "$APPLICATIONS_DIR"

sed "s|Exec=/workspaces/yank/yank-launcher.sh|Exec=$APP_DIR/yank-launcher.sh|" \
    "$APP_DIR/yank.desktop" |
    sed "s|Icon=/workspaces/yank/yank-logo.svg|Icon=$APP_DIR/yank-logo.svg|" \
        > "$APPLICATIONS_DIR/yank.desktop"
chmod +x "$APPLICATIONS_DIR/yank.desktop"

if [[ "${1:-}" == "--autostart" ]]; then
    mkdir -p "$AUTOSTART_DIR"
    cp "$APPLICATIONS_DIR/yank.desktop" "$AUTOSTART_DIR/yank.desktop"
    echo "Yank desktop and login autostart launchers installed."
elif [[ -n "${1:-}" ]]; then
    echo "Usage: ./install-launcher.sh [--autostart]" >&2
    exit 2
else
    echo "Yank desktop launcher installed."
    echo "Run it from your application menu. Use --autostart to launch at login."
fi
