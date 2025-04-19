// swiftc AppleOCRTool.swift -o AppleOCRTool

import Foundation
import Vision
import CoreImage

guard CommandLine.arguments.count > 1 else {
    fputs("""
    Usage:
      OCRTool <image_path>
    Example:
      OCRTool ./image.jpg

    """, stderr)
    exit(1)
}

let imagePath = CommandLine.arguments[1]
let imageURL = URL(fileURLWithPath: imagePath)

guard FileManager.default.fileExists(atPath: imagePath) else {
    fputs("Image file not found: \(imagePath)\n", stderr)
    exit(1)
}

// MARK: - Load and Preprocess Image
guard let ciInput = CIImage(contentsOf: imageURL) else {
    fputs("Failed to load image: \(imagePath)\n", stderr)
    exit(1)
}

// 1) Enhance contrast
let contrastFilter = CIFilter(name: "CIColorControls")!
contrastFilter.setValue(ciInput, forKey: kCIInputImageKey)
contrastFilter.setValue(1.2, forKey: kCIInputContrastKey)
contrastFilter.setValue(0.0, forKey: kCIInputBrightnessKey)
let contrasted = contrastFilter.outputImage!

// 2) Reduce noise
let noiseFilter = CIFilter(name: "CINoiseReduction")!
noiseFilter.setValue(contrasted, forKey: kCIInputImageKey)
noiseFilter.setValue(0.02, forKey: "inputNoiseLevel")    // Adjust as needed
noiseFilter.setValue(0.40, forKey: "inputSharpness")
let processedCI = noiseFilter.outputImage!

// Convert to CGImage, preserving original resolution and orientation
let context = CIContext()
guard let cgImage = context.createCGImage(processedCI, from: processedCI.extent) else {
    fputs("Failed to create CGImage\n", stderr)
    exit(1)
}

// Set orientation (from EXIF or a fixed value)
let orientation = CGImagePropertyOrientation.up

// MARK: - OCR Request Setup
let textRequest = VNRecognizeTextRequest()
textRequest.revision = VNRecognizeTextRequestRevision3     // Use the latest model
textRequest.recognitionLevel = .accurate
textRequest.recognitionLanguages = [
    "ja-JP",    // Japanese
    "ko-KR",    // Korean
    "zh-Hans",  // Simplified Chinese
    "zh-Hant",  // Traditional Chinese
    "en-US"     // English
]
textRequest.usesLanguageCorrection = true                  // Enable language correction
// If you have custom terms or brand names, uncomment and customize:
// textRequest.customWords = ["0","o"]

// MARK: - Perform OCR
let handler = VNImageRequestHandler(cgImage: cgImage,
                                    orientation: orientation,
                                    options: [:])

do {
    try handler.perform([textRequest])

    guard let observations = textRequest.results,
          !observations.isEmpty else {
        // Print empty line if no text detected
        print("")
        exit(0)
    }

    // Collect recognized text lines
    let lines = observations.compactMap { obs in
        obs.topCandidates(1).first?.string
    }

    // Output each line
    let output = lines.joined(separator: "\n")
    print(output)

} catch {
    fputs("OCR error: \(error.localizedDescription)\n", stderr)
    exit(1)
}