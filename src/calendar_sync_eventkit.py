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

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "CalendarSync"
APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = APP_SUPPORT_DIR


def _load_config():
    """Load configuration from preferences file."""
    from settings_window import load_preferences
    prefs = load_preferences()
    return {
        'days_ahead': 365,  # Sync 1 year ahead
        'days_back': 7,    # Clean up a week back
        # Blocking: personal calendars → work calendar
        'personal_calendar_names': [c['name'] for c in prefs.get('personal_calendars', [])],
        'personal_calendar_sources': {c['name']: c.get('source', '') for c in prefs.get('personal_calendars', [])},
        'work_calendar_name': prefs.get('work_calendar', {}).get('name') if prefs.get('work_calendar') else None,
        'work_calendar_source': prefs.get('work_calendar', {}).get('source', '') if prefs.get('work_calendar') else '',
        'blocking_enabled': prefs.get('blocking_enabled', True),
        'blocking_event_title': prefs.get('blocking_event_title', 'Appointment'),
        'blocking_work_hours_only': prefs.get('blocking_work_hours_only', True),
        'blocking_start_hour': prefs.get('blocking_start_hour', 8),
        'blocking_end_hour': prefs.get('blocking_end_hour', 20),
        'blocking_weekdays_only': prefs.get('blocking_weekdays_only', True),
        'min_blocking_duration_minutes': prefs.get('min_blocking_duration_minutes', 15),
        'excluded_patterns': prefs.get('calendar_sync_excluded_patterns', []),
        # Calendar sync: source → destination
        'calendar_sync_enabled': prefs.get('calendar_sync_enabled', False),
        'sync_source': prefs.get('calendar_sync_source_calendar'),  # {name, source} dict
        'sync_destination': prefs.get('calendar_sync_destination'),  # {name, source} dict
    }


# Legacy fallback values (used if preferences not set)
DAYS_AHEAD = 14
DAYS_BACK = 1
PERSONAL_CALENDAR_NAMES = ["Personal Cal"]
WORK_CALENDAR_NAME = "Calendar"
BLOCKING_EVENT_TITLE = "apt"
AUTO_MARKER = "\u200b"  # Zero-width space — invisible marker for auto-created events
BLOCKING_WORK_HOURS_ONLY = True
BLOCKING_START_HOUR = 8
BLOCKING_END_HOUR = 20
BLOCKING_WEEKDAYS_ONLY = True
MIN_BLOCKING_DURATION_MINUTES = 15


# ============================================================================
# Pattern Matching
# ============================================================================

def _matches_excluded(title: str, patterns: list) -> bool:
    """Check if a title matches any excluded pattern.
    Supports simple glob: 'lunch*' matches any title starting with 'lunch'.
    Plain pattern does substring match: '1:1' matches '1:1 John'.
    """
    import fnmatch
    title_lower = title.lower()
    for p in patterns:
        if not p:
            continue
        p_lower = p.lower()
        if '*' in p_lower or '?' in p_lower:
            if fnmatch.fnmatch(title_lower, p_lower):
                return True
        else:
            if p_lower in title_lower:
                return True
    return False


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
    skipped_excluded = 0

    blocking_work_hours_only = config.get('blocking_work_hours_only', True)
    min_duration = config.get('min_blocking_duration_minutes', 15)
    excluded_patterns = config.get('excluded_patterns', [])
    
    for event in events:
        # Skip all-day events
        if event.isAllDay():
            skipped_all_day += 1
            continue

        # Skip events matching excluded patterns
        title = str(event.title() or "")
        if excluded_patterns and _matches_excluded(title, excluded_patterns):
            skipped_excluded += 1
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
        
        # Use eventIdentifier + start time as key to handle recurring events
        # (all occurrences share the same eventIdentifier)
        occurrence_key = f"{event.eventIdentifier()}_{start_dt.isoformat()}"
        event_data = {
            'apple_id': occurrence_key,
            'title': str(event.title() or "(No Title)"),
            'start': start_dt,
            'end': end_dt,
            'start_iso': start_dt.isoformat(),
            'end_iso': end_dt.isoformat(),
        }
        event_list.append(event_data)
    
    if skipped_all_day > 0:
        print(f"   Skipped {skipped_all_day} all-day events")
    if skipped_excluded > 0:
        print(f"   Skipped {skipped_excluded} events matching excluded patterns")
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


def get_work_calendar_by_name(store, calendar_name: str, calendar_source: str = ''):
    """Get a calendar by name and optionally source."""
    all_calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    # Try matching by both name and source first
    if calendar_source:
        for cal in all_calendars:
            if cal.title() == calendar_name and cal.source().title() == calendar_source:
                return cal
    # Fall back to name-only match
    for cal in all_calendars:
        if cal.title() == calendar_name:
            return cal
    return None


def fetch_blocking_events(store, work_calendar, days_back: int, days_ahead: int, blocking_title: str) -> tuple:
    """Fetch all blocking events from the work calendar.

    Returns (all_blocking, auto_blocking) where:
    - all_blocking: all events matching the blocking title (for duplicate detection)
    - auto_blocking: only auto-created ones (for cleanup/deletion)
    """
    start_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
    end_date = datetime.datetime.now() + datetime.timedelta(days=days_ahead)

    ns_start = NSDate.dateWithTimeIntervalSince1970_(start_date.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(end_date.timestamp())

    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        ns_start, ns_end, [work_calendar]
    )
    events = store.eventsMatchingPredicate_(predicate)

    all_blocking = []
    auto_blocking = []
    for event in events:
        title = str(event.title() or '')
        if title.lower() != blocking_title.lower():
            continue

        start_dt = datetime.datetime.fromtimestamp(event.startDate().timeIntervalSince1970())
        end_dt = datetime.datetime.fromtimestamp(event.endDate().timeIntervalSince1970())
        notes = str(event.notes() or '')
        is_auto = AUTO_MARKER in notes or '[Auto-blocked from personal calendar]' in notes

        entry = {
            'id': str(event.eventIdentifier()),
            'start': start_dt,
            'end': end_dt,
            'start_iso': start_dt.isoformat(),
            'end_iso': end_dt.isoformat(),
            'is_auto': is_auto,
            'notes': notes,
        }
        all_blocking.append(entry)
        if is_auto:
            auto_blocking.append(entry)

    return all_blocking, auto_blocking


def find_matching_blocking_event(personal_event: dict, blocking_events: list) -> Optional[dict]:
    """Find a blocking event that matches a personal event by time."""
    for blk in blocking_events:
        if (blk['start_iso'] == personal_event['start_iso'] and
            blk['end_iso'] == personal_event['end_iso']):
            return blk
    return None


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
        
        event.setNotes_(blocking_title + AUTO_MARKER)
        
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
        
        event.setNotes_(blocking_title + AUTO_MARKER)
        
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

def sync_calendars(event_store=None, config=None):
    """Blocking sync - syncs personal calendar events to work calendar as blocking events."""

    # Load config from preferences
    if config is None:
        config = _load_config()

    if not config.get('blocking_enabled', True):
        print("⏭️  Calendar blocking is disabled, skipping.")
        return {'success': True, 'created': 0, 'updated': 0, 'deleted': 0, 'unchanged': 0}

    personal_calendar_names = config['personal_calendar_names'] or PERSONAL_CALENDAR_NAMES
    work_calendar_name = config['work_calendar_name'] or WORK_CALENDAR_NAME
    work_calendar_source = config.get('work_calendar_source', '')
    days_back = config['days_back']
    days_ahead = config['days_ahead']
    blocking_event_title = config['blocking_event_title']

    print("=" * 70)
    print("  Personal Calendar → Work Calendar Blocking")
    print("=" * 70)
    print(f"  Personal calendars: {personal_calendar_names}")
    print(f"  Work calendar: {work_calendar_name} ({work_calendar_source})")

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
    work_calendar = get_work_calendar_by_name(store, work_calendar_name, work_calendar_source)
    if not work_calendar:
        print(f"❌ Work calendar '{work_calendar_name}' ({work_calendar_source}) not found")
        return {'success': False, 'error': f'Work calendar not found'}

    # Fetch existing blocking events from work calendar (source of truth)
    all_blocking, auto_blocking = fetch_blocking_events(
        store, work_calendar, days_back, days_ahead, blocking_event_title
    )
    print(f"   Found {len(all_blocking)} blocking events on work calendar ({len(auto_blocking)} auto-created)")

    # Track stats
    created = 0
    deleted = 0
    unchanged = 0

    # Track which auto-blocked events are still needed (for cleanup)
    matched_auto_ids = set()

    print(f"\n🔄 Syncing blocking events...")

    for event in personal_events:
        # Check if any blocking event (manual or auto) already covers this time
        match = find_matching_blocking_event(event, all_blocking)
        if match:
            unchanged += 1
            if match['is_auto']:
                matched_auto_ids.add(match['id'])
        else:
            # No blocking event exists for this personal event — create one
            print(f"   ➕ Creating block for: {event['title']} ({event['start'].strftime('%m/%d %H:%M')}-{event['end'].strftime('%H:%M')})")
            create_blocking_event_on_work_calendar(store, work_calendar, event, blocking_event_title)
            created += 1

    # Delete orphaned auto-blocked events (no matching personal event)
    for blk in auto_blocking:
        if blk['id'] not in matched_auto_ids:
            print(f"   🗑️  Removing orphaned auto-block: {blk['start'].strftime('%m/%d %H:%M')}-{blk['end'].strftime('%H:%M')}")
            delete_blocking_event_from_work_calendar(store, blk['id'])
            deleted += 1
    
    # Print summary
    print(f"\n" + "=" * 70)
    print(f"  ✅ Blocking Sync Complete!")
    print(f"=" * 70)
    print(f"   ➕ Created:   {created}")
    print(f"   🗑️  Deleted:   {deleted}")
    print(f"   ⏸️  Unchanged: {unchanged}")
    print(f"=" * 70)

    return {'success': True, 'created': created, 'deleted': deleted, 'unchanged': unchanged}


# ============================================================================
# Calendar Sync: Source → Destination
# ============================================================================

def sync_source_to_destination(event_store=None, config=None):
    """Sync events from source calendar to destination calendar (mirroring)."""

    if config is None:
        config = _load_config()

    if not config.get('calendar_sync_enabled', False):
        print("\n⏭️  Calendar sync is disabled, skipping.")
        return {'success': True, 'created': 0, 'updated': 0, 'deleted': 0, 'unchanged': 0}

    sync_source = config.get('sync_source')
    sync_dest = config.get('sync_destination')

    if not sync_source or not sync_dest:
        print("\n⏭️  Calendar sync source or destination not configured, skipping.")
        return {'success': True, 'created': 0, 'updated': 0, 'deleted': 0, 'unchanged': 0}

    days_back = config['days_back']
    days_ahead = config['days_ahead']
    excluded_patterns = config.get('excluded_patterns', [])

    print("\n" + "=" * 70)
    print("  Calendar Sync: Source → Destination")
    print("=" * 70)
    print(f"  Source: {sync_source['name']} ({sync_source.get('source', '')})")
    print(f"  Destination: {sync_dest['name']} ({sync_dest.get('source', '')})")

    # Get or create event store
    if event_store is None:
        event_store = EventKit.EKEventStore.alloc().init()
        access_granted = request_calendar_access()
        if not access_granted:
            return {'success': False, 'error': 'Calendar access denied'}

    store = event_store

    # Resolve source and destination calendars
    source_cal = get_work_calendar_by_name(store, sync_source['name'], sync_source.get('source', ''))
    if not source_cal:
        print(f"❌ Source calendar '{sync_source['name']}' not found")
        return {'success': False, 'error': 'Source calendar not found'}

    dest_cal = get_work_calendar_by_name(store, sync_dest['name'], sync_dest.get('source', ''))
    if not dest_cal:
        print(f"❌ Destination calendar '{sync_dest['name']}' not found")
        return {'success': False, 'error': 'Destination calendar not found'}

    # Fetch source events
    start_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
    end_date = datetime.datetime.now() + datetime.timedelta(days=days_ahead)
    ns_start = NSDate.dateWithTimeIntervalSince1970_(start_date.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(end_date.timestamp())

    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(ns_start, ns_end, [source_cal])
    source_events = store.eventsMatchingPredicate_(predicate)

    print(f"\n📅 Fetching source calendar events...")

    event_list = []
    skipped_excluded = 0
    for event in source_events:
        if event.status() == 3:  # cancelled
            continue

        title = str(event.title() or "(No Title)")

        # Skip events matching excluded patterns
        if excluded_patterns and _matches_excluded(title, excluded_patterns):
            skipped_excluded += 1
            continue

        start_ts = event.startDate().timeIntervalSince1970()
        end_ts = event.endDate().timeIntervalSince1970()

        # Use eventIdentifier + start time as key to handle recurring events
        start_iso = datetime.datetime.fromtimestamp(start_ts).isoformat()
        occurrence_key = f"{event.eventIdentifier()}_{start_iso}"

        event_list.append({
            'source_id': occurrence_key,
            'title': title,
            'start_ts': start_ts,
            'end_ts': end_ts,
            'start_iso': start_iso,
            'end_iso': datetime.datetime.fromtimestamp(end_ts).isoformat(),
            'is_all_day': bool(event.isAllDay()),
        })

    print(f"   Found {len(event_list)} events to sync")
    if skipped_excluded > 0:
        print(f"   Skipped {skipped_excluded} events matching excluded patterns")

    # Fetch ALL existing events on destination calendar
    dest_predicate = store.predicateForEventsWithStartDate_endDate_calendars_(ns_start, ns_end, [dest_cal])
    dest_events_raw = store.eventsMatchingPredicate_(dest_predicate)

    dest_all_events = []
    dest_auto_events = []
    for ev in dest_events_raw:
        dest_start = datetime.datetime.fromtimestamp(ev.startDate().timeIntervalSince1970())
        dest_end = datetime.datetime.fromtimestamp(ev.endDate().timeIntervalSince1970())
        notes = str(ev.notes() or '')
        is_auto = AUTO_MARKER in notes
        entry = {
            'id': str(ev.eventIdentifier()),
            'title': str(ev.title() or ''),
            'start_iso': dest_start.isoformat(),
            'end_iso': dest_end.isoformat(),
            'is_auto': is_auto,
        }
        dest_all_events.append(entry)
        if is_auto:
            dest_auto_events.append(entry)

    print(f"   Found {len(dest_all_events)} total events on destination ({len(dest_auto_events)} auto-synced)")

    created = 0
    updated = 0
    deleted = 0
    unchanged = 0

    # Track which auto dest events are still needed (for orphan cleanup)
    matched_auto_ids = set()

    print(f"\n🔄 Syncing events...")
    for event in event_list:
        # Check if ANY event on destination matches by title + time
        match = None
        for dest_ev in dest_all_events:
            if (dest_ev['title'] == event['title'] and
                dest_ev['start_iso'] == event['start_iso'] and
                dest_ev['end_iso'] == event['end_iso']):
                match = dest_ev
                break

        if match:
            if match['is_auto']:
                matched_auto_ids.add(match['id'])
            unchanged += 1
        else:
            # No matching event on destination — create one
            print(f"   ➕ Creating: {event['title']} ({datetime.datetime.fromtimestamp(event['start_ts']).strftime('%m/%d %H:%M')})")
            _create_synced_event(store, dest_cal, event, sync_source_name=sync_source['name'])
            created += 1

    # Delete orphaned auto-synced events (no matching source event)
    for dest_ev in dest_auto_events:
        if dest_ev['id'] not in matched_auto_ids:
            print(f"   🗑️  Removing orphaned sync: {dest_ev['title']} ({dest_ev['start_iso']})")
            try:
                ev = store.eventWithIdentifier_(dest_ev['id'])
                if ev:
                    store.removeEvent_span_error_(ev, EventKit.EKSpanThisEvent, None)
            except Exception as e:
                print(f"   ❌ Error deleting: {e}")
            deleted += 1

    print(f"\n" + "=" * 70)
    print(f"  ✅ Calendar Sync Complete!")
    print(f"=" * 70)
    print(f"   ➕ Created:   {created}")
    print(f"   📝 Updated:   {updated}")
    print(f"   🗑️  Deleted:   {deleted}")
    print(f"   ⏸️  Unchanged: {unchanged}")
    print(f"=" * 70)

    return {'success': True, 'created': created, 'updated': updated, 'deleted': deleted, 'unchanged': unchanged}


def _create_synced_event(store, dest_calendar, event_data: dict, sync_source_name: str = '') -> Optional[str]:
    """Create an event on the destination calendar mirroring the source event."""
    try:
        new_event = EventKit.EKEvent.eventWithEventStore_(store)
        new_event.setTitle_(event_data['title'])
        new_event.setCalendar_(dest_calendar)
        new_event.setNotes_(f"Synced from {sync_source_name}" + AUTO_MARKER)

        ns_start = NSDate.dateWithTimeIntervalSince1970_(event_data['start_ts'])
        ns_end = NSDate.dateWithTimeIntervalSince1970_(event_data['end_ts'])
        new_event.setStartDate_(ns_start)
        new_event.setEndDate_(ns_end)

        if event_data.get('is_all_day'):
            new_event.setAllDay_(True)

        success = store.saveEvent_span_error_(new_event, EventKit.EKSpanThisEvent, None)
        if success:
            return str(new_event.eventIdentifier())
        return None
    except Exception as e:
        print(f"   ❌ Error creating synced event: {e}")
        return None


def main():
    """Main entry point. Runs blocking first, then calendar sync."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    config = _load_config()

    # Share a single event store
    event_store = EventKit.EKEventStore.alloc().init()
    access_granted = request_calendar_access()
    if not access_granted:
        print("❌ Calendar access denied")
        sys.exit(1)

    # Step 1: Work blocking (personal → work)
    blocking_result = sync_calendars(event_store=event_store, config=config)
    if not blocking_result.get('success'):
        print("❌ Blocking sync failed")
        sys.exit(1)

    # Step 2: Calendar sync (source → destination)
    # Runs after blocking so new blocking events are picked up
    sync_result = sync_source_to_destination(event_store=event_store, config=config)
    if not sync_result.get('success'):
        print("❌ Calendar sync failed")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
