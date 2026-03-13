#!/usr/bin/env python3
"""Wipe all events from the Work(k) calendar within the sync date range."""

import sys
import datetime

try:
    import EventKit
    from Foundation import NSDate
except ImportError:
    print("ERROR: PyObjC not installed.")
    sys.exit(1)


def main():
    store = EventKit.EKEventStore.alloc().init()

    # Find Work(k) calendar
    all_calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    work_cal = None
    for cal in all_calendars:
        if cal.title() == "Work(k)" and cal.source().title() == "Google":
            work_cal = cal
            break

    if not work_cal:
        print("❌ Work(k) calendar not found")
        print("Available calendars:")
        for cal in all_calendars:
            print(f"  - {cal.title()} ({cal.source().title()})")
        sys.exit(1)

    # Fetch all events in a wide range
    start = datetime.datetime.now() - datetime.timedelta(days=7)
    end = datetime.datetime.now() + datetime.timedelta(days=30)
    ns_start = NSDate.dateWithTimeIntervalSince1970_(start.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(end.timestamp())

    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(ns_start, ns_end, [work_cal])
    events = store.eventsMatchingPredicate_(predicate)

    print(f"Found {len(events)} events on Work(k) to delete")

    if len(events) == 0:
        print("Nothing to do.")
        return

    deleted = 0
    for event in events:
        title = event.title() or "(No Title)"
        start_date = datetime.datetime.fromtimestamp(event.startDate().timeIntervalSince1970())
        try:
            store.removeEvent_span_error_(event, EventKit.EKSpanThisEvent, None)
            print(f"  🗑️  Deleted: {title} ({start_date.strftime('%m/%d %H:%M')})")
            deleted += 1
        except Exception as e:
            print(f"  ❌ Failed to delete {title}: {e}")

    print(f"\n✅ Deleted {deleted} events from Work(k)")


if __name__ == "__main__":
    main()
