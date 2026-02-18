#!/bin/bash
# OpenAthan Installation Script

set -e

INSTALL_DIR="$HOME/.local/share/openathan"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/openAthan"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WAYBAR_CONFIG="$HOME/.config/waybar/config.jsonc"
OPENATHAN_MODULE_DEF='  "custom/openathan": {
    "exec": "'"$BIN_DIR"'/openathan",
    "interval": 60,
    "return-type": "json",
    "tooltip": true
  }'

echo "Installing OpenAthan..."

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$CONFIG_DIR"

# Copy main script
cp "$SCRIPT_DIR/openathan.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/openathan.py"

# Copy sound generator script
cp "$SCRIPT_DIR/create_sound.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/create_sound.py"

# Create symlink
ln -sf "$INSTALL_DIR/openathan.py" "$BIN_DIR/openathan"

# Generate sound files
echo "Generating prayer notification sounds..."
python3 "$INSTALL_DIR/create_sound.py"

# Initialize location and config (this will detect location)
echo "Detecting your location..."
"$BIN_DIR/openathan" > /dev/null 2>&1 || true

# Add to Waybar config
if [ -f "$WAYBAR_CONFIG" ]; then
    echo ""
    echo "Adding to Waybar configuration..."

    # Check if already added
    if grep -q '"custom/openathan"' "$WAYBAR_CONFIG" 2>/dev/null; then
        echo "  Already configured in Waybar."
    else
        # Create a backup
        cp "$WAYBAR_CONFIG" "$WAYBAR_CONFIG.backup.$(date +%s)"

        # Use Python for reliable JSON editing
        python3 - "$WAYBAR_CONFIG" "$BIN_DIR" << 'ENDPYTHON'
import sys
import re

config_file = sys.argv[1]
bin_dir = sys.argv[2]

with open(config_file, 'r') as f:
    content = f.read()

# Add to modules-center array (before clock)
if '"modules-center"' in content and '"custom/openathan"' not in content:
    # Find clock entry and add openathan before it
    content = re.sub(
        r'(\s*)"clock"(\s*\])',
        r'    "custom/openathan",\n\1"clock"\2',
        content
    )

# Add module definition (insert before clock module)
module_def = '''  "custom/openathan": {
    "exec": "{}/openathan",
    "interval": 60,
    "return-type": "json",
    "tooltip": true
  },
  '''.format(bin_dir)

if '"custom/openathan"' not in content:
    # Insert before "clock" module definition
    content = re.sub(
        r'(\s*)"clock":\s*\{',
        module_def + r'\1"clock": {',
        content
    )

with open(config_file, 'w') as f:
    f.write(content)

print("Waybar configuration updated.")
ENDPYTHON
    fi
else
    echo ""
    echo "  Waybar config not found at $WAYBAR_CONFIG"
    echo "  You'll need to manually add the module."
fi

# Add to Hyprland autostart
HYPRLAND_CONFIG="$HOME/.config/hypr/hyprland.conf"
if [ -f "$HYPRLAND_CONFIG" ]; then
    echo ""
    echo "Adding to Hyprland autostart..."

    if grep -q 'openathan.*--daemon' "$HYPRLAND_CONFIG" 2>/dev/null; then
        echo "  Already in Hyprland autostart."
    else
        echo "" >> "$HYPRLAND_CONFIG"
        echo "# OpenAthan - Prayer Times" >> "$HYPRLAND_CONFIG"
        echo "exec-once = $BIN_DIR/openathan --daemon" >> "$HYPRLAND_CONFIG"
        echo "  Added to Hyprland autostart."
    fi
fi

# Check PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "⚠️  ~/.local/bin is not in your PATH"
    echo "   Adding to ~/.bashrc and ~/.zshrc..."

    # Add to bashrc if not already there
    if ! grep -q 'PATH="$HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
        echo '' >> "$HOME/.bashrc"
        echo '# OpenAthan' >> "$HOME/.bashrc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    fi

    # Also check for zsh
    if [ -f "$HOME/.zshrc" ] && ! grep -q 'PATH="$HOME/.local/bin' "$HOME/.zshrc" 2>/dev/null; then
        echo '' >> "$HOME/.zshrc"
        echo '# OpenAthan' >> "$HOME/.zshrc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
    fi
fi

echo ""
echo "=========================================="
echo "  Installation complete!"
echo "=========================================="
echo ""
echo "Starting the notification daemon..."
"$BIN_DIR/openathan" --daemon 2>/dev/null || echo "  Daemon already running or failed to start"

echo ""
echo "Reloading Waybar..."
if pgrep -x waybar > /dev/null; then
    killall waybar 2>/dev/null || true
    sleep 1
    # Waybar should be restarted by Hyprland
    echo "  Waybar reloaded. Look for the prayer time module!"
else
    echo "  Waybar not running. Start it with: waybar &"
fi

echo ""
echo "=========================================="
echo "  You're all set!"
echo "=========================================="
echo ""
echo "Your prayer times:"
"$BIN_DIR/openathan" 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['tooltip'])"
echo ""
echo "Useful commands:"
echo "  openathan                    - Show prayer times"
echo "  openathan --set-method Makkah - Change calculation method"
echo "  openathan --toggle-sound     - Toggle notification sound"
echo "  openathan --list-methods     - List all methods"
echo "  openathan --stop-daemon      - Stop notifications"
echo ""
