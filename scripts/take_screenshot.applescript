a-- take_screenshot.applescript
-- Captures ALL windows of one or more named applications and saves them to the
-- latest SuperWhisper recording folder. Trigger from BetterTouchTool at any
-- point during a meeting – run it multiple times as participants join.
--
-- Usage (one app):
--   osascript scripts/take_screenshot.applescript "Microsoft Teams"
--
-- Usage (several apps at once):
--   osascript scripts/take_screenshot.applescript "Microsoft Teams" "Calendar"
--
-- No arguments → captures every window of the currently frontmost app.

on run argv
	-- ── 1. Resolve the recordings folder ──────────────────────────────────
	set recordingsFolder to (POSIX path of (path to home folder)) & "Documents/superwhisper/recordings"

	-- ── 2. Find the latest recording sub-folder ────────────────────────────
	-- SuperWhisper names folders as ISO-8601 timestamps → alphabetical = chronological
	set latestFolder to getLatestFolder(recordingsFolder)

	if latestFolder is "" then
		display notification "No recording folder found – is SuperWhisper running?" with title "Screenshot"
		return
	end if

	-- ── 3. Build a shared timestamp for this batch ────────────────────────
	set ts to do shell script "date +%Y%m%d_%H%M%S"

	-- ── 4. Build the list of target apps ──────────────────────────────────
	set appList to {}
	if (count of argv) = 0 then
		-- Default: frontmost application
		tell application "System Events"
			set frontAppName to name of first process whose frontmost is true
		end tell
		set appList to {frontAppName}
	else
		set appList to argv
	end if

	-- ── 5. Capture all windows of every target app ────────────────────────
	set totalSaved to 0

	repeat with appName in appList
		set savedCount to captureAllWindows(appName, latestFolder, ts)
		set totalSaved to totalSaved + savedCount
	end repeat

	-- ── 6. Notify ─────────────────────────────────────────────────────────
	set folderName to do shell script "basename " & quoted form of latestFolder
	if totalSaved > 0 then
		display notification "Saved " & totalSaved & " screenshot(s) to " & folderName with title "Meeting Screenshot ✓"
	else
		display notification "No windows found for the requested app(s)" with title "Screenshot ✗"
	end if
end run

-- ── Helper: capture every window of a named app ───────────────────────────
-- Returns the number of screenshots successfully saved.
on captureAllWindows(appName, latestFolder, ts)
	set savedCount to 0

	-- Sanitise app name for use in a filename (spaces → underscores)
	set safeAppName to do shell script "echo " & quoted form of appName & " | tr ' ' '_'"

	try
		-- Collect the CGWindowID of every window the app currently has open
		tell application appName
			set winIDs to id of every window
		end tell

		if (count of winIDs) is 0 then
			return 0
		end if

		repeat with i from 1 to count of winIDs
			set winID to item i of winIDs
			set outputPath to latestFolder & "/screenshot_" & ts & "_" & safeAppName & "_win" & i & ".png"

			try
				-- screencapture -l captures exactly the window with that CGWindowID,
				-- even if it is behind other windows.
				do shell script "screencapture -l " & winID & " " & quoted form of outputPath

				set fileExists to (do shell script "[ -s " & quoted form of outputPath & " ] && echo yes || echo no")
				if fileExists is "yes" then
					set savedCount to savedCount + 1
				else
					-- Empty file means the window ID was not renderable; clean up
					do shell script "rm -f " & quoted form of outputPath
				end if
			on error
				do shell script "rm -f " & quoted form of outputPath
			end try
		end repeat

	on error errMsg
		-- App not running or has no scriptable windows – skip silently
		log "Could not capture windows of " & appName & ": " & errMsg
	end try

	return savedCount
end captureAllWindows

-- ── Helper: find latest sub-folder ────────────────────────────────────────
on getLatestFolder(parentPath)
	try
		set result to do shell script ¬
			"ls -1d " & quoted form of parentPath & "/*/ 2>/dev/null | sort -r | head -1 | tr -d '\\n'"
		return result
	on error
		return ""
	end try
end getLatestFolder
