#!/usr/bin/env bash
# One-time setup: install Python deps and Playwright browser

set -e
cd "$(dirname "$0")"

echo "Installing Python dependencies..."
pip3 install playwright qrcode[pil] Pillow

echo "Installing Playwright Chromium browser..."
python3 -m playwright install chromium

echo ""
echo "Setup complete. Run the generator with:"
echo "  python3 generate_qr_codes.py"
echo ""
echo "To automate (runs daily at 8am), add this cron job:"
echo "  crontab -e"
echo "  Then paste:"
echo "  0 8 * * * cd $(pwd) && /usr/bin/python3 generate_qr_codes.py >> $(pwd)/qr_generator.log 2>&1"
