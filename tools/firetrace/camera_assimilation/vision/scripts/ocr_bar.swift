// macOS Vision OCR for printed-bar crops. usage: ocr_bar <png>...   -> one JSON object per line.
// Language correction is off so digits are not "fixed" into words; every read is parsed and range-checked downstream.
import Foundation
import Vision
import AppKit

for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("{\"path\":\"\(path)\",\"error\":\"load\"}"); continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    var lines: [[String: Any]] = []
    for o in (req.results ?? []) {
        if let c = o.topCandidates(1).first {
            lines.append(["text": c.string, "conf": c.confidence])
        }
    }
    let payload: [String: Any] = ["path": path, "lines": lines]
    let d = try! JSONSerialization.data(withJSONObject: payload)
    print(String(data: d, encoding: .utf8)!)
}
