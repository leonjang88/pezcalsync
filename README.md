# PezCalSync

A macOS menubar app that syncs Apple Calendar events to Google Calendar.

## Structure

```
calendar-tool/
├── PezCalSync.app/     # Built macOS app (run this)
├── src/                # Source code
│   ├── calendar_menubar.py   # Menubar app
│   └── calendar_sync.py      # Sync logic
├── venv/               # Python virtual environment
├── build_app.py        # py2app build configuration
├── build.sh            # Build script
└── README.md           # This file
```

## Data Location

All user data is stored in `~/Library/Application Support/CalendarSync/`:
- `credentials.json` - Google OAuth client credentials
- `token.json` - Google OAuth tokens (auto-generated)
- `event_mapping.json` - Sync state tracking
- `logs/` - Application logs

## Usage

1. **Run the app**: Double-click `PezCalSync.app` or drag to `/Applications`
2. **Menu bar options**:
   - Sync Now - Trigger manual sync
   - View Logs - Open debug logs
   - Edit Credentials - Open credentials folder
   - Quit - Close the app

## Building

To rebuild after making changes:

```bash
./build.sh
```

Or manually:

```bash
source venv/bin/activate
python build_app.py py2app
cp -r dist/PezCalSync.app .
```

## Setup (First Time)

1. Set up Google Cloud project with Calendar API enabled
2. Create OAuth credentials and download `credentials.json`
3. Place `credentials.json` in `~/Library/Application Support/CalendarSync/`
4. Run the app - it will prompt for Google authorization on first sync
