# ANGLE (Metal) 后端支持 — macOS CI headless 渲染设计

日期: 2026-07-23
状态: 已确认（headless-only / 仅 CMake / 使用 kivy/angle-builder prebuilt）

## 目标

让 Panda3D 在 GitHub Actions 的 macOS runner（Apple Paravirtual 设备，只有
Metal 可用、无可用硬件 OpenGL）上能进行真实的 GPU 离屏渲染，使 pytest 中依赖
`graphics_pipe` / `gsg` fixture 的图形测试不再被跳过。

渲染链路：`Panda3D (pandagles2) -> EGL/GLES2 -> ANGLE -> Metal`。

## 非目标（本期不做）

- macOS 上通过 ANGLE 开真实 Cocoa 窗口（需要 CALayer/NSView 对接 EGLSurface）。
  本期只做 headless pbuffer 离屏渲染。
- GLES1 / 桌面 GL over ANGLE（ANGLE 只暴露 GLES）。
- 把 ANGLE 加入官方 thirdparty 打包仓库（可作为后续工作）。

## 背景与关键发现

- `panda/src/egldisplay` 已经支持无 X11 的 headless 渲染（`EGL_NO_X11` +
  pbuffer + `EGL_EXT_platform_device` 设备枚举），GSG 的 context 创建是标准
  EGL 调用，ANGLE 可以直接兼容。**不需要像 webgldisplay 那样从零写一套
  pipe/window/gsg**；webgl port 的价值在于证明了 gles2gsg 渲染管线的可移植性。
- 目前 egldisplay / GLES2 在两处被显式排除出 macOS：
  - `dtool/Package.cmake:786,797` — `if(NOT APPLE)`（原因是 Apple X11 的
    GLES 头文件损坏；用 ANGLE 自带头文件时该原因不成立）
  - `panda/src/egldisplay/CMakeLists.txt` — GLES2 分支无条件链接
    `p3x11display`（在无 X11 的平台上是 bug）
  - makepanda 同样在 darwin 上跳过 egldisplay（本期不处理，见"已确认决策"）
- CI 现状：macOS job（CMake 两个 profile + makepanda job）跑 pytest 时
  `make_default_pipe()` 无效，所有图形测试 skip。
- ANGLE 预编译产物有现成来源：[kivy/angle-builder](https://github.com/kivy/angle-builder)
  发布 macos-x64 / arm64 / universal 的 `libEGL.dylib`、`libGLESv2.dylib` 和
  include 头文件（Kivy 自己在 macOS CI 上就是这么用的）；备选
  [libgdx/gdx-angle-natives](https://github.com/libgdx/gdx-angle-natives)。

## 方案选型

考虑过的三个方案：

1. **复用 egldisplay，让它在 macOS 上以 ANGLE 为 EGL 实现编译（推荐，选定）**
   — 改动最小，headless 路径已存在且经过验证；ANGLE 就是一个 EGL 实现，
   本来就该走这条路。
2. 仿 webgldisplay 新建独立 `angledisplay` 模块 — 约 2000 行重复代码，只在
   将来做窗口化 ANGLE 时才有必要；headless 目标下没有收益。
3. 在 cocoadisplay 里加 ANGLE 窗口支持 — 范围远超 CI 需求。

## 设计

### 1. 构建系统（CMake 为主）

- `dtool/Package.cmake`：去掉 GLES1/GLES2/EGL 探测上的 `NOT APPLE` 门。改为
  正常 `find_package`，Apple X11 破损头文件的问题通过"找到的头文件必须可用"
  自然解决——CI 上通过 `-DOPENGLES2_INCLUDE_DIR=... -DEGL_INCLUDE_DIR=...`
  等缓存变量（或 `CMAKE_PREFIX_PATH` 指向 ANGLE 解包目录）显式指定 ANGLE
  的头文件和 dylib，避免误捡系统 X11 的破损头。
- `panda/src/egldisplay/CMakeLists.txt`：
  - 修正 GLES1/GLES2 分支：只有 `HAVE_X11` 时才链接 `p3x11display`
    （顺带修掉现有的 `target_link_librarise` 拼写错误）。
  - macOS 上允许构建 `p3egldisplay_gles2`（桌面 GL over EGL 分支维持
    `NOT APPLE`，因为 ANGLE 不支持 `EGL_OPENGL_API`）。
- metalib `pandagles2` 在 macOS 上照常生成，运行时通过
  `load-display pandagles2` 加载。
- 链接产物对 ANGLE dylib 的运行时定位：CI 测试步骤用 `DYLD_LIBRARY_PATH`
  指向 ANGLE lib 目录（现有 makepanda 测试步骤已经在设置 DYLD_LIBRARY_PATH，
  沿用同一机制），不引入 install_name/rpath 改动。

### 2. egldisplay 代码改动（小）

- 新增 PRC 变量 `egl-angle-platform`（`default|metal|opengl|vulkan|swiftshader`，
  默认 `default`）。当 EGL 客户端扩展包含 `EGL_ANGLE_platform_angle` 且该变量
  非 default 时，用 `eglGetPlatformDisplayEXT(EGL_PLATFORM_ANGLE_ANGLE, ...,
  {EGL_PLATFORM_ANGLE_TYPE_ANGLE: <type>})` 获取 display，替代
  `eglGetDisplay(EGL_DEFAULT_DISPLAY)`。所需枚举常量若 eglext.h 未提供则在
  本地补充定义（带 ANGLE 注册值）。
  - 这一步严格说是可选的（新版 ANGLE 在 macOS 默认后端就是 Metal），但显式
    可控便于 CI 固定行为和本地调试。
- 其余 pipe/buffer/GSG 代码不动。

### 3. CI 集成（.github/workflows/ci.yml，macOS CMake profile）

- 新增步骤：从 kivy/angle-builder release 下载**固定版本**的 macos-universal
  压缩包，解包到 `thirdparty/darwin-libs-a/angle`（或独立目录），并在 CMake
  configure 时传入头文件/库路径。
- pytest 步骤（macOS）设置：
  - `DYLD_LIBRARY_PATH` 追加 ANGLE lib 目录；
  - PRC 配置 `load-display pandagles2`（通过环境变量注入，如
    `PANDA_PRC_DIR` 指向一个生成的 prc 文件，或现有等效机制）；
  - 可选 `egl-angle-platform metal` 固化后端。
- 预期结果分两层验收：
  1. `make_default_pipe()` 返回有效 pipe，`gsg` fixture 能创建离屏 buffer；
  2. 图形测试在 GLES2 下的通过情况——允许存在因 GLES2 特性差异导致的
     个别失败，逐个用 skip/xfail 标注（不属于本设计的阻塞项）。

### 4. 错误处理

- ANGLE dylib 缺失/加载失败：EGL display 初始化失败 → pipe `is_valid()` 为
  false → 测试照旧 skip（回到现状，不会更糟）。
- `egl-angle-platform` 请求的后端不可用：打 warning 后回退到
  `eglGetDisplay(EGL_DEFAULT_DISPLAY)`。

### 5. 测试策略

- 本地无 macOS 环境，验证以 CI 为准：先在分支上推 CI 观察 macOS job。
- Linux job 回归：egldisplay 的 CMake/代码改动不得破坏现有
  linux EGL 构建（CI 的 ubuntu profile 覆盖）。
- 可在 Linux 本地先验证 CMake 改动的构建正确性。

## 已确认决策（2026-07-23 用户确认）

1. 范围：只做 headless 离屏渲染，不做 macOS 真实窗口。
2. 构建系统：只做 CMake；makepanda 的 macOS 支持不在本期范围。
3. ANGLE 二进制：直接使用 kivy/angle-builder 的 release（固定版本 URL）；
   如将来发现需要修改 ANGLE 构建参数，再考虑 fork 自托管。
