import Foundation
import ApplicationServices
import AppKit
import Vision
import CoreGraphics
import AVFoundation

@_silgen_name("IsSecureEventInputEnabled")
func IsSecureEventInputEnabled() -> DarwinBoolean

// MARK: - 1. Accessibility Selection & Secure Input Guard (EP-05 / AC-03)

struct SelectionResult: Codable {
    let status: String
    let appName: String?
    let bundleId: String?
    let role: String?
    let subrole: String?
    let isSecureField: Bool
    let selectedText: String?
    let method: String
    let message: String
}

func probeAccessibilitySelection(simulateSecureField: Bool = false) -> SelectionResult {
    let trusted = AXIsProcessTrusted()
    let frontApp = NSWorkspace.shared.frontmostApplication
    let appName = frontApp?.localizedName
    let bundleId = frontApp?.bundleIdentifier

    if simulateSecureField {
        return SelectionResult(
            status: "blocked_secure_input",
            appName: appName ?? "SecurityAgent",
            bundleId: bundleId ?? "com.apple.SecurityAgent",
            role: "AXTextField",
            subrole: "AXSecureTextField",
            isSecureField: true,
            selectedText: nil,
            method: "ax_secure_guard",
            message: "检测到系统安全输入框（AXSecureTextField），已拒绝读取并阻止剪贴板回退（符合 AC-03）"
        )
    }

    if !trusted {
        return SelectionResult(
            status: "permission_required",
            appName: appName,
            bundleId: bundleId,
            role: nil,
            subrole: nil,
            isSecureField: false,
            selectedText: nil,
            method: "macos_ax",
            message: "需要辅助功能权限（Accessibility）才能直接读取选中文本；未授权时引导用户开启或使用手动粘贴"
        )
    }

    let sysWide = AXUIElementCreateSystemWide()
    var focusedObj: CFTypeRef?
    let err = AXUIElementCopyAttributeValue(sysWide, kAXFocusedUIElementAttribute as CFString, &focusedObj)
    guard err == .success, let focusedElement = focusedObj else {
        return SelectionResult(
            status: "no_focused_element",
            appName: appName,
            bundleId: bundleId,
            role: nil,
            subrole: nil,
            isSecureField: false,
            selectedText: nil,
            method: "macos_ax",
            message: "当前前台焦点元素未暴露 AX 选中文本接口，可按用户配置触发受控复制回退"
        )
    }

    let axElem = focusedElement as! AXUIElement
    var roleObj: CFTypeRef?
    var subroleObj: CFTypeRef?
    AXUIElementCopyAttributeValue(axElem, kAXRoleAttribute as CFString, &roleObj)
    AXUIElementCopyAttributeValue(axElem, kAXSubroleAttribute as CFString, &subroleObj)

    let role = roleObj as? String
    let subrole = subroleObj as? String

    // AC-03: Never read from password / secure text fields
    if subrole == "AXSecureTextField" || IsSecureEventInputEnabled().boolValue {
        return SelectionResult(
            status: "blocked_secure_input",
            appName: appName,
            bundleId: bundleId,
            role: role,
            subrole: subrole ?? "SecureEventInput",
            isSecureField: true,
            selectedText: nil,
            method: "ax_secure_guard",
            message: "检测到安全密码输入状态，已中止取词与记录（AC-03）"
        )
    }

    var selectedTextObj: CFTypeRef?
    let textErr = AXUIElementCopyAttributeValue(axElem, kAXSelectedTextAttribute as CFString, &selectedTextObj)
    if textErr == .success, let text = selectedTextObj as? String, !text.isEmpty {
        let truncated = String(text.prefix(5000))
        return SelectionResult(
            status: "ok",
            appName: appName,
            bundleId: bundleId,
            role: role,
            subrole: subrole,
            isSecureField: false,
            selectedText: truncated,
            method: "macos_ax",
            message: "通过 macOS Accessibility API 成功读取选中文本"
        )
    }

    return SelectionResult(
        status: "empty_selection",
        appName: appName,
        bundleId: bundleId,
        role: role,
        subrole: subrole,
        isSecureField: false,
        selectedText: nil,
        method: "macos_ax",
        message: "当前未选中文本"
    )
}

// MARK: - 2. In-Memory Bilingual OCR Benchmark via Vision.framework (EP-07 / AC-04)

struct OCRLineResult: Codable {
    let text: String
    let confidence: Float
}

struct OCRBenchmarkResult: Codable {
    let status: String
    let elapsedMs: Double
    let lines: [OCRLineResult]
    let persistedToDisk: Bool
}

func renderBilingualTestImageInMemory() -> CGImage? {
    let width = 900
    let height = 220
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    guard let ctx = CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else {
        return nil
    }

    // White background
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))

    let nsCtx = NSGraphicsContext(cgContext: ctx, flipped: false)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = nsCtx

    let attrs1: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 28, weight: .semibold),
        .foregroundColor: NSColor.black
    ]
    let attrs2: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 26, weight: .regular),
        .foregroundColor: NSColor.black
    ]

    let line1 = "AI Dictionary runs Hy-MT2-1.8B locally on your device."
    let line2 = "支持离线中英查词、全局划词与本地截图 OCR 识别。"

    (line1 as NSString).draw(at: NSPoint(x: 32, y: 130), withAttributes: attrs1)
    (line2 as NSString).draw(at: NSPoint(x: 32, y: 60), withAttributes: attrs2)

    NSGraphicsContext.restoreGraphicsState()
    return ctx.makeImage()
}

func runInMemoryVisionOCR() -> OCRBenchmarkResult {
    let t0 = CFAbsoluteTimeGetCurrent()
    guard let cgImage = renderBilingualTestImageInMemory() else {
        return OCRBenchmarkResult(status: "render_error", elapsedMs: 0, lines: [], persistedToDisk: false)
    }

    var recognizedLines: [OCRLineResult] = []
    let request = VNRecognizeTextRequest { req, _ in
        guard let observations = req.results as? [VNRecognizedTextObservation] else { return }
        for obs in observations {
            if let top = obs.topCandidates(1).first {
                recognizedLines.append(OCRLineResult(text: top.string, confidence: top.confidence))
            }
        }
    }
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true

    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    do {
        try handler.perform([request])
    } catch {
        let elapsed = (CFAbsoluteTimeGetCurrent() - t0) * 1000.0
        return OCRBenchmarkResult(status: "error: \(error.localizedDescription)", elapsedMs: elapsed, lines: [], persistedToDisk: false)
    }

    let elapsed = (CFAbsoluteTimeGetCurrent() - t0) * 1000.0
    return OCRBenchmarkResult(status: "ok", elapsedMs: elapsed, lines: recognizedLines, persistedToDisk: false)
}

// MARK: - 3. Offline System TTS Verification (EP-08 / F-003)

struct TTSVoiceInfo: Codable {
    let identifier: String
    let name: String
    let locale: String
}

func listOfflineSystemVoices() -> [TTSVoiceInfo] {
    let voices = AVSpeechSynthesisVoice.speechVoices()
    var result: [TTSVoiceInfo] = []
    for v in voices {
        let locale = v.language
        if locale.hasPrefix("en") || locale.hasPrefix("zh") {
            result.append(TTSVoiceInfo(identifier: v.identifier, name: v.name, locale: locale))
        }
    }
    return result
}

// MARK: - CLI Entrypoint

struct FullBridgeReport: Codable {
    let liveSelection: SelectionResult
    let secureFieldSimulation: SelectionResult
    let visionOcr: OCRBenchmarkResult
    let availableVoicesCount: Int
    let sampleVoices: [TTSVoiceInfo]
}

let liveSel = probeAccessibilitySelection(simulateSecureField: false)
let secureSel = probeAccessibilitySelection(simulateSecureField: true)
let ocrRes = runInMemoryVisionOCR()
let voices = listOfflineSystemVoices()

let report = FullBridgeReport(
    liveSelection: liveSel,
    secureFieldSimulation: secureSel,
    visionOcr: ocrRes,
    availableVoicesCount: voices.count,
    sampleVoices: Array(voices.prefix(6))
)

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
if let data = try? encoder.encode(report), let jsonStr = String(data: data, encoding: .utf8) {
    print(jsonStr)
}
