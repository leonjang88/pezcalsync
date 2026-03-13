import Foundation

/// Story 5.3: Reads event mapping files to determine sync status.
final class MappingManager {
    static let shared = MappingManager()

    private static let mappingDirectory: URL = {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        return appSupport.appendingPathComponent("CalendarSync")
    }()

    private static let eventMappingURL: URL = {
        mappingDirectory.appendingPathComponent("event_mapping.json")
    }()

    private static let personalBlockMappingURL: URL = {
        mappingDirectory.appendingPathComponent("personal_block_mapping.json")
    }()

    /// Apple event ID -> Google event ID
    private(set) var eventMapping: [String: String] = [:]

    /// Personal event ID -> Blocking event ID
    private(set) var personalBlockMapping: [String: String] = [:]

    private init() {
        reload()
    }

    /// Reloads both mapping files from disk.
    func reload() {
        eventMapping = Self.loadMapping(from: Self.eventMappingURL, label: "event_mapping")
        personalBlockMapping = Self.loadMapping(from: Self.personalBlockMappingURL, label: "personal_block_mapping")
    }

    /// Returns true if the given Apple event ID exists as a key in event_mapping.json.
    func isSynced(appleEventId: String) -> Bool {
        return eventMapping[appleEventId] != nil
    }

    // MARK: - Private

    private static func loadMapping(from url: URL, label: String) -> [String: String] {
        guard FileManager.default.fileExists(atPath: url.path) else {
            NSLog("[MappingManager] %@ file not found at %@", label, url.path)
            return [:]
        }

        do {
            let data = try Data(contentsOf: url)
            let dict = try JSONDecoder().decode([String: String].self, from: data)
            NSLog("[MappingManager] Loaded %d entries from %@", dict.count, label)
            return dict
        } catch {
            NSLog("[MappingManager] Failed to read %@ – %@", label, error.localizedDescription)
            return [:]
        }
    }
}
