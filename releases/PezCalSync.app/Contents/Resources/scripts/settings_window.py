#!/usr/bin/env python3
"""
Settings Window for PezCalSync

Native macOS settings window with dropdown menus for calendar selection.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from AppKit import (
        NSApplication, NSWindow, NSView, NSTextField, NSPopUpButton,
        NSButton, NSFont, NSColor, NSWindowStyleMaskTitled,
        NSWindowStyleMaskClosable, NSBackingStoreBuffered,
        NSMakeRect, NSBezelStyleRounded, NSTextFieldCell,
        NSLineBreakByTruncatingTail, NSControlStateValueOn,
        NSControlStateValueOff, NSStackView, NSUserInterfaceLayoutOrientationVertical,
        NSLayoutAttributeLeading, NSLayoutAttributeTrailing,
    )
    from Foundation import NSObject
    import objc
except ImportError as e:
    print(f"Error importing AppKit: {e}")

# Preferences file location
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "CalendarSync"
APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
PREFERENCES_FILE = APP_SUPPORT_DIR / "preferences.json"

# Default preferences
DEFAULT_PREFERENCES = {
    "personal_calendars": [],
    "work_calendar": None,
    "display_calendars": [],
    # Google Calendar Sync settings
    "google_sync_enabled": False,
    "google_sync_source_calendar": None,  # Apple/Exchange calendar to sync FROM
    "google_sync_target_calendar_id": "",  # Google Calendar ID to sync TO
    # Personal→Work Blocking settings
    "blocking_enabled": True,
    "blocking_event_title": "apt",
    "blocking_start_hour": 8,
    "blocking_end_hour": 20,
    "blocking_days": "weekdays",  # "weekdays" or "all"
    "min_blocking_duration_minutes": 15,
    # General settings
    "days_ahead": 14,
    "days_back": 1,
    "menubar_icon": "calendar_idle.png",
}

# Icon types with their available colors/variants
# Format: "type": [(display_name, filename), ...]
ICON_TYPES = {
    "Brief": [
        ("Blue (Circle)", "brief-blue-circle.png"),
        ("Blue (Filled)", "brief-blue-filled.png"),
        ("Green (Circle)", "brief-green-circle.png"),
        ("Green (Filled)", "brief-green-filled.png"),
        ("Orange (Circle)", "brief-orange-circle.png"),
        ("Orange (Filled)", "brief-orange-filled.png"),
        ("Purple (Circle)", "brief-purple-circle.png"),
        ("Purple (Filled)", "brief-purple-filled.png"),
        ("Red (Circle)", "brief-red-circle.png"),
        ("Red (Filled)", "brief-red-filled.png"),
        ("Teal (Circle)", "brief-teal-circle.png"),
        ("Teal (Filled)", "brief-teal-filled.png"),
        ("White (Circle)", "brief-white-circle.png"),
        ("White (Filled)", "brief-white-filled.png"),
        ("Yellow (Circle)", "brief-yellow-circle.png"),
        ("Yellow (Filled)", "brief-yellow-filled.png"),
    ],
    "Person": [
        ("Black (Circle)", "person-black-circle.png"),
        ("Black (Filled)", "person-black-filled.png"),
        ("Blue (Circle)", "person-blue-circle.png"),
        ("Blue (Filled)", "person-blue-filled.png"),
        ("Green (Filled)", "person-green-filled.png"),
        ("Grey (Circle)", "person-grey-circle.png"),
        ("Grey (Filled)", "person-grey-filled.png"),
        ("Orange (Circle)", "person-orange-circle.png"),
        ("Orange (Filled)", "person-orange-filled.png"),
        ("Red (Circle)", "person-red-circle.png"),
        ("Red (Filled)", "person-red-filled.png"),
        ("Teal (Circle)", "person-teal-circle.png"),
        ("Teal (Filled)", "person-teal-filled.png"),
        ("White (Circle)", "person-white-circle.png"),
        ("White (Filled)", "person-white-filled.png"),
    ],
    "Badminton": [
        ("Yellow", "badminton-yellow.png"),
    ],
    "Rolling Suitcase": [
        ("Purple", "rollingsuitcase-purple.png"),
        ("Purple (Not Synced)", "rollingsuitcase-purple-notsynced.png"),
    ],
    "Box": [
        ("Blue", "box-blue.png"),
    ],
    "Calendar": [
        ("Default", "calendar_idle.png"),
    ],
}

def get_icon_type_from_filename(filename: str) -> Optional[str]:
    """Get the icon type from a filename."""
    if not filename:
        return None
    for icon_type, variants in ICON_TYPES.items():
        for _, fn in variants:
            if fn == filename:
                return icon_type
    return None

def get_icon_variant_name(filename: str) -> Optional[str]:
    """Get the variant display name from a filename."""
    if not filename:
        return None
    for icon_type, variants in ICON_TYPES.items():
        for name, fn in variants:
            if fn == filename:
                return name
    return None


def load_preferences() -> Dict[str, Any]:
    """Load preferences from file."""
    if PREFERENCES_FILE.exists():
        try:
            with open(PREFERENCES_FILE, 'r') as f:
                prefs = json.load(f)
                merged = DEFAULT_PREFERENCES.copy()
                merged.update(prefs)
                return merged
        except (json.JSONDecodeError, IOError):
            pass
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
    """Get all available calendars grouped by source/account."""
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
        
        calendars.sort(key=lambda c: (c["source"], c["name"]))
        return calendars
        
    except Exception as e:
        print(f"Error getting calendars: {e}")
        return []


def _get_source_type_name(source_type: int) -> str:
    """Convert EKSourceType to human-readable name."""
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
    """Get calendars organized by source account."""
    calendars = get_available_calendars(store)
    
    by_source = {}
    for cal in calendars:
        source = cal["source"]
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(cal)
    
    return by_source


class SettingsWindowController(NSObject):
    """Controller for the settings window."""
    
    def init(self):
        self = objc.super(SettingsWindowController, self).init()
        if self is None:
            return None
        
        self.store = None
        self.prefs = load_preferences()
        self.calendars = []
        self.window = None
        self.personal_popup = None
        self.work_popup = None
        self.display_checkboxes = []  # List of (checkbox, cal, type_popup, variant_popup) tuples
        self.on_save_callback = None
        
        # Google Sync controls
        self.google_sync_checkbox = None
        self.google_source_popup = None
        self.google_target_field = None
        
        # Blocking Sync controls
        self.blocking_checkbox = None
        self.blocking_start_popup = None
        self.blocking_end_popup = None
        self.blocking_days_popup = None
        
        return self
    
    def setStore_(self, store):
        """Set the EventKit store."""
        self.store = store
        self.calendars = get_available_calendars(store)
    
    def setOnSaveCallback_(self, callback):
        """Set callback to run after saving."""
        self.on_save_callback = callback
    
    def showWindow(self):
        """Create and show the settings window."""
        try:
            # If window exists and is visible, just bring it to front
            if self.window is not None:
                try:
                    if self.window.isVisible():
                        self.window.makeKeyAndOrderFront_(None)
                        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                        return
                except:
                    pass
            
            # Reload preferences fresh each time
            self.prefs = load_preferences()
            # Reset all UI element references
            self.window = None
            self.personal_popup = None
            self.work_popup = None
            self.display_checkboxes = []
            self.google_sync_checkbox = None
            self.google_source_popup = None
            self.google_target_field = None
            self.blocking_checkbox = None
            self.blocking_start_popup = None
            self.blocking_end_popup = None
            self.blocking_days_popup = None
            
            self._buildWindow()
        except Exception as e:
            import traceback
            print(f"ERROR in showWindow: {e}")
            traceback.print_exc()
    
    def _buildWindow(self):
        """Build the settings window UI."""
        # Calculate height based on number of calendars
        calendars_by_source = get_calendars_by_source(self.store)
        num_calendars = sum(len(cals) for cals in calendars_by_source.values())
        num_sources = len(calendars_by_source)
        
        # Window dimensions
        width = 620
        
        # Calculate exact content height needed:
        # - Top padding: 40
        # - Google Sync section: header(30) + checkbox row(35) + calendar row(35) + target field row(35) = 135
        # - Personal→Work Blocking section: header(30) + checkbox row(35) + calendars(70) + hours(35) + days(35) = 205
        # - Display section: header(30) + column headers(20) + calendars
        # - Per source: header (33) + calendars (32 each with icon dropdowns) + gap (10)
        # - Bottom padding for buttons: 70
        
        google_section = 150  # Google sync settings
        blocking_section = 210  # Personal→Work blocking settings
        display_header = 50
        checkbox_section = num_sources * 43 + num_calendars * 32
        button_section = 70
        
        height = 40 + google_section + blocking_section + display_header + checkbox_section + button_section
        height = max(700, height)  # Minimum for usability
        
        # Create window
        frame = NSMakeRect(200, 200, width, height)
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("PezCalSync Settings")
        self.window.center()
        
        # Content view
        content = self.window.contentView()
        
        y_offset = height - 40
        label_width = 180
        control_width = 250
        row_height = 35
        
        # =========================================================================
        # GOOGLE CALENDAR SYNC SECTION
        # =========================================================================
        y_offset = self._add_section_header(content, "Apple → Google Calendar Sync", y_offset, width)
        y_offset -= 5
        
        # Enable/Disable checkbox
        self.google_sync_checkbox = NSButton.alloc().initWithFrame_(NSMakeRect(20, y_offset, 300, 24))
        self.google_sync_checkbox.setButtonType_(3)  # Switch/checkbox
        self.google_sync_checkbox.setTitle_("Enable Apple → Google sync")
        self.google_sync_checkbox.setState_(
            NSControlStateValueOn if self.prefs.get("google_sync_enabled", False) else NSControlStateValueOff
        )
        self.google_sync_checkbox.setTarget_(self)
        self.google_sync_checkbox.setAction_(objc.selector(self.googleSyncToggled_, signature=b'v@:@'))
        content.addSubview_(self.google_sync_checkbox)
        y_offset -= row_height
        
        # Source calendar dropdown (Apple/Exchange calendar)
        y_offset = self._add_label(content, "Source Calendar:", 40, y_offset)
        self.google_source_popup = self._create_calendar_popup(content, 40 + label_width, y_offset + 3, control_width)
        source_cal = self.prefs.get("google_sync_source_calendar")
        if source_cal:
            self._select_calendar_in_popup(self.google_source_popup, [source_cal])
        y_offset -= row_height
        
        # Target Google Calendar ID field
        y_offset = self._add_label(content, "Google Calendar ID:", 40, y_offset)
        self.google_target_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(40 + label_width, y_offset + 3, control_width, 22)
        )
        self.google_target_field.setStringValue_(self.prefs.get("google_sync_target_calendar_id", ""))
        self.google_target_field.setPlaceholderString_("calendar_id@group.calendar.google.com")
        self.google_target_field.setFont_(NSFont.systemFontOfSize_(11))
        content.addSubview_(self.google_target_field)
        y_offset -= row_height
        
        # Update enabled state of Google sync controls
        self._updateGoogleSyncControlsState()
        
        # =========================================================================
        # PERSONAL → WORK BLOCKING SECTION
        # =========================================================================
        y_offset -= 15
        y_offset = self._add_section_header(content, "Personal → Work Calendar Blocking", y_offset, width)
        y_offset -= 5
        
        # Enable/Disable checkbox
        self.blocking_checkbox = NSButton.alloc().initWithFrame_(NSMakeRect(20, y_offset, 350, 24))
        self.blocking_checkbox.setButtonType_(3)  # Switch/checkbox
        self.blocking_checkbox.setTitle_("Enable Personal → Work blocking")
        self.blocking_checkbox.setState_(
            NSControlStateValueOn if self.prefs.get("blocking_enabled", True) else NSControlStateValueOff
        )
        self.blocking_checkbox.setTarget_(self)
        self.blocking_checkbox.setAction_(objc.selector(self.blockingToggled_, signature=b'v@:@'))
        content.addSubview_(self.blocking_checkbox)
        y_offset -= row_height
        
        # Personal Calendar dropdown
        y_offset = self._add_label(content, "Personal Calendar:", 40, y_offset)
        self.personal_popup = self._create_calendar_popup(content, 40 + label_width, y_offset + 3, control_width)
        self._select_calendar_in_popup(self.personal_popup, self.prefs.get("personal_calendars", []))
        y_offset -= row_height
        
        # Work Calendar dropdown
        y_offset = self._add_label(content, "Work Calendar:", 40, y_offset)
        self.work_popup = self._create_calendar_popup(content, 40 + label_width, y_offset + 3, control_width)
        work_cal = self.prefs.get("work_calendar")
        if work_cal:
            self._select_calendar_in_popup(self.work_popup, [work_cal])
        y_offset -= row_height
        
        # Blocking hours row (start and end time)
        y_offset = self._add_label(content, "Blocking Hours:", 40, y_offset)
        
        # Start hour dropdown
        self.blocking_start_popup = self._create_hour_popup(content, 40 + label_width, y_offset + 3, 70)
        self.blocking_start_popup.selectItemWithTitle_(
            self._format_hour(self.prefs.get("blocking_start_hour", 8))
        )
        
        # "to" label
        to_label = NSTextField.alloc().initWithFrame_(NSMakeRect(40 + label_width + 75, y_offset + 3, 25, 22))
        to_label.setStringValue_("to")
        to_label.setBezeled_(False)
        to_label.setDrawsBackground_(False)
        to_label.setEditable_(False)
        to_label.setSelectable_(False)
        to_label.setAlignment_(1)  # Center
        content.addSubview_(to_label)
        
        # End hour dropdown
        self.blocking_end_popup = self._create_hour_popup(content, 40 + label_width + 100, y_offset + 3, 70)
        self.blocking_end_popup.selectItemWithTitle_(
            self._format_hour(self.prefs.get("blocking_end_hour", 20))
        )
        y_offset -= row_height
        
        # Days selection
        y_offset = self._add_label(content, "Block On:", 40, y_offset)
        self.blocking_days_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(40 + label_width, y_offset + 3, 120, 25), False
        )
        self.blocking_days_popup.addItemWithTitle_("Weekdays Only")
        self.blocking_days_popup.addItemWithTitle_("All Days")
        days_pref = self.prefs.get("blocking_days", "weekdays")
        if days_pref == "all":
            self.blocking_days_popup.selectItemWithTitle_("All Days")
        else:
            self.blocking_days_popup.selectItemWithTitle_("Weekdays Only")
        content.addSubview_(self.blocking_days_popup)
        y_offset -= row_height
        
        # Update enabled state of blocking controls
        self._updateBlockingControlsState()
        
        # =========================================================================
        # DISPLAY CALENDARS SECTION
        # =========================================================================
        y_offset -= 15
        y_offset = self._add_section_header(content, "Display in Menu", y_offset, width)
        y_offset -= 5
        
        # Column headers
        hint_label = NSTextField.alloc().initWithFrame_(NSMakeRect(45, y_offset, 180, 16))
        hint_label.setStringValue_("Calendar")
        hint_label.setBezeled_(False)
        hint_label.setDrawsBackground_(False)
        hint_label.setEditable_(False)
        hint_label.setSelectable_(False)
        hint_label.setFont_(NSFont.boldSystemFontOfSize_(10))
        hint_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(hint_label)
        
        icon_type_label = NSTextField.alloc().initWithFrame_(NSMakeRect(width - 250, y_offset, 80, 16))
        icon_type_label.setStringValue_("Icon")
        icon_type_label.setBezeled_(False)
        icon_type_label.setDrawsBackground_(False)
        icon_type_label.setEditable_(False)
        icon_type_label.setSelectable_(False)
        icon_type_label.setFont_(NSFont.boldSystemFontOfSize_(10))
        icon_type_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(icon_type_label)
        
        variant_label = NSTextField.alloc().initWithFrame_(NSMakeRect(width - 145, y_offset, 120, 16))
        variant_label.setStringValue_("Color/Style")
        variant_label.setBezeled_(False)
        variant_label.setDrawsBackground_(False)
        variant_label.setEditable_(False)
        variant_label.setSelectable_(False)
        variant_label.setFont_(NSFont.boldSystemFontOfSize_(10))
        variant_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(variant_label)
        y_offset -= 20
        
        # Get saved display calendar preferences (with icons)
        self.display_checkboxes = []
        display_cal_prefs = self.prefs.get("display_calendars", [])
        display_cals_dict = {c["name"]: c for c in display_cal_prefs}
        
        for source, cals in calendars_by_source.items():
            # Source header with spacing
            y_offset -= 8
            y_offset = self._add_label(content, f"📁 {source}", 25, y_offset, bold=True)
            y_offset -= 25
            
            for cal in cals:
                # Checkbox for enabling this calendar
                checkbox = NSButton.alloc().initWithFrame_(NSMakeRect(45, y_offset, 180, 24))
                checkbox.setButtonType_(3)  # Switch/checkbox
                checkbox.setTitle_(cal["name"])
                
                # Check if enabled based on saved preferences
                saved_cal = display_cals_dict.get(cal["name"])
                is_enabled = saved_cal is not None if display_cals_dict else cal["name"] in ['Calendar', 'Personal Cal', 'Release Calendar']
                checkbox.setState_(NSControlStateValueOn if is_enabled else NSControlStateValueOff)
                content.addSubview_(checkbox)
                
                # Icon type dropdown (Brief, Person, Calendar, etc.)
                type_popup = self._create_icon_type_popup(content, width - 250, y_offset, 100)
                
                # Icon variant dropdown (color/style) - updates based on type selection
                variant_popup = self._create_icon_variant_popup(content, width - 145, y_offset, 120)
                
                # Set saved icon or default
                saved_icon = saved_cal.get("icon") if saved_cal else None
                if saved_icon:
                    self._select_icon_type_and_variant(type_popup, variant_popup, saved_icon)
                
                # Link type popup to update variant popup when changed
                type_popup.setTarget_(self)
                type_popup.setAction_(objc.selector(self.iconTypeChanged_, signature=b'v@:@'))
                
                self.display_checkboxes.append((checkbox, cal, type_popup, variant_popup))
                y_offset -= 30  # More spacing between rows
            
            y_offset -= 10  # Gap between source groups
        
        # =========================================================================
        # BUTTONS
        # =========================================================================
        button_y = 20
        
        # Save button
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(width - 100, button_y, 80, 30))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setTarget_(self)
        save_btn.setAction_(objc.selector(self.saveSettings_, signature=b'v@:@'))
        content.addSubview_(save_btn)
        
        # Cancel button
        cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(width - 190, button_y, 80, 30))
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(NSBezelStyleRounded)
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_(objc.selector(self.cancelSettings_, signature=b'v@:@'))
        content.addSubview_(cancel_btn)
        
        # Show window
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    
    def _add_section_header(self, view, text, y, width):
        """Add a section header label."""
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y, width - 40, 20))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(NSFont.boldSystemFontOfSize_(13))
        view.addSubview_(label)
        return y - 30
    
    def _add_label(self, view, text, x, y, bold=False):
        """Add a label."""
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, 150, 20))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        if bold:
            label.setFont_(NSFont.boldSystemFontOfSize_(11))
        view.addSubview_(label)
        return y
    
    def _create_calendar_popup(self, view, x, y, width):
        """Create a popup button with calendar options."""
        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(x, y, width, 25), False
        )
        
        # Add calendars grouped by source
        calendars_by_source = get_calendars_by_source(self.store)
        
        popup.addItemWithTitle_("(None)")
        
        for source, cals in calendars_by_source.items():
            # Add separator and source header
            popup.menu().addItem_(objc.lookUpClass('NSMenuItem').separatorItem())
            header = objc.lookUpClass('NSMenuItem').alloc().initWithTitle_action_keyEquivalent_(
                f"— {source} —", None, ""
            )
            header.setEnabled_(False)
            popup.menu().addItem_(header)
            
            for cal in cals:
                popup.addItemWithTitle_(cal["name"])
        
        view.addSubview_(popup)
        return popup
    
    def _select_calendar_in_popup(self, popup, calendars):
        """Select a calendar in the popup."""
        if calendars and len(calendars) > 0:
            cal_name = calendars[0].get("name", "") if isinstance(calendars[0], dict) else calendars[0]
            popup.selectItemWithTitle_(cal_name)
    
    def _create_icon_type_popup(self, view, x, y, width):
        """Create a popup button for icon type selection (Brief, Person, etc.)."""
        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(x, y, width, 24), False
        )
        popup.setFont_(NSFont.systemFontOfSize_(11))
        
        # Add "None" option
        popup.addItemWithTitle_("None")
        
        # Add each icon type
        for icon_type in ICON_TYPES.keys():
            popup.addItemWithTitle_(icon_type)
        
        view.addSubview_(popup)
        return popup
    
    def _create_icon_variant_popup(self, view, x, y, width):
        """Create a popup button for icon variant/color selection."""
        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(x, y, width, 24), False
        )
        popup.setFont_(NSFont.systemFontOfSize_(11))
        
        # Start empty - will be populated when type is selected
        popup.addItemWithTitle_("—")
        popup.setEnabled_(False)
        
        view.addSubview_(popup)
        return popup
    
    def _update_variant_popup_for_type(self, variant_popup, icon_type):
        """Update the variant popup with options for the selected icon type."""
        variant_popup.removeAllItems()
        
        if icon_type == "None" or icon_type not in ICON_TYPES:
            variant_popup.addItemWithTitle_("—")
            variant_popup.setEnabled_(False)
            return
        
        variant_popup.setEnabled_(True)
        variants = ICON_TYPES[icon_type]
        for display_name, filename in variants:
            variant_popup.addItemWithTitle_(display_name)
            item = variant_popup.lastItem()
            item.setRepresentedObject_(filename)
    
    def _select_icon_type_and_variant(self, type_popup, variant_popup, icon_filename):
        """Select the correct type and variant for a saved icon filename."""
        if not icon_filename:
            type_popup.selectItemWithTitle_("None")
            self._update_variant_popup_for_type(variant_popup, "None")
            return
        
        # Find which type and variant this filename belongs to
        icon_type = get_icon_type_from_filename(icon_filename)
        if icon_type:
            type_popup.selectItemWithTitle_(icon_type)
            self._update_variant_popup_for_type(variant_popup, icon_type)
            
            # Select the variant
            for i in range(variant_popup.numberOfItems()):
                item = variant_popup.itemAtIndex_(i)
                if item.representedObject() == icon_filename:
                    variant_popup.selectItemAtIndex_(i)
                    return
        
        # Not found, select None
        type_popup.selectItemWithTitle_("None")
        self._update_variant_popup_for_type(variant_popup, "None")
    
    def _get_selected_icon_filename(self, type_popup, variant_popup):
        """Get the selected icon filename from type and variant popups."""
        type_title = type_popup.titleOfSelectedItem()
        if type_title == "None" or not type_title:
            return None
        
        item = variant_popup.selectedItem()
        if item:
            obj = item.representedObject()
            if obj:
                return str(obj)
        return None
    
    def _create_hour_popup(self, view, x, y, width):
        """Create a popup button for hour selection (6 AM to 11 PM)."""
        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(x, y, width, 25), False
        )
        popup.setFont_(NSFont.systemFontOfSize_(11))
        
        # Add hours from 6 AM to 11 PM
        for hour in range(6, 24):
            popup.addItemWithTitle_(self._format_hour(hour))
        
        view.addSubview_(popup)
        return popup
    
    def _format_hour(self, hour: int) -> str:
        """Format hour as 12-hour time string."""
        if hour == 0:
            return "12 AM"
        elif hour < 12:
            return f"{hour} AM"
        elif hour == 12:
            return "12 PM"
        else:
            return f"{hour - 12} PM"
    
    def _parse_hour(self, hour_str: str) -> int:
        """Parse hour string back to 24-hour integer."""
        hour_str = hour_str.strip()
        if hour_str.endswith(" AM"):
            hour = int(hour_str.replace(" AM", ""))
            return 0 if hour == 12 else hour
        elif hour_str.endswith(" PM"):
            hour = int(hour_str.replace(" PM", ""))
            return hour if hour == 12 else hour + 12
        return 8  # Default
    
    def _updateGoogleSyncControlsState(self):
        """Enable/disable Google sync controls based on checkbox state."""
        enabled = self.google_sync_checkbox.state() == NSControlStateValueOn
        self.google_source_popup.setEnabled_(enabled)
        self.google_target_field.setEnabled_(enabled)
        if not enabled:
            self.google_target_field.setTextColor_(NSColor.disabledControlTextColor())
        else:
            self.google_target_field.setTextColor_(NSColor.controlTextColor())
    
    def _updateBlockingControlsState(self):
        """Enable/disable blocking controls based on checkbox state."""
        enabled = self.blocking_checkbox.state() == NSControlStateValueOn
        self.personal_popup.setEnabled_(enabled)
        self.work_popup.setEnabled_(enabled)
        self.blocking_start_popup.setEnabled_(enabled)
        self.blocking_end_popup.setEnabled_(enabled)
        self.blocking_days_popup.setEnabled_(enabled)
    
    @objc.typedSelector(b'v@:@')
    def googleSyncToggled_(self, sender):
        """Handle Google sync checkbox toggle."""
        self._updateGoogleSyncControlsState()
    
    @objc.typedSelector(b'v@:@')
    def blockingToggled_(self, sender):
        """Handle blocking checkbox toggle."""
        self._updateBlockingControlsState()
    
    @objc.typedSelector(b'v@:@')
    def iconTypeChanged_(self, sender):
        """Handle icon type dropdown change - update the variant popup."""
        # Find which row this type popup belongs to
        for checkbox, cal, type_popup, variant_popup in self.display_checkboxes:
            if type_popup == sender:
                selected_type = type_popup.titleOfSelectedItem()
                self._update_variant_popup_for_type(variant_popup, selected_type)
                break
    
    @objc.typedSelector(b'v@:@')
    def saveSettings_(self, sender):
        """Save settings and close window."""
        try:
            # =====================================================================
            # GOOGLE SYNC SETTINGS
            # =====================================================================
            self.prefs["google_sync_enabled"] = self.google_sync_checkbox.state() == NSControlStateValueOn
            
            # Google sync source calendar
            google_source_title = self.google_source_popup.titleOfSelectedItem()
            if google_source_title:
                google_source_title = str(google_source_title)
            if google_source_title and google_source_title != "(None)" and not google_source_title.startswith("—"):
                for cal in self.calendars:
                    if cal["name"] == google_source_title:
                        self.prefs["google_sync_source_calendar"] = {"name": cal["name"], "source": cal["source"]}
                        break
            else:
                self.prefs["google_sync_source_calendar"] = None
            
            # Google sync target calendar ID
            target_value = self.google_target_field.stringValue()
            self.prefs["google_sync_target_calendar_id"] = str(target_value) if target_value else ""
            
            # =====================================================================
            # BLOCKING SETTINGS
            # =====================================================================
            self.prefs["blocking_enabled"] = self.blocking_checkbox.state() == NSControlStateValueOn
            
            # Personal calendar selection
            personal_title = self.personal_popup.titleOfSelectedItem()
            if personal_title:
                personal_title = str(personal_title)
            if personal_title and personal_title != "(None)" and not personal_title.startswith("—"):
                for cal in self.calendars:
                    if cal["name"] == personal_title:
                        self.prefs["personal_calendars"] = [{"name": cal["name"], "source": cal["source"]}]
                        break
            else:
                self.prefs["personal_calendars"] = []
            
            # Work calendar selection
            work_title = self.work_popup.titleOfSelectedItem()
            if work_title:
                work_title = str(work_title)
            if work_title and work_title != "(None)" and not work_title.startswith("—"):
                for cal in self.calendars:
                    if cal["name"] == work_title:
                        self.prefs["work_calendar"] = {"name": cal["name"], "source": cal["source"]}
                        break
            else:
                self.prefs["work_calendar"] = None
            
            # Blocking hours
            start_title = self.blocking_start_popup.titleOfSelectedItem()
            end_title = self.blocking_end_popup.titleOfSelectedItem()
            self.prefs["blocking_start_hour"] = self._parse_hour(str(start_title)) if start_title else 8
            self.prefs["blocking_end_hour"] = self._parse_hour(str(end_title)) if end_title else 20
            
            # Blocking days
            days_title = self.blocking_days_popup.titleOfSelectedItem()
            days_selection = str(days_title) if days_title else "Weekdays Only"
            self.prefs["blocking_days"] = "all" if days_selection == "All Days" else "weekdays"
            
            # =====================================================================
            # DISPLAY CALENDARS
            # =====================================================================
            display_cals = []
            for checkbox, cal, type_popup, variant_popup in self.display_checkboxes:
                if checkbox.state() == NSControlStateValueOn:
                    icon_filename = self._get_selected_icon_filename(type_popup, variant_popup)
                    cal_pref = {"name": cal["name"], "source": cal["source"]}
                    if icon_filename:
                        cal_pref["icon"] = icon_filename
                    display_cals.append(cal_pref)
            self.prefs["display_calendars"] = display_cals
            
            # Save
            save_preferences(self.prefs)
            
            # Close window
            self.window.close()
            
            # Call callback if set
            if self.on_save_callback:
                self.on_save_callback()
        except Exception as e:
            import traceback
            print(f"ERROR saving settings: {e}")
            traceback.print_exc()
    
    @objc.typedSelector(b'v@:@')
    def cancelSettings_(self, sender):
        """Close window without saving."""
        self.window.close()


# Keep a reference to prevent garbage collection crashes
_active_controller = None


def show_settings_window(store=None, on_save=None):
    """Show the settings window."""
    global _active_controller
    
    # Create new controller each time
    _active_controller = SettingsWindowController.alloc().init()
    _active_controller.setStore_(store)
    if on_save:
        _active_controller.setOnSaveCallback_(on_save)
    _active_controller.showWindow()
    return _active_controller


# Helper functions for other modules
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


def get_display_calendar_icon(calendar_name: str) -> Optional[str]:
    """Get the icon filename for a specific display calendar."""
    prefs = load_preferences()
    display_cals = prefs.get("display_calendars", [])
    for cal in display_cals:
        if cal.get("name") == calendar_name:
            return cal.get("icon")
    return None


def get_display_calendars_with_icons() -> List[Dict[str, Any]]:
    """Get list of display calendars with their icon settings."""
    prefs = load_preferences()
    return prefs.get("display_calendars", [])


# ============================================================================
# Google Sync Settings Helpers
# ============================================================================

def is_google_sync_enabled() -> bool:
    """Check if Google sync is enabled."""
    prefs = load_preferences()
    return prefs.get("google_sync_enabled", False)


def get_google_sync_source_calendar() -> Optional[str]:
    """Get the source calendar name for Google sync."""
    prefs = load_preferences()
    source_cal = prefs.get("google_sync_source_calendar")
    return source_cal["name"] if source_cal else None


def get_google_sync_target_calendar_id() -> str:
    """Get the target Google Calendar ID."""
    prefs = load_preferences()
    return prefs.get("google_sync_target_calendar_id", "")


# ============================================================================
# Personal→Work Blocking Settings Helpers
# ============================================================================

def is_blocking_enabled() -> bool:
    """Check if personal→work blocking is enabled."""
    prefs = load_preferences()
    return prefs.get("blocking_enabled", True)


def get_blocking_hours() -> tuple:
    """Get the blocking start and end hours (24-hour format)."""
    prefs = load_preferences()
    start = prefs.get("blocking_start_hour", 8)
    end = prefs.get("blocking_end_hour", 20)
    return (start, end)


def get_blocking_days() -> str:
    """Get blocking days setting ('weekdays' or 'all')."""
    prefs = load_preferences()
    return prefs.get("blocking_days", "weekdays")


def is_blocking_weekdays_only() -> bool:
    """Check if blocking is weekdays only."""
    return get_blocking_days() == "weekdays"
