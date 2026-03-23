#!/usr/bin/env swift
// capture_meeting.swift
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
