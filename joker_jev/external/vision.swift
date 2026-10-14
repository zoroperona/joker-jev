import Foundation
import Vision
import AppKit
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
let fast = CommandLine.arguments.contains("--fast")
request.recognitionLevel = fast ? .fast : .accurate
request.recognitionLanguages = fast ? ["en-US"] : ["zh-Hans", "en-US"]
request.usesLanguageCorrection = false
try VNImageRequestHandler(url: url).perform([request])
let rows: [[String: Any]] = (request.results ?? []).compactMap { observation in
    guard let text = observation.topCandidates(1).first else { return nil }
    let b = observation.boundingBox
    return ["text": text.string, "confidence": text.confidence,
            "box": [b.minX, 1-b.maxY, b.width, b.height]]
}
let data = try JSONSerialization.data(withJSONObject: rows, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
