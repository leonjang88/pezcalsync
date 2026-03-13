# PezCalSync Swift Rebuild - Technical Implementation Plan

**Date**: March 2026  
**Status**: Planning  
**Current Version**: Python/PyObjC with rumps  
**Target Version**: Native Swift/SwiftUI + Python sync scripts

---

## Executive Summary

This document outlines the technical plan for rebuilding PezCalSync from a Python/PyObjC application to a native Swift/SwiftUI application. The primary motivation is to resolve a critical bug where the settings window crashes on reopen due to PyObjC memory management issues. The sync logic will remain in Python to preserve the existing, working implementation.

---

## 1. Architecture Overview

### Current Architecture (Python)
```
┌─────────────────────────────────────────────────────────┐
│                  Python Application                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │   rumps     │  │  PyObjC      │  │   EventKit     │ │
│  │  Menubar    │  │  Settings    │  │   (via PyObjC) │ │
│  │   (UI)      │  │  Window      │  │                │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
│                           │                             │
│  ┌────────────────────────┴──────────────────────────┐ │
│  │              calendar_sync_eventkit.py            │ │
│  │         (Personal→Work blocking sync)             │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Target Architecture (Swift + Python)
```
┌─────────────────────────────────────────────────────────┐
│                 Swift Application (UI)                   │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │   NSMenu    │  │   SwiftUI    │  │   EventKit     │ │
│  │  StatusBar  │  │  Settings    │  │   (native)     │ │
│  │   (Menu)    │  │  Window      │  │                │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
│         │                                    │          │
│         └────────────────┬───────────────────┘          │
│                          │                              │
│                    ┌─────┴─────┐                        │
│                    │  Process  │                        │
│                    │  (spawn)  │                        │
│                    └─────┬─────┘                        │
└──────────────────────────│──────────────────────────────┘
                           │
┌──────────────────────────│──────────────────────────────┐
│              Python Scripts (Sync Logic)                 │
│  ┌───────────────────────┴───────────────────────────┐ │
│  │              calendar_sync_eventkit.py            │ │
│  │         (Personal→Work blocking sync)             │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │              calendar_sync.py                     │ │
│  │         (Apple→Google Calendar sync)              │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

         Shared: ~/Library/Application Support/CalendarSync/
         ├── preferences.json
         ├── event_mapping.json
         └── personal_block_mapping.json
```

### Communication Flow

1. **Swift → Python**: Execute Python scripts via `Process` (NSTask)
2. **Data Sharing**: Both read/write to shared JSON files in Application Support
3. **Sync Results**: Python outputs JSON to stdout, Swift parses for notifications
4. **Calendar Display**: Swift uses EventKit directly (no Python needed)

---

## 2. Story-Based Implementation Increments

### Epic 1: Core Menubar App (Foundation)

#### Story 1.1: Basic Menubar App Shell
**Title**: Create basic Swift menubar app with status item  
**Complexity**: Small  
**Dependencies**: None  

**Acceptance Criteria**:
- [x] App launches as menubar-only (no dock icon)
- [x] Calendar icon appears in menubar
- [x] Basic menu with "Quit" item works
- [x] App can be quit cleanly
- [x] App hides dock icon using `LSUIElement`

**Technical Notes**:
- Use `NSStatusBar.system.statusItem(withLength:)`
- Set `NSApp.setActivationPolicy(.accessory)` or use Info.plist `LSUIElement = true`
- Use SF Symbols or bundled PNG for menubar icon

---

#### Story 1.2: Menu Structure with Placeholders
**Title**: Implement full menu structure with placeholder items  
**Complexity**: Small  
**Dependencies**: Story 1.1  

**Acceptance Criteria**:
- [x] Menu shows sections: Events, Sync Now, Status, Settings, Quit
- [x] Separator lines between sections
- [x] "Sync Now" menu item exists (no action yet)
- [x] "Settings..." menu item exists (no action yet)
- [x] Status and last sync items display placeholder text

**Menu Structure**:
```
─────────────────────
Today, Mar 13
  No events
─────────────────────
Tomorrow, Mar 14
  No events
─────────────────────
Sync Now
Status: Idle
Last sync: Never
─────────────────────
Settings...
View Logs
─────────────────────
Quit
```

---

### Epic 2: EventKit Integration (Calendar Display)

#### Story 2.1: Request Calendar Permissions
**Title**: Implement EventKit permission request flow  
**Complexity**: Small  
**Dependencies**: Story 1.1  

**Acceptance Criteria**:
- [x] App requests calendar access on first launch
- [x] Handles macOS 14+ `requestFullAccessToEvents` API
- [x] Falls back to legacy API for older macOS
- [x] Shows appropriate error if access denied
- [x] Permission status is cached

**Technical Notes**:
```swift
if #available(macOS 14.0, *) {
    store.requestFullAccessToEvents { granted, error in ... }
} else {
    store.requestAccess(to: .event) { granted, error in ... }
}
```

---

#### Story 2.2: Fetch and Display Today's Events
**Title**: Display today's calendar events in menu  
**Complexity**: Medium  
**Dependencies**: Story 2.1, Story 1.2  

**Acceptance Criteria**:
- [x] Fetches events from start of today to 3 days ahead
- [x] Groups events by day (Today, Tomorrow, Day After)
- [x] Shows event time and title for each event
- [x] Skips cancelled events (status == .canceled)
- [x] All-day events show "All day" instead of time
- [ ] Past events are grayed out

**Technical Notes**:
```swift
let predicate = store.predicateForEvents(
    withStart: startOfToday,
    end: threeDaysLater,
    calendars: displayCalendars
)
let events = store.events(matching: predicate)
```

---

#### Story 2.3: Calendar Icons in Event Menu
**Title**: Show calendar-specific icons next to events  
**Complexity**: Medium  
**Dependencies**: Story 2.2  

**Acceptance Criteria**:
- [x] Each event shows icon based on its calendar
- [x] Icons loaded from bundled assets
- [ ] Icons render correctly in dark/light mode (template images)
- [x] Icon selection read from preferences.json

**Icon Files Available**:
| Type | Files |
|------|-------|
| Brief | `brief-{color}-{circle\|filled}.png` (colors: blue, green, orange, purple, red, teal, white, yellow) |
| Person | `person-{color}-{circle\|filled}.png` (colors: black, blue, green, grey, orange, red, teal, white) |
| Badminton | `badminton-yellow.png` |
| Rolling Suitcase | `rollingsuitcase-purple.png`, `rollingsuitcase-purple-notsynced.png` |
| Box | `box-blue.png` |
| Calendar | `calendar_idle.png` |

---

#### Story 2.4: Sync Status Icons for Work Events
**Title**: Show sync status indicator on work calendar events  
**Complexity**: Medium  
**Dependencies**: Story 2.3  

**Acceptance Criteria**:
- [x] When calendar sync enabled, work events show sync status
- [x] User's selected icon variant = event IS synced
- [x] Opposite variant = event NOT yet synced
- [x] Reads `event_mapping.json` to determine sync status
- [x] When sync disabled, always shows selected icon

**Logic**:
```swift
func iconForEvent(_ event: EKEvent, isSynced: Bool, selectedIcon: String) -> String {
    guard !isSynced else { return selectedIcon }
    
    // Swap variant: circle ↔ filled
    if selectedIcon.contains("-circle") {
        return selectedIcon.replacingOccurrences(of: "-circle", with: "-filled")
    } else if selectedIcon.contains("-filled") {
        return selectedIcon.replacingOccurrences(of: "-filled", with: "-circle")
    }
    return selectedIcon
}
```

---

#### Story 2.5: Calendar Change Notifications
**Title**: Refresh menu when calendars change  
**Complexity**: Small  
**Dependencies**: Story 2.2  

**Acceptance Criteria**:
- [x] Listens for `EKEventStoreChangedNotification`
- [x] Refreshes event display when notification received
- [x] Debounces rapid updates (2 second delay)
- [ ] Triggers sync after debounce period

---

### Epic 3: Python Script Execution

#### Story 3.1: Execute Python Sync Script
**Title**: Run Python sync script from Swift  
**Complexity**: Medium  
**Dependencies**: Story 1.2  

**Acceptance Criteria**:
- [x] Locates Python interpreter (bundled or system)
- [x] Executes `calendar_sync_eventkit.py`
- [x] Captures stdout/stderr output
- [x] Parses JSON result from stdout
- [x] Handles script timeout (30 seconds)
- [x] Shows error if script fails

**Technical Notes**:
```swift
let process = Process()
process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
process.arguments = [scriptPath]
process.currentDirectoryURL = scriptsDirectory

let pipe = Pipe()
process.standardOutput = pipe
process.standardError = pipe

try process.run()
process.waitUntilExit()

let data = pipe.fileHandleForReading.readDataToEndOfFile()
let output = String(data: data, encoding: .utf8)
```

---

#### Story 3.2: Sync Now Menu Action
**Title**: Implement "Sync Now" menu action  
**Complexity**: Small  
**Dependencies**: Story 3.1  

**Acceptance Criteria**:
- [x] Clicking "Sync Now" triggers Python sync
- [x] Menu item disabled while sync in progress
- [x] Shows syncing icon during sync
- [x] Shows success/failure icon after sync
- [x] Updates "Last sync" time on success

---

#### Story 3.3: Automatic Sync on Calendar Change
**Title**: Auto-sync when calendar changes detected  
**Complexity**: Small  
**Dependencies**: Story 2.5, Story 3.1  

**Acceptance Criteria**:
- [x] Sync triggered after calendar change notification
- [x] Debounced to prevent rapid fire (5 seconds)
- [x] Minimum interval between syncs (30 seconds)
- [ ] Shows scheduled sync icon while waiting

---

#### Story 3.4: Periodic Background Sync
**Title**: Implement periodic sync timer  
**Complexity**: Small  
**Dependencies**: Story 3.1  

**Acceptance Criteria**:
- [x] Sync runs every 30 minutes as fallback
- [x] Timer resets after manual sync
- [x] Timer survives app backgrounding
- [ ] Can be configured via preferences (future)

---

### Epic 4: Settings Window (SwiftUI)

#### Story 4.1: Basic Settings Window Shell
**Title**: Create SwiftUI settings window  
**Complexity**: Small  
**Dependencies**: Story 1.2  

**Acceptance Criteria**:
- [x] Settings window opens from menu item
- [x] Window has proper title "PezCalSync Settings"
- [x] Window can be closed with close button
- [x] Window can be reopened without crash (main goal!)
- [x] Save and Cancel buttons at bottom

**Technical Notes**:
```swift
struct SettingsView: View {
    @Environment(\.dismiss) var dismiss
    @StateObject var viewModel = SettingsViewModel()
    
    var body: some View {
        VStack {
            // Content
            HStack {
                Button("Cancel") { dismiss() }
                Button("Save") { 
                    viewModel.save()
                    dismiss()
                }
            }
        }
        .frame(width: 600, height: 700)
    }
}
```

---

#### Story 4.2: Apple→Google Sync Settings Section
**Title**: Implement Google sync configuration UI  
**Complexity**: Medium  
**Dependencies**: Story 4.1  

**Acceptance Criteria**:
- [x] Enable/disable toggle for Google sync
- [x] Source calendar dropdown (populated from EventKit)
- [x] Google Calendar ID text field
- [x] Controls disabled when toggle off
- [x] Values saved to preferences.json

**UI Layout**:
```
┌─ Apple → Google Calendar Sync ───────────────────┐
│ [x] Enable Apple → Google sync                   │
│                                                   │
│ Source Calendar:     [Calendar (Exchange)    ▼]  │
│ Google Calendar ID:  [calendar_id@group...    ]  │
└──────────────────────────────────────────────────┘
```

---

#### Story 4.3: Personal→Work Blocking Settings Section
**Title**: Implement blocking sync configuration UI  
**Complexity**: Medium  
**Dependencies**: Story 4.1  

**Acceptance Criteria**:
- [x] Enable/disable toggle for blocking
- [x] Personal calendar dropdown
- [x] Work calendar dropdown
- [x] Blocking hours start/end dropdowns (6 AM - 11 PM)
- [x] Block days dropdown (Weekdays Only / All Days)
- [x] Controls disabled when toggle off
- [x] Values saved to preferences.json

**UI Layout**:
```
┌─ Personal → Work Calendar Blocking ──────────────┐
│ [x] Enable Personal → Work blocking              │
│                                                   │
│ Personal Calendar:   [Personal Cal (Google)  ▼]  │
│ Work Calendar:       [Calendar (Exchange)    ▼]  │
│ Blocking Hours:      [8 AM ▼] to [8 PM ▼]       │
│ Block On:            [Weekdays Only          ▼]  │
└──────────────────────────────────────────────────┘
```

---

#### Story 4.4: Display Calendars Settings Section
**Title**: Implement display calendar configuration UI  
**Complexity**: Large  
**Dependencies**: Story 4.1  

**Acceptance Criteria**:
- [x] Lists all available calendars grouped by source
- [x] Checkbox to show/hide each calendar in menu
- [x] Icon type dropdown per calendar (Brief, Person, etc.)
- [x] Icon variant dropdown per calendar (color/style)
- [x] Variant dropdown updates based on icon type selection
- [x] Values saved to preferences.json

**UI Layout**:
```
┌─ Display in Menu ────────────────────────────────┐
│ Calendar                      Icon    Color/Style│
│                                                   │
│ 📁 Exchange                                      │
│   [x] Calendar               [Brief▼] [Purple▼] │
│                                                   │
│ 📁 Google                                        │
│   [x] Personal Cal           [Badminton▼][Yel▼] │
│   [ ] Holidays               [Calendar▼][Def▼] │
└──────────────────────────────────────────────────┘
```

---

#### Story 4.5: Excluded Event Patterns (Future)
**Title**: Implement event exclusion pattern configuration  
**Complexity**: Medium  
**Dependencies**: Story 4.2  

**Acceptance Criteria**:
- [x] List of wildcard patterns to exclude
- [x] Add/remove pattern buttons
- [x] Pattern examples shown as hint text
- [x] Patterns saved to preferences.json
- [x] Patterns read by Python sync script

**UI Layout**:
```
┌─ Excluded Events ────────────────────────────────┐
│ Events matching these patterns won't be synced:  │
│ ┌──────────────────────────────────────────┐    │
│ │ lunch*                              [x]  │    │
│ │ 1:1 *                               [x]  │    │
│ └──────────────────────────────────────────┘    │
│                              [+ Add Pattern]     │
│ Examples: "lunch*" matches "Lunch!", "LUNCH"    │
└──────────────────────────────────────────────────┘
```

---

### Epic 5: Preferences Management

#### Story 5.1: Read Preferences from JSON
**Title**: Load preferences from shared JSON file  
**Complexity**: Small  
**Dependencies**: None  

**Acceptance Criteria**:
- [x] Reads from `~/Library/Application Support/CalendarSync/preferences.json`
- [x] Handles missing file (use defaults)
- [x] Handles malformed JSON gracefully
- [x] Defines Swift Codable structs matching schema

**Preferences Schema**:
```swift
struct Preferences: Codable {
    var calendarSyncEnabled: Bool = false
    var calendarSyncSource: CalendarRef?
    var calendarSyncDestination: CalendarRef?
    var calendarSyncExcludedPatterns: [String] = []
    
    var blockingEnabled: Bool = true
    var blockingStartHour: Int = 8
    var blockingEndHour: Int = 20
    var blockingDays: String = "weekdays"
    
    var personalCalendars: [CalendarRef] = []
    var workCalendar: CalendarRef?
    
    var displayCalendars: [DisplayCalendar] = []
    
    var daysAhead: Int = 14
    var daysBack: Int = 1
}

struct CalendarRef: Codable {
    var name: String
    var source: String
}

struct DisplayCalendar: Codable {
    var name: String
    var source: String
    var icon: String
}
```

---

#### Story 5.2: Write Preferences to JSON
**Title**: Save preferences to shared JSON file  
**Complexity**: Small  
**Dependencies**: Story 5.1  

**Acceptance Criteria**:
- [x] Writes to `~/Library/Application Support/CalendarSync/preferences.json`
- [x] Creates directory if needed
- [ ] Preserves existing unknown keys (forward compatibility)
- [x] Uses consistent JSON formatting (indent, sorted keys)

---

#### Story 5.3: Read Event Mapping for Sync Status
**Title**: Load event mapping to show sync status  
**Complexity**: Small  
**Dependencies**: Story 5.1  

**Acceptance Criteria**:
- [x] Reads `event_mapping.json` for Apple→Google mapping
- [x] Reads `personal_block_mapping.json` for Personal→Work mapping
- [x] Provides lookup function: `isSynced(appleEventId:) -> Bool`
- [x] Handles missing/malformed files

---

### Epic 6: App Polish & Packaging

#### Story 6.1: Menubar Icon States
**Title**: Implement all menubar icon states  
**Complexity**: Small  
**Dependencies**: Story 1.1, Story 3.2  

**Acceptance Criteria**:
- [x] Idle state: `calendar_idle.png`
- [x] Syncing state: `manualsync.png`
- [ ] Scheduled sync: `schedule_sync.png`
- [x] Success: `sync_success.png`
- [ ] Warning: `warning.png`
- [x] Failed: `sync_failed.png`
- [x] Icons are template images (adapt to dark/light mode)

---

#### Story 6.2: Launch at Login
**Title**: Add launch at login option  
**Complexity**: Small  
**Dependencies**: Story 4.1  

**Acceptance Criteria**:
- [ ] Settings toggle for "Launch at Login" (deferred — requires app bundle)
- [ ] Uses `SMAppService` for macOS 13+
- [ ] Fallback to Login Items for older macOS

---

#### Story 6.3: View Logs Menu Item
**Title**: Implement View Logs action  
**Complexity**: Small  
**Dependencies**: Story 1.2  

**Acceptance Criteria**:
- [x] Opens `~/Library/Application Support/CalendarSync/Logs/` in Finder
- [ ] Or opens specific log file in Console.app

---

#### Story 6.4: App Bundle & Code Signing
**Title**: Create distributable app bundle  
**Complexity**: Medium  
**Dependencies**: All previous stories  

**Acceptance Criteria**:
- [ ] Xcode project creates proper `.app` bundle
- [ ] Python scripts bundled in Resources
- [ ] Icon assets bundled in Resources
- [ ] App is code signed (Developer ID or self-signed)
- [ ] App passes notarization (for distribution)

---

#### Story 6.5: Python Environment Bundling
**Title**: Bundle Python interpreter with app  
**Complexity**: Large  
**Dependencies**: Story 6.4  

**Acceptance Criteria**:
- [ ] Minimal Python environment bundled in app
- [ ] Required packages: `pyobjc-framework-EventKit`
- [ ] Optional: `google-api-python-client` for Google sync
- [ ] Falls back to system Python if bundled not available

**Options**:
1. Bundle full Python with py2app/PyInstaller
2. Use system Python (`/usr/bin/python3`)
3. Use Homebrew Python (check common paths)

---

## 3. Technical Details

### 3.1 Swift Menubar App Setup

**Project Structure**:
```
PezCalSyncSwift/
├── Package.swift (or .xcodeproj)
├── Sources/
│   └── PezCalSync/
│       ├── PezCalSyncApp.swift      # Main app entry
│       ├── MenuBarController.swift   # NSStatusItem management
│       ├── EventKitManager.swift     # Calendar access
│       ├── SyncManager.swift         # Python script execution
│       ├── PreferencesManager.swift  # JSON read/write
│       └── Views/
│           ├── SettingsView.swift    # Main settings window
│           ├── SyncSettingsView.swift
│           ├── BlockingSettingsView.swift
│           └── DisplaySettingsView.swift
├── Resources/
│   ├── Assets.xcassets/             # App icons
│   ├── icons/                       # Menubar & calendar icons
│   └── scripts/                     # Python scripts (copy)
└── Info.plist
```

**Key Info.plist Settings**:
```xml
<key>LSUIElement</key>
<true/>
<key>NSCalendarsUsageDescription</key>
<string>PezCalSync needs calendar access to display events and sync calendars.</string>
```

---

### 3.2 EventKit Integration

**Calendar Access**:
```swift
class EventKitManager: ObservableObject {
    let store = EKEventStore()
    @Published var hasAccess = false
    @Published var calendars: [EKCalendar] = []
    
    func requestAccess() async -> Bool {
        if #available(macOS 14.0, *) {
            do {
                return try await store.requestFullAccessToEvents()
            } catch {
                return false
            }
        } else {
            return await withCheckedContinuation { continuation in
                store.requestAccess(to: .event) { granted, _ in
                    continuation.resume(returning: granted)
                }
            }
        }
    }
    
    func fetchEvents(from start: Date, to end: Date, calendars: [EKCalendar]?) -> [EKEvent] {
        let predicate = store.predicateForEvents(withStart: start, end: end, calendars: calendars)
        return store.events(matching: predicate)
            .filter { $0.status != .canceled }
            .sorted { $0.startDate < $1.startDate }
    }
}
```

**Calendar Change Observer**:
```swift
NotificationCenter.default.addObserver(
    forName: .EKEventStoreChanged,
    object: store,
    queue: .main
) { [weak self] _ in
    self?.handleCalendarChange()
}
```

---

### 3.3 SwiftUI Settings Window

**Window Presentation**:
```swift
class AppDelegate: NSObject, NSApplicationDelegate {
    var settingsWindow: NSWindow?
    
    func showSettings() {
        if let window = settingsWindow {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        
        let settingsView = SettingsView()
        let hostingController = NSHostingController(rootView: settingsView)
        
        let window = NSWindow(contentViewController: hostingController)
        window.title = "PezCalSync Settings"
        window.styleMask = [.titled, .closable]
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        
        self.settingsWindow = window
    }
}
```

**Settings View Structure**:
```swift
struct SettingsView: View {
    @StateObject var viewModel = SettingsViewModel()
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                GoogleSyncSection(viewModel: viewModel)
                Divider()
                BlockingSyncSection(viewModel: viewModel)
                Divider()
                DisplayCalendarsSection(viewModel: viewModel)
            }
            .padding()
        }
        .frame(width: 600, height: 700)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") {
                    viewModel.save()
                    dismiss()
                }
            }
        }
    }
}
```

---

### 3.4 Python Script Execution

**SyncManager Implementation**:
```swift
class SyncManager {
    let scriptsPath: URL
    
    func runSync() async throws -> SyncResult {
        let process = Process()
        
        // Find Python interpreter
        process.executableURL = findPythonInterpreter()
        process.arguments = [scriptsPath.appendingPathComponent("calendar_sync_eventkit.py").path]
        process.currentDirectoryURL = scriptsPath
        
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
        
        try process.run()
        
        return try await withCheckedThrowingContinuation { continuation in
            process.terminationHandler = { process in
                let stdout = String(data: stdoutPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                let stderr = String(data: stderrPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                
                if process.terminationStatus == 0 {
                    // Parse JSON result from stdout
                    if let result = self.parseResult(stdout) {
                        continuation.resume(returning: result)
                    } else {
                        continuation.resume(returning: SyncResult(success: true))
                    }
                } else {
                    continuation.resume(throwing: SyncError.scriptFailed(stderr))
                }
            }
        }
    }
    
    private func findPythonInterpreter() -> URL {
        // Check bundled Python first
        let bundledPython = Bundle.main.resourceURL?
            .appendingPathComponent("python/bin/python3")
        if let bundled = bundledPython, FileManager.default.fileExists(atPath: bundled.path) {
            return bundled
        }
        
        // Fall back to system Python
        return URL(fileURLWithPath: "/usr/bin/python3")
    }
}
```

---

### 3.5 Preferences Management

**PreferencesManager**:
```swift
class PreferencesManager: ObservableObject {
    static let shared = PreferencesManager()
    
    let preferencesURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/CalendarSync/preferences.json")
    
    @Published var preferences: Preferences = .default
    
    func load() {
        guard FileManager.default.fileExists(atPath: preferencesURL.path) else {
            return
        }
        
        do {
            let data = try Data(contentsOf: preferencesURL)
            preferences = try JSONDecoder().decode(Preferences.self, from: data)
        } catch {
            print("Failed to load preferences: \(error)")
        }
    }
    
    func save() {
        do {
            // Ensure directory exists
            try FileManager.default.createDirectory(
                at: preferencesURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(preferences)
            try data.write(to: preferencesURL)
        } catch {
            print("Failed to save preferences: \(error)")
        }
    }
}
```

---

## 4. Migration Strategy

### Phase 1: Parallel Development (Week 1-2)
1. Create new Swift/SwiftUI project
2. Implement core menubar and EventKit display
3. Keep Python app running as primary
4. Test Swift app alongside Python app

### Phase 2: Feature Parity (Week 3-4)
1. Implement settings window in SwiftUI
2. Add Python script execution
3. Verify preferences compatibility
4. Test sync functionality end-to-end

### Phase 3: Transition (Week 5)
1. Replace Python app with Swift app
2. Migrate users by replacing `.app` bundle
3. Keep Python scripts in Resources
4. Monitor for issues

### Phase 4: Cleanup (Week 6+)
1. Remove unused Python UI code
2. Optimize Python scripts for subprocess execution
3. Add any deferred features
4. Polish and release

### Data Migration
**No migration required** - both apps use the same:
- `~/Library/Application Support/CalendarSync/preferences.json`
- `~/Library/Application Support/CalendarSync/event_mapping.json`
- `~/Library/Application Support/CalendarSync/personal_block_mapping.json`

The Swift app will read/write the exact same files as the Python app.

### Rollback Plan
If issues arise:
1. Quit Swift app
2. Launch Python app (keep old `.app` bundle as backup)
3. Data remains compatible

---

## 5. Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Python script execution fails in sandboxed app | High | Medium | Test early; use entitlements or disable sandbox |
| EventKit API differences from PyObjC | Medium | Low | API is standard; use same patterns |
| Settings window still has issues | High | Low | SwiftUI window lifecycle is simpler |
| Google API credentials not found | Medium | Medium | Document credential file location |
| Performance issues with large calendars | Low | Low | Same as current app; use pagination if needed |

---

## 6. Testing Checklist

### Functional Tests
- [ ] App launches and shows in menubar
- [ ] Menu displays events correctly
- [ ] Settings window opens and closes repeatedly (no crash)
- [ ] Settings save and persist correctly
- [ ] Sync executes Python script successfully
- [ ] Calendar change triggers sync
- [ ] Icon states change appropriately

### Edge Cases
- [ ] No calendar access granted
- [ ] Empty calendars
- [ ] Malformed preferences.json
- [ ] Python script missing
- [ ] Network unavailable (for Google sync)
- [ ] Very long event titles

### Compatibility
- [ ] macOS 13 (Ventura)
- [ ] macOS 14 (Sonoma)
- [ ] macOS 15 (Sequoia)
- [ ] Dark mode
- [ ] Light mode

---

## 7. Dependencies & Resources

### Swift/SwiftUI Resources
- EventKit Framework Documentation
- NSStatusItem/NSMenu Documentation
- SwiftUI Window Management

### Existing Assets to Reuse
- All PNG icons in `/src/icons/`
- Python sync scripts
- Preferences JSON schema

### External Dependencies
- None for Swift app (all native frameworks)
- Python: `pyobjc-framework-EventKit`
- Python (optional): `google-api-python-client`

---

## Appendix A: File Reference

### Icons Directory Contents
```
badminton-yellow.png
box-blue.png
brief-{blue,green,orange,purple,red,teal,white,yellow}-{circle,filled}.png
calendar_idle.png
manualsync.png
person-{black,blue,green,grey,orange,red,teal,white}-{circle,filled}.png
rollingsuitcase-purple.png
rollingsuitcase-purple-notsynced.png
schedule_sync.png
sync_failed.png
sync_success.png
warning.png
```

### Preferences JSON Example
```json
{
  "google_sync_enabled": false,
  "google_sync_source_calendar": {"name": "Calendar", "source": "Exchange"},
  "google_sync_target_calendar_id": "calendar_id@group.calendar.google.com",
  "blocking_enabled": true,
  "blocking_event_title": "apt",
  "blocking_start_hour": 8,
  "blocking_end_hour": 20,
  "blocking_days": "weekdays",
  "personal_calendars": [{"name": "Personal Cal", "source": "Google"}],
  "work_calendar": {"name": "Calendar", "source": "Exchange"},
  "display_calendars": [
    {"name": "Calendar", "source": "Exchange", "icon": "brief-purple-filled.png"},
    {"name": "Personal Cal", "source": "Google", "icon": "badminton-yellow.png"}
  ],
  "days_ahead": 14,
  "days_back": 1
}
```

---

## Appendix B: Story Dependency Graph

```
1.1 Basic Menubar ─────────────────────────────────────────────┐
       │                                                        │
       ├──► 1.2 Menu Structure ────────────────────────────────┤
       │         │                                              │
       │         ├──► 2.2 Display Events ◄── 2.1 Permissions   │
       │         │         │                                    │
       │         │         ├──► 2.3 Calendar Icons             │
       │         │         │         │                          │
       │         │         │         └──► 2.4 Sync Status Icons │
       │         │         │                                    │
       │         │         └──► 2.5 Change Notifications ──────┤
       │         │                                              │
       │         ├──► 3.1 Execute Script ──────────────────────┤
       │         │         │                                    │
       │         │         ├──► 3.2 Sync Now Action            │
       │         │         │                                    │
       │         │         ├──► 3.3 Auto Sync                  │
       │         │         │                                    │
       │         │         └──► 3.4 Periodic Sync              │
       │         │                                              │
       │         └──► 4.1 Settings Shell ──────────────────────┤
       │                   │                                    │
       │                   ├──► 4.2 Google Sync Settings       │
       │                   │                                    │
       │                   ├──► 4.3 Blocking Settings          │
       │                   │                                    │
       │                   ├──► 4.4 Display Settings           │
       │                   │                                    │
       │                   └──► 4.5 Excluded Patterns          │
       │                                                        │
       └──► 5.1 Read Preferences ◄─────────────────────────────┤
                 │                                              │
                 ├──► 5.2 Write Preferences                    │
                 │                                              │
                 └──► 5.3 Read Mappings                        │
                                                                │
6.1 Icon States ◄──────────────────────────────────────────────┤
6.2 Launch at Login ◄──────────────────────────────────────────┤
6.3 View Logs ◄────────────────────────────────────────────────┤
6.4 App Bundle ◄───────────────────────────────────────────────┘
       │
       └──► 6.5 Python Bundling
```

---

*Document Version: 1.0*  
*Last Updated: March 2026*
