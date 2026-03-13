import Cocoa
import EventKit

class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private let eventKitManager = EventKitManager.shared
    private let preferencesManager = PreferencesManager.shared
    private let syncManager = SyncManager.shared
    private let settingsWindowController = SettingsWindowController()

    /// Work item for reverting a temporary menubar icon back to idle.
    private var iconRevertWorkItem: DispatchWorkItem?

    /// Timer for spinning the sync icon.
    private var spinTimer: Timer?
    private var spinAngle: CGFloat = 0

    // Story 6.2 - Launch at Login: Placeholder
    // TODO: Implement Launch at Login using SMAppService.mainApp.register()
    // when building as a proper app bundle with entitlements.
    // SPM executables cannot use SMAppService because it requires an app bundle
    // with a proper bundle identifier and the ServiceManagement entitlement.

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Hide dock icon
        NSApp.setActivationPolicy(.accessory)

        // Load preferences
        preferencesManager.load()

        // Request calendar access on launch
        eventKitManager.requestAccess()

        // Create menubar status item
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)

        // Story 6.1: Set initial menubar icon using SF Symbol
        setMenuBarIcon("calendar.circle")

        // Story 2.5: Rebuild the menu when the calendar store changes
        // Story 3.3: Also trigger a throttled sync on calendar changes
        eventKitManager.onStoreChanged = { [weak self] in
            guard let self = self else { return }
            NSLog("[AppDelegate] Calendar store changed – rebuilding menu and triggering sync.")
            self.statusItem.menu = self.buildMenu()
            self.syncManager.runSyncThrottled()
        }

        // Story 3.2: On sync complete, rebuild menu and reload mappings
        syncManager.onSyncComplete = { [weak self] status in
            guard let self = self else { return }
            self.updateMenuBarIcon()
            self.statusItem.menu = self.buildMenu()
        }

        // Build and attach menu
        statusItem.menu = buildMenu()

        // Story 3.4: Start periodic background sync timer
        syncManager.startPeriodicTimer()

        // Sync on launch
        syncManager.runSync()
    }

    // MARK: - Menubar Icon Helpers (Story 6.1)

    /// Sets the menubar icon to an SF Symbol. The image is set as a template image
    /// (adapts to dark/light mode) and resized to 18x18.
    private func setMenuBarIcon(_ symbolName: String) {
        guard let button = statusItem.button else { return }
        if let image = NSImage(systemSymbolName: symbolName, accessibilityDescription: nil) {
            let config = NSImage.SymbolConfiguration(pointSize: 18, weight: .regular)
            let configured = image.withSymbolConfiguration(config) ?? image
            configured.isTemplate = true
            button.image = configured
        } else {
            NSLog("[AppDelegate] Failed to load SF Symbol: %@", symbolName)
        }
    }

    /// Sets the menubar icon temporarily, then reverts to idle after the given duration.
    private func setMenuBarIconTemporarily(_ symbolName: String, duration: TimeInterval) {
        // Cancel any pending revert
        iconRevertWorkItem?.cancel()

        setMenuBarIcon(symbolName)

        let workItem = DispatchWorkItem { [weak self] in
            self?.setMenuBarIcon("calendar.circle")
        }
        iconRevertWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + duration, execute: workItem)
    }

    /// Updates the menubar icon based on sync state (Stories 3.2 & 6.1).
    private func updateMenuBarIcon() {
        if syncManager.isSyncing {
            startSpinning()
        } else {
            stopSpinning()
            switch syncManager.lastSyncStatus {
            case .success:
                setMenuBarIconTemporarily("checkmark.circle.fill", duration: 3.0)
            case .failed:
                setMenuBarIconTemporarily("xmark.circle", duration: 5.0)
            default:
                setMenuBarIcon("calendar.circle")
            }
        }
    }

    private func startSpinning() {
        guard spinTimer == nil else { return }
        spinAngle = 0
        setSyncIconRotated()
        spinTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            self?.spinAngle += 30
            if self?.spinAngle ?? 0 >= 360 { self?.spinAngle = 0 }
            self?.setSyncIconRotated()
        }
    }

    private func stopSpinning() {
        spinTimer?.invalidate()
        spinTimer = nil
    }

    private func setSyncIconRotated() {
        guard let button = statusItem.button,
              let baseImage = NSImage(systemSymbolName: "arrow.trianglehead.2.clockwise.rotate.90", accessibilityDescription: nil) else { return }
        let config = NSImage.SymbolConfiguration(pointSize: 18, weight: .regular)
        let configured = baseImage.withSymbolConfiguration(config) ?? baseImage
        let size = configured.size

        let rotated = NSImage(size: size)
        rotated.lockFocus()
        let transform = NSAffineTransform()
        transform.translateX(by: size.width / 2, yBy: size.height / 2)
        transform.rotate(byDegrees: -spinAngle)
        transform.translateX(by: -size.width / 2, yBy: -size.height / 2)
        transform.concat()
        configured.draw(in: NSRect(origin: .zero, size: size))
        rotated.unlockFocus()

        rotated.isTemplate = true
        button.image = rotated
    }

    /// Builds the full menu structure. Can be called again to refresh.
    func buildMenu() -> NSMenu {
        let menu = NSMenu()

        let cal = Calendar.current
        let now = Date()
        let startOfToday = cal.startOfDay(for: now)

        let headerFormatter = DateFormatter()
        headerFormatter.dateFormat = "MMM d"

        let weekdayFormatter = DateFormatter()
        weekdayFormatter.dateFormat = "EEEE"

        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "h:mm a"
        let prefs = preferencesManager.preferences

        // Build day offsets: collect N matching days (skipping weekends if weekdays only)
        var dayOffsets: [Int] = []
        var offset = 0
        while dayOffsets.count < prefs.daysAhead {
            let dayDate = cal.date(byAdding: .day, value: offset, to: startOfToday)!
            if prefs.displayDayFilter == "weekdays" {
                let weekday = cal.component(.weekday, from: dayDate)
                if weekday == 1 || weekday == 7 { offset += 1; continue }
            }
            dayOffsets.append(offset)
            offset += 1
        }

        let maxOffset = (dayOffsets.last ?? 0) + 1
        let endOfRange = cal.date(byAdding: .day, value: maxOffset, to: startOfToday)!
        let ekCalendars = eventKitManager.resolveCalendars(from: prefs.displayCalendars)
        let allEvents = eventKitManager.fetchEvents(from: startOfToday, to: endOfRange, calendars: ekCalendars)

        // Resolve release calendar for sprint headers
        let releaseEKCalendar: EKCalendar? = {
            guard let ref = prefs.releaseCalendar else { return nil }
            return eventKitManager.resolveCalendar(from: ref)
        }()

        // Filter out all release calendar multi-day events when a prefix is selected
        let selectedPrefix = prefs.releaseEventPrefix
        let filteredEvents: [EKEvent]
        if let relCal = releaseEKCalendar, !selectedPrefix.isEmpty {
            filteredEvents = allEvents.filter { event in
                guard event.calendar?.calendarIdentifier == relCal.calendarIdentifier else { return true }
                // Hide all multi-day events from the release calendar
                let eventStartDay = cal.startOfDay(for: event.startDate)
                let eventEndDay = cal.startOfDay(for: event.endDate)
                return eventStartDay == eventEndDay
            }
        } else {
            filteredEvents = allEvents
        }

        // Group events by day offset (0 = today, 1 = tomorrow, 2 = day after)
        var eventsByDay: [Int: [EKEvent]] = [:]
        for event in filteredEvents {
            for offset in dayOffsets {
                let dayStart = cal.date(byAdding: .day, value: offset, to: startOfToday)!
                let dayEnd = cal.date(byAdding: .day, value: offset + 1, to: startOfToday)!
                // An event belongs to a day if it overlaps with [dayStart, dayEnd)
                if event.startDate < dayEnd && event.endDate > dayStart {
                    eventsByDay[offset, default: []].append(event)
                }
            }
        }

        // Sprint countdown at the very top
        if let relCal = releaseEKCalendar, !selectedPrefix.isEmpty,
           let sprintEvent = eventKitManager.fetchSprintEvent(
               for: startOfToday, calendar: relCal, titlePrefix: selectedPrefix) {
            let daysLeft = cal.dateComponents([.day], from: startOfToday, to: cal.startOfDay(for: sprintEvent.endDate)).day ?? 0
            let sprintId: String = {
                guard let title = sprintEvent.title else { return "" }
                if let range = title.range(of: #"\d[\d-]+"#, options: .regularExpression) {
                    return String(title[range])
                }
                return ""
            }()
            let sprintText: String
            if daysLeft == 0 {
                sprintText = "Sprint \(sprintId) | Last day"
            } else {
                sprintText = "Sprint \(sprintId) | \(daysLeft)d left"
            }
            let sprintItem = NSMenuItem(title: sprintText, action: nil, keyEquivalent: "")
            sprintItem.isEnabled = false
            if let runImage = createColoredSFSymbol(name: "figure.run", color: .white, size: 14) {
                sprintItem.image = runImage
            }
            menu.addItem(sprintItem)
            menu.addItem(NSMenuItem.separator())
        }

        for (index, offset) in dayOffsets.enumerated() {
            let dayDate = cal.date(byAdding: .day, value: offset, to: startOfToday)!
            let headerTitle: String
            switch offset {
            case 0:
                headerTitle = "Today, \(headerFormatter.string(from: dayDate))"
            case 1:
                headerTitle = "Tomorrow, \(headerFormatter.string(from: dayDate))"
            default:
                headerTitle = "\(weekdayFormatter.string(from: dayDate)), \(headerFormatter.string(from: dayDate))"
            }

            let header = NSMenuItem(title: headerTitle, action: #selector(eventClicked(_:)), keyEquivalent: "")
            header.target = self
            header.attributedTitle = NSAttributedString(string: headerTitle, attributes: [
                .font: NSFont.boldSystemFont(ofSize: 13)
            ])
            // Day number calendar icon (e.g., "13.calendar" for the 13th)
            let dayNumber = cal.component(.day, from: dayDate)
            if let dayImage = NSImage(systemSymbolName: "\(dayNumber).calendar", accessibilityDescription: nil) {
                let config = NSImage.SymbolConfiguration(pointSize: 18, weight: .regular)
                let colorConfig = NSImage.SymbolConfiguration(hierarchicalColor: .white)
                let combined = config.applying(colorConfig)
                header.image = dayImage.withSymbolConfiguration(combined) ?? dayImage
            }
            if index > 0 {
                menu.addItem(NSMenuItem.separator())
            }
            menu.addItem(header)

            let dayEvents = (eventsByDay[offset] ?? []).sorted { a, b in
                // All-day events first
                if a.isAllDay != b.isAllDay { return a.isAllDay }
                // Then by start time
                if a.startDate != b.startDate { return a.startDate < b.startDate }
                // Then by calendar name
                return (a.calendar?.title ?? "") < (b.calendar?.title ?? "")
            }
            if dayEvents.isEmpty {
                let noEvents = NSMenuItem(title: "No events", action: nil, keyEquivalent: "")
                noEvents.isEnabled = false
                menu.addItem(noEvents)
            } else {
                for event in dayEvents {
                    let title: String
                    if event.isAllDay {
                        title = "All day - \(event.title ?? "(No title)")"
                    } else {
                        let timeString = timeFormatter.string(from: event.startDate)
                        title = "\(timeString) - \(event.title ?? "(No title)")"
                    }
                    let item: NSMenuItem
                    if event.isAllDay || event.endDate < now {
                        item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
                        item.isEnabled = false
                    } else {
                        item = NSMenuItem(title: title, action: #selector(eventClicked(_:)), keyEquivalent: "")
                        item.target = self
                        item.representedObject = event.startDate
                    }

                    // Story 2.3: Set calendar icon on the menu item
                    if let dc = displayCalendar(for: event, in: prefs.displayCalendars) {
                        let isPast = event.isAllDay || event.endDate < now
                        if isPast {
                            // Past event — grey icon
                            let symbolName = sfSymbolName(forDescriptor: dc.icon, filled: true)
                            if let image = createColoredSFSymbol(name: symbolName, color: .systemGray, size: 18) {
                                item.image = image
                            }
                        } else if isExcludedFromSync(event: event, prefs: prefs) {
                            // Unsynced — use outline variant
                            if let image = createUnfilledIconImage(forDescriptor: dc.icon, size: 18) {
                                item.image = image
                            }
                        } else {
                            // Synced — use filled variant
                            if let image = createIconImage(forDescriptor: dc.icon, size: 18) {
                                item.image = image
                            }
                        }
                    }

                    menu.addItem(item)
                }
            }
        }

        menu.addItem(NSMenuItem.separator())

        // --- Sync section (Story 3.2) ---
        let syncItem = NSMenuItem(title: "Sync Now", action: #selector(syncNowClicked(_:)), keyEquivalent: "")
        syncItem.target = self
        if syncManager.isSyncing {
            syncItem.isEnabled = false
        }
        menu.addItem(syncItem)

        let lastSyncText: String
        if let lastTime = syncManager.lastSyncTime {
            lastSyncText = "Last sync: \(SyncManager.relativeTimeString(from: lastTime))"
        } else {
            lastSyncText = "Last sync: Never"
        }
        let lastSyncItem = NSMenuItem(title: lastSyncText, action: nil, keyEquivalent: "")
        lastSyncItem.isEnabled = false
        menu.addItem(lastSyncItem)

        menu.addItem(NSMenuItem.separator())

        // --- Settings section ---
        let settingsItem = NSMenuItem(title: "Settings...", action: #selector(settingsClicked(_:)), keyEquivalent: "")
        settingsItem.target = self
        menu.addItem(settingsItem)

        let viewLogsItem = NSMenuItem(title: "View Logs", action: #selector(viewLogsClicked(_:)), keyEquivalent: "")
        viewLogsItem.target = self
        menu.addItem(viewLogsItem)

        menu.addItem(NSMenuItem.separator())

        // --- Quit ---
        menu.addItem(NSMenuItem(title: "Quit PezCalSync", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))

        return menu
    }

    // MARK: - Icon Helpers

    /// Checks if an event is excluded from sync (matches an excluded pattern on the sync source calendar).
    private func isExcludedFromSync(event: EKEvent, prefs: Preferences) -> Bool {
        guard prefs.calendarSyncEnabled,
              let source = prefs.calendarSyncSourceCalendar,
              let ekCal = event.calendar,
              ekCal.title == source.name,
              (ekCal.source?.title ?? "") == source.source,
              !prefs.calendarSyncExcludedPatterns.isEmpty,
              let title = event.title else {
            return false
        }
        let titleLower = title.lowercased()
        for pattern in prefs.calendarSyncExcludedPatterns where !pattern.isEmpty {
            let patternLower = pattern.lowercased()
            if patternLower.contains("*") || patternLower.contains("?") {
                // Simple glob: convert to check
                let base = patternLower.replacingOccurrences(of: "*", with: "")
                    .replacingOccurrences(of: "?", with: "")
                if titleLower.hasPrefix(base) { return true }
            } else {
                if titleLower.contains(patternLower) { return true }
            }
        }
        return false
    }

    /// Finds the DisplayCalendar entry matching an EKEvent's calendar.
    private func displayCalendar(for event: EKEvent, in displayCalendars: [DisplayCalendar]) -> DisplayCalendar? {
        guard let ekCal = event.calendar else { return nil }
        return displayCalendars.first { dc in
            dc.name == ekCal.title && dc.source == (ekCal.source?.title ?? "")
        }
    }

    // MARK: - Menu Actions (placeholders)

    @objc func eventClicked(_ sender: NSMenuItem) {
        if let date = sender.representedObject as? Date {
            // Open Apple Calendar to the event's date
            let timestamp = date.timeIntervalSinceReferenceDate
            let url = URL(string: "ical://show/date/\(Int(timestamp))")!
            NSWorkspace.shared.open(url)
        } else {
            // Header click — just open Calendar
            NSWorkspace.shared.open(URL(string: "ical://")!)
        }
    }

    @objc func syncNowClicked(_ sender: NSMenuItem) {
        NSLog("[AppDelegate] Sync Now clicked.")
        syncManager.runSync()
    }

    @objc func settingsClicked(_ sender: NSMenuItem) {
        NSLog("[AppDelegate] Settings clicked.")
        settingsWindowController.showSettings()
    }

    @objc func viewLogsClicked(_ sender: NSMenuItem) {
        // Story 6.3: Open the Logs directory in Finder
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let logsDir = appSupport.appendingPathComponent("CalendarSync/Logs")

        // Create the directory if it doesn't exist
        do {
            try FileManager.default.createDirectory(at: logsDir, withIntermediateDirectories: true)
        } catch {
            NSLog("[AppDelegate] Failed to create Logs directory: %@", error.localizedDescription)
        }

        NSWorkspace.shared.open(logsDir)
        NSLog("[AppDelegate] Opened Logs directory: %@", logsDir.path)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
