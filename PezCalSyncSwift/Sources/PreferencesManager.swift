import Foundation

// MARK: - CalendarRef

struct CalendarRef: Codable, Equatable {
    var name: String
    var source: String
}

// MARK: - DisplayCalendar

struct DisplayCalendar: Codable, Equatable {
    var name: String
    var source: String
    var icon: String
}

// MARK: - Preferences

struct Preferences: Codable {
    var calendarSyncEnabled: Bool
    var calendarSyncSourceCalendar: CalendarRef?
    var calendarSyncDestination: CalendarRef?
    var calendarSyncExcludedPatterns: [String]

    var blockingEnabled: Bool
    var blockingEventTitle: String
    var blockingStartHour: Int
    var blockingEndHour: Int
    var blockingDays: String

    var personalCalendars: [CalendarRef]
    var workCalendar: CalendarRef?

    var displayCalendars: [DisplayCalendar]

    var releaseCalendar: CalendarRef?
    var releaseEventPrefix: String

    var daysAhead: Int
    var displayDayFilter: String
    var daysBack: Int

    enum CodingKeys: String, CodingKey {
        case calendarSyncEnabled = "calendar_sync_enabled"
        case calendarSyncSourceCalendar = "calendar_sync_source_calendar"
        case calendarSyncDestination = "calendar_sync_destination"
        case calendarSyncExcludedPatterns = "calendar_sync_excluded_patterns"
        case blockingEnabled = "blocking_enabled"
        case blockingEventTitle = "blocking_event_title"
        case blockingStartHour = "blocking_start_hour"
        case blockingEndHour = "blocking_end_hour"
        case blockingDays = "blocking_days"
        case personalCalendars = "personal_calendars"
        case workCalendar = "work_calendar"
        case displayCalendars = "display_calendars"
        case releaseCalendar = "release_calendar"
        case releaseEventPrefix = "release_event_prefix"
        case daysAhead = "days_ahead"
        case displayDayFilter = "display_day_filter"
        case daysBack = "days_back"
    }

    static let `default` = Preferences(
        calendarSyncEnabled: false,
        calendarSyncSourceCalendar: nil,
        calendarSyncDestination: nil,
        calendarSyncExcludedPatterns: [],
        blockingEnabled: true,
        blockingEventTitle: "Appointment",
        blockingStartHour: 8,
        blockingEndHour: 20,
        blockingDays: "weekdays",
        personalCalendars: [],
        workCalendar: nil,
        displayCalendars: [],
        releaseCalendar: nil,
        releaseEventPrefix: "",
        daysAhead: 3,
        displayDayFilter: "all",
        daysBack: 1
    )

    init(
        calendarSyncEnabled: Bool = false,
        calendarSyncSourceCalendar: CalendarRef? = nil,
        calendarSyncDestination: CalendarRef? = nil,
        calendarSyncExcludedPatterns: [String] = [],
        blockingEnabled: Bool = true,
        blockingEventTitle: String = "Appointment",
        blockingStartHour: Int = 8,
        blockingEndHour: Int = 20,
        blockingDays: String = "weekdays",
        personalCalendars: [CalendarRef] = [],
        workCalendar: CalendarRef? = nil,
        displayCalendars: [DisplayCalendar] = [],
        releaseCalendar: CalendarRef? = nil,
        releaseEventPrefix: String = "",
        daysAhead: Int = 3,
        displayDayFilter: String = "all",
        daysBack: Int = 1
    ) {
        self.calendarSyncEnabled = calendarSyncEnabled
        self.calendarSyncSourceCalendar = calendarSyncSourceCalendar
        self.calendarSyncDestination = calendarSyncDestination
        self.calendarSyncExcludedPatterns = calendarSyncExcludedPatterns
        self.blockingEnabled = blockingEnabled
        self.blockingEventTitle = blockingEventTitle
        self.blockingStartHour = blockingStartHour
        self.blockingEndHour = blockingEndHour
        self.blockingDays = blockingDays
        self.personalCalendars = personalCalendars
        self.workCalendar = workCalendar
        self.displayCalendars = displayCalendars
        self.releaseCalendar = releaseCalendar
        self.releaseEventPrefix = releaseEventPrefix
        self.daysAhead = daysAhead
        self.displayDayFilter = displayDayFilter
        self.daysBack = daysBack
    }

    init(from decoder: Decoder) throws {
        let defaults = Preferences.default
        let container = try decoder.container(keyedBy: CodingKeys.self)

        calendarSyncEnabled = (try? container.decode(Bool.self, forKey: .calendarSyncEnabled)) ?? defaults.calendarSyncEnabled
        calendarSyncSourceCalendar = try? container.decode(CalendarRef.self, forKey: .calendarSyncSourceCalendar)
        calendarSyncDestination = try? container.decode(CalendarRef.self, forKey: .calendarSyncDestination)
        calendarSyncExcludedPatterns = (try? container.decode([String].self, forKey: .calendarSyncExcludedPatterns)) ?? defaults.calendarSyncExcludedPatterns

        blockingEnabled = (try? container.decode(Bool.self, forKey: .blockingEnabled)) ?? defaults.blockingEnabled
        blockingEventTitle = (try? container.decode(String.self, forKey: .blockingEventTitle)) ?? defaults.blockingEventTitle
        blockingStartHour = (try? container.decode(Int.self, forKey: .blockingStartHour)) ?? defaults.blockingStartHour
        blockingEndHour = (try? container.decode(Int.self, forKey: .blockingEndHour)) ?? defaults.blockingEndHour
        blockingDays = (try? container.decode(String.self, forKey: .blockingDays)) ?? defaults.blockingDays

        personalCalendars = (try? container.decode([CalendarRef].self, forKey: .personalCalendars)) ?? defaults.personalCalendars
        workCalendar = try? container.decode(CalendarRef.self, forKey: .workCalendar)

        displayCalendars = (try? container.decode([DisplayCalendar].self, forKey: .displayCalendars)) ?? defaults.displayCalendars

        releaseCalendar = try? container.decode(CalendarRef.self, forKey: .releaseCalendar)
        releaseEventPrefix = (try? container.decode(String.self, forKey: .releaseEventPrefix)) ?? defaults.releaseEventPrefix

        daysAhead = (try? container.decode(Int.self, forKey: .daysAhead)) ?? defaults.daysAhead
        displayDayFilter = (try? container.decode(String.self, forKey: .displayDayFilter)) ?? defaults.displayDayFilter
        daysBack = (try? container.decode(Int.self, forKey: .daysBack)) ?? defaults.daysBack
    }
}

// MARK: - PreferencesManager

final class PreferencesManager {
    static let shared = PreferencesManager()

    private static let preferencesDirectory: URL = {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        return appSupport.appendingPathComponent("CalendarSync")
    }()

    private static let preferencesFileURL: URL = {
        preferencesDirectory.appendingPathComponent("preferences.json")
    }()

    private(set) var preferences: Preferences = .default

    private init() {}

    /// Saves the given preferences to disk, creating the directory if needed.
    /// Updates the in-memory `preferences` property before writing.
    func save(_ newPreferences: Preferences) {
        preferences = newPreferences
        let fileURL = Self.preferencesFileURL
        let dirURL = Self.preferencesDirectory

        do {
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(preferences)
            try data.write(to: fileURL, options: .atomic)
            NSLog("PreferencesManager: saved preferences to %@", fileURL.path)
        } catch {
            NSLog("PreferencesManager: failed to save preferences – %@", error.localizedDescription)
        }
    }

    /// Loads preferences from disk. Returns the loaded preferences, falling
    /// back to defaults when the file is missing or contains invalid JSON.
    @discardableResult
    func load() -> Preferences {
        let fileURL = Self.preferencesFileURL

        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            NSLog("PreferencesManager: preferences file not found at %@, using defaults", fileURL.path)
            preferences = .default
            return preferences
        }

        do {
            let data = try Data(contentsOf: fileURL)
            let decoded = try JSONDecoder().decode(Preferences.self, from: data)
            preferences = decoded
            NSLog("PreferencesManager: loaded preferences from %@", fileURL.path)
        } catch {
            NSLog("PreferencesManager: failed to read preferences – %@, using defaults", error.localizedDescription)
            preferences = .default
        }

        return preferences
    }
}
