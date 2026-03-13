#!/usr/bin/env python3
"""
Personal Calendar → Work Calendar Blocking

Uses EventKit to sync personal calendar events to work calendar as blocking events.
No external API dependencies - works purely with local Apple Calendar.
"""

import sys
import os
import json
import datetime
from pathlib import Path
from typing import Optional, List, Dict

# EventKit imports
try:
    import EventKit
    from Foundation import NSDate
except ImportError:
    print("ERROR: PyObjC not installed. Install with:")
    print("  pip install pyobjc-framework-EventKit")
    sys.exit(1)


# ============================================================================
# CONFIGURATION - Loaded from preferences
# ============================================================================

# Path to store mapping
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "CalendarSync"
APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = APP_SUPPORT_DIR
PERSONAL_BLOCK_MAPPING_FILE = DATA_DIR / "personal_block_mapping.json"


def _load_config():
    """Load configuration from preferences file."""
    from settings_window import load_preferences
    prefs = load_preferences()
    return {
        'days_ahead': prefs.get('days_ahead', 14),
        'days_back': prefs.get('days_back', 1),
        'personal_calendar_names': [c['name'] for c in prefs.get('personal_calendars', [])],
        'work_calendar_name': prefs.get('work_calendar', {}).get('name') if prefs.get('work_calendar') else None,
        'blocking_event_title': prefs.get('blocking_event_title', 'apt'),
        'blocking_work_hours_only': prefs.get('blocking_work_hours_only', True),
        'blocking_start_hour': prefs.get('blocking_start_hour', 8),
        'blocking_end_hour': prefs.get('blocking_end_hour', 20),
        'blocking_weekdays_only': prefs.get('blocking_weekdays_only', True),
        'min_blocking_duration_minutes': prefs.get('min_blocking_duration_minutes', 15),
    }


# Legacy fallback values (used if preferences not set)
DAYS_AHEAD = 14
DAYS_BACK = 1
PERSONAL_CALENDAR_NAMES = ["Personal Cal"]
WORK_CALENDAR_NAME = "Calendar"
BLOCKING_EVENT_TITLE = "apt"
BLOCKING_WORK_HOURS_ONLY = True
BLOCKING_START_HOUR = 8
BLOCKING_END_HOUR = 20
BLOCKING_WEEKDAYS_ONLY = True
MIN_BLOCKING_DURATION_MINUTES = 15


# ============================================================================
# Calendar Access
# ============================================================================

def request_calendar_access() -> bool:
    """Request access to calendars via EventKit."""
    store = EventKit.EKEventStore.alloc().init()
    
    # Use a simple synchronous wait for access
    import time
    access_result = [None]
    
    def callback(granted, error):
        access_result[0] = granted
    
    store.requestAccessToEntityType_completion_(
        EventKit.EKEntityTypeEvent,
        callback
    )
    
    # Wait for callback (with timeout)
    timeout = 30
    start = time.time()
    while access_result[0] is None and (time.time() - start) < timeout:
        time.sleep(0.1)
    
    return access_result[0] == True


# ============================================================================
# Mapping Persistence
# ============================================================================

def load_personal_block_mapping() -> Dict:
    """Load the personal event → work blocking event mapping."""
    if PERSONAL_BLOCK_MAPPING_FILE.exists():
        try:
            with open(PERSONAL_BLOCK_MAPPING_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_personal_block_mapping(mapping: Dict):
    """Save the personal event → work blocking event mapping."""
    with open(PERSONAL_BLOCK_MAPPING_FILE, 'w') as f:
        json.dump(mapping, f, indent=2)


# ============================================================================
# Personal Calendar Events
# ============================================================================

def is_during_work_hours(start_dt: datetime.datetime, end_dt: datetime.datetime, config: dict = None) -> bool:
    """Check if an event falls within work hours."""
    weekdays_only = config.get('blocking_weekdays_only', BLOCKING_WEEKDAYS_ONLY) if config else BLOCKING_WEEKDAYS_ONLY
    start_hour_limit = config.get('blocking_start_hour', BLOCKING_START_HOUR) if config else BLOCKING_START_HOUR
    end_hour_limit = config.get('blocking_end_hour', BLOCKING_END_HOUR) if config else BLOCKING_END_HOUR
    
    if weekdays_only and start_dt.weekday() > 4:
        return False  # Saturday (5) or Sunday (6)
    
    start_hour = start_dt.hour
    end_hour = end_dt.hour
    
    event_starts_before_end = start_hour < end_hour_limit
    event_ends_after_start = end_hour >= start_hour_limit or (end_hour == 0 and end_dt.minute == 0)
    
    return event_starts_before_end and event_ends_after_start


def get_personal_calendar_events(days_back: int = 1, days_ahead: int = 14, store=None) -> Optional[List[Dict]]:
    """Fetch events from personal calendars (legacy, uses global constants)."""
    config = {
        'blocking_work_hours_only': BLOCKING_WORK_HOURS_ONLY,
        'blocking_weekdays_only': BLOCKING_WEEKDAYS_ONLY,
        'blocking_start_hour': BLOCKING_START_HOUR,
        'blocking_end_hour': BLOCKING_END_HOUR,
        'min_blocking_duration_minutes': MIN_BLOCKING_DURATION_MINUTES,
    }
    return get_personal_calendar_events_with_config(days_back, days_ahead, PERSONAL_CALENDAR_NAMES, config, store)


def get_personal_calendar_events_with_config(days_back: int, days_ahead: int, calendar_names: List[str], config: dict, store=None) -> Optional[List[Dict]]:
    """Fetch events from personal calendars that should block work calendar."""
    if not calendar_names:
        return []
    
    if store is None:
        store = EventKit.EKEventStore.alloc().init()
        access_granted = request_calendar_access()
        if not access_granted:
            return None

    start_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
    end_date = datetime.datetime.now() + datetime.timedelta(days=days_ahead)

    ns_start = NSDate.dateWithTimeIntervalSince1970_(start_date.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(end_date.timestamp())

    all_calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    
    print(f"   📋 All available calendars:")
    for cal in all_calendars:
        print(f"      - \"{cal.title()}\" (source: {cal.source().title()})")
    
    personal_calendars = [cal for cal in all_calendars if cal.title() in calendar_names]
    
    if not personal_calendars:
        print(f"   ⚠️  No personal calendars found matching: {calendar_names}")
        return []
    
    print(f"   ✅ Found personal calendars: {[c.title() for c in personal_calendars]}")
    
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        ns_start, ns_end, personal_calendars
    )
    events = store.eventsMatchingPredicate_(predicate)
    
    event_list = []
    skipped_short = 0
    skipped_work_hours = 0
    skipped_all_day = 0
    
    blocking_work_hours_only = config.get('blocking_work_hours_only', True)
    min_duration = config.get('min_blocking_duration_minutes', 15)
    
    for event in events:
        # Skip all-day events
        if event.isAllDay():
            skipped_all_day += 1
            continue
        
        start_ts = event.startDate().timeIntervalSince1970()
        end_ts = event.endDate().timeIntervalSince1970()
        start_dt = datetime.datetime.fromtimestamp(start_ts)
        end_dt = datetime.datetime.fromtimestamp(end_ts)
        
        # Skip events outside work hours
        if blocking_work_hours_only and not is_during_work_hours(start_dt, end_dt, config):
            skipped_work_hours += 1
            continue
        
        # Skip very short events
        duration_minutes = (end_ts - start_ts) / 60
        if duration_minutes < min_duration:
            skipped_short += 1
            continue
        
        event_data = {
            'apple_id': str(event.eventIdentifier()),
            'title': str(event.title() or "(No Title)"),
            'start': start_dt,
            'end': end_dt,
            'start_iso': start_dt.isoformat(),
            'end_iso': end_dt.isoformat(),
        }
        event_list.append(event_data)
    
    if skipped_all_day > 0:
        print(f"   Skipped {skipped_all_day} all-day events")
    if skipped_work_hours > 0:
        print(f"   Skipped {skipped_work_hours} events outside work hours")
    if skipped_short > 0:
        print(f"   Skipped {skipped_short} events shorter than {min_duration} min")
    
    return event_list


# ============================================================================
# Work Calendar Operations
# ============================================================================

def get_work_calendar(store):
    """Get the work calendar by name (legacy, uses global constant)."""
    return get_work_calendar_by_name(store, WORK_CALENDAR_NAME)


def get_work_calendar_by_name(store, calendar_name: str):
    """Get a calendar by name."""
    all_calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    for cal in all_calendars:
        if cal.title() == calendar_name:
            return cal
    return None


def get_existing_apt_events(store, work_calendar, days_back: int = 1, days_ahead: int = 14) -> List[Dict]:
    """Get existing 'apt' events from the work calendar (legacy, uses global constant)."""
    return get_existing_apt_events_with_config(store, work_calendar, days_back, days_ahead, BLOCKING_EVENT_TITLE)


def get_existing_apt_events_with_config(store, work_calendar, days_back: int, days_ahead: int, blocking_title: str) -> List[Dict]:
    """Get existing blocking events from the work calendar (manually created ones)."""
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
        if title.lower() == blocking_title.lower():
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
    
    return apt_events


def is_covered_by_existing_apt(personal_event: dict, apt_events: List[Dict]) -> bool:
    """Check if a personal event is fully covered by an existing apt event."""
    personal_start = personal_event['start']
    personal_end = personal_event['end']
    
    for apt in apt_events:
        if apt['start'] <= personal_start and apt['end'] >= personal_end:
            return True
    
    return False


def create_blocking_event_on_work_calendar(store, work_calendar, personal_event: dict, blocking_title: str = None) -> Optional[str]:
    """Create a blocking event on the work calendar for a personal event."""
    title = blocking_title or BLOCKING_EVENT_TITLE
    try:
        event = EventKit.EKEvent.eventWithEventStore_(store)
        event.setTitle_(title)
        event.setCalendar_(work_calendar)
        
        ns_start = NSDate.dateWithTimeIntervalSince1970_(personal_event['start'].timestamp())
        ns_end = NSDate.dateWithTimeIntervalSince1970_(personal_event['end'].timestamp())
        event.setStartDate_(ns_start)
        event.setEndDate_(ns_end)
        
        event.setNotes_(f"[Auto-blocked from personal calendar]\nOriginal: {personal_event['title']}")
        
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
        
        ns_start = NSDate.dateWithTimeIntervalSince1970_(personal_event['start'].timestamp())
        ns_end = NSDate.dateWithTimeIntervalSince1970_(personal_event['end'].timestamp())
        event.setStartDate_(ns_start)
        event.setEndDate_(ns_end)
        
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
            return True  # Already gone
        
        success = store.removeEvent_span_error_(event, EventKit.EKSpanThisEvent, None)
        return success
        
    except Exception as e:
        print(f"   ❌ Error deleting blocking event: {e}")
        return False


# ============================================================================
# Main Sync Function
# ============================================================================

def sync_calendars(event_store=None):
    """Main sync function - syncs personal calendar events to work calendar as blocking events."""
    
    # Load config from preferences
    config = _load_config()
    
    personal_calendar_names = config['personal_calendar_names'] or PERSONAL_CALENDAR_NAMES
    work_calendar_name = config['work_calendar_name'] or WORK_CALENDAR_NAME
    days_back = config['days_back']
    days_ahead = config['days_ahead']
    blocking_event_title = config['blocking_event_title']
    
    print("=" * 70)
    print("  Personal Calendar → Work Calendar Blocking")
    print("=" * 70)
    print(f"  Personal calendars: {personal_calendar_names}")
    print(f"  Work calendar: {work_calendar_name}")
    
    # Get or create event store
    if event_store is None:
        event_store = EventKit.EKEventStore.alloc().init()
        access_granted = request_calendar_access()
        if not access_granted:
            return {'success': False, 'error': 'Calendar access denied'}
    
    store = event_store
    
    # Get personal events
    print(f"\n👤 Fetching personal calendar events...")
    personal_events = get_personal_calendar_events_with_config(
        days_back, days_ahead, personal_calendar_names, config, store=store
    )
    
    if personal_events is None:
        print("❌ Failed to get personal calendar events")
        return {'success': False, 'error': 'Failed to get personal calendar events'}
    
    print(f"   Found {len(personal_events)} events to block")
    
    # Get work calendar
    work_calendar = get_work_calendar_by_name(store, work_calendar_name)
    if not work_calendar:
        print(f"❌ Work calendar '{work_calendar_name}' not found")
        return {'success': False, 'error': f'Work calendar not found'}
    
    # Get existing manual "apt" events to avoid duplicates
    existing_apt_events = get_existing_apt_events_with_config(
        store, work_calendar, days_back, days_ahead, blocking_event_title
    )
    print(f"   Found {len(existing_apt_events)} existing manual '{blocking_event_title}' events on work calendar")
    
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
            stored = mapping[personal_id]
            work_event_id = stored['work_event_id']
            
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
                    new_work_id = create_blocking_event_on_work_calendar(store, work_calendar, event, blocking_event_title)
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
            print(f"   ➕ Creating block for: {event['title']} ({event['start'].strftime('%m/%d %H:%M')}-{event['end'].strftime('%H:%M')})")
            work_event_id = create_blocking_event_on_work_calendar(store, work_calendar, event, blocking_event_title)
            
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
        print(f"   🗑️  Removing block for deleted event: {stored.get('title', 'Unknown')}")
        
        if delete_blocking_event_from_work_calendar(store, stored['work_event_id']):
            del mapping[personal_id]
            deleted += 1
    
    # Save updated mapping
    save_personal_block_mapping(mapping)
    
    # Print summary
    print(f"\n" + "=" * 70)
    print(f"  ✅ Sync Complete!")
    print(f"=" * 70)
    print(f"   ➕ Created:   {created}")
    print(f"   📝 Updated:   {updated}")
    print(f"   🗑️  Deleted:   {deleted}")
    print(f"   ⏸️  Unchanged: {unchanged}")
    if skipped_covered > 0:
        print(f"   ⏭️  Skipped (covered by manual apt): {skipped_covered}")
    print(f"=" * 70)
    
    return {'success': True, 'created': created, 'updated': updated, 'deleted': deleted, 'unchanged': unchanged}


def main():
    """Main entry point."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = sync_calendars()
    sys.exit(0 if result.get('success') else 1)


if __name__ == "__main__":
    main()
