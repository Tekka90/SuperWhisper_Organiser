#!/usr/bin/env swift
// capture_meeting.swift
// Takes occlusion-proof screenshots of every window belonging to the given
// app(s) and saves them to the latest SuperWhisper recording folder.
//
// Usage:
//   swift scripts/capture_meeting.swift "Microsoft Teams"
//   swift scripts/capture_meeting.swift "Microsoft Teams" "Calendar"
//   swift scripts/capture_meeting.swift --list        ← show all visible app names
//
// No arguments → captures the frontmost application.
// Trigger from BetterTouchTool during a meeting; run as many times as needed.

import CoreGraphics
import Foundation

// MARK: - Helpers

@discardableResult
func run(_ executable: String, _ args: [String] = []) -> (status: Int32, output: String) {
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: executable)
    proc.arguments = args
    let outPipe = Pipe()
    proc.standardOutput = outPipe
    proc.standardError  = Pipe()
    try? proc.run()
    proc.waitUntilExit()
    let out = String(data: outPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return (proc.terminationStatus, out)
}

func log(_ msg: String) {
    fputs(msg + "\n", stderr)
}

func notify(title: String, message: String) {
    let safeMsg   = message.replacingOccurrences(of: "\"", with: "\\\"")
    let safeTitle = title.replacingOccurrences(of:   "\"", with: "\\\"")
    run("/usr/bin/osascript",
        ["-e", "display notification \"\(safeMsg)\" with title \"\(safeTitle)\""])
}

func fileSize(at path: String) -> Int {
    (try? FileManager.default.attributesOfItem(atPath: path)[.size] as? Int) ?? 0
}

// MARK: - CoreGraphics window enumeration

struct WinInfo { let id: CGWindowID; let owner: String; let width: Double; let height: Double }

func allNormalWindows() -> [WinInfo] {
    let opts: CGWindowListOption = [.optionAll, .excludeDesktopElements]
    guard let list = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] else {
        log("⚠️  CGWindowListCopyWindowInfo returned nil — check Screen Recording permission")
        log("   System Settings → Privacy & Security → Screen Recording → enable Terminal")
        return []
    }
    return list.compactMap { w -> WinInfo? in
        guard
            let owner  = w["kCGWindowOwnerName"] as? String,
            (w["kCGWindowLayer"] as? Int) == 0,
            let wid    = w["kCGWindowNumber"] as? CGWindowID,
            let bounds = w["kCGWindowBounds"] as? [String: Any],
            let width  = bounds["Width"]  as? Double, width  > 50,
            let height = bounds["Height"] as? Double, height > 50
        else { return nil }
        return WinInfo(id: wid, owner: owner, width: width, height: height)
    }
}

func windowIDs(for appName: String, in windows: [WinInfo]) -> [CGWindowID] {
    windows
        .filter { $0.owner.lowercased().contains(appName.lowercased()) }
        .map    { $0.id }
}

// MARK: - --list mode

let rawArgs = Array(CommandLine.arguments.dropFirst())

if rawArgs.first == "--list" {
    let wins = allNormalWindows()
    if wins.isEmpty {
        print("No windows found. Screen Recording permission may be missing.")
    } else {
        let owners = Dictionary(grouping: wins, by: { $0.owner })
            .sorted { $0.key < $1.key }
        print("Visible app windows (use exact name or substring):")
        for (owner, ws) in owners {
            print("  \(owner)  (\(ws.count) window\(ws.count == 1 ? "" : "s"))")
        }
    }
    exit(0)
}

// MARK: - Read recordings path from config.yaml

let fm   = FileManager.default
let home = fm.homeDirectoryForCurrentUser.path

// Resolve project root from script location OR cwd
let scriptArg  = CommandLine.arguments[0]
let scriptURL  = URL(fileURLWithPath: scriptArg.hasPrefix("/") ? scriptArg
                     : fm.currentDirectoryPath + "/" + scriptArg).standardized
let projectDir = scriptURL.deletingLastPathComponent().deletingLastPathComponent().path
let configURL  = URL(fileURLWithPath: "\(projectDir)/config.yaml")

var recordingsPath = "\(home)/Documents/superwhisper/recordings"

if let yaml = try? String(contentsOf: configURL, encoding: .utf8) {
    var inPaths = false
    for line in yaml.components(separatedBy: "\n") {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed == "paths:" { inPaths = true; continue }
        if inPaths {
            if trimmed.hasPrefix("recordings:") {
                let raw = trimmed
                    .dropFirst("recordings:".count)
                    .trimmingCharacters(in: .whitespaces)
                    .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
                    .replacingOccurrences(of: "~", with: home)
                recordingsPath = raw
                break
            }
            if !trimmed.isEmpty && !trimmed.hasPrefix("#")
                && !line.hasPrefix(" ") && !line.hasPrefix("\t") { break }
        }
    }
}

log("Recordings path: \(recordingsPath)")

// MARK: - Find latest recording folder

guard let dirContents = try? fm.contentsOfDirectory(
    at: URL(fileURLWithPath: recordingsPath),
    includingPropertiesForKeys: [.isDirectoryKey],
    options: .skipsHiddenFiles
) else {
    notify(title: "Screenshot ✗", message: "Cannot read recordings folder")
    log("❌ Cannot read recordings folder: \(recordingsPath)")
    exit(1)
}

let latestFolder = dirContents
    .filter { (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true }
    .map    { $0.path }
    .sorted(by: >)
    .first

guard let folder = latestFolder else {
    notify(title: "Screenshot ✗", message: "No recording folder found – is SuperWhisper running?")
    log("❌ No sub-folders found in \(recordingsPath)")
    exit(1)
}

log("Target folder: \(URL(fileURLWithPath: folder).lastPathComponent)")

// MARK: - Resolve target app names

let appNames: [String]
if rawArgs.isEmpty {
    let (_, front) = run("/usr/bin/osascript", [
        "-e", "tell application \"System Events\" to get name of first process whose frontmost is true"
    ])
    appNames = front.isEmpty ? [] : [front]
    log("No app specified – using frontmost: \(front)")
} else {
    appNames = rawArgs
}

// MARK: - Capture

let allWins = allNormalWindows()
log("Total visible windows found: \(allWins.count)")

let ts     = run("/bin/date", ["+%Y%m%d_%H%M%S"]).output
var nSaved = 0

for appName in appNames {
    let safeApp = appName.replacingOccurrences(of: " ", with: "_")
    let ids     = windowIDs(for: appName, in: allWins)

    if ids.isEmpty {
        log("⚠️  No windows found for '\(appName)'")
        log("   Run with --list to see available app names")
        continue
    }

    log("Found \(ids.count) window(s) for '\(appName)'")

    for (i, wid) in ids.enumerated() {
        let outPath = "\(folder)/screenshot_\(ts)_\(safeApp)_win\(i + 1).png"
        let (status, _) = run("/usr/sbin/screencapture", ["-l", String(wid), outPath])
        if status == 0 && fileSize(at: outPath) > 0 {
            nSaved += 1
            log("✓ Saved: \(URL(fileURLWithPath: outPath).lastPathComponent)")
        } else {
            log("✗ screencapture failed for window \(wid) (status \(status))")
            try? fm.removeItem(atPath: outPath)
        }
    }
}

// MARK: - Notify

let folderName = URL(fileURLWithPath: folder).lastPathComponent
if nSaved > 0 {
    notify(title: "Meeting Screenshot ✓", message: "Saved \(nSaved) screenshot(s) to \(folderName)")
} else {
    notify(title: "Screenshot ✗", message: "No windows captured – run with --list to debug")
}

// Takes occlusion-proof screenshots of every window belonging to the given
// app(s) and saves them to the latest SuperWhisper recording folder.
//
// Usage:
//   swift scripts/capture_meeting.swift "Microsoft Teams"
//   swift scripts/capture_meeting.swift "Microsoft Teams" "Calendar"
//
// No arguments → captures the frontmost application.
// Trigger from BetterTouchTool during a meeting; run as many times as needed.

import CoreGraphics
import Foundation

// MARK: - Helpers

/// Run an executable with arguments; returns exit status + stdout.
@discardableResult
func run(_ executable: String, _ args: [String] = []) -> (status: Int32, output: String) {
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: executable)
    proc.arguments = args
    let outPipe = Pipe()
    proc.standardOutput = outPipe
    proc.standardError  = Pipe()
    try? proc.run()
    proc.waitUntilExit()
    let out = String(data: outPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return (proc.terminationStatus, out)
}

func notify(title: String, message: String) {
    // Single-quotes inside the message are safe; escape double-quotes.
    let safeMsg   = message.replacingOccurrences(of: "\"", with: "\\\"")
    let safeTitle = title.replacingOccurrences(of:   "\"", with: "\\\"")
    run("/usr/bin/osascript",
        ["-e", "display notification \"\(safeMsg)\" with title \"\(safeTitle)\""])
}

func fileSize(at path: String) -> Int {
    (try? FileManager.default.attributesOfItem(atPath: path)[.size] as? Int) ?? 0
}

// MARK: - Read recordings path from config.yaml

let home       = FileManager.default.homeDirectoryForCurrentUser.path
let scriptURL  = URL(fileURLWithPath: CommandLine.arguments[0]).standardized
let projectDir = scriptURL.deletingLastPathComponent()   // scripts/
                          .deletingLastPathComponent()   // project root
                          .path
let configURL  = URL(fileURLWithPath: "\(projectDir)/config.yaml")

var recordingsPath = "\(home)/Documents/superwhisper/recordings"

if let yaml = try? String(contentsOf: configURL, encoding: .utf8) {
    var inPaths = false
    for line in yaml.components(separatedBy: "\n") {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed == "paths:" { inPaths = true; continue }
        if inPaths {
            if trimmed.hasPrefix("recordings:") {
                let raw = trimmed
                    .dropFirst("recordings:".count)
                    .trimmingCharacters(in: .whitespaces)
                    .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
                    .replacingOccurrences(of: "~", with: home)
                recordingsPath = raw
                break
            }
            // Left the paths block (next top-level key)
            if !trimmed.isEmpty && !trimmed.hasPrefix("#")
                && !line.hasPrefix(" ") && !line.hasPrefix("\t") { break }
        }
    }
}

// MARK: - Find latest recording folder

let fm = FileManager.default

guard let dirContents = try? fm.contentsOfDirectory(
    at: URL(fileURLWithPath: recordingsPath),
    includingPropertiesForKeys: [.isDirectoryKey],
    options: .skipsHiddenFiles
) else {
    notify(title: "Screenshot ✗", message: "Cannot read recordings folder")
    exit(1)
}

let latestFolder = dirContents
    .filter { (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true }
    .map    { $0.path }
    .sorted(by: >)   // ISO-8601 folder names → reverse alpha = most recent first
    .first

guard let folder = latestFolder else {
    notify(title: "Screenshot ✗", message: "No recording folder found – is SuperWhisper running?")
    exit(1)
}

// MARK: - Resolve target app names

let appArgs  = Array(CommandLine.arguments.dropFirst())
let appNames: [String]

if appArgs.isEmpty {
    let (_, front) = run("/usr/bin/osascript", [
        "-e", "tell application \"System Events\" to get name of first process whose frontmost is true"
    ])
    appNames = front.isEmpty ? [] : [front]
} else {
    appNames = appArgs
}

// MARK: - CoreGraphics window enumeration

/// Returns CGWindowIDs for all visible, normal-layer windows whose owner name
/// contains `appName` (case-insensitive).  Works for any app including Electron.
func windowIDs(for appName: String) -> [CGWindowID] {
    let opts: CGWindowListOption = [.optionAll, .excludeDesktopElements]
    guard let list = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]]
    else { return [] }

    return list.compactMap { w -> CGWindowID? in
        guard
            let owner  = w["kCGWindowOwnerName"] as? String,
            owner.lowercased().contains(appName.lowercased()),
            (w["kCGWindowLayer"] as? Int) == 0,          // normal window layer
            let wid    = w["kCGWindowNumber"] as? CGWindowID,
            let bounds = w["kCGWindowBounds"] as? [String: Any],
            let width  = bounds["Width"]  as? Double, width  > 50,
            let height = bounds["Height"] as? Double, height > 50
        else { return nil }
        return wid
    }
}

// MARK: - Capture

let ts      = run("/bin/date", ["+%Y%m%d_%H%M%S"]).output
var nSaved  = 0

for appName in appNames {
    let safeApp = appName.replacingOccurrences(of: " ", with: "_")
    let ids     = windowIDs(for: appName)

    if ids.isEmpty {
        print("No windows found for '\(appName)'")
        continue
    }

    for (i, wid) in ids.enumerated() {
        let outPath = "\(folder)/screenshot_\(ts)_\(safeApp)_win\(i + 1).png"
        // screencapture -l reads the window's own compositor buffer → occlusion-proof
        let (status, _) = run("/usr/sbin/screencapture", ["-l", String(wid), outPath])
        if status == 0 && fileSize(at: outPath) > 0 {
            nSaved += 1
            print("Saved: \(URL(fileURLWithPath: outPath).lastPathComponent)")
        } else {
            try? fm.removeItem(atPath: outPath)
        }
    }
}

// MARK: - Notify

let folderName = URL(fileURLWithPath: folder).lastPathComponent
if nSaved > 0 {
    notify(title: "Meeting Screenshot ✓", message: "Saved \(nSaved) screenshot(s) to \(folderName)")
} else {
    notify(title: "Screenshot ✗", message: "No windows captured for the requested app(s)")
}
