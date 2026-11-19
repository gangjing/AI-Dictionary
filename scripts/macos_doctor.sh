#!/usr/bin/env bash
# AI Dictionary macOS diagnostic collector.
# Usage:
#   bash scripts/macos_doctor.sh
#   bash scripts/macos_doctor.sh --self-test
#
# This script only reads state; --self-test starts the app with a temporary
# user-data directory and exits automatically. Quit any running AI Dictionary first.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="/Applications/AI Dictionary.app"
APP_BIN="$APP/Contents/MacOS/AIDictionary"
BUNDLE_ID="com.aidictionary.desktop"
DATA_DIR="$HOME/Library/Application Support/AIDictionary"
RUN_SELFTEST=0
[ "${1:-}" = "--self-test" ] && RUN_SELFTEST=1

section() { printf '\n===== %s =====\n' "$1"; }
run() { printf '\n$ %s\n' "$*"; "$@" 2>&1 || true; }

section "System"
run sw_vers
run uname -m
run sysctl -n hw.physicalcpu
run xcode-select -p
run xcodebuild -version
run python3 --version
python3 -c 'import PyInstaller, playwright; print("PyInstaller", PyInstaller.__version__); print("playwright", playwright.__file__)' 2>&1 || true

section "Repository"
cd "$ROOT" || exit 1
run git status --short --branch
run git log --oneline --decorate -5
run git describe --tags --always

section "Installed app"
if [ -d "$APP" ]; then
  run plutil -p "$APP/Contents/Info.plist"
  run codesign -dv --verbose=4 "$APP"
  run spctl -a -vv "$APP"
  run xattr -l "$APP"
else
  echo "NOT INSTALLED: $APP"
fi

section "Process / port"
run pgrep -fl "AIDictionary|llama-server"
run lsof -nP -iTCP:14205 -sTCP:LISTEN

section "User data"
run ls -la "$DATA_DIR"
if [ -d "$DATA_DIR/models" ]; then
  run ls -lh "$DATA_DIR/models"
fi
if [ -f "$DATA_DIR/llama-server.log" ]; then
  run tail -n 40 "$DATA_DIR/llama-server.log"
fi

section "Backend status"
curl -sS --max-time 3 http://127.0.0.1:14205/api/dict/stats 2>&1 || true
printf '\n'
curl -sS --max-time 3 http://127.0.0.1:14205/api/translate/status 2>&1 || true
printf '\n'

if [ "$RUN_SELFTEST" -eq 1 ]; then
  section "Native self-test"
  if [ ! -x "$APP_BIN" ]; then
    echo "Cannot run: $APP_BIN not found"
    exit 0
  fi
  if lsof -nP -iTCP:14205 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port 14205 is in use. Quit the running app first."
    exit 0
  fi
  TMPDIR_SELFTEST="$(mktemp -d)"
  echo "Temporary user data: $TMPDIR_SELFTEST"
  AIDICT_USER_DATA_DIR="$TMPDIR_SELFTEST" "$APP_BIN" --self-test 2>&1 | tee "$TMPDIR_SELFTEST/self-test.log"
  rm -rf "$TMPDIR_SELFTEST"
fi

section "Permissions checklist"
cat <<'EOF'
Accessibility and Screen Recording cannot be queried reliably from a shell.
Open System Settings -> Privacy & Security:
  1. Accessibility: AI Dictionary must be present and enabled.
  2. Screen Recording: AI Dictionary must be present and enabled; restart the app after granting.
If you replaced an ad-hoc signed build, remove the old entry first, then re-add the new app.
Reset only this app's grants if needed:
  tccutil reset Accessibility com.aidictionary.desktop
  tccutil reset ScreenCapture com.aidictionary.desktop
EOF
