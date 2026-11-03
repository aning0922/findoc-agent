// Real local OCR spike; never receives PDF text, values, or financial authority.
import Foundation
import Vision
import ImageIO

struct OCRLine: Codable {
    let text: String
    let confidence: Float
    let bbox: [Double]  // top-left normalized coordinates
}
struct OCRResult: Codable {
    let engine: String
    let os_version: String
    let request_revision: Int
    let model_revision: String
    let languages: [String]
    let elapsed_seconds: Double
    let lines: [OCRLine]
}

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: swift vision_ocr.swift input.png output.json\n", stderr)
    exit(2)
}
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
let supported = try request.supportedRecognitionLanguages()
guard supported.contains("zh-Hans") else {
    fputs("Simplified Chinese recognition unavailable\n", stderr)
    exit(3)
}
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = false
let handler = VNImageRequestHandler(url: input, options: [:])
let start = Date()
try handler.perform([request])
let lines = (request.results ?? []).compactMap { observation -> OCRLine? in
    guard let candidate = observation.topCandidates(1).first else { return nil }
    let b = observation.boundingBox
    return OCRLine(text: candidate.string, confidence: candidate.confidence,
                   bbox: [b.minX, 1 - b.maxY, b.maxX, 1 - b.minY])
}.sorted { a, b in
    if abs(a.bbox[1] - b.bbox[1]) > 0.006 { return a.bbox[1] < b.bbox[1] }
    return a.bbox[0] < b.bbox[0]
}
let result = OCRResult(engine: "Apple Vision VNRecognizeTextRequest",
    os_version: ProcessInfo.processInfo.operatingSystemVersionString,
    request_revision: request.revision, model_revision: "not_exposed_by_framework",
    languages: request.recognitionLanguages, elapsed_seconds: Date().timeIntervalSince(start),
    lines: lines)
let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
try encoder.encode(result).write(to: output, options: .withoutOverwriting)
print("Recognized \(lines.count) lines using Vision revision \(request.revision)")
