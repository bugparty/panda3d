"""Render a panda3d demo scene offscreen through pandagles2 -> ANGLE and save a PNG.

Used by CI to visually confirm real geometry/lighting/textures render through the
ANGLE backend (Metal on macOS, Vulkan/GL elsewhere).  Uses only panda3d.core so it
does not depend on the `direct` tree.  The display module and ANGLE backend are
selected via the prc (load-display pandagles2 / egl-angle-platform ...).
"""
import sys
from panda3d.core import (
    loadPrcFileData, GraphicsPipeSelection, GraphicsEngine, GraphicsPipe,
    FrameBufferProperties, WindowProperties, GraphicsOutput, Filename,
    NodePath, Camera, PerspectiveLens, AmbientLight, DirectionalLight, LColor,
    Loader, LoaderOptions,
)

loadPrcFileData("", "window-type none")
loadPrcFileData("", "load-file-type egg pandaegg")

out_path = sys.argv[1] if len(sys.argv) > 1 else "panda_angle_demo.png"

pipe = GraphicsPipeSelection.get_global_ptr().make_default_pipe()
if pipe is None or not pipe.is_valid():
    print("FAIL: no valid graphics pipe")
    sys.exit(1)
print("PIPE:", pipe.get_type().get_name(), "| interface:", pipe.get_interface_name())

engine = GraphicsEngine.get_global_ptr()
fb = FrameBufferProperties()
fb.set_rgba_bits(8, 8, 8, 8)
fb.set_depth_bits(24)
buf = engine.make_output(pipe, "demo", 0, fb, WindowProperties.size(960, 540),
                         GraphicsPipe.BF_refuse_window)
engine.open_windows()
if buf is None:
    print("FAIL: could not open offscreen buffer")
    sys.exit(1)

gsg = buf.get_gsg()
print("GL_VENDOR:  ", gsg.get_driver_vendor())
print("GL_RENDERER:", gsg.get_driver_renderer())
print("GL_VERSION: ", gsg.get_driver_version())

buf.set_clear_color_active(True)
buf.set_clear_color(LColor(0.53, 0.72, 0.92, 1.0))

loader = Loader.get_global_ptr()
opts = LoaderOptions()
render = NodePath("render")
render.set_shader_auto()  # GLES2 has no fixed-function lighting/texturing

def load(name):
    node = loader.load_sync(Filename(name), opts)
    return NodePath(node) if node is not None else None

env = load("models/environment.egg")
if env is not None:
    env.reparent_to(render)
    env.set_scale(0.25)
    env.set_pos(-8, 42, 0)
else:
    print("WARN: environment model not found")

panda = load("models/panda.egg")
if panda is not None:
    panda.reparent_to(render)
    panda.set_scale(0.6)
    panda.set_pos(0, 8, 0)
    panda.set_h(200)
else:
    print("WARN: panda model not found")

alight = AmbientLight("ambient")
alight.set_color(LColor(0.35, 0.35, 0.4, 1))
render.set_light(render.attach_new_node(alight))
dlight = DirectionalLight("sun")
dlight.set_color(LColor(1.0, 0.95, 0.85, 1))
dnp = render.attach_new_node(dlight)
dnp.set_hpr(-40, -60, 0)
render.set_light(dnp)

camera = Camera("cam")
camera.set_lens(PerspectiveLens())
camnp = render.attach_new_node(camera)
camnp.set_pos(-6, -18, 7)
camnp.look_at(0, 8, 2)
dr = buf.make_display_region()
dr.set_camera(camnp)

for _ in range(10):
    engine.render_frame()
engine.sync_frame()

ok = buf.save_screenshot(Filename.from_os_specific(out_path))
print("saved:", ok, "->", out_path)
if not ok:
    sys.exit(1)
print("RESULT: rendered demo via", gsg.get_driver_renderer())

# Clean shutdown to avoid the atexit GSG-teardown crash on some platforms.
engine.remove_all_windows()
