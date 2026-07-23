# ANGLE (Metal) macOS Headless Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 GitHub CI 的 macOS runner 通过 `pandagles2 → EGL/GLES2 → ANGLE → Metal` 做 headless 离屏渲染，使 pytest 图形测试不再被跳过。

**Architecture:** 复用现有 `panda/src/egldisplay` 的 headless 路径（pbuffer + `EGL_NO_X11`），在 CMake 侧解除 macOS 上 GLES2/EGL 的探测限制并修复无 X11 平台的链接 bug；egldisplay 新增一个 PRC 变量用 `EGL_ANGLE_platform_angle` 扩展显式选 ANGLE 的 Metal 后端；CI 下载 kivy/angle-builder 的 prebuilt ANGLE 并配置 CMake 与 PRC。

**Tech Stack:** CMake、C++（Panda3D egldisplay）、GitHub Actions YAML、ANGLE prebuilt (kivy/angle-builder)。

设计规格见 `docs/superpowers/specs/2026-07-23-angle-macos-backend-design.md`。

## Global Constraints

- 仅改 CMake 构建系统；**不改 makepanda**（makepanda.py 一行都不能动）。
- 仅 headless 离屏；不实现 macOS 真实窗口。
- 不得回归 Linux 的 EGL/GLX 构建（CI ubuntu profile 必须保持绿色）。
- ANGLE 版本固定：kivy/angle-builder release `chromium-7151_rev1`，资产
  `angle-macos-universal.tar.gz`，SHA256
  `b87f1d0144218a0699859340bfc9864949190d5f4b4d19d4265c3ab561fcd078`。
- 该 tarball 布局：`./include/`（EGL/GLES2/KHR 等头文件）、`./libEGL.dylib`、
  `./libGLESv2.dylib`（install name 均为 `@rpath/libXXX.dylib`）、`./LICENSE`。
- C++ 代码风格遵循 panda3d 惯例（文件头注释、2 空格缩进、`egldisplay_cat` 日志）。
- 工作分支：`angle-macos-headless`（已存在，spec 已提交在其上）。

---

### Task 1: CMake — 解除 Apple 上的 GLES 探测限制并修复无 X11 链接

**Files:**
- Modify: `dtool/Package.cmake:785-805`（GLES1/GLES2 探测的 `NOT APPLE` 门）
- Modify: `panda/src/egldisplay/CMakeLists.txt`（GLES1/GLES2 分支无条件链接 `p3x11display` 的 bug；GL 分支 `target_link_librarise` 拼写错误）
- Modify: `panda/metalibs/pandagles2/CMakeLists.txt`（COMPONENTS 无条件含 `p3x11display`）
- Modify: `panda/metalibs/pandagles/CMakeLists.txt`（同上）

**Interfaces:**
- Consumes: 无（首个任务）。
- Produces: CMake 配置项 —— 在 macOS 上传入 `-DOPENGLES2_INCLUDE_DIR`、`-DOPENGLES2_LIBRARY`、`-DEGL_INCLUDE_DIR`、`-DEGL_LIBRARY` 后，`HAVE_GLES2`/`HAVE_EGL` 生效并产出 `pandagles2` 模块。Task 3 的 CI configure 依赖这组变量名。

- [ ] **Step 1: 确认本地 Linux 有 GLES2/EGL 开发头文件（验证环境）**

```bash
ls /usr/include/GLES2/gl2.h /usr/include/EGL/egl.h
```

若不存在，安装（Fedora）：`sudo dnf install mesa-libGLES-devel mesa-libEGL-devel`。

- [ ] **Step 2: 修改 `dtool/Package.cmake`**

把（约 786 行起）：

```cmake
# OpenGL ES 1
if(NOT APPLE) # Apple X11 ships the GLES headers but they're broken
  find_package(OpenGLES1 QUIET)
endif()
```

改为：

```cmake
# OpenGL ES 1
# NB. Apple X11 ships broken GLES headers, so on Apple platforms we only look
# for GLES if the user explicitly points us to an implementation (e.g. ANGLE)
# via -DOPENGLES1_INCLUDE_DIR/-DOPENGLES1_LIBRARY.
if(NOT APPLE OR OPENGLES1_INCLUDE_DIR)
  find_package(OpenGLES1 QUIET)
endif()
```

把（约 797 行起）：

```cmake
# OpenGL ES 2
if(NOT APPLE) # Apple X11 ships the GLES headers but they're broken
  find_package(OpenGLES2 QUIET)
endif()
```

改为：

```cmake
# OpenGL ES 2
# NB. Apple X11 ships broken GLES headers, so on Apple platforms we only look
# for GLES if the user explicitly points us to an implementation (e.g. ANGLE)
# via -DOPENGLES2_INCLUDE_DIR/-DOPENGLES2_LIBRARY.
if(NOT APPLE OR OPENGLES2_INCLUDE_DIR)
  find_package(OpenGLES2 QUIET)
endif()
```

- [ ] **Step 3: 修改 `panda/src/egldisplay/CMakeLists.txt`**

3a. GL 分支拼写修复——把：

```cmake
  if(HAVE_X11 AND NOT HAVE_GLX)
    target_link_librarise(p3egldisplay_gl p3x11display)
    target_compile_definitions(p3egldisplay_gl PUBLIC USE_X11)
```

改为：

```cmake
  if(HAVE_X11 AND NOT HAVE_GLX)
    target_link_libraries(p3egldisplay_gl p3x11display)
    target_compile_definitions(p3egldisplay_gl PUBLIC USE_X11)
```

3b. GLES1 分支——把：

```cmake
  target_compile_definitions(p3egldisplay_gles1 PUBLIC OPENGLES_1)
  target_link_libraries(p3egldisplay_gles1 p3glesgsg p3x11display
    PKG::EGL PKG::GLES1)

  if(HAVE_X11)
    target_compile_definitions(p3egldisplay_gles1 PUBLIC USE_X11)
  else()
    target_compile_definitions(p3egldisplay_gles1 PRIVATE EGL_NO_X11)
  endif()
```

改为：

```cmake
  target_compile_definitions(p3egldisplay_gles1 PUBLIC OPENGLES_1)
  target_link_libraries(p3egldisplay_gles1 p3glesgsg
    PKG::EGL PKG::GLES1)

  if(HAVE_X11)
    target_link_libraries(p3egldisplay_gles1 p3x11display)
    target_compile_definitions(p3egldisplay_gles1 PUBLIC USE_X11)
  else()
    target_compile_definitions(p3egldisplay_gles1 PRIVATE EGL_NO_X11)
  endif()
```

3c. GLES2 分支——把：

```cmake
  target_compile_definitions(p3egldisplay_gles2 PUBLIC OPENGLES_2)
  target_link_libraries(p3egldisplay_gles2 p3gles2gsg p3x11display
    PKG::EGL PKG::GLES2)

  if(HAVE_X11)
    target_compile_definitions(p3egldisplay_gles2 PUBLIC USE_X11)
  else()
    target_compile_definitions(p3egldisplay_gles2 PRIVATE EGL_NO_X11)
  endif()
```

改为：

```cmake
  target_compile_definitions(p3egldisplay_gles2 PUBLIC OPENGLES_2)
  target_link_libraries(p3egldisplay_gles2 p3gles2gsg
    PKG::EGL PKG::GLES2)

  if(HAVE_X11)
    target_link_libraries(p3egldisplay_gles2 p3x11display)
    target_compile_definitions(p3egldisplay_gles2 PUBLIC USE_X11)
  else()
    target_compile_definitions(p3egldisplay_gles2 PRIVATE EGL_NO_X11)
  endif()
```

- [ ] **Step 4: 修改 `panda/metalibs/pandagles2/CMakeLists.txt`**

把：

```cmake
set(CMAKE_INSTALL_DEFAULT_COMPONENT_NAME "OpenGLES2Devel")
add_metalib(pandagles2 ${MODULE_TYPE}
  INCLUDE eglGraphicsPipe.h
  INIT init_libpandagles2 pandagles2.h
  EXPORT int get_pipe_type_pandagles2 "eglGraphicsPipe::get_class_type().get_index()"
  COMPONENTS p3egldisplay_gles2 p3gles2gsg p3glstuff p3x11display)
unset(CMAKE_INSTALL_DEFAULT_COMPONENT_NAME)
```

改为：

```cmake
set(PANDAGLES2_COMPONENTS p3egldisplay_gles2 p3gles2gsg p3glstuff)
if(HAVE_X11)
  list(APPEND PANDAGLES2_COMPONENTS p3x11display)
endif()

set(CMAKE_INSTALL_DEFAULT_COMPONENT_NAME "OpenGLES2Devel")
add_metalib(pandagles2 ${MODULE_TYPE}
  INCLUDE eglGraphicsPipe.h
  INIT init_libpandagles2 pandagles2.h
  EXPORT int get_pipe_type_pandagles2 "eglGraphicsPipe::get_class_type().get_index()"
  COMPONENTS ${PANDAGLES2_COMPONENTS})
unset(CMAKE_INSTALL_DEFAULT_COMPONENT_NAME)
```

- [ ] **Step 5: 修改 `panda/metalibs/pandagles/CMakeLists.txt`**

把：

```cmake
set(CMAKE_INSTALL_DEFAULT_COMPONENT_NAME "OpenGLES1Devel")
add_metalib(pandagles ${MODULE_TYPE}
  INCLUDE "${GLES1_PIPE_INCLUDE}"
  INIT init_libpandagles pandagles.h
  EXPORT int get_pipe_type_pandagles "${GLES1_PIPE_TYPE}::get_class_type().get_index()"
  COMPONENTS p3egldisplay_gles1 p3glesgsg p3glstuff p3x11display)
unset(CMAKE_INSTALL_DEFAULT_COMPONENT_NAME)
```

改为：

```cmake
set(PANDAGLES_COMPONENTS p3egldisplay_gles1 p3glesgsg p3glstuff)
if(HAVE_X11)
  list(APPEND PANDAGLES_COMPONENTS p3x11display)
endif()

set(CMAKE_INSTALL_DEFAULT_COMPONENT_NAME "OpenGLES1Devel")
add_metalib(pandagles ${MODULE_TYPE}
  INCLUDE "${GLES1_PIPE_INCLUDE}"
  INIT init_libpandagles pandagles.h
  EXPORT int get_pipe_type_pandagles "${GLES1_PIPE_TYPE}::get_class_type().get_index()"
  COMPONENTS ${PANDAGLES_COMPONENTS})
unset(CMAKE_INSTALL_DEFAULT_COMPONENT_NAME)
```

- [ ] **Step 6: 本地验证——常规 Linux 配置（含 X11）能配置并构建 pandagles2**

```bash
cd /home/bowmanhan/Code/panda3d
cmake -B build-angle -G Ninja -DHAVE_PYTHON=NO -DBUILD_METALIBS=YES 2>&1 | tail -20
cmake --build build-angle --target pandagles2 --parallel 2>&1 | tail -5
```

预期：configure 输出的 package 汇总中 `OpenGL ES 2.x` 为 enabled；构建以 exit code 0 结束（`echo $?` 为 0）。若本机无 Ninja，去掉 `-G Ninja` 用默认 Makefiles。

- [ ] **Step 7: 本地验证——模拟 macOS 的无 X11 配置**

```bash
cmake -B build-angle-nox11 -G Ninja -DHAVE_PYTHON=NO -DHAVE_X11=NO -DBUILD_METALIBS=YES 2>&1 | tail -20
cmake --build build-angle-nox11 --target pandagles2 --parallel 2>&1 | tail -5
```

预期：configure 成功且构建 exit code 0。这条路径覆盖了本任务修的所有链接 bug（改动前该配置会因 `p3x11display` 目标不存在而在 configure/链接时失败）。

- [ ] **Step 8: Commit**

```bash
cd /home/bowmanhan/Code/panda3d
git add dtool/Package.cmake panda/src/egldisplay/CMakeLists.txt \
  panda/metalibs/pandagles2/CMakeLists.txt panda/metalibs/pandagles/CMakeLists.txt
git commit -m "CMake: Allow building egldisplay against ANGLE on macOS, fix non-X11 link"
```

---

### Task 2: egldisplay — `egl-angle-platform` PRC 变量与 ANGLE 后端选择

**Files:**
- Modify: `panda/src/egldisplay/eglGraphicsPipe.cxx:22-30`（头文件 include 后加枚举兜底定义和新 PRC 变量）
- Modify: `panda/src/egldisplay/eglGraphicsPipe.cxx:35-115`（构造函数：ANGLE platform 分支）

**Interfaces:**
- Consumes: Task 1 的构建配置（本任务用同两个 build 目录验证编译）。
- Produces: PRC 变量 `egl-angle-platform`（字符串，取值 `default|metal|vulkan|opengl|opengles|d3d11|swiftshader`，默认 `default`）。Task 3 的 CI prc 文件写入 `egl-angle-platform metal`。

- [ ] **Step 1: 在 `eglGraphicsPipe.cxx` 的 `#include <EGL/eglext.h>` 之后添加枚举兜底定义**

Linux 的 Khronos `eglext.h` 不含 ANGLE 扩展枚举（ANGLE 自带头文件含），因此需要带注册值的兜底定义。在第 22 行 `#include <EGL/eglext.h>` 之后插入：

```cpp
// These are defined by ANGLE's eglext.h, but not by the stock Khronos
// headers, so define them here to allow selecting an ANGLE backend at
// runtime regardless of which headers we were compiled against.
#ifndef EGL_PLATFORM_ANGLE_ANGLE
#define EGL_PLATFORM_ANGLE_ANGLE 0x3202
#define EGL_PLATFORM_ANGLE_TYPE_ANGLE 0x3203
#endif
#ifndef EGL_PLATFORM_ANGLE_TYPE_D3D11_ANGLE
#define EGL_PLATFORM_ANGLE_TYPE_D3D11_ANGLE 0x3208
#endif
#ifndef EGL_PLATFORM_ANGLE_DEVICE_TYPE_ANGLE
#define EGL_PLATFORM_ANGLE_DEVICE_TYPE_ANGLE 0x3209
#endif
#ifndef EGL_PLATFORM_ANGLE_TYPE_OPENGL_ANGLE
#define EGL_PLATFORM_ANGLE_TYPE_OPENGL_ANGLE 0x320D
#define EGL_PLATFORM_ANGLE_TYPE_OPENGLES_ANGLE 0x320E
#endif
#ifndef EGL_PLATFORM_ANGLE_TYPE_VULKAN_ANGLE
#define EGL_PLATFORM_ANGLE_TYPE_VULKAN_ANGLE 0x3450
#endif
#ifndef EGL_PLATFORM_ANGLE_DEVICE_TYPE_SWIFTSHADER_ANGLE
#define EGL_PLATFORM_ANGLE_DEVICE_TYPE_SWIFTSHADER_ANGLE 0x3487
#endif
#ifndef EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE
#define EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE 0x3489
#endif
```

- [ ] **Step 2: 在 `egl_device_index` 变量定义之后添加新 PRC 变量**

现有代码（约 24-28 行）：

```cpp
static ConfigVariableInt egl_device_index
("egl-device-index", -1,
 PRC_DESC("Selects which EGL device index is used to create the EGL display in "
          "a headless configuration.  The special value -1 selects the default "
          "device."));
```

在其后插入：

```cpp
static ConfigVariableString egl_angle_platform
("egl-angle-platform", "default",
 PRC_DESC("Selects which rendering backend ANGLE should use, if the EGL "
          "implementation is ANGLE.  Valid values are default, metal, "
          "vulkan, opengl, opengles, d3d11 and swiftshader.  This is "
          "ignored if the EGL implementation does not support the "
          "EGL_ANGLE_platform_angle extension."));
```

`ConfigVariableString` 已由 `config_egldisplay.h` 引入，无需新 include。

- [ ] **Step 3: 构造函数中检测 `EGL_ANGLE_platform_angle` 客户端扩展**

现有代码（约 38-59 行）声明了 `supports_platform_device` / `supports_device_enumeration` 两个 bool 并在扩展列表里查找。同样地：

在 `bool supports_device_enumeration = false;` 之后加一行：

```cpp
  bool supports_angle_platform = false;
```

在下面这段之后：

```cpp
    if (std::find(extensions.begin(), extensions.end(), "EGL_EXT_device_enumeration") != extensions.end()) {
      supports_device_enumeration = true;
    }
```

加：

```cpp
    if (std::find(extensions.begin(), extensions.end(), "EGL_ANGLE_platform_angle") != extensions.end()) {
      supports_angle_platform = true;
    }
```

- [ ] **Step 4: 构造函数中插入 ANGLE platform display 分支**

在 `EGLint major, minor;`（约 67 行）之后、`int index = egl_device_index.get_value();` 之前插入：

```cpp
  std::string angle_platform = egl_angle_platform.get_value();
  if (angle_platform != "default") {
    if (supports_angle_platform) {
      EGLint platform_type = 0;
      EGLint device_type = 0;
      if (angle_platform == "metal") {
        platform_type = EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE;
      }
      else if (angle_platform == "vulkan") {
        platform_type = EGL_PLATFORM_ANGLE_TYPE_VULKAN_ANGLE;
      }
      else if (angle_platform == "opengl") {
        platform_type = EGL_PLATFORM_ANGLE_TYPE_OPENGL_ANGLE;
      }
      else if (angle_platform == "opengles") {
        platform_type = EGL_PLATFORM_ANGLE_TYPE_OPENGLES_ANGLE;
      }
      else if (angle_platform == "d3d11") {
        platform_type = EGL_PLATFORM_ANGLE_TYPE_D3D11_ANGLE;
      }
      else if (angle_platform == "swiftshader") {
        platform_type = EGL_PLATFORM_ANGLE_TYPE_VULKAN_ANGLE;
        device_type = EGL_PLATFORM_ANGLE_DEVICE_TYPE_SWIFTSHADER_ANGLE;
      }
      else {
        egldisplay_cat.error()
          << "Invalid egl-angle-platform value '" << angle_platform
          << "' (expected default, metal, vulkan, opengl, opengles, d3d11 "
          << "or swiftshader)\n";
      }

      if (platform_type != 0) {
        PFNEGLGETPLATFORMDISPLAYEXTPROC eglGetPlatformDisplayEXT =
          (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");

        if (eglGetPlatformDisplayEXT != nullptr) {
          EGLint attribs[5];
          int n = 0;
          attribs[n++] = EGL_PLATFORM_ANGLE_TYPE_ANGLE;
          attribs[n++] = platform_type;
          if (device_type != 0) {
            attribs[n++] = EGL_PLATFORM_ANGLE_DEVICE_TYPE_ANGLE;
            attribs[n++] = device_type;
          }
          attribs[n] = EGL_NONE;

          _egl_display = eglGetPlatformDisplayEXT(EGL_PLATFORM_ANGLE_ANGLE, nullptr, attribs);

          if (_egl_display != EGL_NO_DISPLAY && !eglInitialize(_egl_display, &major, &minor)) {
            egldisplay_cat.warning()
              << "Couldn't initialize ANGLE " << angle_platform << " display: "
              << get_egl_error_string(eglGetError()) << "\n";
            _egl_display = EGL_NO_DISPLAY;
          }
        }
      }
    }
    else if (egldisplay_cat.is_debug()) {
      egldisplay_cat.debug()
        << "Ignoring egl-angle-platform setting since EGL_ANGLE_platform_angle "
        << "is not supported.\n";
    }
  }
```

（`_egl_display` 在头文件中默认成员初始化为 0（`eglGraphicsPipe.h:83`），失败时保持 `EGL_NO_DISPLAY`，自然落入后续 fallback。）

- [ ] **Step 5: 让原有的两个 display 获取分支只在 ANGLE 分支未成功时执行**

把（约 69-70 行）：

```cpp
  int index = egl_device_index.get_value();
  if (index >= 0 && supports_platform_device && supports_device_enumeration) {
```

改为：

```cpp
  int index = egl_device_index.get_value();
  if (_egl_display == EGL_NO_DISPLAY &&
      index >= 0 && supports_platform_device && supports_device_enumeration) {
```

把该 if 对应的（约 108 行）：

```cpp
  else {
```

改为：

```cpp
  else if (_egl_display == EGL_NO_DISPLAY) {
```

- [ ] **Step 6: 编译验证（两种配置）**

```bash
cd /home/bowmanhan/Code/panda3d
cmake --build build-angle --target pandagles2 --parallel 2>&1 | tail -5
cmake --build build-angle-nox11 --target pandagles2 --parallel 2>&1 | tail -5
```

预期：两个 build 均 exit code 0，无新警告。

- [ ] **Step 7: 行为冒烟验证（Linux，验证不干扰非 ANGLE EGL）**

Mesa 的 EGL 不支持 `EGL_ANGLE_platform_angle`，设置该变量应被安静忽略、走原默认路径。用 no-X11 构建里的任一链接了 pipe 的可执行文件不可行（HAVE_PYTHON=NO 无 python 模块），因此本步只验证"编译期无破坏"+代码走查：确认新分支失败/跳过时 `_egl_display` 保持 `EGL_NO_DISPLAY` 且原有分支条件被正确追加。真实运行时行为在 Task 4 的 CI 上验证（ubuntu job 的 p3headlessgl 路径也会覆盖 egldisplay 的回归）。

- [ ] **Step 8: Commit**

```bash
git add panda/src/egldisplay/eglGraphicsPipe.cxx
git commit -m "egldisplay: Add egl-angle-platform variable to select ANGLE backend"
```

---

### Task 3: CI — macOS 下载 ANGLE、配置 CMake、写入 PRC

**Files:**
- Modify: `.github/workflows/ci.yml`（"Install dependencies (macOS)" 步骤、"Configure" 步骤、新增 "Configure headless ANGLE (macOS)" 步骤）

**Interfaces:**
- Consumes: Task 1 的 CMake 变量名（`EGL_INCLUDE_DIR`/`EGL_LIBRARY`/`OPENGLES2_INCLUDE_DIR`/`OPENGLES2_LIBRARY`）；Task 2 的 PRC 变量 `egl-angle-platform`。
- Produces: 环境变量 `ANGLE_ROOT`（指向解包后的 ANGLE 目录，含 `include/` 与 `lib/`）；prc 文件 `build/etc/panda3d/10_ci.prc`。

- [ ] **Step 1: 在 "Install dependencies (macOS)" 步骤末尾追加 ANGLE 下载**

该步骤目前以 `brew install ccache` 结尾（`.github/workflows/ci.yml` 约 101-112 行）。在 `brew install ccache` 之后追加：

```yaml
        curl --retry 5 --retry-delay 10 --retry-all-errors -fLo angle-macos-universal.tar.gz \
          https://github.com/kivy/angle-builder/releases/download/chromium-7151_rev1/angle-macos-universal.tar.gz
        echo "b87f1d0144218a0699859340bfc9864949190d5f4b4d19d4265c3ab561fcd078  angle-macos-universal.tar.gz" | shasum -a 256 -c
        mkdir -p thirdparty/angle/lib
        tar -xzf angle-macos-universal.tar.gz -C thirdparty/angle
        mv thirdparty/angle/libEGL.dylib thirdparty/angle/libGLESv2.dylib thirdparty/angle/lib/
        rm angle-macos-universal.tar.gz
        echo "ANGLE_ROOT=$PWD/thirdparty/angle" >> $GITHUB_ENV
```

（注意缩进与该 run 块内其余行保持一致，即 8 空格。）

- [ ] **Step 2: 在 "Configure" 步骤的 cmake 调用前注入 macOS 专属参数**

在 `run: >` 块内、`cmake` 调用之前（即 `if ${{ runner.os != 'Windows' }}; then ... fi` 块之后）插入：

```bash
        if ${{ runner.os == 'macOS' }}; then
          angleArgs="-DEGL_INCLUDE_DIR=$ANGLE_ROOT/include -DEGL_LIBRARY=$ANGLE_ROOT/lib/libEGL.dylib -DOPENGLES2_INCLUDE_DIR=$ANGLE_ROOT/include -DOPENGLES2_LIBRARY=$ANGLE_ROOT/lib/libGLESv2.dylib -DHAVE_GLES2=YES -DHAVE_EGL=YES"
        fi
```

并在 cmake 参数列表中（`-D ENABLE_ASAN=...` 之后、`..` 之前）加一行：

```
        ${angleArgs:-}
```

- [ ] **Step 3: 新增 "Configure headless ANGLE (macOS)" 步骤**

放在现有 "Configure headless OpenGL"（ubuntu 专属，约 196-204 行）之后：

```yaml
    - name: Configure headless ANGLE (macOS)
      if: runner.os == 'macOS'
      run: |
        mkdir -p build/etc/panda3d
        echo "load-display pandagles2" >> build/etc/panda3d/10_ci.prc
        echo "egl-angle-platform metal" >> build/etc/panda3d/10_ci.prc
        echo "notify-level-egldisplay debug" >> build/etc/panda3d/10_ci.prc
```

（`notify-level-egldisplay debug` 用于首轮观察 EGL 初始化日志，跑通后可在 Task 4 收尾时移除。）

- [ ] **Step 4: 本地校验 YAML 语法**

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"
```

预期输出 `OK`。（若无 pyyaml：`pip install --user pyyaml` 或改用 `ruby -ryaml -e "YAML.load_file('.github/workflows/ci.yml'); puts 'OK'"`。）

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "CI: Use ANGLE (Metal) for headless GLES2 rendering on macOS"
```

---

### Task 4: 推送、观察 CI、triage GLES2 测试结果

**Files:**
- 可能 Modify: `tests/**`（按 CI 结果加 skip/xfail 标记）
- 可能 Modify: `.github/workflows/ci.yml`（若 dyld 找不到 ANGLE dylib 时的兜底）

**Interfaces:**
- Consumes: Task 1-3 的全部产物。
- Produces: 绿色（或明确标注 xfail 的）macOS CI。

- [ ] **Step 1: 推送分支并触发 CI**

```bash
git push -u origin angle-macos-headless
gh run list --branch angle-macos-headless --limit 5
```

- [ ] **Step 2: 等待并检查 macOS job 结果**

```bash
gh run watch $(gh run list --branch angle-macos-headless --limit 1 --json databaseId -q '.[0].databaseId')
```

结果判读必须使用 `reading-ci-results` skill（对完整日志做对抗式检查，不要只看绿勾）。重点核对：

1. Configure 日志中 `OpenGL ES 2.x` 为 enabled；
2. pytest 输出中图形测试从 "skipped (GraphicsPipe is invalid)" 变为实际执行（对比 master 上同 job 的 skip 数）；
3. egldisplay debug 日志显示 ANGLE Metal display 初始化成功。

- [ ] **Step 3: 若 dlopen/dyld 报找不到 `@rpath/libEGL.dylib`**

首选修复：在 "Configure headless ANGLE (macOS)" 步骤追加把 dylib 复制进构建输出目录（与 panda 库同目录，走 loader path）：

```yaml
        cp thirdparty/angle/lib/libEGL.dylib thirdparty/angle/lib/libGLESv2.dylib build/lib/ 2>/dev/null \
          || cp thirdparty/angle/lib/libEGL.dylib thirdparty/angle/lib/libGLESv2.dylib "build/${{ matrix.config }}/lib/"
```

（实际输出目录以 CI 日志为准，Xcode generator 会带 config 子目录。）修改后 commit 并重新推送观察。

- [ ] **Step 4: triage GLES2 下的测试失败**

对每个失败测试判断：
- **GLES2 能力差异**（如桌面 GL 独有 feature、精度差异）→ 在测试中加条件 skip/xfail，条件用 GSG 能力查询（如 `gsg.supports_glsl` 等已有属性）或 `pipe.interface_name == "OpenGL ES"`，不要按平台硬编码；
- **真实 bug**（egldisplay/ANGLE 集成问题）→ 停下来用 systematic-debugging skill 定位，不要用 skip 掩盖。

每轮修改单独 commit（例：`tests: Skip desktop-GL-only tests on OpenGL ES pipes`），重新推送直到 macOS job 达到与 ubuntu job 相当的健康状态。

- [ ] **Step 5: 收尾**

- 移除 prc 中的 `notify-level-egldisplay debug` 行，commit：`CI: Remove debug logging for ANGLE EGL display`；
- 确认最终一轮 CI 全绿（仍用 reading-ci-results skill 判读）。
