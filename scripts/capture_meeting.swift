#!/usr/bin/env swift
// capture_meeting.swift
// Takes occlusion-proof screenshots of every window belonging to the given
// app(s) and saves them to the latest SuperWhisper recording folder.
//
// Usage:
//   swift scripts/capture_meeting.swift "Microsoft Teams"
//   swift scripts/capture_meeting.swift "Microsoft Teams" "Calendar"
//   swift scripts/capture_meeting.swift --list
//
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

struct WinInfo { let id: CGWindowID; let owner: String }

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
        return WinInfo(id: wid, owner: owner)
    }
}

func matchingWindowIDs(appName: String, in windows: [WinInfo]) -> [CGWindowID] {
    windows.filter { $0.owner.lowercased().contains(appName.lowercased()) }.map { $0.id }
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
        print("Visible app windows (pass any substring as argument):")
        for (owner, ws) in grouped {
            print("  \(owner)  (\(ws.count) window\(ws.count == 1 ? "" : "s"))")
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

let appNames: [String]
if rawArgs.isEmpty {
    let (_, front) = shellRun("/usr/bin/osascript", [
        "-e", "tell application \"System Events\" to get name of first process whose frontmost is true"
    ])
    appNames = front.isEmpty ? [] : [front]
    logInfo("No app specified – using frontmost: \(front)")
} else {
    appNames = rawArgs
}

// MARK: - Capture

let allWins = allNormalWindows()
logInfo("Total visible windows: \(allWins.count)")

let timestamp  = shellRun("/bin/date", ["+%Y%m%d_%H%M%S"]).output
var savedCount = 0

for appName in appNames {
    let safeApp = appName.replacingOccurrences(of: " ", with: "_")
    let ids     = matchingWindowIDs(appName: appName, in: allWins)

    if ids.isEmpty {
        logInfo("No windows for '\(appName)' – run with --list to see available names")
        continue
    }
    logInfo("Found \(ids.count) window(s) for '\(appName)'")

    for (i, wid) in ids.enumerated() {
        let outPath = "\(folder)/screenshot_\(timestamp)_\(safeApp)_win\(i + 1).png"
        // -l captures the window's own compositor buffer, occlusion-proof
        let (status, _) = shellRun("/usr/sbin/screencapture", ["-l", String(wid), outPath])
        if status == 0 && isValidCapture(at: outPath) {
            savedCount += 1
            logInfo("Saved: \(URL(fileURLWithPath: outPath).lastPathComponent)")
        } else {
            logInfo("screencapture failed for window \(wid) (exit \(status))")
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
