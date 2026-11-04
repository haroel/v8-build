#!/usr/bin/env python3
"""Build and run the standalone Android V8 smoke test.

Artifact layout:
  <artifacts>/headers/include/v8.h
  <artifacts>/{arm64,arm,x64}/libv8_monolith.a

The shared libc++ runtime must match the V8 archive (NDK 30 for V8 15.7.112.23).
Use --runtime-ndk when that runtime comes from a Chromium NDK repack without a
compiler; --ndk still selects the complete local compiler/header toolchain.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import re
import secrets
import shlex
import shutil
import subprocess
import sys


ARCHITECTURES = {
    "arm64": ("aarch64-linux-android", "aarch64-linux-android", "arm64-v8a"),
    "arm": ("armv7a-linux-androideabi", "arm-linux-androideabi", "armeabi-v7a"),
    "x64": ("x86_64-linux-android", "x86_64-linux-android", "x86_64"),
}
MINIMUM_API = 23


class CommandFailed(RuntimeError):
    def __init__(self, command: list[str], returncode: int):
        super().__init__(f"Command exited with {returncode}: {shlex.join(command)}")
        self.returncode = returncode


class CommandLog:
    def __init__(self, path: Path):
        self.path = path
        self.file = path.open("w", encoding="utf-8")

    def write(self, message: str) -> None:
        print(message, flush=True)
        self.file.write(message + "\n")
        self.file.flush()

    def run(self, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        self.write("$ " + shlex.join(command))
        output: list[str] = []
        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        ) as process:
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    output.append(line)
                    print(line, end="", flush=True)
                    self.file.write(line)
                    self.file.flush()
                returncode = process.wait()
            except KeyboardInterrupt:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise
        self.write(f"[exit {returncode}]")
        if check and returncode:
            raise CommandFailed(command, returncode)
        return subprocess.CompletedProcess(command, returncode, "".join(output))

    def close(self) -> None:
        self.file.close()


def existing_file(path: Path, description: str) -> Path:
    if not path.is_file():
        raise RuntimeError(f"{description} not found: {path}")
    return path


def artifact_api(directory: Path) -> tuple[int, Path]:
    args = directory / "args.gn"
    if args.is_file():
        match = re.search(
            r"^\s*android_ndk_api_level\s*=\s*(\d+)\s*(?:#.*)?$",
            args.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match:
            return int(match.group(1)), args
    full_args = directory / "args.full.txt"
    if full_args.is_file():
        match = re.search(
            r"^android_ndk_api_level\s*\n"
            r"\s+Current value(?: \([^\n]*\))? = (\d+)\s*$",
            full_args.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match:
            return int(match.group(1)), full_args
    raise RuntimeError(
        f"Cannot determine artifact Android API: {directory} must contain "
        "args.gn with an explicit android_ndk_api_level or args.full.txt "
        "with its current value"
    )


def host_prebuilts(ndk: Path) -> list[Path]:
    host_prefix = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}.get(
        platform.system()
    )
    if host_prefix is None:
        raise RuntimeError(f"Unsupported build host: {platform.system()}")

    return sorted((ndk / "toolchains/llvm/prebuilt").glob(host_prefix + "*"))


def ndk_compiler(ndk: Path, arch: str, api: int) -> list[str]:
    driver_triple = ARCHITECTURES[arch][0]
    for prebuilt in host_prebuilts(ndk):
        wrapper = prebuilt / "bin" / f"{driver_triple}{api}-clang++"
        compiler = prebuilt / "bin" / ("clang++.exe" if os.name == "nt" else "clang++")
        if os.name != "nt" and wrapper.is_file():
            return [str(wrapper)]
        # Chromium's NDK packages may omit the API wrappers. The underlying
        # Clang driver accepts the identical target/API selection directly.
        if compiler.is_file():
            return [str(compiler), f"--target={driver_triple}{api}"]
    raise RuntimeError(f"No {arch} API {api} Clang toolchain under {ndk}")


def ndk_readelf(ndk: Path) -> Path:
    name = "llvm-readelf.exe" if os.name == "nt" else "llvm-readelf"
    for prebuilt in host_prebuilts(ndk):
        readelf = prebuilt / "bin" / name
        if readelf.is_file():
            return readelf
    raise RuntimeError(f"No {name} under compiler NDK {ndk}")


def check_elf_compatibility(
    log: CommandLog, readelf: Path, path: Path, api: int, page_size: int
) -> None:
    result = log.run([str(readelf), "--program-headers", "--wide", str(path)])
    native_tls = bool(re.search(r"^\s*(?:PT_)?TLS\s+", result.stdout, re.MULTILINE))
    log.write(
        f"ELF TLS check: {path}; PT_TLS {'present' if native_tls else 'absent'}; "
        f"target Android API {api}"
    )
    if native_tls and api < 29:
        raise RuntimeError(
            f"{path} contains native ELF TLS (PT_TLS), which requires Android "
            f"API 29; rebuild with emulated TLS for API {api}"
        )
    loads = [line.split() for line in result.stdout.splitlines()
             if re.match(r"^\s*(?:PT_)?LOAD\s+", line)]
    if not loads:
        raise RuntimeError(f"No ELF LOAD segments found in {path}")
    for fields in loads:
        try:
            offset, address, alignment = (
                int(fields[1], 0), int(fields[2], 0), int(fields[-1], 0)
            )
        except (IndexError, ValueError) as error:
            raise RuntimeError(f"Malformed ELF LOAD segment in {path}: {fields}") from error
        if (alignment < page_size or alignment & (alignment - 1)
                or (address - offset) % alignment):
            raise RuntimeError(
                f"{path} has an incompatible ELF LOAD segment: offset={offset:#x}, "
                f"address={address:#x}, alignment={alignment:#x}; "
                f"requires at least {page_size}-byte page alignment"
            )
    log.write(
        f"ELF LOAD alignment verified: {path}; {len(loads)} segments; "
        f"at least {page_size} bytes"
    )


def ndk_runtime(ndk: Path, arch: str) -> Path:
    library_triple = ARCHITECTURES[arch][1]
    # The Android runtime is independent of its package's host OS. Prefer the
    # local host package, but also accept a repack downloaded for another host.
    preferred = host_prebuilts(ndk)
    others = sorted((ndk / "toolchains/llvm/prebuilt").glob("*"))
    for prebuilt in preferred + [p for p in others if p not in preferred]:
        runtime = prebuilt / "sysroot/usr/lib" / library_triple / "libc++_shared.so"
        if runtime.is_file():
            return runtime
    raise RuntimeError(f"No {arch} libc++_shared.so under runtime NDK {ndk}")


def adb_path() -> str:
    found = shutil.which("adb")
    if found:
        return found
    roots = [
        os.environ.get("ANDROID_SDK_ROOT"),
        os.environ.get("ANDROID_HOME"),
        str(Path.home() / "Library/Android/sdk"),
        str(Path.home() / "Android/Sdk"),
    ]
    name = "adb.exe" if os.name == "nt" else "adb"
    for root in roots:
        if root and (Path(root) / "platform-tools" / name).is_file():
            return str(Path(root) / "platform-tools" / name)
    raise RuntimeError("adb not found. Add Android SDK platform-tools to PATH.")


def device_command(log: CommandLog, serial: str | None) -> list[str]:
    adb = adb_path()
    if serial is None:
        result = log.run([adb, "devices"])
        devices = []
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[1] == "device":
                devices.append(fields[0])
        if len(devices) != 1:
            raise RuntimeError(
                f"Expected one connected, authorized adb device; found {len(devices)}. "
                "Connect a device/emulator or select one with --serial."
            )
        serial = devices[0]
    command = [adb, "-s", serial]
    state_lines = log.run(command + ["get-state"]).stdout.strip().splitlines()
    state = state_lines[-1] if state_lines else ""
    if state != "device":
        raise RuntimeError(f"adb device {serial} is not ready: {state}")
    return command


def run_remote_smoke(
    log: CommandLog, adb: list[str], command: str, token: str
) -> None:
    marker = f"V8_SMOKE_EXIT_{token}"
    status_format = "\\n" + marker + "=%s\\n"
    # API 23 adbd uses shell v1, which can report success after a remote crash.
    # A subshell also lets us capture an explicit exit or signal from the test.
    script = (
        f"( {command} ); v8_smoke_status=$?; "
        f"printf {shlex.quote(status_format)} \"$v8_smoke_status\""
    )
    result = log.run(adb + ["shell", script], check=False)
    if result.returncode:
        raise RuntimeError(f"adb test transport failed with exit {result.returncode}")
    lines = result.stdout.splitlines()
    status_lines = [line for line in lines if line.startswith(marker)]
    if len(status_lines) != 1:
        raise RuntimeError("Missing or ambiguous remote smoke-test exit status")
    match = re.fullmatch(re.escape(marker) + r"=([0-9]+)", status_lines[0])
    if match is None:
        raise RuntimeError(f"Malformed remote smoke-test exit status: {status_lines[0]!r}")
    status = int(match.group(1))
    if status:
        raise RuntimeError(f"Remote smoke test exited with {status}")
    if "SUCCESS: 14 checks passed" not in lines:
        raise RuntimeError("Remote smoke test did not report SUCCESS: 14 checks passed")
    log.write("Remote smoke test verified: exit 0; 14 checks passed")


def run_on_device(
    log: CommandLog, binary: Path, runtime: Path, arch: str, api: int,
    serial: str | None, expected_page_size: int | None = None
) -> None:
    adb = device_command(log, serial)
    device_abi = ARCHITECTURES[arch][2]
    abi_list = log.run(adb + ["shell", "getprop", "ro.product.cpu.abilist"]).stdout.strip()
    if not abi_list:
        abi_list = log.run(adb + ["shell", "getprop", "ro.product.cpu.abi"]).stdout.strip()
    if device_abi not in abi_list.split(","):
        raise RuntimeError(f"Device ABIs {abi_list!r} do not support {device_abi}")
    sdk = log.run(adb + ["shell", "getprop", "ro.build.version.sdk"]).stdout.strip()
    if not sdk.isdigit() or int(sdk) < api:
        raise RuntimeError(f"Device API {sdk!r} is below the test's API {api}")
    page_size = log.run(adb + ["shell", "getconf", "PAGE_SIZE"]).stdout.strip()
    if not page_size.isdigit():
        raise RuntimeError(f"Cannot determine device page size: {page_size!r}")
    log.write(f"Device page size: {page_size} bytes")
    if expected_page_size is not None and int(page_size) != expected_page_size:
        raise RuntimeError(
            f"Device page size is {page_size}, expected {expected_page_size}; "
            "use a system image with the required page size"
        )

    remote = f"/data/local/tmp/v8-smoke-{arch}-{os.getpid()}-{secrets.token_hex(4)}"
    if not re.fullmatch(r"/data/local/tmp/v8-smoke-(arm64|arm|x64)-\d+-[0-9a-f]{8}", remote):
        raise RuntimeError("Refusing an unexpected remote test directory")
    created = False
    failed = False
    try:
        # No -p: this run must create and own a fresh directory before cleanup.
        log.run(adb + ["shell", "mkdir", remote])
        created = True
        log.run(adb + ["push", str(binary), remote + "/v8_smoke"])
        log.run(adb + ["push", str(runtime), remote + "/libc++_shared.so"])
        log.run(adb + ["shell", "chmod", "755", remote + "/v8_smoke"])
        command = f"LD_LIBRARY_PATH={shlex.quote(remote)} {shlex.quote(remote + '/v8_smoke')}"
        run_remote_smoke(log, adb, command, remote.rsplit("/", 1)[-1])
    except BaseException:
        failed = True
        raise
    finally:
        if created:
            cleanup = log.run(adb + ["shell", "rm -rf " + shlex.quote(remote)], check=False)
            if cleanup.returncode:
                message = f"Could not clean this run's test directory: {remote}"
                if failed:
                    log.write("WARNING: " + message)
                else:
                    raise RuntimeError(message)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and run tests/android/smoke.cc against Android V8 release artifacts.",
        epilog=(
            "Example: python3 tests/android/run_smoke.py "
            "--artifacts scratch/android-smoke/artifacts/v15.7.112.23-1 "
            "--ndk /path/to/compiler-ndk --runtime-ndk /path/to/chromium-ndk-30 "
            "--arch arm64 --serial emulator-5554"
        ),
    )
    parser.add_argument("--artifacts", type=Path, required=True, help="Artifact root containing headers/include and architecture directories")
    parser.add_argument("--ndk", type=Path, required=True, help="Complete Android NDK compiler/header toolchain root")
    parser.add_argument("--runtime-ndk", type=Path, help="NDK supplying the matching libc++_shared.so (default: --ndk; V8 15.7.112.23 needs NDK 30 runtime)")
    parser.add_argument("--arch", choices=ARCHITECTURES, default="arm64", help="V8 artifact architecture (default: arm64)")
    parser.add_argument("--api", type=int, default=MINIMUM_API, help="Android target API, at least 23 / Android 6.0 (default: 23; must meet the artifact's API floor)")
    parser.add_argument("--output", type=Path, help="Build/log directory (default: build/android-smoke/<arch>)")
    parser.add_argument("--serial", help="adb device serial; required when multiple devices are connected")
    parser.add_argument("--page-size", type=int, choices=(4096, 16384), help="Require this device page size before running (bytes)")
    parser.add_argument("--build-only", action="store_true", help="Build without querying or modifying any device")
    args = parser.parse_args()
    if args.api < MINIMUM_API:
        parser.error(f"--api must be at least {MINIMUM_API} (Android 6.0)")
    return args


def main() -> int:
    args = parse_arguments()
    repo = Path(__file__).resolve().parents[2]
    artifacts = args.artifacts.expanduser().resolve()
    ndk = args.ndk.expanduser().resolve()
    runtime_ndk = args.runtime_ndk.expanduser().resolve() if args.runtime_ndk else ndk
    output = (args.output.expanduser() if args.output else repo / "build/android-smoke" / args.arch).resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = CommandLog(output / "smoke.log")
    try:
        source = existing_file(Path(__file__).resolve().with_name("smoke.cc"), "Smoke test source")
        headers = artifacts / "headers/include"
        existing_file(headers / "v8.h", "V8 headers")
        library = existing_file(artifacts / args.arch / "libv8_monolith.a", "V8 archive")
        log.write(f"Architecture: {args.arch}; Android target API: {args.api}")
        log.write(f"V8 artifacts: {artifacts}")
        api_floor, metadata = artifact_api(artifacts / args.arch)
        log.write(f"Artifact Android API floor: {api_floor} (from {metadata})")
        if args.api < api_floor:
            raise RuntimeError(
                f"Requested Android API {args.api} is below the artifact's API "
                f"floor {api_floor}; rebuild V8 for API {args.api} before testing"
            )
        compiler = ndk_compiler(ndk, args.arch, args.api)
        readelf = ndk_readelf(ndk)
        shared_runtime = ndk_runtime(runtime_ndk, args.arch)
        runtime = output / "libc++_shared.so"
        if shared_runtime.resolve() != runtime.resolve():
            # Chromium's repack can mark its files read-only. Do not preserve
            # that mode in this run's output or a second smoke run cannot
            # replace the previously copied runtime.
            runtime.unlink(missing_ok=True)
            shutil.copyfile(shared_runtime, runtime)
        binary = output / "v8_smoke"
        log.write(f"NDK: {ndk}")
        log.write(f"Runtime NDK: {runtime_ndk}")
        log.write(f"Matching C++ runtime: {shared_runtime}")
        command = compiler + [
            "-std=c++20", "-O2", "-fno-rtti", "-fno-exceptions",
            "-fPIE", "-pie", "-Wl,-z,max-page-size=16384",
            "-Wl,-z,common-page-size=16384", "-isystem", str(headers),
            # Do not add this directory to -L: Chromium repacks also contain
            # private bionic static libraries which must not replace the
            # compiler NDK's API-specific Android system stubs.
            str(source), str(library), "-nostdlib++", str(shared_runtime),
            "-llog", "-ldl", "-lm", "-latomic", "-landroid",
            "-o", str(binary),
        ]
        log.run(command)
        # Android's 16 KiB requirement applies to 64-bit ABIs. The 32-bit NDK
        # runtime continues to use 4 KiB segments and is tested separately.
        elf_page_size = 4096 if args.arch == "arm" else 16384
        check_elf_compatibility(log, readelf, binary, args.api, elf_page_size)
        check_elf_compatibility(log, readelf, runtime, args.api, elf_page_size)
        log.write(f"Built: {binary}")
        if not args.build_only:
            run_on_device(log, binary, runtime, args.arch, args.api, args.serial, args.page_size)
        log.write(f"Log: {log.path}")
        return 0
    except CommandFailed as error:
        log.write("ERROR: " + str(error))
        return error.returncode if 0 < error.returncode < 126 else 1
    except (OSError, RuntimeError) as error:
        log.write("ERROR: " + str(error))
        return 1
    except KeyboardInterrupt:
        log.write("Interrupted")
        return 130
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main())
