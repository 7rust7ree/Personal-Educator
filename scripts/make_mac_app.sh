#!/bin/zsh
# Builds "Personal Educator.app" in ~/Applications so you can open the app from Launchpad/Spotlight/Dock.
# Re-run after moving the project folder.
set -e
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/Applications/Personal Educator.app"

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Personal Educator</string>
  <key>CFBundleDisplayName</key><string>Personal Educator</string>
  <key>CFBundleIdentifier</key><string>edu.unt.personal-educator</string>
  <key>CFBundleVersion</key><string>0.2</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>NSMicrophoneUsageDescription</key><string>Voice input for your thinking boxes, transcribed on this Mac.</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

# The launcher reads your API key from ~/.zshrc, then starts the app with the project's Python.
cat > "$APP/Contents/MacOS/launch" <<LAUNCH
#!/bin/zsh
source "\$HOME/.zshrc" >/dev/null 2>&1
cd "$PROJECT"
exec "$PROJECT/.venv/bin/python" -m backend.desktop >> "$PROJECT/data/app.log" 2>&1
LAUNCH
chmod +x "$APP/Contents/MacOS/launch"
mkdir -p "$PROJECT/data"

if [[ -f "$PROJECT/frontend/icon.icns" ]]; then cp "$PROJECT/frontend/icon.icns" "$APP/Contents/Resources/icon.icns"; fi
touch "$APP"
echo "Built: $APP"
