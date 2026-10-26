// studio-autotake: helpers for unattended screen takes (cutroom autotake).
//   studio-autotake windows                      -> JSON list of on-screen app windows (id, owner, title, bounds in points)
//   studio-autotake screen                       -> JSON visible screen area (points, top-left origin)
//   studio-autotake record --window ID --out F   -> records ONE window (or --display: the whole screen minus Terminal; --audio adds app sound)
//                                                   ScreenCaptureKit, HEVC .mov, cursor shown, until
//                                                   SIGINT/SIGTERM/SIGHUP; prints "first_frame <unix seconds>" when recording starts
//   studio-autotake click X Y | scroll X Y LINES | drag X1 Y1 X2 Y2 [SECS]   -> mouse at global points
// Needs Screen Recording (record) and Accessibility (click) permission for the app that runs it.
import AppKit
import AVFoundation
import CoreGraphics
import Foundation
import ScreenCaptureKit

func windowsJSON() -> String {
  let opts = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)
  let list = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] ?? []
  var out: [[String: Any]] = []
  for w in list {
    if (w[kCGWindowLayer as String] as? Int ?? 0) != 0 { continue }
    let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
    out.append([
      "id": w[kCGWindowNumber as String] as? Int ?? 0,
      "owner": w[kCGWindowOwnerName as String] as? String ?? "",
      "title": w[kCGWindowName as String] as? String ?? "",
      "x": b["X"] ?? 0, "y": b["Y"] ?? 0, "w": b["Width"] ?? 0, "h": b["Height"] ?? 0,
    ])
  }
  let data = try! JSONSerialization.data(withJSONObject: out)
  return String(data: data, encoding: .utf8)!
}

func click(_ x: Double, _ y: Double) {
  let p = CGPoint(x: x, y: y)
  let src = CGEventSource(stateID: .hidSystemState)
  CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
  usleep(120_000)
  CGEvent(mouseEventSource: src, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
  usleep(60_000)
  CGEvent(mouseEventSource: src, mouseType: .leftMouseUp, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
}

/// Scroll by `lines` (negative = down) with the pointer at X,Y.
func scroll(_ x: Double, _ y: Double, _ lines: Int32) {
  let src = CGEventSource(stateID: .hidSystemState)
  CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: CGPoint(x: x, y: y), mouseButton: .left)?.post(tap: .cghidEventTap)
  usleep(100_000)
  let step: Int32 = lines < 0 ? -1 : 1
  for _ in 0..<abs(lines) {
    CGEvent(scrollWheelEvent2Source: src, units: .line, wheelCount: 1, wheel1: step, wheel2: 0, wheel3: 0)?.post(tap: .cghidEventTap)
    usleep(40_000)
  }
}

/// Press at A, move smoothly to B over `secs`, release (drag a shape, a slider, a file).
func drag(_ x1: Double, _ y1: Double, _ x2: Double, _ y2: Double, _ secs: Double) {
  let src = CGEventSource(stateID: .hidSystemState)
  let a = CGPoint(x: x1, y: y1)
  CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: a, mouseButton: .left)?.post(tap: .cghidEventTap)
  usleep(120_000)
  CGEvent(mouseEventSource: src, mouseType: .leftMouseDown, mouseCursorPosition: a, mouseButton: .left)?.post(tap: .cghidEventTap)
  let n = max(10, Int(secs * 60))
  for i in 1...n {
    let t = Double(i) / Double(n), e = t * t * (3 - 2 * t)   // eased, looks like a hand
    let p = CGPoint(x: x1 + (x2 - x1) * e, y: y1 + (y2 - y1) * e)
    CGEvent(mouseEventSource: src, mouseType: .leftMouseDragged, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
    usleep(useconds_t(secs / Double(n) * 1_000_000))
  }
  CGEvent(mouseEventSource: src, mouseType: .leftMouseUp, mouseCursorPosition: CGPoint(x: x2, y: y2), mouseButton: .left)?.post(tap: .cghidEventTap)
}

final class Recorder: NSObject, SCStreamOutput, SCStreamDelegate {
  let writer: AVAssetWriter
  let input: AVAssetWriterInput
  var audio: AVAssetWriterInput?
  var stream: SCStream?
  var started = false
  var startPTS = CMTime.zero
  let q = DispatchQueue(label: "rec")

  init(out: URL, width: Int, height: Int, withAudio: Bool) throws {
    try? FileManager.default.removeItem(at: out)
    writer = try AVAssetWriter(outputURL: out, fileType: .mov)
    input = AVAssetWriterInput(mediaType: .video, outputSettings: [
      AVVideoCodecKey: AVVideoCodecType.hevc, AVVideoWidthKey: width, AVVideoHeightKey: height,
      AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 40_000_000, AVVideoExpectedSourceFrameRateKey: 60],
    ])
    input.expectsMediaDataInRealTime = true
    writer.add(input)
    if withAudio {
      let a = AVAssetWriterInput(mediaType: .audio, outputSettings: [
        AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48000, AVNumberOfChannelsKey: 2, AVEncoderBitRateKey: 192_000,
      ])
      a.expectsMediaDataInRealTime = true
      writer.add(a)
      audio = a
    }
  }

  func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
    guard sb.isValid else { return }
    if type == .audio {
      // app sound: only after the first video frame started the file, never before its start time
      if started, let a = audio, sb.presentationTimeStamp >= startPTS, a.isReadyForMoreMediaData { a.append(sb) }
      return
    }
    guard type == .screen else { return }
    // skip idle/blank frames: only "complete" frames carry new pixels
    if let att = CMSampleBufferGetSampleAttachmentsArray(sb, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
       let raw = att.first?[.status] as? Int, let st = SCFrameStatus(rawValue: raw), st != .complete { return }
    if !started {
      writer.startWriting()
      startPTS = sb.presentationTimeStamp
      writer.startSession(atSourceTime: startPTS)
      started = true
      print(String(format: "first_frame %.3f", Date().timeIntervalSince1970)); fflush(stdout)
    }
    if input.isReadyForMoreMediaData { input.append(sb) }
  }

  func stream(_ stream: SCStream, didStopWithError error: Error) {
    FileHandle.standardError.write("stream stopped: \(error)\n".data(using: .utf8)!)
    finish()
  }

  func finish() {
    q.sync {
      let done = DispatchSemaphore(value: 0)
      if let s = stream { s.stopCapture { _ in done.signal() }; _ = done.wait(timeout: .now() + 3) }
      guard started else { print("stopped 0"); exit(2) }
      input.markAsFinished()
      audio?.markAsFinished()
      writer.finishWriting { print("stopped \(self.writer.status.rawValue)"); fflush(stdout); exit(0) }
    }
  }
}

/// One window (`windowID`), or the whole display under it (`windowID == nil`), leaving out every window whose
/// owner is in `excludeOwners` (e.g. the Terminal running the take). `withAudio` adds the apps' sound.
func record(windowID: Int?, out: String, fps: Int, excludeOwners: [String], withAudio: Bool) async throws {
  let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
  let filter: SCContentFilter
  var pixW = 0, pixH = 0
  if let id = windowID {
    guard let win = content.windows.first(where: { Int($0.windowID) == id }) else {
      FileHandle.standardError.write("window \(id) not found\n".data(using: .utf8)!); exit(3)
    }
    filter = SCContentFilter(desktopIndependentWindow: win)
    let scale = Double(filter.pointPixelScale)
    pixW = Int(win.frame.width * scale); pixH = Int(win.frame.height * scale)
  } else {
    guard let display = content.displays.first(where: { $0.displayID == CGMainDisplayID() }) ?? content.displays.first else {
      FileHandle.standardError.write("no display\n".data(using: .utf8)!); exit(3)
    }
    let skip = content.windows.filter { excludeOwners.contains($0.owningApplication?.applicationName ?? "") }
    filter = SCContentFilter(display: display, excludingWindows: skip)
    let scale = Double(filter.pointPixelScale)
    pixW = Int(Double(display.width) * scale); pixH = Int(Double(display.height) * scale)
  }
  let cfg = SCStreamConfiguration()
  cfg.width = pixW / 2 * 2
  cfg.height = pixH / 2 * 2
  cfg.showsCursor = true
  cfg.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(fps))
  cfg.pixelFormat = kCVPixelFormatType_32BGRA
  cfg.queueDepth = 8
  if withAudio {
    cfg.capturesAudio = true
    cfg.sampleRate = 48000
    cfg.channelCount = 2
    cfg.excludesCurrentProcessAudio = true
  }
  let rec = try Recorder(out: URL(fileURLWithPath: out), width: cfg.width, height: cfg.height, withAudio: withAudio)
  let s = SCStream(filter: filter, configuration: cfg, delegate: rec)
  try s.addStreamOutput(rec, type: .screen, sampleHandlerQueue: rec.q)
  if withAudio { try s.addStreamOutput(rec, type: .audio, sampleHandlerQueue: rec.q) }
  rec.stream = s
  for sig in [SIGINT, SIGTERM, SIGHUP] {
    signal(sig, SIG_IGN)
    let src = DispatchSource.makeSignalSource(signal: sig, queue: .global())
    src.setEventHandler { rec.finish() }
    src.resume()
    signalSources.append(src)
  }
  try await s.startCapture()
  let what = windowID.map { "window \($0)" } ?? "screen (without \(excludeOwners.joined(separator: ", ")))"
  FileHandle.standardError.write("recording \(what) at \(cfg.width)x\(cfg.height)\(withAudio ? " + sound" : "")\n".data(using: .utf8)!)
}

func screenJSON() -> String {
  _ = NSApplication.shared
  guard let s = NSScreen.main else { return "{}" }
  // visible frame in top-left-origin points (what System Events positions use), without menu bar and Dock
  let f = s.visibleFrame, full = s.frame
  let d: [String: Any] = ["x": f.minX, "y": full.maxY - f.maxY, "w": f.width, "h": f.height, "full_w": full.width, "full_h": full.height]
  return String(data: try! JSONSerialization.data(withJSONObject: d), encoding: .utf8)!
}

var signalSources: [DispatchSourceSignal] = []
let args = CommandLine.arguments
func arg(_ name: String) -> String? {
  guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
  return args[i + 1]
}

switch args.count > 1 ? args[1] : "" {
case "windows":
  print(windowsJSON())
case "screen":
  print(screenJSON())
case "click":
  guard args.count >= 4, let x = Double(args[2]), let y = Double(args[3]) else { print("usage: click X Y"); exit(1) }
  click(x, y)
case "scroll":
  guard args.count >= 5, let x = Double(args[2]), let y = Double(args[3]), let l = Int32(args[4]) else { print("usage: scroll X Y LINES"); exit(1) }
  scroll(x, y, l)
case "drag":
  guard args.count >= 6, let a = Double(args[2]), let b = Double(args[3]), let c = Double(args[4]), let d = Double(args[5]) else { print("usage: drag X1 Y1 X2 Y2 [SECS]"); exit(1) }
  drag(a, b, c, d, args.count > 6 ? Double(args[6]) ?? 0.6 : 0.6)
case "record":
  _ = NSApplication.shared  // starts the window-server connection ScreenCaptureKit needs
  let w = arg("--window").flatMap(Int.init)
  guard let out = arg("--out"), w != nil || args.contains("--display") else {
    print("usage: record (--window ID | --display [--exclude Terminal,…]) --out FILE [--fps 60] [--audio]"); exit(1)
  }
  let fps = arg("--fps").flatMap(Int.init) ?? 60
  let excl = (arg("--exclude") ?? "Terminal").split(separator: ",").map { String($0) }
  let withAudio = args.contains("--audio")
  Task {
    do { try await record(windowID: w, out: out, fps: fps, excludeOwners: excl, withAudio: withAudio) } catch {
      FileHandle.standardError.write("record failed: \(error)\n".data(using: .utf8)!); exit(4)
    }
  }
  dispatchMain()
default:
  print("usage: studio-autotake windows | screen | record (--window ID | --display [--exclude A,B]) --out FILE [--fps 60] [--audio] | click X Y | scroll X Y LINES | drag X1 Y1 X2 Y2 [SECS]")
  exit(1)
}
