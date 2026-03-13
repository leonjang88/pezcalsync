# PezCalSync

A lightweight macOS menubar app that puts your calendar right where you need it. See your upcoming events at a glance, keep personal and work calendars in sync, and never miss a meeting again — all from your menu bar.

<!-- TODO: Add screenshot of menubar dropdown here -->
<!-- ![PezCalSync menubar](docs/screenshot.png) -->

## TL;DR

- Menubar calendar — see your day at a glance
- Sync work calendar to your phone or personal devices (titles only, for security)
- Auto-block your work calendar when you have personal events
- Sprint/release countdown tracking
- Works with any calendar synced to Apple Calendar (Google, Outlook, iCloud, etc.)

## How It Works

PezCalSync reads from **Apple Calendar**, so any calendars you want to see need to be synced there first (Google, Outlook, iCloud — they all work once added to Apple Calendar).

## What It Does

- **See your schedule at a glance** — Upcoming events appear right in your menu bar, organized by day
- **Colorful event icons** — Each calendar gets its own color-coded icon so you can tell them apart instantly
- **Sync your work calendar where you want it** — Pull your work calendar into a personal calendar you can access anywhere — your phone, your Mac, or even iPhone Shortcuts automations like meeting alarms. Only event titles are synced, never descriptions, so no sensitive details leave your work account
- **Block your work calendar automatically** — Personal events (doctor appointments, errands, etc.) get synced to your work calendar as "busy" blocks, so coworkers won't book over them
- **Sprint countdown** — Track how many days are left in your current sprint or release cycle
- **Weekdays only mode** — Skip weekends if you just want to see your work week

## Install

1. Download `PezCalSync.app.zip` from the [latest release](https://github.com/leonjang88/pezcalsync/releases/latest)
2. Unzip the file
3. Drag `PezCalSync.app` into your Applications folder
4. Open PezCalSync — you'll see a calendar icon appear in your menu bar
5. Grant calendar access when prompted

**Requires macOS 13 (Ventura) or later.**

## Settings

Click the calendar icon in your menu bar and select **Settings** to customize:

- **Display** — Choose how many days ahead to show, toggle weekday-only mode, and set up excluded event patterns
- **Sync** — Configure which personal calendar syncs to your work calendar
- **Blocking** — Manage how personal events appear on your work calendar
- **Release** — Set up sprint/release tracking dates

Settings auto-save as you change them.

---

## Development

Everything below is for contributors and developers.

### Project Structure

```
calendar-tool/
├── PezCalSyncSwift/        # Swift package (main app)
│   ├── Package.swift
│   └── Sources/
│       ├── main.swift              # App entry, menubar, menu building
│       ├── EventKitManager.swift   # Calendar access and event fetching
│       ├── PreferencesManager.swift # JSON preferences
│       ├── SettingsViews.swift     # SwiftUI settings (Sync + Display tabs)
│       ├── SettingsWindow.swift    # NSWindow hosting SwiftUI settings
│       ├── SyncManager.swift       # Python script runner for blocking sync
│       └── IconRegistry.swift      # SF Symbol icon types, colors, and helpers
├── src/                    # Python sync scripts
│   ├── calendar_sync_eventkit.py   # Personal → Work blocking sync
│   ├── calendar_sync.py           # Legacy Google Calendar sync
│   ├── preferences.py
│   └── settings_window.py
├── build.sh                # Builds .app bundle
├── archive/                # Old Python menubar app and PNG icons
└── docs/                   # Requirements and implementation plan
```

### Building

**Quick iteration (debug):**

```bash
cd PezCalSyncSwift
swift build && .build/debug/PezCalSync
```

**Release build (.app bundle):**

```bash
./build.sh
# Output: PezCalSync.app
```

### Data Location

All user data is stored in `~/Library/Application Support/CalendarSync/`:
- `preferences.json` — App settings
- `personal_block_mapping.json` — Blocking sync state
- `Logs/` — Application logs

### Dev Requirements

- macOS 13+
- Xcode Command Line Tools (for `swift build`)
- Python 3 with PyObjC (for blocking sync script)
