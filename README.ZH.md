# V8 单体静态库构建

本仓库使用 GitHub Actions 自动化构建多平台的 Google V8 静态库。

[English](README.md) | 简体中文

## 当前 V8 版本

**15.7.112.23**

## 支持平台

- **Android** (arm64, arm, x64)
- **iOS** (XCFramework: arm64 真机、arm64 模拟器)
- **macOS** (XCFramework: arm64 Apple Silicon)
- **Windows** (x64，Release + Debug)

## 最新版本

访问 [Releases](../../releases) 页面获取最新的预编译二进制文件。

## 包内容

每个发布版本的 zip 包包含：
- **静态库文件** (libv8_monolith.a / v8_monolith.lib)
- **args.gn** - 编译时使用的构建配置
- **args.full.txt** - 完整的 GN 参数列表，包含所有默认值和说明

## 构建产物

| 平台 | 产物文件 | 架构 | 说明 |
|------|---------|------|------|
| Android  | `libv8_monolith-android-arm64.zip` | arm64 | 静态库 + args.gn + args.full.txt |
| Android  | `libv8_monolith-android-arm.zip` | arm | 静态库 + args.gn + args.full.txt |
| Android  | `libv8_monolith-android-x64.zip` | x64 | 静态库 + args.gn + args.full.txt |
| Android  | `include-android.zip` | - | V8 头文件 |
| Apple    | `libv8_monolith-apple.zip` | arm64（iOS 真机+模拟器+macOS） | 单个 XCFramework，含每个切片的头文件 + args.gn + args.full.txt |
| Windows  | `libv8_monolith-win-x64-release.zip` | x64 | Release 静态库 + args.gn + args.full.txt |
| Windows  | `libv8_monolith-win-x64-debug.zip` | x64 | Debug 静态库 + args.gn + args.full.txt |
| Windows  | `include-win.zip` | - | V8 头文件 |

## 构建配置文件

本仓库包含各平台的 GN 构建配置文件：

### Android
- [args.android.arm64.gn](args.android.arm64.gn)
- [args.android.arm.gn](args.android.arm.gn)
- [args.android.x64.gn](args.android.x64.gn)

### Apple（iOS + macOS）

- [args.ios.arm64.gn](args.ios.arm64.gn) - iOS 真机
- [args.ios.arm64.simulator.gn](args.ios.arm64.simulator.gn) - iOS 模拟器
- [args.mac.arm64.gn](args.mac.arm64.gn) - macOS Apple Silicon

`libv8_monolith-apple.zip` 包含一个 XCFramework，提供三个 arm64 切片：

```
libv8_monolith.xcframework/
├── ios-arm64/
├── ios-arm64-simulator/
└── macos-arm64/
```

每个切片都有独立的 `libv8_monolith.framework`，包含静态库、`Info.plist` 和该切片构建时生成的头文件。iOS 保持关闭 JavaScript JIT、WebAssembly、DrumBrake、指针压缩及 cppgc caged heap；macOS 保持启用 WebAssembly。

在 Xcode 中使用：

1. 将 `libv8_monolith.xcframework` 拖入项目。
2. 添加到 "Frameworks, Libraries, and Embedded Content"。
3. 导入头文件：`#include <libv8_monolith/v8.h>`。
4. Xcode 自动选择对应的平台切片。

### Windows

- [args.win.x64.release.gn](args.win.x64.release.gn) - Release
- [args.win.x64.debug.gn](args.win.x64.debug.gn) - Debug

### XCFramework 配置
- [Info.plist.template](Info.plist.template) - XCFramework Info.plist 模板文件（构建时自动替换版本号）

## 特性

- ✅ 通过 GitHub Actions 自动化构建
- ✅ 跨平台统一配置
- ✅ 编译前验证源码版本 ([builder.js](builder.js))
- ✅ 完整的构建参数可追溯性
- ✅ Apple 各平台共用一个 XCFramework，保留各切片独立头文件
- ✅ Windows 提供 Release 和 Debug 包

## 使用方法

1. 从 [Releases](../../releases) 页面下载适合您平台的 zip 文件
2. 解压静态库文件
3. 在您的项目中链接该库
4. 包含 V8 头文件（包含在发布版本中）
5. 参考 `args.gn` 和 `args.full.txt` 了解构建配置详情

## 构建系统

所有构建均通过 [GitHub Actions](.github/workflows/main.yml) 自动化完成：
- 为每个平台提供干净的构建环境
- 源码与依赖锁定到同一个 V8 标签
- 可重现的构建过程
- 自动创建发布版本

Android 使用 V8 `DEPS` 固定的 NDK 和 Clang，不需要单独安装 NDK。同步依赖和 hooks 完成后，CI 在生成 GN 构建文件前安装并检查 amd64 主机 sysroot，以及 ARM 快照生成所需的 i386 sysroot 和运行库。缺少头文件或启动库时会立即停止构建，并报告对应的绝对路径。

所有平台在编译前检查 `include/v8-version.h`，并拒绝无效的 GN 参数。各平台设置直接声明在 GN 文件中，不修改 V8 源码。Windows CI 会安装此 V8 版本要求的 SDK `10.0.28000.0`。

## V8 文档

### V8 官方资源
- [V8 构建说明](https://v8.dev/docs/build)
- [使用 GN 构建 V8](https://v8.dev/docs/build-gn)
- [V8 ARM64 构建](https://v8.dev/docs/compile-arm64)

### Chromium 构建说明
- [Windows 构建说明](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/windows_build_instructions.md)
- [Android 构建说明](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/android_build_instructions.md)
- [iOS 构建说明](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/ios/build_instructions.md)
- [macOS 构建说明](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/mac_build_instructions.md)
- [macOS ARM64 构建](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/mac_arm64.md)

### 其他资源
- [V8 发布计划](https://chromiumdash.appspot.com/schedule)
- [GitHub Actions Runner 镜像](https://github.com/actions/runner-images)

## 贡献

更新 V8 版本或修改构建配置：

1. 在 [.github/workflows/main.yml](.github/workflows/main.yml) 中更新 `V8_VERSION`
2. 根据需要修改平台特定的 `args.*.gn` 文件
3. 更新 [builder.js](builder.js) 中的平台特定构建逻辑
4. 创建新的 git 标签以触发构建工作流

## 致谢

本项目受到 [just-js/v8](https://github.com/just-js/v8) 的启发并参考了其相关工作。

## 许可证

本仓库包含构建配置和自动化脚本。V8 本身采用 BSD 许可证。详情请参阅 [V8 仓库](https://github.com/v8/v8)。

