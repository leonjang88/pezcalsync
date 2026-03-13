// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PezCalSync",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "PezCalSync", targets: ["PezCalSync"])
    ],
    targets: [
        .executableTarget(
            name: "PezCalSync",
            path: "Sources"
        )
    ]
)
