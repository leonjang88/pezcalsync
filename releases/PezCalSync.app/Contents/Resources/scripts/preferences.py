#!/usr/bin/env python3
"""
Preferences management for PezCalSync

Handles loading/saving user preferences and provides a settings UI.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

# Preferences file location
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "CalendarSync"
APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
PREFERENCES_FILE = APP_SUPPORT_DIR / "preferences.json"

# Default preferences
DEFAULT_PREFERENCES = {
    "personal_calendars": [],  # List of {"name": "...", "source": "..."} 
    "work_calendar": None,     # {"name": "...", "source": "..."}
    "display_calendars": [],   # Calendars to show in menu
    "blocking_enabled": True,
    "blocking_event_title": "apt",
    "blocking_work_hours_only": True,
    "blocking_start_hour": 8,
    "blocking_end_hour": 20,
    "blocking_weekdays_only": True,
    "min_blocking_duration_minutes": 15,
    "days_ahead": 14,
    "days_back": 1,
}


def load_preferences() -> Dict[str, Any]:
    """Load preferences from file, returning defaults if not found."""
    if PREFERENCES_FILE.exists():
        try:
            with open(PREFERENCES_FILE, 'r') as f:
                prefs = json.load(f)
                # Merge with defaults for any missing keys
                merged = DEFAULT_PREFERENCES.copy()
                merged.update(prefs)
                return merged
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading preferences: {e}")
    return DEFAULT_PREFERENCES.copy()


def save_preferences(prefs: Dict[str, Any]) -> bool:
    """Save preferences to file."""
    try:
        with open(PREFERENCES_FILE, 'w') as f:
            json.dump(prefs, f, indent=2)
        return True
    except IOError as e:
        print(f"Error saving preferences: {e}")
        return False


def get_available_calendars(store=None) -> List[Dict[str, str]]:
    """Get all available calendars grouped by source/account.
    
    Returns list of dicts with keys: name, source, source_type, calendar_id
    """
    try:
        import EventKit
        
        if store is None:
            store = EventKit.EKEventStore.alloc().init()
        
        all_calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
        
        calendars = []
        for cal in all_calendars:
            source = cal.source()
            calendars.append({
                "name": str(cal.title()),
                "source": str(source.title()) if source else "Unknown",
                "source_type": _get_source_type_name(source.sourceType()) if source else "Unknown",
                "calendar_id": str(cal.calendarIdentifier()),
            })
        
        # Sort by source, then by name
        calendars.sort(key=lambda c: (c["source"], c["name"]))
        return calendars
        
    except Exception as e:
        print(f"Error getting calendars: {e}")
        return []


def _get_source_type_name(source_type: int) -> str:
    """Convert EKSourceType to human-readable name."""
    # EKSourceType enum values
    source_types = {
        0: "Local",
        1: "Exchange",
        2: "CalDAV",
        3: "MobileMe",
        4: "Subscribed",
        5: "Birthdays",
    }
    return source_types.get(source_type, "Other")


def get_calendars_by_source(store=None) -> Dict[str, List[Dict[str, str]]]:
    """Get calendars organized by source account.
    
    Returns dict: {source_name: [calendar_info, ...]}
    """
    calendars = get_available_calendars(store)
    
    by_source = {}
    for cal in calendars:
        source = cal["source"]
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(cal)
    
    return by_source


class PreferencesWindow:
    """A simple preferences window using rumps alerts and menus."""
    
    def __init__(self, store=None):
        self.store = store
        self.prefs = load_preferences()
    
    def show_calendar_picker(self, title: str, multi_select: bool = False) -> Optional[List[Dict]]:
        """Show a calendar selection dialog.
        
        For now, returns the current selection. A full implementation would
        use a proper UI framework like PyObjC's NSAlert with accessory view.
        """
        import rumps
        
        calendars_by_source = get_calendars_by_source(self.store)
        
        # Build a simple text representation
        lines = [f"{title}\n"]
        cal_list = []
        index = 1
        
        for source, cals in calendars_by_source.items():
            lines.append(f"\n📁 {source}:")
            for cal in cals:
                lines.append(f"   {index}. {cal['name']}")
                cal_list.append(cal)
                index += 1
        
        lines.append("\n\nEnter number(s) separated by commas:")
        
        # Show input dialog
        response = rumps.Window(
            message="\n".join(lines),
            title="Select Calendar(s)",
            default_text="",
            ok="Select",
            cancel="Cancel",
            dimensions=(300, 24)
        ).run()
        
        if response.clicked:
            try:
                if multi_select:
                    indices = [int(x.strip()) - 1 for x in response.text.split(",")]
                    return [cal_list[i] for i in indices if 0 <= i < len(cal_list)]
                else:
                    idx = int(response.text.strip()) - 1
                    if 0 <= idx < len(cal_list):
                        return [cal_list[idx]]
            except (ValueError, IndexError):
                pass
        
        return None
    
    def configure_personal_calendars(self):
        """Let user select personal calendars."""
        selected = self.show_calendar_picker(
            "Select Personal Calendar(s)\n(events from these will create blocks on work calendar)",
            multi_select=True
        )
        
        if selected:
            self.prefs["personal_calendars"] = [
                {"name": c["name"], "source": c["source"]} for c in selected
            ]
            save_preferences(self.prefs)
            return True
        return False
    
    def configure_work_calendar(self):
        """Let user select work calendar."""
        selected = self.show_calendar_picker(
            "Select Work Calendar\n(blocking events will be created here)",
            multi_select=False
        )
        
        if selected:
            c = selected[0]
            self.prefs["work_calendar"] = {"name": c["name"], "source": c["source"]}
            save_preferences(self.prefs)
            return True
        return False
    
    def configure_display_calendars(self):
        """Let user select which calendars to display in menu."""
        selected = self.show_calendar_picker(
            "Select Calendars to Display in Menu",
            multi_select=True
        )
        
        if selected:
            self.prefs["display_calendars"] = [
                {"name": c["name"], "source": c["source"]} for c in selected
            ]
            save_preferences(self.prefs)
            return True
        return False


def get_personal_calendar_names() -> List[str]:
    """Get list of personal calendar names from preferences."""
    prefs = load_preferences()
    return [c["name"] for c in prefs.get("personal_calendars", [])]


def get_work_calendar_name() -> Optional[str]:
    """Get work calendar name from preferences."""
    prefs = load_preferences()
    work_cal = prefs.get("work_calendar")
    return work_cal["name"] if work_cal else None


def get_display_calendar_names() -> List[str]:
    """Get list of display calendar names from preferences."""
    prefs = load_preferences()
    display_cals = prefs.get("display_calendars", [])
    return [c["name"] for c in display_cals] if display_cals else []
