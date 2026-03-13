import Foundation

// MARK: - SyncStatus

enum SyncStatus {
    case idle
    case syncing
    case success
    case failed
}

// MARK: - SyncManager (Stories 3.1 & 3.4)

final class SyncManager {
    static let shared = SyncManager()

    private(set) var isSyncing: Bool = false
    private(set) var lastSyncTime: Date?
    private(set) var lastSyncStatus: SyncStatus = .idle

    /// Called on the main thread when a sync run finishes.
    var onSyncComplete: ((SyncStatus) -> Void)?

    /// Minimum interval between syncs (Story 3.3 throttle).
    private let minimumSyncInterval: TimeInterval = 30

    /// Periodic sync timer (Story 3.4).
    private var periodicTimer: Timer?
    private let periodicInterval: TimeInterval = 30 * 60  // 30 minutes

    /// Scripts directory. Tries bundle Resources first, falls back to dev path.
    private var scriptDirectory: String {
        if let resourcePath = Bundle.main.resourcePath {
            let bundled = "\(resourcePath)/scripts"
            if FileManager.default.fileExists(atPath: bundled) {
                return bundled
            }
        }
        return "/Users/leonjang/calendar-tool/src"
    }

    private init() {}

    // MARK: - Python Location

    private func locatePython() -> String {
        // Check for bundled Python in app bundle
        if let resourcePath = Bundle.main.resourcePath {
            let bundledPython = "\(resourcePath)/python/bin/python3"
            if FileManager.default.fileExists(atPath: bundledPython) {
                return bundledPython
            }
        }
        // Dev venv
        let venvPython = "/Users/leonjang/calendar-tool/venv/bin/python3"
        if FileManager.default.fileExists(atPath: venvPython) {
            return venvPython
        }
        return "/usr/bin/python3"
    }

    // MARK: - Run Sync (Story 3.1)

    func runSync() {
        guard PreferencesManager.shared.preferences.calendarSyncEnabled else {
            NSLog("[SyncManager] Calendar sync is disabled, skipping.")
            return
        }
        guard !isSyncing else {
            NSLog("[SyncManager] Sync already in progress, skipping.")
            return
        }

        isSyncing = true
        lastSyncStatus = .syncing

        // Notify UI immediately so menu can update
        DispatchQueue.main.async {
            self.onSyncComplete?(.syncing)
        }

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }

            let pythonPath = self.locatePython()
            NSLog("[SyncManager] Using Python at: %@", pythonPath)

            // Script 1: calendar_sync_eventkit.py (always runs)
            let script1 = "\(self.scriptDirectory)/calendar_sync_eventkit.py"
            let result1 = self.runScript(pythonPath: pythonPath, scriptPath: script1)

            if !result1 {
                NSLog("[SyncManager] calendar_sync_eventkit.py failed.")
                self.finishSync(status: .failed)
                return
            }

            NSLog("[SyncManager] Sync completed successfully.")
            self.finishSync(status: .success)
        }
    }

    /// Runs a single Python script. Returns true on success (exit code 0).
    private func runScript(pythonPath: String, scriptPath: String) -> Bool {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [scriptPath]
        process.currentDirectoryURL = URL(fileURLWithPath: scriptDirectory)

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        do {
            try process.run()
        } catch {
            NSLog("[SyncManager] Failed to launch %@: %@", scriptPath, error.localizedDescription)
            return false
        }

        // Timeout: terminate after 30 seconds
        let timeoutItem = DispatchWorkItem {
            if process.isRunning {
                NSLog("[SyncManager] Script timed out after 30s: %@", scriptPath)
                process.terminate()
            }
        }
        DispatchQueue.global().asyncAfter(deadline: .now() + 30.0, execute: timeoutItem)

        process.waitUntilExit()
        timeoutItem.cancel()

        // Log output
        let stdoutData = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()

        if let stdoutStr = String(data: stdoutData, encoding: .utf8), !stdoutStr.isEmpty {
            NSLog("[SyncManager] stdout (%@): %@", scriptPath, stdoutStr)
        }
        if let stderrStr = String(data: stderrData, encoding: .utf8), !stderrStr.isEmpty {
            NSLog("[SyncManager] stderr (%@): %@", scriptPath, stderrStr)
        }

        let exitCode = process.terminationStatus
        NSLog("[SyncManager] %@ exited with code %d", scriptPath, exitCode)
        return exitCode == 0
    }

    private func finishSync(status: SyncStatus) {
        DispatchQueue.main.async {
            self.isSyncing = false
            self.lastSyncStatus = status
            if status == .success || status == .failed {
                self.lastSyncTime = Date()
            }
            self.onSyncComplete?(status)
            // Reset periodic timer after any sync (Story 3.4)
            self.resetPeriodicTimer()
        }
    }

    // MARK: - Throttled Sync (Story 3.3)

    /// Triggers a sync only if the minimum interval has elapsed since the last sync.
    func runSyncThrottled() {
        if let lastTime = lastSyncTime {
            let elapsed = Date().timeIntervalSince(lastTime)
            if elapsed < minimumSyncInterval {
                NSLog("[SyncManager] Throttled: only %.0fs since last sync (min %0.fs).", elapsed, minimumSyncInterval)
                return
            }
        }
        runSync()
    }

    // MARK: - Periodic Timer (Story 3.4)

    /// Starts the periodic background sync timer. Call once at launch.
    func startPeriodicTimer() {
        resetPeriodicTimer()
    }

    /// Invalidates and recreates the periodic timer.
    private func resetPeriodicTimer() {
        periodicTimer?.invalidate()
        periodicTimer = Timer.scheduledTimer(withTimeInterval: periodicInterval, repeats: true) { [weak self] _ in
            NSLog("[SyncManager] Periodic sync timer fired.")
            self?.runSync()
        }
    }

    // MARK: - Relative Time Formatting

    /// Returns a human-readable relative time string, e.g. "2 min ago", "Just now".
    static func relativeTimeString(from date: Date) -> String {
        let elapsed = Int(Date().timeIntervalSince(date))
        if elapsed < 60 {
            return "Just now"
        } else if elapsed < 3600 {
            let mins = elapsed / 60
            return "\(mins) min ago"
        } else if elapsed < 86400 {
            let hours = elapsed / 3600
            return "\(hours) hr ago"
        } else {
            let days = elapsed / 86400
            return "\(days) day\(days == 1 ? "" : "s") ago"
        }
    }
}
