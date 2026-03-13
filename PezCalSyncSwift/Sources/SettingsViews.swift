import SwiftUI
import EventKit

// Icon types, colors, SF Symbol mappings, and helpers are all in IconRegistry.swift.
// To add a new icon type or color, edit the arrays there.

// MARK: - Calendar Info (for UI display)

struct CalendarInfo: Identifiable, Hashable {
    let id: String // unique: "source|name"
    let name: String
    let source: String

    var displayName: String {
        "\(name) (\(source))"
    }

    var calendarRef: CalendarRef {
        CalendarRef(name: name, source: source)
    }
}

// MARK: - Display Calendar UI Model

class DisplayCalendarItem: ObservableObject, Identifiable {
    let id: String
    let name: String
    let source: String
    @Published var shown: Bool
    @Published var iconType: String
    @Published var iconColor: String
    @Published var iconVariant: String

    init(name: String, source: String, shown: Bool, iconType: String, iconColor: String, iconVariant: String) {
        self.id = "\(source)|\(name)"
        self.name = name
        self.source = source
        self.shown = shown
        self.iconType = iconType
        self.iconColor = iconColor
        self.iconVariant = iconVariant
    }
}

// MARK: - SettingsViewModel

class SettingsViewModel: ObservableObject {
    // Calendar Sync (Story 4.2)
    @Published var calendarSyncEnabled: Bool = false
    @Published var calendarSyncSourceCalendar: String = "" // "source|name"
    @Published var calendarSyncDestination: String = "" // "source|name"

    // Blocking (Story 4.3)
    @Published var blockingEnabled: Bool = false
    @Published var personalCalendars: [String] = [] // ["source|name"]
    @Published var workCalendar: String = ""
    @Published var blockingStartHour: Int = 8
    @Published var blockingEndHour: Int = 20
    @Published var blockingEventTitle: String = "Appointment"
    @Published var blockingDays: String = "weekdays"

    // Release calendar
    @Published var releaseCalendar: String = "" // "source|name"
    @Published var releaseEventPrefix: String = "" // selected prefix (e.g. "VDEV")
    @Published var availableReleasePrefixes: [String] = [] // discovered prefixes

    // Excluded patterns (Story 4.5)
    @Published var excludedPatterns: [String] = []

    // Display settings
    @Published var daysAhead: Int = 3
    @Published var displayDayFilter: String = "all"

    // Display calendars (Story 4.4)
    @Published var displayCalendarItems: [DisplayCalendarItem] = []

    // Available calendars from EventKit
    @Published var availableCalendars: [CalendarInfo] = []
    @Published var calendarsBySource: [(source: String, calendars: [CalendarInfo])] = []

    init() {
        loadFromPreferences()
        loadCalendars()
    }

    private func loadCalendars() {
        let ekManager = EventKitManager.shared
        let ekCalendars = ekManager.eventStore.calendars(for: .event)
        var infos: [CalendarInfo] = []
        for cal in ekCalendars {
            let sourceName = cal.source?.title ?? "Unknown"
            let info = CalendarInfo(id: "\(sourceName)|\(cal.title)", name: cal.title, source: sourceName)
            infos.append(info)
        }
        availableCalendars = infos.sorted { $0.displayName < $1.displayName }

        // Group by source
        var grouped: [String: [CalendarInfo]] = [:]
        for info in infos {
            grouped[info.source, default: []].append(info)
        }
        calendarsBySource = grouped.sorted { $0.key < $1.key }.map { (source: $0.key, calendars: $0.value.sorted { $0.name < $1.name }) }

        // Build display calendar items from all available calendars
        let prefs = PreferencesManager.shared.preferences
        var items: [DisplayCalendarItem] = []
        for info in infos {
            let existing = prefs.displayCalendars.first { $0.name == info.name && $0.source == info.source }
            let shown = existing != nil
            let parsed: (type: String, color: String, variant: String)
            if let ex = existing {
                parsed = parseIconDescriptor(ex.icon)
            } else {
                parsed = ("brief", "blue", "")  // Default, only visible once checked
            }
            items.append(DisplayCalendarItem(
                name: info.name,
                source: info.source,
                shown: shown,
                iconType: parsed.type,
                iconColor: parsed.color,
                iconVariant: parsed.variant
            ))
        }
        displayCalendarItems = items.sorted { "\($0.source)|\($0.name)" < "\($1.source)|\($1.name)" }

        refreshReleasePrefixes()
    }

    func refreshReleasePrefixes() {
        guard !releaseCalendar.isEmpty else {
            availableReleasePrefixes = []
            return
        }
        let parts = releaseCalendar.split(separator: "|", maxSplits: 1)
        guard parts.count == 2 else {
            availableReleasePrefixes = []
            return
        }
        let ref = CalendarRef(name: String(parts[1]), source: String(parts[0]))
        guard let ekCal = EventKitManager.shared.resolveCalendar(from: ref) else {
            availableReleasePrefixes = []
            return
        }
        availableReleasePrefixes = EventKitManager.shared.fetchReleaseEventPrefixes(from: ekCal)
    }

    private func loadFromPreferences() {
        let prefs = PreferencesManager.shared.preferences

        calendarSyncEnabled = prefs.calendarSyncEnabled
        if let src = prefs.calendarSyncSourceCalendar {
            calendarSyncSourceCalendar = "\(src.source)|\(src.name)"
        }
        if let dst = prefs.calendarSyncDestination {
            calendarSyncDestination = "\(dst.source)|\(dst.name)"
        }

        blockingEnabled = prefs.blockingEnabled
        personalCalendars = prefs.personalCalendars.map { "\($0.source)|\($0.name)" }
        if let wc = prefs.workCalendar {
            workCalendar = "\(wc.source)|\(wc.name)"
        }
        blockingStartHour = prefs.blockingStartHour
        blockingEndHour = prefs.blockingEndHour
        blockingEventTitle = prefs.blockingEventTitle
        blockingDays = prefs.blockingDays

        daysAhead = prefs.daysAhead
        displayDayFilter = prefs.displayDayFilter

        if let rc = prefs.releaseCalendar {
            releaseCalendar = "\(rc.source)|\(rc.name)"
        }
        releaseEventPrefix = prefs.releaseEventPrefix

        excludedPatterns = prefs.calendarSyncExcludedPatterns
    }

    func save() {
        // Build display calendars from items that are shown
        let displayCals = displayCalendarItems.filter { $0.shown }.map { item in
            DisplayCalendar(
                name: item.name,
                source: item.source,
                icon: buildIconDescriptor(type: item.iconType, color: item.iconColor, variant: item.iconVariant)
            )
        }

        // Parse calendar refs
        let srcRef: CalendarRef? = {
            let parts = calendarSyncSourceCalendar.split(separator: "|", maxSplits: 1)
            guard parts.count == 2 else { return nil }
            return CalendarRef(name: String(parts[1]), source: String(parts[0]))
        }()

        let destRef: CalendarRef? = {
            let parts = calendarSyncDestination.split(separator: "|", maxSplits: 1)
            guard parts.count == 2 else { return nil }
            return CalendarRef(name: String(parts[1]), source: String(parts[0]))
        }()

        let workRef: CalendarRef? = {
            let parts = workCalendar.split(separator: "|", maxSplits: 1)
            guard parts.count == 2 else { return nil }
            return CalendarRef(name: String(parts[1]), source: String(parts[0]))
        }()

        let personalRefs = personalCalendars.compactMap { id -> CalendarRef? in
            let parts = id.split(separator: "|", maxSplits: 1)
            guard parts.count == 2 else { return nil }
            return CalendarRef(name: String(parts[1]), source: String(parts[0]))
        }

        let releaseRef: CalendarRef? = {
            let parts = releaseCalendar.split(separator: "|", maxSplits: 1)
            guard parts.count == 2 else { return nil }
            return CalendarRef(name: String(parts[1]), source: String(parts[0]))
        }()

        let oldPrefs = PreferencesManager.shared.preferences
        let newPrefs = Preferences(
            calendarSyncEnabled: calendarSyncEnabled,
            calendarSyncSourceCalendar: srcRef,
            calendarSyncDestination: destRef,
            calendarSyncExcludedPatterns: excludedPatterns.filter { !$0.isEmpty },
            blockingEnabled: blockingEnabled,
            blockingEventTitle: blockingEventTitle.isEmpty ? "Appointment" : blockingEventTitle,
            blockingStartHour: blockingStartHour,
            blockingEndHour: blockingEndHour,
            blockingDays: blockingDays,
            personalCalendars: personalRefs,
            workCalendar: workRef,
            displayCalendars: displayCals,
            releaseCalendar: releaseRef,
            releaseEventPrefix: releaseEventPrefix,
            daysAhead: daysAhead,
            displayDayFilter: displayDayFilter,
            daysBack: oldPrefs.daysBack
        )

        PreferencesManager.shared.save(newPrefs)
    }
}

// MARK: - Story 4.2: Apple -> Google Sync Settings View

private let settingsLabelWidth: CGFloat = 180

struct SyncSettingsSection: View {
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Spacer().frame(width: settingsLabelWidth)
                Toggle("Enable Calendar Sync", isOn: $viewModel.calendarSyncEnabled)
            }

            Group {
                HStack {
                    Text("Source Calendar:")
                        .fontWeight(.bold)
                        .frame(width: settingsLabelWidth, alignment: .trailing)
                    Picker("", selection: $viewModel.calendarSyncSourceCalendar) {
                        Text("Select...").tag("")
                        ForEach(viewModel.availableCalendars) { cal in
                            Text(cal.displayName).tag(cal.id)
                        }
                    }
                    .labelsHidden()
                }

                HStack {
                    Text("Destination Calendar:")
                        .fontWeight(.bold)
                        .frame(width: settingsLabelWidth, alignment: .trailing)
                    Picker("", selection: $viewModel.calendarSyncDestination) {
                        Text("Select...").tag("")
                        ForEach(viewModel.availableCalendars) { cal in
                            Text(cal.displayName).tag(cal.id)
                        }
                    }
                    .labelsHidden()
                }

                ExcludedPatternsSection(viewModel: viewModel)
            }
            .disabled(!viewModel.calendarSyncEnabled)
            .opacity(viewModel.calendarSyncEnabled ? 1.0 : 0.5)
        }
    }
}

// MARK: - Story 4.5: Excluded Event Patterns

struct ExcludedPatternsSection: View {
    @ObservedObject var viewModel: SettingsViewModel
    @State private var selectedIndex: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top) {
                Text("Exclude events matching:")
                    .fontWeight(.bold)
                    .frame(width: settingsLabelWidth, alignment: .trailing)
                VStack(alignment: .leading, spacing: 0) {
                    // Table header
                    HStack {
                        Text("Pattern")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.gray.opacity(0.15))

                    // Pattern rows
                    List(selection: $selectedIndex) {
                        ForEach(viewModel.excludedPatterns.indices, id: \.self) { index in
                            TextField("Pattern", text: Binding(
                                get: { viewModel.excludedPatterns[index] },
                                set: { viewModel.excludedPatterns[index] = $0 }
                            ))
                            .textFieldStyle(.plain)
                            .tag(index)
                        }
                    }
                    .listStyle(.plain)
                    .frame(height: max(80, CGFloat(viewModel.excludedPatterns.count) * 24 + 8))

                    Divider()

                    // +/- buttons
                    HStack(spacing: 0) {
                        Button(action: {
                            viewModel.excludedPatterns.append("")
                        }) {
                            Image(systemName: "plus")
                                .frame(width: 24, height: 20)
                        }
                        .buttonStyle(.borderless)

                        Divider()
                            .frame(height: 16)

                        Button(action: {
                            if let idx = selectedIndex, idx < viewModel.excludedPatterns.count {
                                viewModel.excludedPatterns.remove(at: idx)
                                selectedIndex = nil
                            } else if !viewModel.excludedPatterns.isEmpty {
                                viewModel.excludedPatterns.removeLast()
                            }
                        }) {
                            Image(systemName: "minus")
                                .frame(width: 24, height: 20)
                        }
                        .buttonStyle(.borderless)
                        .disabled(viewModel.excludedPatterns.isEmpty)

                        Spacer()
                    }
                    .padding(.horizontal, 4)
                    .padding(.vertical, 2)
                    .background(Color.gray.opacity(0.1))
                }
                .background(Color.gray.opacity(0.05))
                .cornerRadius(6)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                )
            }

            HStack {
                Spacer().frame(width: settingsLabelWidth + 8)
                Text("e.g. lunch* excludes Lunch!, 1:1 * excludes 1:1 John")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }
}

// MARK: - Story 4.3: Personal -> Work Blocking Settings

struct BlockingSettingsSection: View {
    @ObservedObject var viewModel: SettingsViewModel

    let hourOptions: [Int] = Array(6...23)

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Spacer().frame(width: settingsLabelWidth)
                Toggle("Enable Calendar Blocking", isOn: $viewModel.blockingEnabled)
            }

            Group {
                HStack {
                    Text("Personal Calendar:")
                        .fontWeight(.bold)
                        .frame(width: settingsLabelWidth, alignment: .trailing)
                    Picker("", selection: Binding(
                        get: { viewModel.personalCalendars.first ?? "" },
                        set: { newVal in
                            if newVal.isEmpty {
                                viewModel.personalCalendars = []
                            } else {
                                viewModel.personalCalendars = [newVal]
                            }
                        }
                    )) {
                        Text("Select...").tag("")
                        ForEach(viewModel.availableCalendars) { cal in
                            Text(cal.displayName).tag(cal.id)
                        }
                    }
                    .labelsHidden()
                }

                HStack {
                    Text("Work Calendar:")
                        .fontWeight(.bold)
                        .frame(width: settingsLabelWidth, alignment: .trailing)
                    Picker("", selection: $viewModel.workCalendar) {
                        Text("Select...").tag("")
                        ForEach(viewModel.availableCalendars) { cal in
                            Text(cal.displayName).tag(cal.id)
                        }
                    }
                    .labelsHidden()
                }

                HStack {
                    Text("Event Title:")
                        .fontWeight(.bold)
                        .frame(width: settingsLabelWidth, alignment: .trailing)
                    TextField("Appointment", text: $viewModel.blockingEventTitle)
                        .textFieldStyle(.roundedBorder)
                }

                HStack {
                    Text("Blocking Hours:")
                        .fontWeight(.bold)
                        .frame(width: settingsLabelWidth, alignment: .trailing)
                    Picker("Start", selection: $viewModel.blockingStartHour) {
                        ForEach(hourOptions, id: \.self) { hour in
                            Text(formatHour(hour)).tag(hour)
                        }
                    }
                    .frame(width: 120)
                    Text("to")
                    Picker("End", selection: $viewModel.blockingEndHour) {
                        ForEach(hourOptions, id: \.self) { hour in
                            Text(formatHour(hour)).tag(hour)
                        }
                    }
                    .frame(width: 120)
                }

                HStack {
                    Text("Blocking Days:")
                        .fontWeight(.bold)
                        .frame(width: settingsLabelWidth, alignment: .trailing)
                    Picker("", selection: $viewModel.blockingDays) {
                        Text("Weekdays Only").tag("weekdays")
                        Text("All Days").tag("all")
                    }
                    .labelsHidden()
                }
            }
            .disabled(!viewModel.blockingEnabled)
            .opacity(viewModel.blockingEnabled ? 1.0 : 0.5)
        }
    }

    private func formatHour(_ hour: Int) -> String {
        if hour == 0 { return "12 AM" }
        if hour < 12 { return "\(hour) AM" }
        if hour == 12 { return "12 PM" }
        return "\(hour - 12) PM"
    }
}

// MARK: - Story 4.4: Display Calendars Settings

struct DisplayCalendarsSection: View {
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Spacer()
                Text("Days shown in menu:")
                    .fontWeight(.bold)
                Picker("", selection: $viewModel.daysAhead) {
                    ForEach(1...14, id: \.self) { day in
                        Text("\(day)").tag(day)
                    }
                }
                .labelsHidden()
                .fixedSize()
                Spacer()
            }

            HStack {
                Spacer()
                Text("Show:")
                    .fontWeight(.bold)
                Picker("", selection: $viewModel.displayDayFilter) {
                    Text("All Days").tag("all")
                    Text("Weekdays Only").tag("weekdays")
                }
                .labelsHidden()
                .fixedSize()
                Spacer()
            }

            Divider()

            VStack(alignment: .leading, spacing: 8) {
                ForEach(viewModel.calendarsBySource, id: \.source) { group in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(group.source)
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundColor(.secondary)

                        ForEach(group.calendars) { calInfo in
                            if let item = viewModel.displayCalendarItems.first(where: { $0.id == calInfo.id }) {
                                DisplayCalendarRow(item: item)
                            }
                        }
                    }
                }
            }
            .padding(12)
            .background(Color.gray.opacity(0.1))
            .cornerRadius(8)
        }
    }
}

struct DisplayCalendarRow: View {
    @ObservedObject var item: DisplayCalendarItem

    var body: some View {
        HStack(spacing: 6) {
            Toggle("", isOn: $item.shown)
                .labelsHidden()
                .toggleStyle(.checkbox)

            Text(item.name)
                .frame(minWidth: 80, alignment: .leading)
                .lineLimit(1)

            if item.shown {
                Spacer()

                Image(systemName: sfSymbolName(forType: item.iconType, variant: item.iconVariant))
                    .symbolRenderingMode(.hierarchical)
                    .foregroundColor(swiftUIColor(forName: item.iconColor))
                    .font(.system(size: 18))
                    .frame(width: 22)

                Picker("", selection: $item.iconType) {
                    ForEach(iconTypes, id: \.name) { t in
                        Label {
                            Text(t.displayName)
                        } icon: {
                            Image(systemName: t.previewSymbol)
                                .symbolRenderingMode(.hierarchical)
                                .foregroundColor(.white)
                        }
                        .tag(t.name)
                    }
                }
                .labelsHidden()
                .fixedSize()
                .onChange(of: item.iconType) { newType in
                    // Reset circle variant if new icon doesn't support it
                    if let t = iconType(named: newType), !t.hasCircle {
                        item.iconVariant = ""
                    }
                }

                Picker("", selection: $item.iconColor) {
                    ForEach(allColors, id: \.name) { c in
                        Text(c.displayName).tag(c.name)
                    }
                }
                .labelsHidden()
                .fixedSize()

                ZStack {
                    if let t = iconType(named: item.iconType), t.hasCircle {
                        Toggle("Circle", isOn: Binding(
                            get: { item.iconVariant == "circle" },
                            set: { item.iconVariant = $0 ? "circle" : "" }
                        ))
                        .toggleStyle(.checkbox)
                    }
                }
                .frame(width: 70, alignment: .leading)
            }
        }
        .padding(.vertical, 1)
    }
}

// MARK: - Release Calendar Settings

struct ReleaseCalendarSection: View {
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Release Calendar:")
                    .fontWeight(.bold)
                    .frame(width: settingsLabelWidth, alignment: .trailing)
                Picker("", selection: Binding(
                    get: { viewModel.releaseCalendar },
                    set: { newVal in
                        viewModel.releaseCalendar = newVal
                        viewModel.refreshReleasePrefixes()
                    }
                )) {
                    Text("None").tag("")
                    ForEach(viewModel.availableCalendars) { cal in
                        Text(cal.displayName).tag(cal.id)
                    }
                }
                .labelsHidden()
            }

            HStack {
                Spacer().frame(width: settingsLabelWidth + 8)
                Text("Pick a team prefix to match a sprint event and show a countdown in the menu.")
                    .foregroundColor(.secondary)
            }

            if !viewModel.availableReleasePrefixes.isEmpty {
                HStack {
                    Text("Team:")
                        .fontWeight(.bold)
                        .frame(width: settingsLabelWidth, alignment: .trailing)
                    Picker("", selection: $viewModel.releaseEventPrefix) {
                        Text("None").tag("")
                        ForEach(viewModel.availableReleasePrefixes, id: \.self) { prefix in
                            Text(prefix).tag(prefix)
                        }
                    }
                    .labelsHidden()
                }
            }
        }
    }
}

// MARK: - Main Settings View

struct SettingsView: View {
    @ObservedObject var viewModel: SettingsViewModel
    @State private var selectedTab = 0

    private let tabs: [(String, String)] = [
        ("Display", "calendar"),
        ("Sync", "arrow.triangle.2.circlepath"),
        ("Blocking", "shield.lefthalf.filled"),
        ("Release", "shippingbox"),
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Custom tab bar with icons
            HStack(spacing: 2) {
                ForEach(tabs.indices, id: \.self) { index in
                    VStack(spacing: 4) {
                        Image(systemName: tabs[index].1)
                            .font(.system(size: 20))
                        Text(tabs[index].0)
                            .font(.system(size: 11))
                    }
                    .frame(width: 80, height: 50)
                    .foregroundColor(selectedTab == index ? .accentColor : .secondary)
                    .background(selectedTab == index ? Color.accentColor.opacity(0.15) : Color.clear)
                    .cornerRadius(8)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        selectedTab = index
                    }
                }
            }
            .padding(.top, 8)
            .padding(.bottom, 4)

            Divider()

            // Tab content
            switch selectedTab {
            case 0:
                VStack(alignment: .leading, spacing: 20) {
                    DisplayCalendarsSection(viewModel: viewModel)
                }
                .padding(20)
            case 1:
                VStack(alignment: .leading, spacing: 20) {
                    SyncSettingsSection(viewModel: viewModel)
                }
                .padding(20)
            case 2:
                VStack(alignment: .leading, spacing: 20) {
                    BlockingSettingsSection(viewModel: viewModel)
                }
                .padding(20)
            case 3:
                VStack(alignment: .leading, spacing: 20) {
                    ReleaseCalendarSection(viewModel: viewModel)
                }
                .padding(20)
            default:
                EmptyView()
            }
        }
        .frame(width: 600)
        .fixedSize(horizontal: false, vertical: true)
        .onChange(of: selectedTab) { _ in
            DispatchQueue.main.async {
                guard let window = NSApp.windows.first(where: { $0.title == "Display" || $0.title == "Sync" || $0.title == "Blocking" || $0.title == "Release" }) else { return }
                window.title = tabs[selectedTab].0
            }
        }
        .onReceive(viewModel.objectWillChange) { _ in
            DispatchQueue.main.async {
                viewModel.save()
            }
        }
    }
}
