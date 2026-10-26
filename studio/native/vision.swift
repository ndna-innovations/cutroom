// studio-vision: macOS Vision helpers for studio-engine.
//   studio-vision ocr IMG...            -> one JSON object per image per line: {"file":..,"w":..,"h":..,"lines":[[x,y,w,h,"text",conf],...]}
//   studio-vision ocrdir DIR            -> same, for every .png/.jpg in DIR (sorted)
//   studio-vision person IN_DIR OUT_DIR -> 8-bit person mask PNG per image (Vision person segmentation, accurate)
// Pixel coordinates, origin top-left.
import Foundation
import Vision
import AppKit
import CoreImage

func cgImage(_ path: String) -> CGImage? {
    guard let img = NSImage(contentsOfFile: path) else { return nil }
    return img.cgImage(forProposedRect: nil, context: nil, hints: nil)
}

func esc(_ s: String) -> String {
    let d = try! JSONSerialization.data(withJSONObject: [s], options: [])
    let j = String(data: d, encoding: .utf8)!
    return String(j.dropFirst().dropLast())
}

func ocr(_ path: String) {
    guard let cg = cgImage(path) else { print("{\"file\":\(esc(path)),\"error\":\"unreadable\"}"); return }
    let W = Double(cg.width), H = Double(cg.height)
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    var parts: [String] = []
    for o in req.results ?? [] {
        if let c = o.topCandidates(1).first {
            let b = o.boundingBox
            parts.append(String(format: "[%.1f,%.1f,%.1f,%.1f,", b.minX * W, (1 - b.maxY) * H, b.width * W, b.height * H) + esc(c.string) + String(format: ",%.3f]", c.confidence))
        }
    }
    print("{\"file\":\(esc(path)),\"w\":\(cg.width),\"h\":\(cg.height),\"lines\":[" + parts.joined(separator: ",") + "]}")
    fflush(stdout)
}

func listImages(_ dir: String) -> [String] {
    let fm = FileManager.default
    return ((try? fm.contentsOfDirectory(atPath: dir)) ?? []).filter { $0.hasSuffix(".png") || $0.hasSuffix(".jpg") }.sorted().map { dir + "/" + $0 }
}

let a = CommandLine.arguments
guard a.count >= 3 else { print("usage: studio-vision ocr IMG... | ocrdir DIR | person IN OUT"); exit(2) }
switch a[1] {
case "ocr": for p in a[2...] { autoreleasepool { ocr(p) } }
case "ocrdir": for p in listImages(a[2]) { autoreleasepool { ocr(p) } }
case "person":
    let ctx = CIContext()
    try? FileManager.default.createDirectory(atPath: a[3], withIntermediateDirectories: true)
    for p in listImages(a[2]) { autoreleasepool {
        guard let ci = CIImage(contentsOf: URL(fileURLWithPath: p)) else { return }
        let req = VNGeneratePersonSegmentationRequest(); req.qualityLevel = .accurate
        req.outputPixelFormat = kCVPixelFormatType_OneComponent8
        try? VNImageRequestHandler(ciImage: ci).perform([req])
        let name = (p as NSString).lastPathComponent
        var mask = CIImage(color: .black).cropped(to: ci.extent)
        if let pb = req.results?.first?.pixelBuffer {
            let m = CIImage(cvPixelBuffer: pb)
            mask = m.transformed(by: CGAffineTransform(scaleX: ci.extent.width / m.extent.width, y: ci.extent.height / m.extent.height))
        }
        let cg = ctx.createCGImage(mask, from: ci.extent)!
        try? NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: a[3] + "/" + name))
    } }
default: print("unknown command"); exit(2)
}
