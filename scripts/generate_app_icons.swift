import Cocoa
import CoreGraphics

func renderLogoPng(size: Int, outputPath: String) {
    let cgSize = CGSize(width: size, height: size)
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    guard let ctx = CGContext(
        data: nil,
        width: size,
        height: size,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { return }

    let nsCtx = NSGraphicsContext(cgContext: ctx, flipped: true)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = nsCtx

    let scale = CGFloat(size) / 128.0
    ctx.scaleBy(x: scale, y: scale)

    // 1. Squircle background with deep blue gradient
    let bgPath = NSBezierPath(roundedRect: NSRect(x: 6, y: 6, width: 116, height: 116), xRadius: 28, yRadius: 28)
    let gradColors = [
        NSColor(calibratedRed: 0.145, green: 0.388, blue: 0.922, alpha: 1.0),
        NSColor(calibratedRed: 0.114, green: 0.306, blue: 0.847, alpha: 1.0),
        NSColor(calibratedRed: 0.059, green: 0.090, blue: 0.165, alpha: 1.0)
    ]
    let bgGrad = NSGradient(colors: gradColors)!
    bgGrad.draw(in: bgPath, angle: 45)

    // 2. Left white page
    let leftPage = NSBezierPath(roundedRect: NSRect(x: 24, y: 32, width: 38, height: 58), xRadius: 6, yRadius: 6)
    NSColor(calibratedWhite: 0.98, alpha: 0.96).setFill()
    leftPage.fill()

    // 3. Right sky-cyan page
    let rightPage = NSBezierPath(roundedRect: NSRect(x: 66, y: 32, width: 38, height: 58), xRadius: 6, yRadius: 6)
    NSColor(calibratedRed: 0.22, green: 0.74, blue: 0.97, alpha: 0.94).setFill()
    rightPage.fill()

    // 4. Letter 'A' on left page
    let attrs: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 30, weight: .heavy),
        .foregroundColor: NSColor(calibratedRed: 0.118, green: 0.227, blue: 0.541, alpha: 1.0)
    ]
    ("A" as NSString).draw(at: NSPoint(x: 32, y: 43), withAttributes: attrs)

    // 5. Semantic bars on right page
    NSColor(calibratedRed: 0.059, green: 0.090, blue: 0.165, alpha: 0.85).setFill()
    NSBezierPath(roundedRect: NSRect(x: 73, y: 46, width: 22, height: 5), xRadius: 2.5, yRadius: 2.5).fill()
    NSBezierPath(roundedRect: NSRect(x: 73, y: 58, width: 16, height: 5), xRadius: 2.5, yRadius: 2.5).fill()
    NSBezierPath(roundedRect: NSRect(x: 73, y: 70, width: 20, height: 5), xRadius: 2.5, yRadius: 2.5).fill()

    // 6. Gold/Cyan AI Spark
    NSColor(calibratedRed: 0.99, green: 0.88, blue: 0.28, alpha: 1.0).setFill()
    let spark = NSBezierPath(ovalIn: NSRect(x: 92, y: 18, width: 12, height: 12))
    spark.fill()

    NSGraphicsContext.restoreGraphicsState()

    guard let cgImg = ctx.makeImage() else { return }
    let rep = NSBitmapImageRep(cgImage: cgImg)
    if let pngData = rep.representation(using: .png, properties: [:]) {
        try? pngData.write(to: URL(fileURLWithPath: outputPath))
    }
}

let args = CommandLine.arguments
if args.count >= 3, let sz = Int(args[1]) {
    renderLogoPng(size: sz, outputPath: args[2])
}
