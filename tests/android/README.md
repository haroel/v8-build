# Android V8 smoke test

This builds a standalone native executable against the released V8 monolith and
runs it through `adb`. The 14 checks cover the exact V8 version, JavaScript and a
hot loop, C++ callbacks and exceptions, BigInt, ArrayBuffer, Promise microtasks,
allocation/GC, WebAssembly, feature flags, and context isolation.

Extract artifacts from the same release into:

```text
<artifacts>/headers/include/           # include-android.zip
<artifacts>/arm64/libv8_monolith.a     # libv8_monolith-android-arm64.zip
<artifacts>/arm/libv8_monolith.a       # libv8_monolith-android-arm.zip
<artifacts>/x64/libv8_monolith.a       # libv8_monolith-android-x64.zip
```

Run on a connected device or emulator with the selected ABI and Android API 23
or newer:

```bash
python3 tests/android/run_smoke.py \
  --artifacts scratch/android-smoke/artifacts/v15.7.112.23-4 \
  --ndk /path/to/compiler-ndk \
  --runtime-ndk /path/to/matching-runtime-ndk \
  --arch arm64 --serial emulator-5554
```

Use `--build-only` for link checks without a device, and `--output` to select a
build directory. Commands and results are saved to
`build/android-smoke/<arch>/smoke.log`. The runner cleans up its device directory.
Use `--page-size 16384` to require a 16 KiB device, or `--page-size 4096` for the
Android 6.0 test; a mismatched device fails before the executable is uploaded.

V8 15.7.112.23 pins NDK **30.0.16248370** in its `DEPS`; CI selects that exact
version for the smoke compiler instead of the runner's floating latest NDK.
A Chromium NDK repack can be
passed as `--runtime-ndk`; it contains runtime libraries but omits the compiler.
The test was linked successfully with the installed NDK 28.2 compiler and the
matching NDK 30 `libc++_shared.so`. NDK 28.2's own runtime cannot link these
artifacts because it lacks `std::__ndk1::__hash_memory`. Link the shared runtime
by its absolute path: adding its whole directory to `-L` can pull in private
bionic static libraries.

These artifacts disable pointer compression and sandboxing. Consumers must use
the matching headers and build macros; do not define `V8_COMPRESS_POINTERS`.
Current configurations explicitly set `default_min_sdk_version=23` and
`android_ndk_api_level=23`. Clang uses emulated TLS for this target. Artifacts
from the earlier `v15.7.112.23-1` and `-2` builds targeted API 29 and must be
rebuilt for Android 6.0. The runner reads the artifact's `args.gn` or
`args.full.txt` and rejects a requested API below that recorded minimum.

## Android 6.0 compatibility gate

CI links the smoke executable against API 23 system stubs for every architecture.
For API targets below 29, the runner also rejects native ELF TLS (`PT_TLS`) in
the executable or its C++ runtime. The x64 build runs all 14 checks in an actual
Android 6.0 emulator before uploading the release asset. Failed compatibility
checks prevent release publication.

Android 6.0's legacy ADB shell does not propagate a program's exit code. The
runner checks an explicit remote exit marker and all 14 successful checks, so a
loader error or crash cannot silently pass CI.

On the local Android 6.0 ARM64 emulator, the matching C++ runtime passed checks
for threads, emulated TLS, TLS destruction, hash tables, and `__hash_memory`.
The old API 29 V8 executable failed to load because `__fwrite_chk` was missing.
The rebuilt API 23 V8 artifact must pass its own smoke test before compatibility
is considered verified.

## 16 KiB compatibility gate

Android 6.0 / API 23 is the minimum OS version; it does not prevent the same
64-bit artifact from supporting newer 16 KiB-page devices. V8's pinned build
configuration uses 16 KiB linker alignment for arm64/x64, and its Android ARM64
embedded builtins are also aligned to 16 KiB. Runtime page sizes are detected
dynamically.

The runner rejects arm64/x64 executables or `libc++_shared.so` whose ELF `LOAD`
segments have alignment below 16384, or inconsistent file offsets and virtual
addresses. The 32-bit ARM runtime uses 4096-byte alignment. CI additionally runs
all 14 checks with the API 23 artifact in the API 35 `google_apis_ps16k` x86_64
image, requiring `getconf PAGE_SIZE` to return exactly 16384. Both the Android
6.0 and 16 KiB tests must pass before release upload/publication.

The published V8 library is a static `.a`, so final application linking and
packaging also matter. Link every final native `.so` with 16 KiB alignment
(NDK r28+ defaults, or explicit `-Wl,-z,max-page-size=16384` and
`-Wl,-z,common-page-size=16384`) and use AGP 8.5.1+ for uncompressed native
libraries. All packaged native dependencies, including the matching NDK 30 C++
runtime, must comply. Verify the final APK with `zipalign -c -P 16 -v 4 app.apk`.
See the [Android 16 KB page-size guide](https://developer.android.com/guide/practices/page-sizes).

## Verification on 2026-11-04

Artifacts: tag `v15.7.112.23-1`, workflow run `41770086489`.

- ARM64: 14/14 checks passed on an Android 16 / API 36 ARM64 emulator, with 4 KiB
  pages. Compiler: NDK 28.2.13676358; C++ runtime: NDK 30.0.16248370.
- ARM and x64: compiled and linked successfully; runtime execution has not been
  verified because the available emulator supports only ARM64.
- ARM64: 14/14 checks also passed on the official Android 15 / API 35 ARM64
  16 KiB system image. Both `getconf PAGE_SIZE` and the executable's
  `sysconf(_SC_PAGESIZE)` reported 16384. The executable and matching NDK 30
  C++ runtime passed the ELF load-alignment check.
- These runtime results use the older API 29 artifact. The rebuilt API 23
  artifact still needs its own Android 6.0 and 16 KiB CI checks; the older
  artifact's results do not establish Android 6.0 compatibility.
