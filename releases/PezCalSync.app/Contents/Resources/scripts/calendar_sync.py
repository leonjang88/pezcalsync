#!/usr/bin/env python3
"""
Apple Calendar → Google Calendar Sync

Syncs events from Apple Calendar (including Outlook) to Google Calendar.
Handles create, update, and delete operations.
"""

import sys
import os
import json
import datetime
from pathlib import Path
from typing import Optional, List, Dict

# Fix SSL certificates for bundled app - must be done BEFORE importing google libs
def _fix_ssl_certificates():
    """Set up SSL certificates for bundled macOS app."""
    if getattr(sys, 'frozen', False):
        resource_path = os.environ.get('RESOURCEPATH', '')
        cert_file = os.path.join(resource_path, 'openssl.ca', 'cert.pem')
        cert_dir = os.path.join(resource_path, 'openssl.ca', 'certs')
        
        if os.path.exists(cert_file):
            os.environ['SSL_CERT_FILE'] = cert_file
            os.environ['SSL_CERT_DIR'] = cert_dir
            os.environ['REQUESTS_CA_BUNDLE'] = cert_file
            os.environ['CURL_CA_BUNDLE'] = cert_file
            try:
                import certifi
                certifi.where = lambda: cert_file
            except ImportError:
                pass

_fix_ssl_certificates()

# EventKit imports
try:
    import EventKit
    from Foundation import NSDate
except ImportError:
    print("ERROR: PyObjC not installed. Install with:")
    print("  pip install pyobjc-framework-EventKit")
    sys.exit(1)

# Google Calendar imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: Google API client not installed. Install with:")
    print("  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Google Calendar API scopes (read/write access)
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# How many days ahead to sync
DAYS_AHEAD = 14

# How many days back to sync (for cleanup)
DAYS_BACK = 1

# Path to store credentials and mapping
# Use standard macOS Application Support directory
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "CalendarSync"
APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = APP_SUPPORT_DIR
CREDENTIALS_FILE = DATA_DIR / "credentials.json"
TOKEN_FILE = DATA_DIR / "token.json"
MAPPING_FILE = DATA_DIR / "event_mapping.json"

# Google Calendar ID to sync to (use 'primary' for main calendar, or a specific calendar ID)
# You can create a dedicated calendar and use its ID here
GOOGLE_CALENDAR_ID = "c_7aadcf57f3b72a2da78eb960dc5a8350fa88ba378146ce154487744963bc8480@group.calendar.google.com"

# Filter: Only sync from these Apple Calendar names (empty list = sync all)
# "Calendar" is the default Exchange/Outlook calendar name
APPLE_CALENDAR_FILTER = ["Calendar"]

# Events to exclude by title (case-insensitive partial match)
EXCLUDED_EVENT_TITLES = ["lunch!"]

# Prefix for synced events (helps identify them)
EVENT_PREFIX = ""  # Set to something like "[Work] " if you want to prefix events

# ============================================================================
# PERSONAL CALENDAR BLOCKING CONFIGURATION
# ============================================================================

# Personal calendar name(s) to monitor for blocking work calendar
# These are Apple Calendar names (can be from any source: iCloud, Google, etc.)
# Set to empty list to disable this feature
PERSONAL_CALENDAR_NAMES = ["Personal Cal"]

# Work calendar name to create blocking events on (Exchange/Outlook calendar)
WORK_CALENDAR_NAME = "Calendar"

# Hours during which personal events should block work calendar (24-hour format)
BLOCKING_START_HOUR = 8   # 8 AM
BLOCKING_END_HOUR = 20    # 8 PM

# Only create blocking events on weekdays (Monday=0 through Friday=4)
BLOCKING_WEEKDAYS_ONLY = True

# Title for blocking events created on work calendar
BLOCKING_EVENT_TITLE = "apt"

# Mapping file for personal→work blocking events
PERSONAL_BLOCK_MAPPING_FILE = DATA_DIR / "personal_block_mapping.json"


# ============================================================================
# Event Mapping (for tracking synced events)
# ============================================================================

def load_mapping() -> dict:
    """Load the Apple → Google event ID mapping."""
    if MAPPING_FILE.exists():
        with open(MAPPING_FILE, "r") as f:
            return json.load(f)
    return {}


def save_mapping(mapping: dict):
    """Save the Apple → Google event ID mapping."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MAPPING_FILE, "w") as f:
        json.dump(mapping, f, indent=2)


def load_personal_block_mapping() -> dict:
    """Load the personal event → work blocking event mapping."""
    if PERSONAL_BLOCK_MAPPING_FILE.exists():
        with open(PERSONAL_BLOCK_MAPPING_FILE, "r") as f:
            return json.load(f)
    return {}


def save_personal_block_mapping(mapping: dict):
    """Save the personal event → work blocking event mapping."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PERSONAL_BLOCK_MAPPING_FILE, "w") as f:
        json.dump(mapping, f, indent=2)


# ============================================================================
# Apple Calendar (EventKit)
# ============================================================================

def request_calendar_access() -> bool:
    """Request calendar access and properly wait for the permission dialog."""
    from Foundation import NSRunLoop, NSDate as FoundationNSDate
    import platform
    
    store = EventKit.EKEventStore.alloc().init()
    
    # Use a mutable container to capture the result from the callback
    result = {'granted': None, 'error': None}
    
    def completion_handler(granted, error):
        result['granted'] = granted
        result['error'] = error
    
    # Check macOS version - use newer API on macOS 14+
    macos_version = tuple(map(int, platform.mac_ver()[0].split('.')))
    
    if macos_version >= (14, 0):
        # macOS 14+ requires requestFullAccessToEventsWithCompletion_
        print("📋 Requesting full calendar access (macOS 14+)...")
        try:
            store.requestFullAccessToEventsWithCompletion_(completion_handler)
        except AttributeError:
            # Fall back to old API if the new one isn't available
            print("   Falling back to legacy API...")
            store.requestAccessToEntityType_completion_(
                EventKit.EKEntityTypeEvent,
                completion_handler
            )
    else:
        # Older macOS versions
        store.requestAccessToEntityType_completion_(
            EventKit.EKEntityTypeEvent,
            completion_handler
        )
    
    # Run the run loop until we get a response (this allows the dialog to appear)
    # Timeout after 60 seconds to avoid hanging forever
    timeout = 60
    start_time = datetime.datetime.now()
    
    while result['granted'] is None:
        # Process pending events (this allows the permission dialog to show)
        NSRunLoop.currentRunLoop().runUntilDate_(
            FoundationNSDate.dateWithTimeIntervalSinceNow_(0.1)
        )
        
        # Check for timeout
        elapsed = (datetime.datetime.now() - start_time).total_seconds()
        if elapsed > timeout:
            print("⏱️  Timeout waiting for calendar permission response")
            return False
    
    if result['error']:
        print(f"❌ Error requesting calendar access: {result['error']}")
        return False
    
    return result['granted']


def get_apple_calendar_events(days_back: int = 1, days_ahead: int = 14, store=None) -> Optional[List[Dict]]:
    """Fetch events from Apple Calendar.
    
    Args:
        days_back: Number of days in the past to fetch
        days_ahead: Number of days in the future to fetch
        store: Optional EKEventStore with existing calendar access
    """
    if store is None:
        store = EventKit.EKEventStore.alloc().init()
        # Request access with proper dialog handling
        access_granted = request_calendar_access()

        if not access_granted:
            print("❌ Calendar access denied!")
            print("   Go to: System Settings → Privacy & Security → Calendars")
            print("   Enable access for Terminal or Python")
            return None
    # If store was provided, assume it already has access

    # Set date range
    start_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
    end_date = datetime.datetime.now() + datetime.timedelta(days=days_ahead)

    ns_start = NSDate.dateWithTimeIntervalSince1970_(start_date.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(end_date.timestamp())

    # Get all calendars
    all_calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)

    # Filter calendars if APPLE_CALENDAR_FILTER is set
    if APPLE_CALENDAR_FILTER:
        calendars = [cal for cal in all_calendars if cal.title() in APPLE_CALENDAR_FILTER]
        print(f"\n📅 Filtering to {len(calendars)} calendar(s) from {len(all_calendars)} total:")
    else:
        calendars = list(all_calendars)
        print(f"\n📅 Found {len(calendars)} Apple Calendar(s):")
    
    for cal in calendars:
        print(f"   - {cal.title()}")
    
    if not calendars:
        print("   ⚠️  No matching calendars found!")
        return []

    # Create predicate and fetch events
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        ns_start, ns_end, calendars
    )

    events = store.eventsMatchingPredicate_(predicate)

    # Format events - track master events for recurring series
    event_list = []
    seen_master_ids = set()  # Track recurring event masters to avoid duplicates
    skipped_cancelled = 0
    
    skipped_excluded = 0
    
    for event in sorted(events, key=lambda e: e.startDate()):
        # Skip cancelled events (status 3 = EKEventStatusCanceled)
        if event.status() == 3:
            skipped_cancelled += 1
            continue
        
        # Skip excluded events by title
        title = str(event.title() or '')
        if any(excluded.lower() in title.lower() for excluded in EXCLUDED_EVENT_TITLES):
            skipped_excluded += 1
            continue
            
        start_dt = datetime.datetime.fromtimestamp(event.startDate().timeIntervalSince1970())
        end_dt = datetime.datetime.fromtimestamp(event.endDate().timeIntervalSince1970())

        # Create a stable ID from the event
        apple_id = str(event.eventIdentifier())
        
        # Check for recurrence rules
        recurrence_rule = None
        has_recurrence = event.hasRecurrenceRules()
        
        if has_recurrence:
            # For recurring events, use base ID (before /RID=) to avoid duplicates
            base_id = apple_id.split('/RID=')[0]
            
            # Skip if we've already seen this recurring event master
            if base_id in seen_master_ids:
                continue
            seen_master_ids.add(base_id)
            
            # Extract RRULE from EventKit
            rules = event.recurrenceRules()
            if rules and len(rules) > 0:
                rule = rules[0]
                recurrence_rule = extract_rrule(rule)
            
            # Use the base ID for recurring events
            apple_id = base_id
        
        event_data = {
            'apple_id': apple_id,
            'title': str(event.title() or "(No Title)"),
            'start': start_dt,
            'end': end_dt,
            'start_iso': start_dt.isoformat(),
            'end_iso': end_dt.isoformat(),
            'location': str(event.location() or ''),
            'all_day': bool(event.isAllDay()),
            'calendar': str(event.calendar().title()),
            'notes': str(event.notes() or '')[:2000],  # Limit notes length
            'recurrence': recurrence_rule,  # RRULE string or None
        }
        event_list.append(event_data)

    if skipped_cancelled > 0:
        print(f"  Skipped {skipped_cancelled} cancelled events")
    if skipped_excluded > 0:
        print(f"  Skipped {skipped_excluded} excluded events (by title)")
    
    return event_list


# ============================================================================
# Personal Calendar → Work Calendar Blocking
# ============================================================================

def is_during_work_hours(start_dt: datetime.datetime, end_dt: datetime.datetime) -> bool:
    """Check if an event falls within work hours (8 AM - 8 PM on weekdays)."""
    # Check if it's a weekday (Monday=0 through Friday=4)
    if BLOCKING_WEEKDAYS_ONLY and start_dt.weekday() > 4:
        return False  # Saturday (5) or Sunday (6)
    
    # Check if any part of the event overlaps with work hours
    start_hour = start_dt.hour
    end_hour = end_dt.hour
    
    # Event must have some overlap with work hours
    # Work hours: BLOCKING_START_HOUR to BLOCKING_END_HOUR
    event_starts_before_end = start_hour < BLOCKING_END_HOUR
    event_ends_after_start = end_hour >= BLOCKING_START_HOUR or (end_hour == 0 and end_dt.minute == 0)
    
    return event_starts_before_end and event_ends_after_start


def get_personal_calendar_events(days_back: int = 1, days_ahead: int = 14, store=None) -> Optional[List[Dict]]:
    """Fetch events from personal calendars that should block work calendar.
    
    Args:
        days_back: Number of days in the past to fetch
        days_ahead: Number of days in the future to fetch
        store: Optional EKEventStore with existing calendar access
    """
    if not PERSONAL_CALENDAR_NAMES:
        return []  # Feature disabled
    
    if store is None:
        store = EventKit.EKEventStore.alloc().init()
        access_granted = request_calendar_access()
        if not access_granted:
            return None

    # Set date range
    start_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
    end_date = datetime.datetime.now() + datetime.timedelta(days=days_ahead)

    ns_start = NSDate.dateWithTimeIntervalSince1970_(start_date.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(end_date.timestamp())

    # Get all calendars and filter to personal ones
    all_calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    
    # Debug: print all available calendars
    print(f"   📋 All available calendars:")
    for cal in all_calendars:
        print(f"      - \"{cal.title()}\" (source: {cal.source().title()})")
    
    personal_calendars = [cal for cal in all_calendars if cal.title() in PERSONAL_CALENDAR_NAMES]
    
    if not personal_calendars:
        print(f"   ⚠️  No personal calendars found matching: {PERSONAL_CALENDAR_NAMES}")
        return []
    
    print(f"\n👤 Found {len(personal_calendars)} personal calendar(s):")
    for cal in personal_calendars:
        print(f"   - {cal.title()}")

    # Fetch events
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        ns_start, ns_end, personal_calendars
    )
    events = store.eventsMatchingPredicate_(predicate)

    # Filter and format events
    event_list = []
    skipped_outside_hours = 0
    skipped_all_day = 0
    
    for event in sorted(events, key=lambda e: e.startDate()):
        # Skip cancelled events
        if event.status() == 3:
            continue
        
        start_dt = datetime.datetime.fromtimestamp(event.startDate().timeIntervalSince1970())
        end_dt = datetime.datetime.fromtimestamp(event.endDate().timeIntervalSince1970())
        
        # Skip all-day events (they're usually not "busy" time)
        if event.isAllDay():
            skipped_all_day += 1
            continue
        
        # Skip events outside work hours
        if not is_during_work_hours(start_dt, end_dt):
            skipped_outside_hours += 1
            continue
        
        # Clip event to work hours if it extends beyond
        if start_dt.hour < BLOCKING_START_HOUR:
            start_dt = start_dt.replace(hour=BLOCKING_START_HOUR, minute=0)
        if end_dt.hour >= BLOCKING_END_HOUR:
            end_dt = end_dt.replace(hour=BLOCKING_END_HOUR, minute=0)
        
        apple_id = str(event.eventIdentifier())
        
        event_data = {
            'apple_id': apple_id,
            'title': str(event.title() or "(No Title)"),
            'start': start_dt,
            'end': end_dt,
            'start_iso': start_dt.isoformat(),
            'end_iso': end_dt.isoformat(),
            'calendar': str(event.calendar().title()),
        }
        event_list.append(event_data)
    
    if skipped_outside_hours > 0:
        print(f"   Skipped {skipped_outside_hours} events outside work hours ({BLOCKING_START_HOUR}:00-{BLOCKING_END_HOUR}:00)")
    if skipped_all_day > 0:
        print(f"   Skipped {skipped_all_day} all-day events")
    
    return event_list


def get_work_calendar(store) -> Optional[object]:
    """Get the work calendar (Exchange/Outlook) object for creating events."""
    all_calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    for cal in all_calendars:
        if cal.title() == WORK_CALENDAR_NAME:
            return cal
    return None


def get_existing_apt_events(store, work_calendar, days_back: int = 1, days_ahead: int = 14) -> List[Dict]:
    """Get existing 'apt' events from the work calendar.
    
    Returns list of apt events with their time ranges for overlap checking.
    """
    start_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
    end_date = datetime.datetime.now() + datetime.timedelta(days=days_ahead)

    ns_start = NSDate.dateWithTimeIntervalSince1970_(start_date.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(end_date.timestamp())

    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        ns_start, ns_end, [work_calendar]
    )
    events = store.eventsMatchingPredicate_(predicate)
    
    apt_events = []
    for event in events:
        title = str(event.title() or '')
        # Match "apt" events (case-insensitive) that were manually created
        # Skip auto-created ones (they have the note marker)
        if title.lower() == BLOCKING_EVENT_TITLE.lower():
            notes = str(event.notes() or '')
            # Skip events we created automatically
            if '[Auto-blocked from personal calendar]' in notes:
                continue
            
            start_dt = datetime.datetime.fromtimestamp(event.startDate().timeIntervalSince1970())
            end_dt = datetime.datetime.fromtimestamp(event.endDate().timeIntervalSince1970())
            
            apt_events.append({
                'id': str(event.eventIdentifier()),
                'start': start_dt,
                'end': end_dt,
            })
    
    return apt_events


def is_covered_by_existing_apt(personal_event: dict, apt_events: List[Dict]) -> bool:
    """Check if a personal event is fully covered by an existing apt event.
    
    Returns True if there's an apt event that starts at or before the personal event
    and ends at or after the personal event.
    """
    personal_start = personal_event['start']
    personal_end = personal_event['end']
    
    for apt in apt_events:
        # Check if apt event fully contains the personal event
        if apt['start'] <= personal_start and apt['end'] >= personal_end:
            return True
    
    return False


def create_blocking_event_on_work_calendar(store, work_calendar, personal_event: dict) -> Optional[str]:
    """Create a blocking event on the work calendar for a personal event."""
    try:
        event = EventKit.EKEvent.eventWithEventStore_(store)
        event.setTitle_(BLOCKING_EVENT_TITLE)
        event.setCalendar_(work_calendar)
        
        # Set start and end times
        ns_start = NSDate.dateWithTimeIntervalSince1970_(personal_event['start'].timestamp())
        ns_end = NSDate.dateWithTimeIntervalSince1970_(personal_event['end'].timestamp())
        event.setStartDate_(ns_start)
        event.setEndDate_(ns_end)
        
        # Add a note to identify this as a synced blocking event
        event.setNotes_(f"[Auto-blocked from personal calendar]\nOriginal: {personal_event['title']}")
        
        # Save the event
        error = None
        success = store.saveEvent_span_error_(event, EventKit.EKSpanThisEvent, None)
        
        if success:
            return str(event.eventIdentifier())
        else:
            print(f"   ❌ Failed to create blocking event")
            return None
            
    except Exception as e:
        print(f"   ❌ Error creating blocking event: {e}")
        return None


def update_blocking_event_on_work_calendar(store, work_event_id: str, personal_event: dict) -> bool:
    """Update an existing blocking event on the work calendar."""
    try:
        event = store.eventWithIdentifier_(work_event_id)
        if not event:
            return False
        
        # Update times
        ns_start = NSDate.dateWithTimeIntervalSince1970_(personal_event['start'].timestamp())
        ns_end = NSDate.dateWithTimeIntervalSince1970_(personal_event['end'].timestamp())
        event.setStartDate_(ns_start)
        event.setEndDate_(ns_end)
        
        # Update note
        event.setNotes_(f"[Auto-blocked from personal calendar]\nOriginal: {personal_event['title']}")
        
        success = store.saveEvent_span_error_(event, EventKit.EKSpanThisEvent, None)
        return success
        
    except Exception as e:
        print(f"   ❌ Error updating blocking event: {e}")
        return False


def delete_blocking_event_from_work_calendar(store, work_event_id: str) -> bool:
    """Delete a blocking event from the work calendar."""
    try:
        event = store.eventWithIdentifier_(work_event_id)
        if not event:
            return True  # Already deleted
        
        success = store.removeEvent_span_error_(event, EventKit.EKSpanThisEvent, None)
        return success
        
    except Exception as e:
        print(f"   ❌ Error deleting blocking event: {e}")
        return False


def sync_personal_to_work_blocking(store) -> dict:
    """Sync personal calendar events to work calendar as blocking events."""
    if not PERSONAL_CALENDAR_NAMES:
        return {'success': True, 'created': 0, 'updated': 0, 'deleted': 0, 'unchanged': 0, 'skipped': True}
    
    print("\n" + "=" * 70)
    print("  Personal Calendar → Work Calendar Blocking")
    print("=" * 70)
    
    # Get personal events
    print(f"\n👤 Fetching personal calendar events...")
    personal_events = get_personal_calendar_events(DAYS_BACK, DAYS_AHEAD, store=store)
    
    if personal_events is None:
        print("❌ Failed to get personal calendar events")
        return {'success': False, 'error': 'Failed to get personal calendar events'}
    
    print(f"   Found {len(personal_events)} events to block")
    
    # Get work calendar
    work_calendar = get_work_calendar(store)
    if not work_calendar:
        print(f"❌ Work calendar '{WORK_CALENDAR_NAME}' not found")
        return {'success': False, 'error': f'Work calendar not found'}
    
    # Get existing manual "apt" events to avoid duplicates
    existing_apt_events = get_existing_apt_events(store, work_calendar, DAYS_BACK, DAYS_AHEAD)
    print(f"   Found {len(existing_apt_events)} existing manual 'apt' events on work calendar")
    
    # Load existing mapping
    mapping = load_personal_block_mapping()
    print(f"\n📋 Loaded mapping with {len(mapping)} previously blocked events")
    
    # Build current personal event IDs
    current_personal_ids = {e['apple_id']: e for e in personal_events}
    
    # Track stats
    created = 0
    updated = 0
    deleted = 0
    unchanged = 0
    skipped_covered = 0
    
    # Process creates and updates
    print(f"\n🔄 Syncing blocking events...")
    
    for personal_id, event in current_personal_ids.items():
        # Check if this event is already covered by an existing manual "apt" event
        if is_covered_by_existing_apt(event, existing_apt_events):
            # If we previously created a blocking event for this, delete it
            if personal_id in mapping:
                stored = mapping[personal_id]
                print(f"   🔄 Removing auto-block (covered by manual apt): {event['title']}")
                delete_blocking_event_from_work_calendar(store, stored['work_event_id'])
                del mapping[personal_id]
                deleted += 1
            else:
                skipped_covered += 1
            continue
        
        if personal_id in mapping:
            # Event exists - check if it needs updating
            stored = mapping[personal_id]
            work_event_id = stored['work_event_id']
            
            # Check if event changed
            if (stored.get('start_iso') != event['start_iso'] or
                stored.get('end_iso') != event['end_iso']):
                
                print(f"   📝 Updating block for: {event['title']}")
                if update_blocking_event_on_work_calendar(store, work_event_id, event):
                    mapping[personal_id] = {
                        'work_event_id': work_event_id,
                        'title': event['title'],
                        'start_iso': event['start_iso'],
                        'end_iso': event['end_iso'],
                    }
                    updated += 1
                else:
                    # Event was deleted, recreate
                    new_work_id = create_blocking_event_on_work_calendar(store, work_calendar, event)
                    if new_work_id:
                        mapping[personal_id] = {
                            'work_event_id': new_work_id,
                            'title': event['title'],
                            'start_iso': event['start_iso'],
                            'end_iso': event['end_iso'],
                        }
                        created += 1
            else:
                unchanged += 1
        else:
            # New event - create blocking event
            print(f"   ➕ Creating block for: {event['title']} ({event['start'].strftime('%m/%d %H:%M')}-{event['end'].strftime('%H:%M')})")
            work_event_id = create_blocking_event_on_work_calendar(store, work_calendar, event)
            
            if work_event_id:
                mapping[personal_id] = {
                    'work_event_id': work_event_id,
                    'title': event['title'],
                    'start_iso': event['start_iso'],
                    'end_iso': event['end_iso'],
                }
                created += 1
    
    # Process deletes
    deleted_personal_ids = set(mapping.keys()) - set(current_personal_ids.keys())
    
    for personal_id in deleted_personal_ids:
        stored = mapping[personal_id]
        print(f"   🗑️  Removing block for: {stored.get('title', 'Unknown')}")
        
        if delete_blocking_event_from_work_calendar(store, stored['work_event_id']):
            del mapping[personal_id]
            deleted += 1
    
    # Save updated mapping
    save_personal_block_mapping(mapping)
    
    # Print summary
    summary = f"+{created} ~{updated} -{deleted}"
    if skipped_covered > 0:
        summary += f" (⏭️ {skipped_covered} already covered by manual apt)"
    print(f"\n   ✅ Personal→Work blocking complete: {summary}")
    
    return {'success': True, 'created': created, 'updated': updated, 'deleted': deleted, 'unchanged': unchanged, 'skipped_covered': skipped_covered}


def extract_rrule(ek_rule) -> Optional[str]:
    """Convert an EKRecurrenceRule to an RRULE string for Google Calendar."""
    try:
        # Get frequency
        freq_map = {
            0: 'DAILY',
            1: 'WEEKLY', 
            2: 'MONTHLY',
            3: 'YEARLY'
        }
        freq = freq_map.get(ek_rule.frequency(), 'WEEKLY')
        
        parts = [f'RRULE:FREQ={freq}']
        
        # Interval
        interval = ek_rule.interval()
        if interval and interval > 1:
            parts.append(f'INTERVAL={interval}')
        
        # Days of week (for weekly recurrence)
        days_of_week = ek_rule.daysOfTheWeek()
        if days_of_week:
            day_map = {1: 'SU', 2: 'MO', 3: 'TU', 4: 'WE', 5: 'TH', 6: 'FR', 7: 'SA'}
            days = []
            for day_obj in days_of_week:
                day_num = day_obj.dayOfTheWeek()
                if day_num in day_map:
                    days.append(day_map[day_num])
            if days:
                parts.append(f'BYDAY={",".join(days)}')
        
        # End date
        end_date = ek_rule.recurrenceEnd()
        if end_date:
            end_ns_date = end_date.endDate()
            if end_ns_date:
                end_dt = datetime.datetime.fromtimestamp(end_ns_date.timeIntervalSince1970())
                parts.append(f'UNTIL={end_dt.strftime("%Y%m%dT%H%M%SZ")}')
        
        # Count (if no end date)
        # Note: EKRecurrenceRule doesn't expose count directly in a simple way
        
        return ';'.join(parts)
    except Exception as e:
        print(f"   ⚠️  Could not extract RRULE: {e}")
        return None


# ============================================================================
# Google Calendar API
# ============================================================================

def get_google_calendar_service():
    """Authenticate and return Google Calendar service."""
    creds = None
    
    # Check for existing token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing Google credentials...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"❌ credentials.json not found at {CREDENTIALS_FILE}")
                print("\nTo set up Google Calendar API:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a project and enable Google Calendar API")
                print("3. Create OAuth 2.0 credentials (Desktop app)")
                print(f"4. Download and save as: {CREDENTIALS_FILE}")
                return None
            
            print("🔐 Opening browser for Google authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=8080)
        
        # Save credentials for next run
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        print("✅ Google credentials saved")
    
    return build("calendar", "v3", credentials=creds)


def create_google_event(service, event: dict) -> Optional[str]:
    """Create an event in Google Calendar. Returns Google event ID."""
    try:
        body = {
            "summary": f"{EVENT_PREFIX}{event['title']}",
            "location": event['location'],
            "description": f"Synced from: {event['calendar']}\n\n{event['notes']}",
        }
        
        if event['all_day']:
            # All-day events use date instead of dateTime
            body["start"] = {"date": event['start'].strftime("%Y-%m-%d")}
            body["end"] = {"date": event['end'].strftime("%Y-%m-%d")}
        else:
            # Timed events
            body["start"] = {
                "dateTime": event['start_iso'],
                "timeZone": "America/New_York",  # Adjust to your timezone
            }
            body["end"] = {
                "dateTime": event['end_iso'],
                "timeZone": "America/New_York",
            }
        
        # Add recurrence rule if present
        if event.get('recurrence'):
            body["recurrence"] = [event['recurrence']]
        
        result = service.events().insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=body
        ).execute()
        
        return result.get('id')
    
    except HttpError as error:
        print(f"   ❌ Error creating event: {error}")
        return None


def update_google_event(service, google_id: str, event: dict) -> bool:
    """Update an existing event in Google Calendar."""
    try:
        body = {
            "summary": f"{EVENT_PREFIX}{event['title']}",
            "location": event['location'],
            "description": f"Synced from: {event['calendar']}\n\n{event['notes']}",
        }
        
        if event['all_day']:
            body["start"] = {"date": event['start'].strftime("%Y-%m-%d")}
            body["end"] = {"date": event['end'].strftime("%Y-%m-%d")}
        else:
            body["start"] = {
                "dateTime": event['start_iso'],
                "timeZone": "America/New_York",
            }
            body["end"] = {
                "dateTime": event['end_iso'],
                "timeZone": "America/New_York",
            }
        
        # Add recurrence rule if present
        if event.get('recurrence'):
            body["recurrence"] = [event['recurrence']]
        
        service.events().update(
            calendarId=GOOGLE_CALENDAR_ID,
            eventId=google_id,
            body=body
        ).execute()
        
        return True
    
    except HttpError as error:
        if error.resp.status == 404:
            # Event was deleted on Google side
            return False
        print(f"   ❌ Error updating event: {error}")
        return False


def delete_google_event(service, google_id: str) -> bool:
    """Delete an event from Google Calendar."""
    try:
        service.events().delete(
            calendarId=GOOGLE_CALENDAR_ID,
            eventId=google_id
        ).execute()
        return True
    
    except HttpError as error:
        if error.resp.status == 404:
            # Already deleted
            return True
        print(f"   ❌ Error deleting event: {error}")
        return False


# ============================================================================
# Sync Logic
# ============================================================================

def sync_calendars(event_store=None):
    """Main sync function.
    
    Args:
        event_store: Optional EKEventStore with existing calendar access.
                     If not provided, will request access.
    """
    print("=" * 70)
    print("  Apple Calendar → Google Calendar Sync")
    print("=" * 70)
    
    # Get Apple Calendar events
    print(f"\n📱 Fetching Apple Calendar events...")
    apple_events = get_apple_calendar_events(DAYS_BACK, DAYS_AHEAD, store=event_store)
    
    if apple_events is None:
        print("❌ Failed to get Apple Calendar events")
        return {'success': False, 'error': 'Failed to get Apple Calendar events'}
    
    print(f"   Found {len(apple_events)} events")
    
    # Get Google Calendar service
    print(f"\n🔗 Connecting to Google Calendar...")
    service = get_google_calendar_service()
    
    if service is None:
        print("❌ Failed to connect to Google Calendar")
        return {'success': False, 'error': 'Failed to connect to Google Calendar'}
    
    print("   ✅ Connected")
    
    # Load existing mapping
    mapping = load_mapping()
    print(f"\n📋 Loaded mapping with {len(mapping)} previously synced events")
    
    # Build current Apple event IDs
    current_apple_ids = {e['apple_id']: e for e in apple_events}
    
    # Track stats
    created = 0
    updated = 0
    deleted = 0
    unchanged = 0
    
    # Process creates and updates
    print(f"\n🔄 Syncing events...")
    
    for apple_id, event in current_apple_ids.items():
        if apple_id in mapping:
            # Event exists - check if it needs updating
            stored = mapping[apple_id]
            google_id = stored['google_id']
            
            # Check if event changed (compare key fields)
            if (stored.get('title') != event['title'] or
                stored.get('start_iso') != event['start_iso'] or
                stored.get('end_iso') != event['end_iso'] or
                stored.get('location') != event['location']):
                
                print(f"   📝 Updating: {event['title']}")
                if update_google_event(service, google_id, event):
                    mapping[apple_id] = {
                        'google_id': google_id,
                        'title': event['title'],
                        'start_iso': event['start_iso'],
                        'end_iso': event['end_iso'],
                        'location': event['location'],
                    }
                    updated += 1
                else:
                    # Event was deleted on Google, recreate
                    new_google_id = create_google_event(service, event)
                    if new_google_id:
                        mapping[apple_id] = {
                            'google_id': new_google_id,
                            'title': event['title'],
                            'start_iso': event['start_iso'],
                            'end_iso': event['end_iso'],
                            'location': event['location'],
                        }
                        created += 1
            else:
                unchanged += 1
        else:
            # New event - create it
            print(f"   ➕ Creating: {event['title']}")
            google_id = create_google_event(service, event)
            
            if google_id:
                mapping[apple_id] = {
                    'google_id': google_id,
                    'title': event['title'],
                    'start_iso': event['start_iso'],
                    'end_iso': event['end_iso'],
                    'location': event['location'],
                }
                created += 1
    
    # Process deletes (events in mapping but not in current Apple Calendar)
    deleted_apple_ids = set(mapping.keys()) - set(current_apple_ids.keys())
    
    for apple_id in deleted_apple_ids:
        stored = mapping[apple_id]
        print(f"   🗑️  Deleting: {stored.get('title', 'Unknown')}")
        
        if delete_google_event(service, stored['google_id']):
            del mapping[apple_id]
            deleted += 1
    
    # Save updated mapping
    save_mapping(mapping)
    
    # Print summary
    print(f"\n" + "=" * 70)
    print(f"  ✅ Work→Google Sync Complete!")
    print(f"=" * 70)
    print(f"   ➕ Created:   {created}")
    print(f"   📝 Updated:   {updated}")
    print(f"   🗑️  Deleted:   {deleted}")
    print(f"   ⏸️  Unchanged: {unchanged}")
    print(f"=" * 70)
    
    # Also sync personal calendar → work calendar blocking
    if PERSONAL_CALENDAR_NAMES:
        # Get or create the event store for personal calendar sync
        if event_store is None:
            event_store = EventKit.EKEventStore.alloc().init()
            request_calendar_access()
        
        blocking_result = sync_personal_to_work_blocking(event_store)
        if not blocking_result.get('success') and not blocking_result.get('skipped'):
            print(f"⚠️  Personal→Work blocking had issues: {blocking_result.get('error', 'Unknown')}")
    
    return {'success': True, 'created': created, 'updated': updated, 'deleted': deleted, 'unchanged': unchanged}


# ============================================================================
# Main
# ============================================================================

def main():
    """Main entry point."""
    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    result = sync_calendars()
    sys.exit(0 if result.get('success') else 1)


if __name__ == "__main__":
    main()
