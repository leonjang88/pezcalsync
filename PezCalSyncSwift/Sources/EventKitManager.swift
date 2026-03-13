import EventKit
import Foundation

final class EventKitManager {
    static let shared = EventKitManager()

    let eventStore = EKEventStore()
    private(set) var hasAccess: Bool = false

    /// Callback invoked (on the main thread) when the calendar store changes.
    var onStoreChanged: (() -> Void)?

    /// Debounce work item for store-change notifications.
    private var debounceWorkItem: DispatchWorkItem?

    private init() {
        // Check cached / current authorization status on init
        refreshAccessStatus()

        // Story 2.5: Listen for calendar store changes
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(eventStoreDidChange(_:)),
            name: .EKEventStoreChanged,
            object: eventStore
        )
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    // MARK: - Store Change Handling (Story 2.5)

    @objc private func eventStoreDidChange(_ notification: Notification) {
        // Debounce rapid updates with a 2-second delay
        debounceWorkItem?.cancel()
        let workItem = DispatchWorkItem { [weak self] in
            guard let self = self else { return }
            NSLog("[EventKitManager] Calendar store changed, notifying listener.")
            self.onStoreChanged?()
        }
        debounceWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0, execute: workItem)
    }

    /// Updates `hasAccess` based on the current system authorization status.
    private func refreshAccessStatus() {
        if #available(macOS 14.0, *) {
            hasAccess = EKEventStore.authorizationStatus(for: .event) == .fullAccess
        } else {
            hasAccess = EKEventStore.authorizationStatus(for: .event) == .authorized
        }
    }

    /// Requests calendar access, using the macOS 14+ full-access API when
    /// available and falling back to the legacy API on older systems.
    func requestAccess() {
        let status = EKEventStore.authorizationStatus(for: .event)

        if #available(macOS 14.0, *) {
            if status == .fullAccess {
                hasAccess = true
                NSLog("[EventKitManager] Calendar access already granted (fullAccess).")
                return
            }
            eventStore.requestFullAccessToEvents { [weak self] granted, error in
                DispatchQueue.main.async {
                    self?.hasAccess = granted
                    if granted {
                        NSLog("[EventKitManager] Calendar full access granted.")
                    } else {
                        let desc = error?.localizedDescription ?? "unknown"
                        NSLog("[EventKitManager] Calendar full access denied: %@", desc)
                    }
                }
            }
        } else {
            if status == .authorized {
                hasAccess = true
                NSLog("[EventKitManager] Calendar access already granted (authorized).")
                return
            }
            eventStore.requestAccess(to: .event) { [weak self] granted, error in
                DispatchQueue.main.async {
                    self?.hasAccess = granted
                    if granted {
                        NSLog("[EventKitManager] Calendar access granted (legacy).")
                    } else {
                        let desc = error?.localizedDescription ?? "unknown"
                        NSLog("[EventKitManager] Calendar access denied (legacy): %@", desc)
                    }
                }
            }
        }
    }

    // MARK: - Fetch Events (Story 2.2)

    /// Fetches events in the given date range from the specified calendars.
    /// Filters out cancelled events and sorts by start date.
    /// If `calendars` is nil or empty, events from all calendars are returned.
    func fetchEvents(from startDate: Date, to endDate: Date, calendars: [EKCalendar]?) -> [EKEvent] {
        guard hasAccess else {
            NSLog("[EventKitManager] Cannot fetch events – no calendar access.")
            return []
        }

        let cals = (calendars?.isEmpty ?? true) ? nil : calendars
        let predicate = eventStore.predicateForEvents(withStart: startDate, end: endDate, calendars: cals)
        let events = eventStore.events(matching: predicate)

        // Filter out cancelled events and sort by start date
        let filtered = events
            .filter { $0.status != .canceled }
            .sorted { $0.startDate < $1.startDate }

        NSLog("[EventKitManager] Fetched %d events (from %d total) between %@ and %@.",
              filtered.count, events.count,
              ISO8601DateFormatter().string(from: startDate),
              ISO8601DateFormatter().string(from: endDate))

        return filtered
    }

    /// Resolves `DisplayCalendar` entries to actual `EKCalendar` objects.
    /// Returns nil if displayCalendars is empty (meaning "use all calendars").
    func resolveCalendars(from displayCalendars: [DisplayCalendar]) -> [EKCalendar]? {
        guard !displayCalendars.isEmpty else { return nil }

        let allCalendars = eventStore.calendars(for: .event)
        let matched = allCalendars.filter { ekCal in
            displayCalendars.contains { dc in
                dc.name == ekCal.title && dc.source == (ekCal.source?.title ?? "")
            }
        }

        NSLog("[EventKitManager] Resolved %d display calendars to %d EKCalendars.",
              displayCalendars.count, matched.count)

        return matched.isEmpty ? nil : matched
    }

    /// Resolves a single CalendarRef to an EKCalendar.
    func resolveCalendar(from ref: CalendarRef) -> EKCalendar? {
        let allCalendars = eventStore.calendars(for: .event)
        return allCalendars.first { ekCal in
            ref.name == ekCal.title && ref.source == (ekCal.source?.title ?? "")
        }
    }

    /// Fetches the sprint/release event for a given date from a specific calendar,
    /// matching the given title prefix.
    func fetchSprintEvent(for date: Date, calendar: EKCalendar, titlePrefix: String) -> EKEvent? {
        let cal = Calendar.current
        let dayStart = cal.startOfDay(for: date)
        let dayEnd = cal.date(byAdding: .day, value: 1, to: dayStart)!
        let predicate = eventStore.predicateForEvents(withStart: dayStart, end: dayEnd, calendars: [calendar])
        let events = eventStore.events(matching: predicate)
        return events
            .filter { $0.status != .canceled }
            .first { event in
                let eventStartDay = cal.startOfDay(for: event.startDate)
                let eventEndDay = cal.startOfDay(for: event.endDate)
                guard eventStartDay != eventEndDay else { return false }
                guard let title = event.title else { return false }
                return title.contains(titlePrefix)
            }
    }

    /// Fetches unique title prefixes from multi-day events in a calendar.
    /// Groups by the alphabetic prefix before the first space or digit sequence.
    func fetchReleaseEventPrefixes(from calendar: EKCalendar) -> [String] {
        let cal = Calendar.current
        let now = Date()
        let start = cal.date(byAdding: .month, value: -1, to: now)!
        let end = cal.date(byAdding: .month, value: 3, to: now)!
        let predicate = eventStore.predicateForEvents(withStart: start, end: end, calendars: [calendar])
        let events = eventStore.events(matching: predicate)

        var prefixes = Set<String>()
        for event in events where event.status != .canceled {
            let eventStartDay = cal.startOfDay(for: event.startDate)
            let eventEndDay = cal.startOfDay(for: event.endDate)
            guard eventStartDay != eventEndDay, let title = event.title else { continue }
            // Extract the last all-uppercase word before the first digit
            // e.g., "Vonahi Dev - VDEV 2026-58" -> "VDEV"
            let beforeDigits = String(title.prefix(while: { !$0.isNumber }))
            let words = beforeDigits.components(separatedBy: .whitespaces).filter { !$0.isEmpty }
            // Find the last word that is all uppercase letters
            if let lastUpper = words.last(where: { $0 == $0.uppercased() && $0.allSatisfy({ $0.isLetter }) }) {
                prefixes.insert(lastUpper)
            }
        }
        return prefixes.sorted()
    }
}
