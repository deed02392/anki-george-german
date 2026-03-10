import AppKit

guard CommandLine.arguments.count > 1 else {
    print("Usage: generate-icon <output-directory>")
    exit(1)
}

let outputDir = CommandLine.arguments[1]

// Icon sizes required for .iconset (name, pixel size)
let iconEntries: [(String, Int)] = [
    ("icon_16x16", 16),
    ("icon_16x16@2x", 32),
    ("icon_32x32", 32),
    ("icon_32x32@2x", 64),
    ("icon_128x128", 128),
    ("icon_128x128@2x", 256),
    ("icon_256x256", 256),
    ("icon_256x256@2x", 512),
    ("icon_512x512", 512),
    ("icon_512x512@2x", 1024),
]

func renderIcon(px: Int) -> Data? {
    let s = CGFloat(px)
    let image = NSImage(size: NSSize(width: s, height: s))
    image.lockFocus()

    // Purple rounded-rectangle background (#6c3483)
    let inset = s * 0.05
    let radius = s * 0.22
    let bgRect = NSRect(x: inset, y: inset,
                        width: s - 2 * inset, height: s - 2 * inset)
    let bgPath = NSBezierPath(roundedRect: bgRect,
                              xRadius: radius, yRadius: radius)
    NSColor(red: 0.424, green: 0.204, blue: 0.514, alpha: 1.0).setFill()
    bgPath.fill()

    // White "DE" text (skip for tiny sizes)
    if px >= 32 {
        let fontSize = s * 0.42
        let font = NSFont.systemFont(ofSize: fontSize, weight: .heavy)
        let attrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.white,
        ]
        let text = "DE" as NSString
        let textSize = text.size(withAttributes: attrs)
        text.draw(at: NSPoint(
            x: (s - textSize.width) / 2,
            y: (s - textSize.height) / 2
        ), withAttributes: attrs)
    }

    image.unlockFocus()

    guard let tiff = image.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let png = rep.representation(using: .png, properties: [:]) else {
        return nil
    }
    return png
}

// Create .iconset directory
let iconsetPath = "\(outputDir)/AppIcon.iconset"
let fm = FileManager.default
try? fm.createDirectory(atPath: iconsetPath, withIntermediateDirectories: true)

for (name, px) in iconEntries {
    guard let data = renderIcon(px: px) else { continue }
    try? data.write(to: URL(fileURLWithPath: "\(iconsetPath)/\(name).png"))
}

// Convert .iconset → .icns
let iconutil = Process()
iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
iconutil.arguments = ["-c", "icns", iconsetPath,
                      "-o", "\(outputDir)/AppIcon.icns"]
try iconutil.run()
iconutil.waitUntilExit()

// Clean up .iconset
try? fm.removeItem(atPath: iconsetPath)

exit(iconutil.terminationStatus)
