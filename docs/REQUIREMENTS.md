# PezCalSync Requirements

## Overview
A macOS menubar application that syncs calendars and creates blocking events.

---

## Event Exclusion Patterns

### Pattern Matching Rules
- Patterns are **case-insensitive**
- `*` wildcard matches any characters (zero or more)
- Patterns are matched against the **event title**

### Examples
| Pattern | Matches | Doesn't Match |
|---------|---------|---------------|
| `lunch*` | "Lunch!", "lunch break", "LUNCH" | "Team lunch" |
| `*lunch*` | "Team lunch", "Lunch!", "prelunch" | "Dinner" |
| `1:1 *` | "1:1 John", "1:1 with Manager" | "Team 1:1" |
| `standup` | "Standup", "STANDUP" | "Daily standup" |

### Implementation
Use `fnmatch` module in Python with case-insensitive comparison:
```python
import fnmatch

def is_excluded(event_title: str, patterns: list[str]) -> bool:
    title_lower = event_title.lower()
    for pattern in patterns:
        if fnmatch.fnmatch(title_lower, pattern.lower()):
            return True
    return False
```

---

## Sync Types

### 1. Work Calendar → Personal Calendar Sync
- **Purpose**: Mirror work calendar events to a personal calendar (Google synced via Apple Calendar)
- **Source**: Apple Calendar (Exchange account - "Calendar")
- **Destination**: Apple Calendar (Google account calendar synced locally)
- **Features**:
  - Sync events within configurable time window (default: 1 day back, 14 days ahead)
  - Track synced events via mapping file to handle updates/deletes
  - **Exclude events by pattern** (wildcard support, e.g., "lunch*" matches "lunch!", "lunch break")
  - Optional event title prefix

### 2. Personal Calendar → Work Calendar Blocking
- **Purpose**: Create "apt" blocking events on work calendar for personal events
- **Source**: Personal Cal (iCloud/Google calendar)
- **Destination**: Work Exchange calendar ("Calendar")
- **Features**:
  - Only block during configurable work hours (default: 8 AM - 8 PM)
  - Option for weekdays only or all days
  - Skip all-day events
  - Skip events already covered by manual "apt" events
  - Track blocked events via mapping file

---

## User Interface

### Menubar Icon
- Shows sync status (idle, syncing, error)
- Customizable icon per calendar displayed

### Menubar Menu
- **Today's Events**: Show upcoming events grouped by calendar
  - Each calendar section shows events with time and title
  - Customizable icon per calendar
  - **Sync status indicator** (for work calendar when sync enabled):
    - User's **selected variant** = event IS synced to destination calendar
    - **Opposite variant** = event NOT yet synced
    - Example: If user selects "circle" icon, circle = synced, filled = not synced
    - Example: If user selects "filled" icon, filled = synced, circle = not synced
- **Sync Now**: Manual sync trigger
- **Settings**: Open settings window
- **Quit**: Exit application

### Settings Window
Must support reopening without crashing (current Python/PyObjC issue).

#### Section 1: Work → Personal Calendar Sync
- [ ] Enable/disable toggle
- [ ] Source calendar dropdown (list all Apple calendars)
- [ ] Destination calendar dropdown (list all Apple calendars)
- [ ] **Excluded event patterns** (list of wildcard patterns, e.g., "lunch*", "1:1 *")

#### Section 2: Personal → Work Blocking
- [ ] Enable/disable toggle
- [ ] Personal calendar dropdown
- [ ] Work calendar dropdown
- [ ] Blocking hours: Start time dropdown (6 AM - 11 PM)
- [ ] Blocking hours: End time dropdown (6 AM - 11 PM)
- [ ] Block on: "Weekdays Only" / "All Days" dropdown

#### Section 3: Display in Menu
- List of all calendars with:
  - [ ] Checkbox to show/hide in menu
  - [ ] Icon type dropdown (Brief, Person, Badminton, Rolling Suitcase, Box, Calendar)
  - [ ] Icon color/style dropdown (varies by type)

#### Buttons
- Save: Save preferences and close
- Cancel: Close without saving

---

## Data Storage

### Location
`~/Library/Application Support/CalendarSync/`

### Files
- `preferences.json` - User settings
- `event_mapping.json` - Work→Personal calendar event ID mapping
- `personal_block_mapping.json` - Personal→Work blocking event mapping
- `Logs/` - Log files

### Preferences Schema
```json
{
  "calendar_sync_enabled": false,
  "calendar_sync_source": {"name": "Calendar", "source": "Exchange"},
  "calendar_sync_destination": {"name": "Personal Cal", "source": "Google"},
  "calendar_sync_excluded_patterns": ["lunch*", "1:1 *"],
  
  "blocking_enabled": true,
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

## Icons

### Icon Sync Status Logic
When **calendar sync is enabled**, work calendar events in the menu should show:
- **User's selected variant** = Event IS synced to destination calendar
- **Opposite variant** = Event NOT yet synced to destination calendar

**Examples:**
- User selects `brief-purple-circle.png` → circle = synced, filled = not synced
- User selects `brief-purple-filled.png` → filled = synced, circle = not synced

**Implementation:**
```swift
func iconForEvent(event: EKEvent, isSynced: Bool, selectedIcon: String) -> String {
    if !isSynced {
        // Swap to opposite variant
        if selectedIcon.contains("-circle") {
            return selectedIcon.replacingOccurrences(of: "-circle", with: "-filled")
        } else if selectedIcon.contains("-filled") {
            return selectedIcon.replacingOccurrences(of: "-filled", with: "-circle")
        }
    }
    return selectedIcon  // Synced = use selected icon as-is
}
```

This requires checking the `event_mapping.json` to see if the event's Apple ID exists in the mapping.

When calendar sync is disabled, always show the user's selected icon variant.

### Available Icon Types
| Type | Variants |
|------|----------|
| Brief | Blue/Green/Orange/Purple/Red/Teal/White/Yellow × Circle/Filled |
| Person | Black/Blue/Green/Grey/Orange/Red/Teal/White × Circle/Filled |
| Badminton | Yellow |
| Rolling Suitcase | Purple, Purple (Not Synced) |
| Box | Blue |
| Calendar | Default (idle) |

### Menubar Status Icons
- `calendar_idle.png` - Normal state
- Custom icons for syncing/error states

---

## Technical Requirements

### Platform
- macOS 13.0+ (Ventura or later)
- Native Swift + SwiftUI for UI
- Python for sync logic (called via subprocess)

### Permissions Required
- Calendar access (EventKit)
- Network access (Google API)

### Sync Behavior
- Auto-sync on calendar change notification
- Auto-sync on timer (configurable interval)
- Manual sync via menu
- Show notification on settings save

---

## Architecture

### Swift App (UI Layer)
- Menubar status item
- Menu with events display
- Settings window (SwiftUI)
- Python script execution
- EventKit calendar access for display

### Python Scripts (Sync Logic)
- `calendar_sync.py` - Apple→Google sync + Personal→Work blocking
- Reads/writes preferences.json
- Reads/writes mapping files
- Outputs sync results to stdout

### Communication
- Swift calls Python scripts via `Process`
- Python reads preferences from JSON
- Python outputs status/results to stdout
- Swift parses output for notifications

---

## Future Enhancements
- [ ] Multiple personal calendars support
- [ ] Multiple Google calendar targets
- [ ] Custom blocking event titles
- [ ] Sync interval configuration in UI
- [ ] Event exclusion patterns in UI
- [ ] Dark mode icon variants
