#!/bin/sh
# Install quota-dot as a launchd agent on this Mac (starts at login, restarts if it dies).
#
#   ./deploy/install-launchd.sh            install or update, then start
#   ./deploy/install-launchd.sh --uninstall
#
# Uses this checkout as the working directory and the first python3 on PATH
# (override with PYTHON=/path/to/python3). Logs go to /tmp/quota-dot.log.
set -eu

LABEL=tech.mindreset.quota-dot
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
TEMPLATE="$REPO_DIR/deploy/$LABEL.plist"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--uninstall" ]; then
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$TARGET"
    echo "removed $TARGET"
    exit 0
fi

PYTHON=${PYTHON:-$(command -v python3 || true)}
if [ -z "$PYTHON" ] || ! "$PYTHON" -c 'import PIL, requests' 2>/dev/null; then
    echo "error: ${PYTHON:-python3} not found or missing Pillow/requests." >&2
    echo "       pip install -r requirements.txt, or set PYTHON=/path/to/python3" >&2
    exit 1
fi
if [ ! -f "$REPO_DIR/.env" ]; then
    echo "error: $REPO_DIR/.env not found; cp .env.example .env and fill it in first" >&2
    exit 1
fi
case "$REPO_DIR$PYTHON" in
    *'&'* | *'<'* | *'|'*) echo "error: path contains & < or |, which this script can't put in a plist" >&2; exit 1 ;;
esac

mkdir -p "$(dirname "$TARGET")"
sed -e "s|__REPO_DIR__|$REPO_DIR|g" -e "s|__PYTHON__|$PYTHON|g" "$TEMPLATE" > "$TARGET"
plutil -lint "$TARGET" >/dev/null

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true     # reload if already installed
launchctl bootstrap "$DOMAIN" "$TARGET"

echo "installed $TARGET"
echo "  repo:   $REPO_DIR"
echo "  python: $PYTHON"
echo "  logs:   tail -f /tmp/quota-dot.log"
