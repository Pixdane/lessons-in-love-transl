#!/bin/bash
# Start translator daemon + game
DIR="$(cd "$(dirname "$0")" && pwd)"
GAME="/Volumes/Yuean Jinn/Games/LessonsInLove0.58.0.app"

# Start daemon in background
echo "Starting translator daemon..."
python3 "$DIR/translator/daemon.py" &
DAEMON_PID=$!
echo "Daemon PID: $DAEMON_PID"

# Wait a moment for daemon to initialize
sleep 1

# Launch game
echo "Launching game..."
open "$GAME"

# When game exits, stop daemon
echo "Game launched. Press Ctrl+C to stop daemon when done."
wait $DAEMON_PID 2>/dev/null
#!/bin/bash
# One-click launcher: ensures symlinks, then starts the game.
set -euo pipefail

GAME_DIR="/Volumes/Yuean Jinn/Games/LessonsInLove0.58.0.app/Contents/Resources/autorun/game"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure symlinks exist
for target in zz_translator.rpy translator; do
    link="$GAME_DIR/$target"
    src="$SRC_DIR/$target"
    if [[ ! -e "$link" ]]; then
        echo "Creating symlink: $link -> $src"
        ln -sf "$src" "$link"
    fi
done

echo "Launching Lessons in Love..."
open "/Volumes/Yuean Jinn/Games/LessonsInLove0.58.0.app"
