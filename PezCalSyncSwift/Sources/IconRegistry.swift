import Cocoa
import SwiftUI

// MARK: - Icon Registry
// Single source of truth for all icon types, colors, and SF Symbol mappings.
// To add a new icon type: just add an entry to `iconTypes`.
// To add a new color: just add an entry to `allColors`.

struct IconType {
    let name: String
    let displayName: String
    let sfSymbol: String          // SF Symbol for "circle" or single variant
    let sfSymbolFilled: String?   // SF Symbol for "filled" variant (nil = no variants)

    var hasVariants: Bool { sfSymbolFilled != nil }

    func sfSymbolName(variant: String) -> String {
        if variant == "filled", let filled = sfSymbolFilled {
            return filled
        }
        return sfSymbol
    }
}

struct IconColor {
    let name: String
    let displayName: String
    let nsColor: NSColor
    let swiftUIColor: Color
}

// MARK: - All available icon types
// Add new icon types here — everything else updates automatically.

let iconTypes: [IconType] = [
    IconType(name: "brief",     displayName: "Briefcase",  sfSymbol: "briefcase.circle",           sfSymbolFilled: "briefcase.circle.fill"),
    IconType(name: "person",    displayName: "Person",     sfSymbol: "person.circle",              sfSymbolFilled: "person.circle.fill"),
    IconType(name: "badminton", displayName: "Badminton",  sfSymbol: "figure.badminton.circle.fill", sfSymbolFilled: nil),
    IconType(name: "box",       displayName: "Box",        sfSymbol: "shippingbox.circle.fill",    sfSymbolFilled: nil),
    IconType(name: "suitcase",  displayName: "Suitcase",   sfSymbol: "suitcase.circle",            sfSymbolFilled: "suitcase.circle.fill"),
    IconType(name: "star",      displayName: "Star",       sfSymbol: "star.circle",                sfSymbolFilled: "star.circle.fill"),
    IconType(name: "heart",     displayName: "Heart",      sfSymbol: "heart.circle",               sfSymbolFilled: "heart.circle.fill"),
    IconType(name: "flag",      displayName: "Flag",       sfSymbol: "flag.circle",                sfSymbolFilled: "flag.circle.fill"),
]

// MARK: - All available colors
// Add new colors here — everything else updates automatically.

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
    // Support "grey" as alias for "gray"
    let normalized = name == "grey" ? "gray" : name
    return allColors.first { $0.name == normalized }
}

// MARK: - Descriptor ↔ Components

/// Builds a descriptor string like "brief-purple-filled" or "badminton-yellow"
func buildIconDescriptor(type: String, color: String, variant: String) -> String {
    if variant.isEmpty {
        return "\(type)-\(color)"
    }
    return "\(type)-\(color)-\(variant)"
}

/// Parses a descriptor string back into (type, color, variant).
/// Handles legacy ".png" suffixes for backward compatibility.
func parseIconDescriptor(_ descriptor: String) -> (type: String, color: String, variant: String) {
    let name = descriptor.replacingOccurrences(of: ".png", with: "")
    // Sort types longest-first so "suitcase" doesn't match before a hypothetical longer name
    let sortedTypes = iconTypes.sorted { $0.name.count > $1.name.count }
    for iconType in sortedTypes {
        let prefix = iconType.name + "-"
        if name.hasPrefix(prefix) {
            let rest = String(name.dropFirst(prefix.count))
            if iconType.hasVariants {
                for variant in ["filled", "circle"] {
                    if rest.hasSuffix("-" + variant) {
                        let color = String(rest.dropLast(variant.count + 1))
                        return (iconType.name, color, variant)
                    }
                }
                return (iconType.name, rest, "circle")
            } else {
                return (iconType.name, rest, "")
            }
        }
    }
    return ("brief", "blue", "circle")
}

// MARK: - SF Symbol Resolution

/// Returns the SF Symbol name for a given icon descriptor like "brief-purple-filled"
func sfSymbolName(forDescriptor descriptor: String) -> String {
    let parsed = parseIconDescriptor(descriptor)
    return iconType(named: parsed.type)?.sfSymbolName(variant: parsed.variant) ?? "briefcase.circle"
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

/// Returns the SF Symbol name for a given type and variant
func sfSymbolName(forType type: String, variant: String) -> String {
    iconType(named: type)?.sfSymbolName(variant: variant) ?? "briefcase.circle"
}

// MARK: - NSImage Creation

/// Creates a colored SF Symbol NSImage using hierarchical rendering for gradient effect.
func createColoredSFSymbol(name: String, color: NSColor, size: CGFloat = 16) -> NSImage? {
    guard let image = NSImage(systemSymbolName: name, accessibilityDescription: nil) else { return nil }
    let sizeConfig = NSImage.SymbolConfiguration(pointSize: size, weight: .regular)
    let colorConfig = NSImage.SymbolConfiguration(hierarchicalColor: color)
    let combined = sizeConfig.applying(colorConfig)
    return image.withSymbolConfiguration(combined) ?? image
}

/// Creates a colored SF Symbol NSImage from an icon descriptor like "brief-purple-filled"
func createIconImage(forDescriptor descriptor: String, size: CGFloat = 16) -> NSImage? {
    let symbolName = sfSymbolName(forDescriptor: descriptor)
    let color = nsColor(forDescriptor: descriptor)
    return createColoredSFSymbol(name: symbolName, color: color, size: size)
}
