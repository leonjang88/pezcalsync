# PezCalSync

A native macOS menubar calendar app built with Swift and SwiftUI. Displays upcoming events from Apple Calendar with customizable icons, sprint countdown tracking, and personal-to-work calendar blocking sync.

## Features

- **Menubar event display** — See today's and upcoming events at a glance with configurable days ahead
- **SF Symbol icons** — Color-coded calendar icons with hierarchical gradient rendering
- **Sprint tracking** — Shows countdown to end of current sprint/release in day headers
- **Calendar blocking** — Syncs personal calendar events to work calendar as blocking events
- **Excluded patterns** — Filter out events by title pattern (e.g., "lunch*", "1:1 *")
- **Weekday filtering** — Option to show only weekdays in the menu

## Structure

```
calendar-tool/
├── PezCalSyncSwift/        # Swift package (main app)
│   ├── Package.swift
│   └── Sources/
│       ├── main.swift              # App entry, menubar, menu building
│       ├── EventKitManager.swift   # Calendar access and event fetching
│       ├── PreferencesManager.swift # JSON preferences (~/Library/Application Support/CalendarSync/)
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

## Building

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

## Data Location

All user data is stored in `~/Library/Application Support/CalendarSync/`:
- `preferences.json` — App settings
- `personal_block_mapping.json` — Blocking sync state
- `Logs/` — Application logs

## Requirements

- macOS 13+
- Xcode Command Line Tools (for `swift build`)
- Python 3 with PyObjC (for blocking sync script)
