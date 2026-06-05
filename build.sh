#!/bin/bash
# Build script for PezCalSync (Swift + Python)
# Creates a self-contained macOS .app bundle

set -e

cd "$(dirname "$0")"

APP_NAME="PezCalSync"
BUILD_DIR="build"
APP_BUNDLE="${BUILD_DIR}/${APP_NAME}.app"
CONTENTS="${APP_BUNDLE}/Contents"
MACOS="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"

echo "Cleaning old builds..."
rm -rf "${BUILD_DIR}" "${APP_NAME}.app"

echo "Building Swift binary..."
cd PezCalSyncSwift
swift build -c release 2>&1 | tail -5
BINARY_PATH=$(swift build -c release --show-bin-path)/${APP_NAME}
cd ..

echo "Creating app bundle..."
mkdir -p "${MACOS}" "${RESOURCES}/scripts"

# Copy binary
cp "${BINARY_PATH}" "${MACOS}/${APP_NAME}"

# Copy Python sync scripts
cp src/work_to_personal_sync.py "${RESOURCES}/scripts/"
cp src/personal_to_work_sync.py "${RESOURCES}/scripts/"
cp src/settings_window.py "${RESOURCES}/scripts/"
cp src/preferences.py "${RESOURCES}/scripts/"

# Create Info.plist
cat > "${CONTENTS}/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>PezCalSync</string>
    <key>CFBundleDisplayName</key>
    <string>PezCalSync</string>
    <key>CFBundleIdentifier</key>
    <string>com.pez.calsync</string>
    <key>CFBundleVersion</key>
    <string>2.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>2.0.0</string>
    <key>CFBundleExecutable</key>
    <string>PezCalSync</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSCalendarsUsageDescription</key>
    <string>PezCalSync needs calendar access to display events and sync calendars.</string>
    <key>NSCalendarsFullAccessUsageDescription</key>
    <string>PezCalSync needs full calendar access to display events and sync calendars.</string>
</dict>
</plist>
PLIST

# Copy to project root for convenience
cp -r "${APP_BUNDLE}" "${APP_NAME}.app"

echo "Build complete!"
echo "  App: $(pwd)/${APP_NAME}.app"
echo ""
echo "To install, drag ${APP_NAME}.app to /Applications"
