import AppKit
import Foundation

// MARK: - Argument parsing
// Usage: unsuspend-agent --uv PATH --project PATH --max N

var uvPath = ""
var projectPath = ""
var maxCards = "5"

let cliArgs = CommandLine.arguments
var i = 1
while i < cliArgs.count {
    switch cliArgs[i] {
    case "--uv":      i += 1; uvPath = cliArgs[i]
    case "--project": i += 1; projectPath = cliArgs[i]
    case "--max":     i += 1; maxCards = cliArgs[i]
    default: break
    }
    i += 1
}

guard !uvPath.isEmpty, !projectPath.isEmpty else {
    print("ERROR: --uv and --project are required")
    exit(1)
}

// MARK: - Helpers

let dateFmt = DateFormatter()
dateFmt.dateFormat = "yyyy-MM-dd HH:mm:ss"

func log(_ msg: String) {
    print(msg)
    fflush(stdout)
}

func ankiIsRunning() -> Bool {
    !NSRunningApplication.runningApplications(
        withBundleIdentifier: "net.ankiweb.launcher"
    ).isEmpty
}

func waitForAnkiConnect(timeout: Int = 30) -> Bool {
    let body = #"{"action":"version","version":6}"#.data(using: .utf8)
    for _ in 0..<timeout {
        let sem = DispatchSemaphore(value: 0)
        var ok = false
        var req = URLRequest(
            url: URL(string: "http://localhost:8765")!,
            timeoutInterval: 2
        )
        req.httpMethod = "POST"
        req.httpBody = body
        URLSession.shared.dataTask(with: req) { _, resp, err in
            if err == nil,
               let http = resp as? HTTPURLResponse,
               http.statusCode == 200 {
                ok = true
            }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 3)
        if ok { return true }
        Thread.sleep(forTimeInterval: 1)
    }
    return false
}

// MARK: - Main

log("=== \(dateFmt.string(from: Date())) ===")

let wasRunning = ankiIsRunning()

if !wasRunning {
    log("Launching Anki (background)...")
    let open = Process()
    open.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    open.arguments = ["-g", "-j", "-a", "Anki"]
    try? open.run()
    open.waitUntilExit()
}

guard waitForAnkiConnect() else {
    log("ERROR: AnkiConnect not responding after 30s")
    exit(1)
}

// Hide Anki if we launched it — NSRunningApplication needs no Accessibility
if !wasRunning {
    for app in NSRunningApplication.runningApplications(
        withBundleIdentifier: "net.ankiweb.launcher"
    ) {
        app.hide()
    }
    log("Launched Anki (hidden)")
}

// Run unsuspend
let proc = Process()
proc.executableURL = URL(fileURLWithPath: uvPath)
proc.arguments = ["run", "anki-german", "unsuspend", "--apply", "--max", maxCards]
proc.currentDirectoryURL = URL(fileURLWithPath: projectPath)

do {
    try proc.run()
    proc.waitUntilExit()
} catch {
    log("ERROR: Failed to run unsuspend: \(error)")
    exit(1)
}

if proc.terminationStatus != 0 {
    log("ERROR: unsuspend exited with status \(proc.terminationStatus)")
    exit(1)
}

log("--- done ---")
