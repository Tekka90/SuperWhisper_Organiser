#!/usr/bin/env swift
// capture_meeting.swift
// Takes occlusion-proof screenshots of every window belonging to the given
// app(s) and saves them to the latest SuperWhisper recording folder.
//
// Usage:
//   swift scripts/capture_meeting.swift "Microsoft Teams"
//   swift scripts/capture_meeting.swift "Microsoft Teams" "Outlook/Calendar"
//   swift scripts/capture_meeting.swift --list
//
// App arguments can be plain app names or "App/WindowPattern" — the latter
// only captures windows of that app whose title contains the given pattern.
// No arguments -> captures the frontmost application.

import CoreGraphics
import Foundation

// MARK: - Helpers

@discardableResult
func shellRun(_ executable: String, _ args: [String] = []) -> (status: Int32, output: String) {
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: executable)
    proc.arguments = args
    let pipe = Pipe()
    proc.standardOutput = pipe
    proc.standardError  = Pipe()
    try? proc.run()
    proc.waitUntilExit()
    let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return (proc.terminationStatus, out)
}

func logInfo(_ msg: String) { fputs(msg + "\n", stderr) }

func sendNotification(title: String, message: String) {
    let m = message.replacingOccurrences(of: "\"", with: "\\\"")
    let t = title.replacingOccurrences(of:   "\"", with: "\\\"")
    shellRun("/usr/bin/osascript", ["-e",
        "display notification \"\(m)\" with title \"\(t)\""])
}

func isValidCapture(at path: String) -> Bool {
    ((try? FileManager.default.attributesOfItem(atPath: path)[.size] as? Int) ?? 0) > 0
}

// MARK: - CoreGraphics window enumeration

struct WinInfo { let id: CGWindowID; let owner: String; let name: String }

func allNormalWindows() -> [WinInfo] {
    let opts: CGWindowListOption = [.optionAll, .excludeDesktopElements]
    guard let list = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] else {
        logInfo("WARNING: CGWindowListCopyWindowInfo returned nil.")
        logInfo("   Grant Screen Recording permission: System Settings -> Privacy & Security -> Screen Recording")
        return []
    }
    return list.compactMap { w -> WinInfo? in
        guard
            let owner  = w["kCGWindowOwnerName"] as? String,
            (w["kCGWindowLayer"] as? Int) == 0,
            (w["kCGWindowIsOnscreen"] as? Bool) == true,
            (w["kCGWindowAlpha"]     as? Double ?? 0) > 0,
            let wid    = w["kCGWindowNumber"] as? CGWindowID,
            let bounds = w["kCGWindowBounds"] as? [String: Any],
            let width  = bounds["Width"]  as? Double, width  > 100,
            let height = bounds["Height"] as? Double, height > 100
        else { return nil }
        let name   = w["kCGWindowName"] as? String ?? ""
        return WinInfo(id: wid, owner: owner, name: name)
    }
}

// MARK: - App / window filter

struct AppFilter {
    let appPattern:    String   // matched against owner name
    let windowPattern: String?  // if set, also matched against window name
}

/// Parse "App" or "App/WindowPattern" into an AppFilter.
func parseFilter(_ arg: String) -> AppFilter {
    if let slash = arg.firstIndex(of: "/") {
        let app = String(arg[arg.startIndex ..< slash])
        let win = String(arg[arg.index(after: slash)...])
        return AppFilter(appPattern: app, windowPattern: win.isEmpty ? nil : win)
    }
    return AppFilter(appPattern: arg, windowPattern: nil)
}

/// Return all windows that match the given filter.
func matchingWindows(filter: AppFilter, in windows: [WinInfo]) -> [WinInfo] {
    windows.filter { w in
        guard w.owner.lowercased().contains(filter.appPattern.lowercased()) else { return false }
        if let wp = filter.windowPattern {
            return w.name.lowercased().contains(wp.lowercased())
        }
        return true
    }
}

/// Sanitise a string for use as a filename component (max 50 chars).
func safeFilenameComponent(_ s: String, fallback: String) -> String {
    let sanitised = s
        .replacingOccurrences(of: "/", with: "-")
        .replacingOccurrences(of: ":", with: "-")
        .map { ($0.isLetter || $0.isNumber || $0 == "-") ? $0 : Character("_") }
    let result = String(sanitised)
        .trimmingCharacters(in: CharacterSet(charactersIn: "_-"))
    return result.isEmpty ? fallback : String(result.prefix(50))
}

// MARK: - Read recordings path from config.yaml

let fm   = FileManager.default
let home = fm.homeDirectoryForCurrentUser.path

let scriptArg  = CommandLine.arguments[0]
let absScript  = scriptArg.hasPrefix("/") ? scriptArg : fm.currentDirectoryPath + "/" + scriptArg
let scriptURL  = URL(fileURLWithPath: absScript).standardized
let projectDir = scriptURL.deletingLastPathComponent().deletingLastPathComponent().path
let configPath = projectDir + "/config.yaml"

var recordingsPath = home + "/Documents/superwhisper/recordings"

if let yaml = try? String(contentsOfFile: configPath, encoding: .utf8) {
    var inPaths = false
    for line in yaml.components(separatedBy: "\n") {
        let trimmed = line.trimmingCharacters(in: CharacterSet.whitespaces)
        if trimmed == "paths:" { inPaths = true; continue }
        if inPaths {
            if trimmed.hasPrefix("recordings:") {
                var raw = String(trimmed.dropFirst("recordings:".count))
                raw = raw.trimmingCharacters(in: CharacterSet.whitespaces)
                raw = raw.trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
                raw = raw.replacingOccurrences(of: "~", with: home)
                recordingsPath = raw
                break
            }
            // Detect end of paths block (next top-level key)
            if !trimmed.isEmpty && !trimmed.hasPrefix("#")
                && !line.hasPrefix(" ") && !line.hasPrefix("\t") { break }
        }
    }
}

// MARK: - Parse arguments

let rawArgs = Array(CommandLine.arguments.dropFirst())

// --list mode: print all visible app names and exit
if rawArgs.first == "--list" {
    let wins = allNormalWindows()
    if wins.isEmpty {
        print("No windows found. Check Screen Recording permission.")
    } else {
        let grouped = Dictionary(grouping: wins, by: { $0.owner }).sorted { $0.key < $1.key }
        print("Visible app windows (pass any substring as argument, use App/Pattern to filter by window name):")
        for (owner, ws) in grouped {
            print("  \(owner)  (\(ws.count) window\(ws.count == 1 ? "" : "s"))")
            for w in ws where !w.name.isEmpty {
                print("    - \"\(w.name)\"")
            }
        }
    }
    exit(0)
}

// MARK: - Find latest recording folder

logInfo("Recordings path: \(recordingsPath)")

guard let dirContents = try? fm.contentsOfDirectory(
    at: URL(fileURLWithPath: recordingsPath),
    includingPropertiesForKeys: [URLResourceKey.isDirectoryKey],
    options: .skipsHiddenFiles
) else {
    sendNotification(title: "Screenshot Failed", message: "Cannot read recordings folder")
    logInfo("ERROR: Cannot read \(recordingsPath)")
    exit(1)
}

let latestFolder = dirContents
    .filter { url in
        (try? url.resourceValues(forKeys: [URLResourceKey.isDirectoryKey]).isDirectory) == true
    }
    .map    { $0.path }
    .sorted(by: >)  // ISO-8601 names → reverse-alpha = most recent first
    .first

guard let folder = latestFolder else {
    sendNotification(title: "Screenshot Failed", message: "No recording folder found – is SuperWhisper running?")
    logInfo("ERROR: No sub-folders in \(recordingsPath)")
    exit(1)
}

logInfo("Target folder: \(URL(fileURLWithPath: folder).lastPathComponent)")

// MARK: - Resolve target app names

let filters: [AppFilter]
if rawArgs.isEmpty {
    let (_, front) = shellRun("/usr/bin/osascript", [
        "-e", "tell application \"System Events\" to get name of first process whose frontmost is true"
    ])
    filters = front.isEmpty ? [] : [AppFilter(appPattern: front, windowPattern: nil)]
    logInfo("No app specified – using frontmost: \(front)")
} else {
    filters = rawArgs.map { parseFilter($0) }
}

// MARK: - Capture

let allWins = allNormalWindows()
logInfo("Total visible windows: \(allWins.count)")

let timestamp  = shellRun("/bin/date", ["+%Y%m%d_%H%M%S"]).output
var savedCount = 0

for filter in filters {
    let safeApp = safeFilenameComponent(filter.appPattern, fallback: "app")
    let matched = matchingWindows(filter: filter, in: allWins)

    if matched.isEmpty {
        let hint = filter.windowPattern.map { " with window pattern '\($0)'" } ?? ""
        logInfo("No windows for '\(filter.appPattern)'\(hint) – run with --list to see available names")
        continue
    }
    logInfo("Found \(matched.count) window(s) for '\(filter.appPattern)'\(filter.windowPattern.map { "/\($0)" } ?? "")")

    for (i, win) in matched.enumerated() {
        let winLabel = safeFilenameComponent(win.name, fallback: "win\(i + 1)")
        let outPath  = "\(folder)/screenshot_\(timestamp)_\(safeApp)_\(winLabel).png"
        // -l captures the window's own compositor buffer, occlusion-proof
        let (status, _) = shellRun("/usr/sbin/screencapture", ["-l", String(win.id), outPath])
        if status == 0 && isValidCapture(at: outPath) {
            savedCount += 1
            logInfo("Saved: \(URL(fileURLWithPath: outPath).lastPathComponent)")
        } else {
            logInfo("screencapture failed for window \(win.id) '\(win.name)' (exit \(status))")
            try? fm.removeItem(atPath: outPath)
        }
    }
}

// MARK: - Notify

let folderName = URL(fileURLWithPath: folder).lastPathComponent
if savedCount > 0 {
    sendNotification(title: "Meeting Screenshot OK",
                     message: "Saved \(savedCount) screenshot(s) to \(folderName)")
} else {
    sendNotification(title: "Screenshot Failed",
                     message: "No windows captured – run with --list to debug")
}
