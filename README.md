# V8 Monolithic Library Builds

This repository contains automated builds of Google V8 static libraries for multiple platforms using GitHub Actions.

English | [简体中文](README.ZH.md)

## Current V8 Version

**15.7.112.23**

## Supported Platforms

- **Android** (arm64, arm, x64; Android 6.0 / API 23 target)
- **iOS** (XCFramework: arm64 device, arm64 simulator)
- **macOS** (XCFramework: arm64 Apple Silicon)
- **Windows** (x64, Release + Debug)

## Latest Release

Check the [Releases](../../releases) page for the latest precompiled binaries.

## Package Contents

Each release includes zip packages with:
- **Static library file** (libv8_monolith.a / v8_monolith.lib)
- **args.gn** - Build configuration used for compilation
- **args.full.txt** - Complete GN arguments list with all default values and descriptions

## Build Artifacts

Tag builds include Android, Apple, and Windows. Publication requires all eight nonempty, fully uploaded artifacts below.

| Platform | Artifact File | Architectures | Description |
|----------|--------------|---------------|-------------|
| Android  | `libv8_monolith-android-arm64.zip` | arm64 | Static library + args.gn + args.full.txt |
| Android  | `libv8_monolith-android-arm.zip` | arm | Static library + args.gn + args.full.txt |
| Android  | `libv8_monolith-android-x64.zip` | x64 | Static library + args.gn + args.full.txt |
| Android  | `include-android.zip` | - | V8 header files |
| Apple  | `libv8_monolith-apple.zip` | arm64 | XCFramework: iOS device, iOS simulator, macOS; headers + GN arguments |
| Windows  | `libv8_monolith-win-x64-release.zip` | x64 | Release static library + args.gn + args.full.txt |
| Windows  | `libv8_monolith-win-x64-debug.zip` | x64 | Debug static library + args.gn + args.full.txt |
| Windows  | `include-win.zip` | - | V8 header files |

## Build Configuration Files

The repository contains GN build configuration files for each platform:

### Android
- [args.android.arm64.gn](args.android.arm64.gn)
- [args.android.arm.gn](args.android.arm.gn)
- [args.android.x64.gn](args.android.x64.gn)

### Apple (iOS + macOS)

Apple CI builds the three slices below and packages them together as an XCFramework.

- [args.ios.arm64.gn](args.ios.arm64.gn) - iOS device
- [args.ios.arm64.simulator.gn](args.ios.arm64.simulator.gn) - iOS simulator
- [args.mac.arm64.gn](args.mac.arm64.gn) - macOS Apple Silicon

`libv8_monolith-apple.zip` contains one XCFramework with three arm64 slices:

```
libv8_monolith.xcframework/
├── ios-arm64/
├── ios-arm64-simulator/
└── macos-arm64/
```

Each slice contains `libv8_monolith.framework` with its static library, `Info.plist`, and its own headers, including generated headers from that slice's build. iOS keeps JavaScript JIT, WebAssembly, DrumBrake, pointer compression, and the cppgc caged heap disabled; macOS keeps WebAssembly enabled.

To use in Xcode:

1. Drag `libv8_monolith.xcframework` into your project.
2. Add it to "Frameworks, Libraries, and Embedded Content".
3. Import headers with `#include <libv8_monolith/v8.h>`.
4. Xcode selects the matching platform slice.

### Windows

- [args.win.x64.release.gn](args.win.x64.release.gn) - Release
- [args.win.x64.debug.gn](args.win.x64.debug.gn) - Debug

### XCFramework Configuration
- [Info.plist.template](Info.plist.template) - Template for XCFramework Info.plist (version is replaced during build)

## Features

- ✅ Automated builds via GitHub Actions
- ✅ Consistent configuration across platforms
- ✅ Source version validation before building ([builder.js](builder.js))
- ✅ Full build argument traceability
- ✅ Apple XCFramework: iOS device, iOS simulator, and macOS arm64
- ✅ Windows Release and Debug packages

## Usage

1. Download the appropriate zip file for your platform from the [Releases](../../releases) page
2. Extract the static library file
3. Link against the library in your project
4. Include the V8 headers (included in the release)
5. Refer to `args.gn` and `args.full.txt` to understand the build configuration

## Build System

All builds are automated using [GitHub Actions](.github/workflows/main.yml):
- Clean build environment for each platform
- Source and dependencies pinned to the same V8 tag
- Reproducible builds
- Automated release creation

Android uses the NDK **30.0.16248370** and Clang pinned by V8's `DEPS`; CI also pins the smoke-test NDK to that version. After dependency sync and hooks complete, CI installs and checks the amd64 host sysroot immediately before GN generation, plus the i386 sysroot/runtime needed by ARM snapshot generation. Missing headers or startup libraries stop the build and report their absolute paths. All three architectures explicitly compile against API 23, enabling the pre-API-29 emulated TLS path. CI links a smoke executable against API 23 system stubs and rejects native ELF TLS before upload; x64 also runs all 14 checks in an Android 6.0 emulator. Earlier `15.7.112.23` artifacts built for API 29 must be rebuilt; lowering an application manifest alone is insufficient.

The 64-bit artifacts support 16 KiB alignment alongside Android 6.0. CI checks the executable and matching C++ runtime's ELF load alignment, then runs the x64 smoke test in a 16 KiB-page emulator. A failed compatibility test blocks publication. Final application `.so` linking and APK/AAB packaging must also support 16 KiB pages; use NDK r28+ and AGP 8.5.1+ with compatible native dependencies. See [Android smoke tests](tests/android/README.md) for checks and integration requirements.

For a failed Android x64, Windows Debug, or Apple job, use **Actions → build and publish v8 libs → Run workflow**, select `main`, set `target` to `android-x64`, `windows-debug`, or `apple`, and enter the existing draft's `release_tag`. Only that target rebuilds. Retries require matching `builder.js` and GN inputs; complete assets are reused and incomplete uploads are rejected. Use `publish-only` to retry publication after all eight required assets are complete.

Targeted retries reuse an existing draft with matching build inputs. Published release assets in this repository are immutable; adding another platform requires a new version tag and a new release.

All platforms check `include/v8-version.h` before building and reject unused GN arguments. Platform settings are declared in the GN files without modifying V8 sources. Windows CI installs SDK `10.0.28000.0`, as required by this V8 version. Both Windows configurations use the upstream Torque generator (`v8_use_metagen=false`) because Metagen rejects `ExtendedMap` tail padding with the MSVC standard library. Windows packages use 7-Zip with ZIP64 support for libraries larger than 2 GB, verify archive integrity, and check the compressed asset is below GitHub's 2 GiB upload limit.

## V8 Documentation

### Official V8 Resources
- [V8 Build Instructions](https://v8.dev/docs/build)
- [V8 Build with GN](https://v8.dev/docs/build-gn)
- [V8 ARM64 Build](https://v8.dev/docs/compile-arm64)

### Chromium Build Instructions
- [Windows Build Instructions](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/windows_build_instructions.md)
- [Android Build Instructions](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/android_build_instructions.md)
- [iOS Build Instructions](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/ios/build_instructions.md)
- [macOS Build Instructions](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/mac_build_instructions.md)
- [macOS ARM64 Build](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/mac_arm64.md)

### Additional Resources
- [V8 Release Schedule](https://chromiumdash.appspot.com/schedule)
- [GitHub Actions Runner Images](https://github.com/actions/runner-images)

## Contributing

To update the V8 version or modify build configurations:

1. Update `V8_VERSION` in [.github/workflows/main.yml](.github/workflows/main.yml)
2. Modify platform-specific `args.*.gn` files as needed
3. Update [builder.js](builder.js) for platform-specific build logic
4. Create a new git tag to trigger the build workflow

## Acknowledgments

This project is inspired by and references the work from [just-js/v8](https://github.com/just-js/v8).

## License

This repository contains build configurations and automation scripts. V8 itself is licensed under the BSD license. See the [V8 repository](https://github.com/v8/v8) for details.
