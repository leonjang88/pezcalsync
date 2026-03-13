import Cocoa
import SwiftUI

// MARK: - Icon Registry
// Single source of truth for all icon types, colors, and SF Symbol mappings.

struct IconType {
    let name: String
    let displayName: String
    let sfBase: String              // e.g. "briefcase"
    let sfFilled: String            // e.g. "briefcase.fill"
    let sfCircle: String?           // e.g. "briefcase.circle" (nil = no circle variant)
    let sfCircleFilled: String?     // e.g. "briefcase.circle.fill"

    var hasCircle: Bool { sfCircle != nil }

    /// Returns the SF Symbol for the given state.
    /// - circle: whether the user chose the circle variant
    /// - filled: true for synced events, false for unsynced
    func sfSymbolName(circle: Bool, filled: Bool) -> String {
        if circle, let c = sfCircle, let cf = sfCircleFilled {
            return filled ? cf : c
        }
        return filled ? sfFilled : sfBase
    }

    /// The display symbol shown in the icon picker (always filled).
    var previewSymbol: String { sfFilled }
}

struct IconColor {
    let name: String
    let displayName: String
    let nsColor: NSColor
    let swiftUIColor: Color
}

// MARK: - All available icon types

let iconTypes: [IconType] = [
    IconType(name: "brief",     displayName: "Briefcase",   sfBase: "briefcase",             sfFilled: "briefcase.fill",                  sfCircle: "briefcase.circle",              sfCircleFilled: "briefcase.circle.fill"),
    IconType(name: "person",    displayName: "Person",      sfBase: "person",                sfFilled: "person.fill",                     sfCircle: "person.circle",                 sfCircleFilled: "person.circle.fill"),
    IconType(name: "badminton", displayName: "Badminton",   sfBase: "figure.badminton",      sfFilled: "figure.badminton",                sfCircle: "figure.badminton.circle",       sfCircleFilled: "figure.badminton.circle.fill"),
    IconType(name: "box",       displayName: "Box",         sfBase: "shippingbox",           sfFilled: "shippingbox.fill",                sfCircle: "shippingbox.circle",            sfCircleFilled: "shippingbox.circle.fill"),
    IconType(name: "suitcase",  displayName: "Suitcase",    sfBase: "suitcase",              sfFilled: "suitcase.fill",                   sfCircle: "suitcase.circle",               sfCircleFilled: "suitcase.circle.fill"),
    IconType(name: "star",      displayName: "Star",        sfBase: "star",                  sfFilled: "star.fill",                       sfCircle: "star.circle",                   sfCircleFilled: "star.circle.fill"),
    IconType(name: "heart",     displayName: "Heart",       sfBase: "heart",                 sfFilled: "heart.fill",                      sfCircle: "heart.circle",                  sfCircleFilled: "heart.circle.fill"),
    IconType(name: "flag",      displayName: "Flag",        sfBase: "flag",                  sfFilled: "flag.fill",                       sfCircle: "flag.circle",                   sfCircleFilled: "flag.circle.fill"),
    IconType(name: "banknote",  displayName: "Dollar Bill", sfBase: "banknote",              sfFilled: "banknote.fill",                   sfCircle: nil,                             sfCircleFilled: nil),
    IconType(name: "house",     displayName: "House",       sfBase: "house",                 sfFilled: "house.fill",                      sfCircle: "house.circle",                  sfCircleFilled: "house.circle.fill"),
    IconType(name: "airplane",  displayName: "Airplane",    sfBase: "airplane",              sfFilled: "airplane",                        sfCircle: "airplane.circle",               sfCircleFilled: "airplane.circle.fill"),
    IconType(name: "car",       displayName: "Car",         sfBase: "car",                   sfFilled: "car.fill",                        sfCircle: "car.circle",                    sfCircleFilled: "car.circle.fill"),
    IconType(name: "building",  displayName: "Building",    sfBase: "building.2",            sfFilled: "building.2.fill",                 sfCircle: "building.2.crop.circle",        sfCircleFilled: "building.2.crop.circle.fill"),
    IconType(name: "ferry",     displayName: "Ferry",       sfBase: "ferry",                 sfFilled: "ferry.fill",                      sfCircle: nil,                             sfCircleFilled: nil),
    IconType(name: "laptop",    displayName: "Laptop",      sfBase: "laptopcomputer",        sfFilled: "laptopcomputer",                  sfCircle: "laptopcomputer.circle",         sfCircleFilled: "laptopcomputer.circle.fill"),
    IconType(name: "phone",     displayName: "Phone",       sfBase: "phone",                 sfFilled: "phone.fill",                      sfCircle: "phone.circle",                  sfCircleFilled: "phone.circle.fill"),
    IconType(name: "envelope",  displayName: "Envelope",    sfBase: "envelope",              sfFilled: "envelope.fill",                   sfCircle: "envelope.circle",               sfCircleFilled: "envelope.circle.fill"),
    IconType(name: "terminal",  displayName: "Terminal",    sfBase: "terminal",              sfFilled: "terminal.fill",                   sfCircle: "terminal.circle",               sfCircleFilled: "terminal.circle.fill"),
    IconType(name: "hammer",    displayName: "Hammer",      sfBase: "hammer",                sfFilled: "hammer.fill",                     sfCircle: "hammer.circle",                 sfCircleFilled: "hammer.circle.fill"),
]

// MARK: - All available colors

let allColors: [IconColor] = [
    IconColor(name: "blue",   displayName: "Blue",   nsColor: .systemBlue,   swiftUIColor: .blue),
    IconColor(name: "green",  displayName: "Green",  nsColor: .systemGreen,  swiftUIColor: .green),
    IconColor(name: "orange", displayName: "Orange", nsColor: .systemOrange, swiftUIColor: .orange),
    IconColor(name: "purple", displayName: "Purple", nsColor: .systemPurple, swiftUIColor: .purple),
    IconColor(name: "red",    displayName: "Red",    nsColor: .systemRed,    swiftUIColor: .red),
    IconColor(name: "teal",   displayName: "Teal",   nsColor: .systemTeal,   swiftUIColor: .teal),
    IconColor(name: "yellow", displayName: "Yellow", nsColor: .systemYellow, swiftUIColor: .yellow),
    IconColor(name: "pink",   displayName: "Pink",   nsColor: .systemPink,   swiftUIColor: .pink),
    IconColor(name: "brown",  displayName: "Brown",  nsColor: .systemBrown,  swiftUIColor: .brown),
    IconColor(name: "indigo", displayName: "Indigo", nsColor: .systemIndigo, swiftUIColor: .indigo),
    IconColor(name: "mint",   displayName: "Mint",   nsColor: .systemMint,   swiftUIColor: .mint),
    IconColor(name: "cyan",   displayName: "Cyan",   nsColor: .systemCyan,   swiftUIColor: .cyan),
    IconColor(name: "gray",   displayName: "Gray",   nsColor: .systemGray,   swiftUIColor: .gray),
    IconColor(name: "white",  displayName: "White",  nsColor: .white,        swiftUIColor: .white),
    IconColor(name: "black",  displayName: "Black",  nsColor: .black,        swiftUIColor: .black),
]

// MARK: - Lookup helpers

let iconTypeNames: [String] = iconTypes.map { $0.name }
let allColorNames: [String] = allColors.map { $0.name }

func iconType(named name: String) -> IconType? {
    iconTypes.first { $0.name == name }
}

func iconColor(named name: String) -> IconColor? {
    let normalized = name == "grey" ? "gray" : name
    return allColors.first { $0.name == normalized }
}

// MARK: - Descriptor ↔ Components
// Descriptor format: "type-color" or "type-color-circle"
// e.g. "brief-purple", "brief-purple-circle"

func buildIconDescriptor(type: String, color: String, variant: String) -> String {
    if variant == "circle" {
        return "\(type)-\(color)-circle"
    }
    return "\(type)-\(color)"
}

func parseIconDescriptor(_ descriptor: String) -> (type: String, color: String, variant: String) {
    let name = descriptor.replacingOccurrences(of: ".png", with: "")
    let sortedTypes = iconTypes.sorted { $0.name.count > $1.name.count }
    for iconType in sortedTypes {
        let prefix = iconType.name + "-"
        if name.hasPrefix(prefix) {
            let rest = String(name.dropFirst(prefix.count))
            if rest.hasSuffix("-circle") {
                let color = String(rest.dropLast("-circle".count))
                return (iconType.name, color, "circle")
            }
            // Legacy: handle old "-filled" descriptors as non-circle
            if rest.hasSuffix("-filled") {
                let color = String(rest.dropLast("-filled".count))
                return (iconType.name, color, "")
            }
            return (iconType.name, rest, "")
        }
    }
    // Legacy: handle old combined names like "briefcircle", "boxcircle", etc.
    return ("brief", "blue", "")
}

// MARK: - SF Symbol Resolution

/// Returns the SF Symbol for a descriptor, defaulting to filled (synced) appearance.
func sfSymbolName(forDescriptor descriptor: String, filled: Bool = true) -> String {
    let parsed = parseIconDescriptor(descriptor)
    let isCircle = parsed.variant == "circle"
    return iconType(named: parsed.type)?.sfSymbolName(circle: isCircle, filled: filled) ?? "briefcase.fill"
}

/// Returns the NSColor for a given icon descriptor
func nsColor(forDescriptor descriptor: String) -> NSColor {
    let parsed = parseIconDescriptor(descriptor)
    return iconColor(named: parsed.color)?.nsColor ?? .systemBlue
}

/// Returns the SwiftUI Color for a given color name
func swiftUIColor(forName name: String) -> Color {
    iconColor(named: name)?.swiftUIColor ?? .blue
}

/// Returns the SF Symbol name for a given type and variant (used in settings preview)
func sfSymbolName(forType type: String, variant: String) -> String {
    let isCircle = variant == "circle"
    return iconType(named: type)?.sfSymbolName(circle: isCircle, filled: true) ?? "briefcase.fill"
}

// MARK: - NSImage Creation

func createColoredSFSymbol(name: String, color: NSColor, size: CGFloat = 16) -> NSImage? {
    guard let image = NSImage(systemSymbolName: name, accessibilityDescription: nil) else { return nil }
    let sizeConfig = NSImage.SymbolConfiguration(pointSize: size, weight: .regular)
    let colorConfig = NSImage.SymbolConfiguration(hierarchicalColor: color)
    let combined = sizeConfig.applying(colorConfig)
    return image.withSymbolConfiguration(combined) ?? image
}

/// Creates a filled (synced) icon image from a descriptor
func createIconImage(forDescriptor descriptor: String, size: CGFloat = 16) -> NSImage? {
    let symbolName = sfSymbolName(forDescriptor: descriptor, filled: true)
    let color = nsColor(forDescriptor: descriptor)
    return createColoredSFSymbol(name: symbolName, color: color, size: size)
}

/// Creates an unfilled (unsynced) icon image from a descriptor
func createUnfilledIconImage(forDescriptor descriptor: String, size: CGFloat = 16) -> NSImage? {
    let symbolName = sfSymbolName(forDescriptor: descriptor, filled: false)
    let color = nsColor(forDescriptor: descriptor)
    return createColoredSFSymbol(name: symbolName, color: color, size: size)
}
