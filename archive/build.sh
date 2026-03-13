#!/bin/bash
# Build script for PezCalSync
# Creates a self-contained macOS app bundle

set -e

cd "$(dirname "$0")"

echo "🧹 Cleaning old builds..."
rm -rf build dist

echo "🔧 Activating virtual environment..."
source venv/bin/activate

echo "📦 Building PezCalSync.app..."
python build_app.py py2app 2>&1 | tail -5

echo "📁 Copying to project root..."
rm -rf PezCalSync.app
cp -r dist/PezCalSync.app .

echo "✅ Build complete!"
echo "   App location: $(pwd)/PezCalSync.app"
echo ""
echo "To install, drag PezCalSync.app to /Applications"
