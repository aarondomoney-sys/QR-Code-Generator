#!/usr/bin/env bash
# Hugo Cars QR — One-time install
# Sets up: Python deps, Playwright, auto-start on login, permanent public URL

set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/ie.hugocars.qrapp.plist"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Hugo Cars QR Code App — Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Python deps
echo ""
echo "▸ Installing Python dependencies..."
pip3 install -q -r "$APP_DIR/requirements.txt"
python3 -m playwright install chromium --with-deps 2>/dev/null || python3 -m playwright install chromium

# 2. LaunchAgent — starts app automatically on every login
echo ""
echo "▸ Setting up auto-start on login..."
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>             <string>ie.hugocars.qrapp</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$APP_DIR/app.py</string>
    </array>
    <key>WorkingDirectory</key>  <string>$APP_DIR</string>
    <key>RunAtLoad</key>         <true/>
    <key>KeepAlive</key>         <true/>
    <key>StandardOutPath</key>   <string>$APP_DIR/app.log</string>
    <key>StandardErrorPath</key> <string>$APP_DIR/app.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "  ✓ App will now start automatically on every login."

# 3. Cloudflare Tunnel — permanent public URL
echo ""
echo "▸ Setting up permanent public URL (Cloudflare Tunnel)..."
if ! command -v cloudflared &>/dev/null; then
    brew install cloudflare/cloudflare/cloudflared
fi

TUNNEL_PLIST="$HOME/Library/LaunchAgents/ie.hugocars.tunnel.plist"
cat > "$TUNNEL_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>             <string>ie.hugocars.tunnel</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/cloudflared</string>
        <string>tunnel</string>
        <string>--url</string>
        <string>http://localhost:8080</string>
        <string>--logfile</string>
        <string>$APP_DIR/tunnel.log</string>
    </array>
    <key>RunAtLoad</key>         <true/>
    <key>KeepAlive</key>         <true/>
    <key>StandardOutPath</key>   <string>$APP_DIR/tunnel.log</string>
    <key>StandardErrorPath</key> <string>$APP_DIR/tunnel.log</string>
</dict>
</plist>
PLIST

launchctl unload "$TUNNEL_PLIST" 2>/dev/null || true
launchctl load "$TUNNEL_PLIST"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo ""
echo "  Your public link will appear in:"
echo "  tail -f $APP_DIR/tunnel.log"
echo ""
echo "  Look for a line like:"
echo "  https://xxxx-xxxx-xxxx.trycloudflare.com"
echo ""
echo "  That link works from anywhere — send it by email."
echo "  The app and tunnel restart automatically on every login."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
