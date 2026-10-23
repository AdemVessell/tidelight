"""Animated cinematic extension for the frozen TIDELIGHT inlet scene.

The parent ``scene.py`` remains the frozen procedural source.  This module
imports it, builds the unchanged baseline, and adds only shot-specific motion:
real vertex displacement for the water, drifting procedural shader coordinates,
an advected spatial mist field, a near wet rock for foreground parallax, and a
slow camera move.  The frame handler is deliberately deterministic: callers
can use :func:`set_time` directly or run ``render_shot.py`` in one Blender
process for a movie.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
FROZEN_SOURCE = ROOT / "scene.py"
FPS = 24
DURATION_SECONDS = 10.0
FRAME_START = 0
FRAME_END = int(round(DURATION_SECONDS * FPS)) - 1

# The wave frequencies are in rad/m.  omega is derived from deep-water gravity
# dispersion, omega = sqrt(g*|k|); WAVE_TIME_SCALE is an explicitly recorded
# artistic time scale that fits several wave periods into a ten-second shot.
GRAVITY = 9.81
WAVE_TIME_SCALE = 0.42
WAVES = (
    {"amplitude": 0.090, "kx": 0.42, "ky": 0.095, "phase": 0.25},
    {"amplitude": 0.042, "kx": 0.93, "ky": -0.16, "phase": 1.70},
    {"amplitude": 0.020, "kx": 1.80, "ky": 0.41, "phase": -0.80},
    {"amplitude": 0.012, "kx": -0.72, "ky": 1.12, "phase": 2.35},
)
MIST_DRIFT = (0.075, 0.030, 0.0)
WATER_SHADER_DRIFT = (0.065, -0.023, 0.0)
_WATER_BASE_CACHE = {}


def _load_frozen_scene():
    """Load the frozen source under a private module name."""
    name = "tidelight_frozen_scene"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, FROZEN_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load frozen source: {FROZEN_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _find_input(node, names):
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            return socket
    return None


def _set_input(node, names, value):
    socket = _find_input(node, names)
    if socket is not None:
        socket.default_value = value
    return socket


def _wave_height(x, y, t):
    """Return deterministic physical-space wave height at time t seconds."""
    tau = t * WAVE_TIME_SCALE
    total = 0.0
    for wave in WAVES:
        kx = wave["kx"]
        ky = wave["ky"]
        k_mag = math.sqrt(kx * kx + ky * ky)
        omega = math.sqrt(GRAVITY * k_mag)
        total += wave["amplitude"] * math.sin(kx * x + ky * y - omega * tau + wave["phase"])
    return total


def _water_vertices(water):
    """Cache the built baseline water vertices without adding another file."""
    cache = _WATER_BASE_CACHE.get(water.name)
    if cache is None or len(cache) != len(water.data.vertices):
        cache = [[float(v.co.x), float(v.co.y), float(v.co.z)] for v in water.data.vertices]
        _WATER_BASE_CACHE[water.name] = cache
    return cache


def _animate_water(water, t):
    base = _water_vertices(water)
    for vertex, original in zip(water.data.vertices, base):
        # The displacement is the complete animated surface height.  The
        # object's world Z offset (-0.04 m) remains in the transform, so this
        # cannot accumulate the frozen scene's baked ripples between frames.
        vertex.co.z = _wave_height(original[0], original[1], t)
    water.data.update()


def _setup_water_shader(t=0.0):
    material = bpy.data.materials.get("MAT_teal_inlet_water")
    if material is None or not material.use_nodes:
        raise RuntimeError("Frozen scene did not provide MAT_teal_inlet_water")
    nodes = material.node_tree.nodes
    mapping = nodes.get("CINEMATIC_water_drift")
    if mapping is None:
        # The frozen shader already has a Mapping node.  Naming it makes this
        # extension robust across imports while retaining its original graph.
        mapping = next((node for node in nodes if node.bl_idname == "ShaderNodeMapping"), None)
        if mapping is None:
            raise RuntimeError("Frozen water shader has no Mapping node")
        mapping.name = "CINEMATIC_water_drift"
    mapping.inputs["Location"].default_value = tuple(t * value for value in WATER_SHADER_DRIFT)
    material["cinematic_shader_motion"] = "Mapping.Location = t * (0.065, -0.023, 0.0)"


def _setup_mist_shader(t=0.0):
    volume = bpy.data.objects.get("ATMOSPHERE_mist_volume")
    if volume is None or not volume.data.materials:
        raise RuntimeError("Frozen scene did not provide ATMOSPHERE_mist_volume")
    material = volume.data.materials[0]
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    vol = next((node for node in nodes if node.bl_idname == "ShaderNodeVolumePrincipled"), None)
    if vol is None:
        raise RuntimeError("Cinematic mist volume has no Principled Volume node")
    _set_input(vol, ["Color"], (0.68, 0.80, 0.96, 1))
    mapping = nodes.get("CINEMATIC_mist_advect")
    noise = nodes.get("CINEMATIC_mist_noise")
    ramp = nodes.get("CINEMATIC_mist_variation")
    if mapping is None:
        tex = nodes.get("Texture Coordinate")
        base = nodes.get("Mist Density")
        old_height = nodes.get("Map Range")
        old_mult = next((node for node in nodes if node.bl_idname == "ShaderNodeMath" and node.operation == "MULTIPLY"), None)
        if tex is None or vol is None or base is None or old_height is None or old_mult is None:
            raise RuntimeError("Frozen mist shader graph changed; expected texture, height, base, and multiply nodes")
        mapping = nodes.new("ShaderNodeMapping")
        mapping.name = "CINEMATIC_mist_advect"
        mapping.label = "Mist field advection (procedural, not fluid simulation)"
        mapping.location = (-540, 210)
        noise = nodes.new("ShaderNodeTexNoise")
        noise.name = "CINEMATIC_mist_noise"
        noise.label = "Spatially varying mist density"
        noise.location = (-340, 220)
        noise.noise_dimensions = "3D"
        noise.inputs["Scale"].default_value = 2.2
        noise.inputs["Detail"].default_value = 4.0
        noise.inputs["Roughness"].default_value = 0.66
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.name = "CINEMATIC_mist_variation"
        ramp.label = "Mist density modulation"
        ramp.location = (-100, 220)
        ramp.color_ramp.elements[0].position = 0.18
        ramp.color_ramp.elements[0].color = (0.18, 0.18, 0.18, 1)
        ramp.color_ramp.elements[1].position = 0.78
        ramp.color_ramp.elements[1].color = (1.28, 1.28, 1.28, 1)
        advect = nodes.new("ShaderNodeMath")
        advect.name = "CINEMATIC_mist_density_product"
        advect.label = "Height falloff × noise"
        advect.operation = "MULTIPLY"
        advect.location = (120, 90)
        links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(old_height.outputs["Result"], advect.inputs[0])
        links.new(ramp.outputs["Color"], advect.inputs[1])
        # Replace the old height-only link while preserving the base density.
        for link in list(links):
            if link.to_node == old_mult and link.to_socket == old_mult.inputs[1]:
                links.remove(link)
        links.new(advect.outputs[0], old_mult.inputs[1])
        mapping.inputs["Scale"].default_value = (0.85, 0.85, 1.05)
    mapping.inputs["Location"].default_value = tuple(t * value for value in MIST_DRIFT)
    if not (mapping and noise and ramp):
        raise RuntimeError("Cinematic mist nodes were not installed")
    material["cinematic_mist_field"] = (
        "density = base_density * heightfalloff(z) * clamp(ramp(noise3D(" 
        "Generated*(0.85,0.85,1.05) + t*(0.075,0.030,0.0); "
        "Scale=2.2, Detail=4.0, Roughness=0.66; ramp Fac 0.18->0.18, "
        "0.78->1.28), 0.18, 1.28); no fluid simulation"
    )


def _make_wet_foreground_material(base_material):
    if base_material is None:
        raise RuntimeError("Frozen scene did not provide MAT_slate_wet_basalt")
    material = bpy.data.materials.get("MAT_cinematic_wet_foreground")
    if material is None:
        material = base_material.copy()
        material.name = "MAT_cinematic_wet_foreground"
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            nodes = material.node_tree.nodes
            links = material.node_tree.links
            geometry = nodes.new("ShaderNodeNewGeometry")
            geometry.name = "CINEMATIC_wet_world_position"
            geometry.label = "World-height wetness"
            geometry.location = (-520, -420)
            separate = nodes.new("ShaderNodeSeparateXYZ")
            separate.name = "CINEMATIC_wet_height"
            separate.location = (-300, -420)
            roughness = nodes.new("ShaderNodeMapRange")
            roughness.name = "CINEMATIC_wet_roughness_by_height"
            roughness.label = "Waterline roughness: wet low, dry high"
            roughness.location = (-80, -350)
            roughness.inputs["From Min"].default_value = -0.30
            roughness.inputs["From Max"].default_value = 1.20
            roughness.inputs["To Min"].default_value = 0.11
            roughness.inputs["To Max"].default_value = 0.58
            roughness.clamp = True
            coat = nodes.new("ShaderNodeMapRange")
            coat.name = "CINEMATIC_wet_coat_by_height"
            coat.label = "Waterline coat: wet low, dry high"
            coat.location = (-80, -560)
            coat.inputs["From Min"].default_value = -0.30
            coat.inputs["From Max"].default_value = 1.20
            coat.inputs["To Min"].default_value = 0.42
            coat.inputs["To Max"].default_value = 0.12
            coat.clamp = True
            links.new(geometry.outputs["Position"], separate.inputs[0])
            links.new(separate.outputs["Z"], roughness.inputs["Value"])
            links.new(separate.outputs["Z"], coat.inputs["Value"])
            links.new(roughness.outputs["Result"], bsdf.inputs["Roughness"])
            coat_socket = _find_input(bsdf, ["Coat Weight"])
            if coat_socket is None:
                raise RuntimeError("Blender Principled shader has no Coat Weight input")
            links.new(coat.outputs["Result"], coat_socket)
            texcoord = nodes.get("Texture Coordinate")
            base_bump = next((node for node in nodes if node.bl_idname == "ShaderNodeBump"), None)
            if texcoord is None or base_bump is None:
                raise RuntimeError("Frozen rock shader lacks the expected coordinate/bump detail")
            micro = nodes.new("ShaderNodeTexNoise")
            micro.name = "CINEMATIC_foreground_micrograin"
            micro.label = "Restrained wet-stone micrograin"
            micro.location = (-300, -700)
            micro.inputs["Scale"].default_value = 260.0
            micro.inputs["Detail"].default_value = 2.5
            micro.inputs["Roughness"].default_value = 0.42
            micro_bump = nodes.new("ShaderNodeBump")
            micro_bump.name = "CINEMATIC_foreground_microbump"
            micro_bump.location = (180, -610)
            micro_bump.inputs["Strength"].default_value = 0.16
            micro_bump.inputs["Distance"].default_value = 0.012
            links.new(texcoord.outputs["Generated"], micro.inputs["Vector"])
            links.new(micro.outputs["Fac"], micro_bump.inputs["Height"])
            links.new(base_bump.outputs["Normal"], micro_bump.inputs["Normal"])
            links.new(micro_bump.outputs["Normal"], bsdf.inputs["Normal"])
            _set_input(bsdf, ["Specular IOR Level", "Specular"], 0.62)
            material["cinematic_wetness_model"] = (
                "world_z -0.30..1.20 m -> roughness 0.11..0.58, "
                "coat_weight 0.42..0.12; clamped"
            )
            material["cinematic_surface_detail"] = "Noise Scale=260, Detail=2.5, Roughness=0.42; Bump Strength=0.16"
    return material


def _add_foreground_detail(frozen):
    collection = bpy.data.collections.get("CINEMATIC_foreground_detail")
    if collection is not None:
        return collection
    collection = bpy.data.collections.new("CINEMATIC_foreground_detail")
    bpy.context.scene.collection.children.link(collection)
    base_material = bpy.data.materials.get("MAT_slate_wet_basalt")
    wet_material = _make_wet_foreground_material(base_material)
    frozen._add_rock(
        collection,
        wet_material,
        "CINEMATIC_near_wet_boulder",
        (3.45, -13.4, 0.33),
        (2.20, 3.20, 1.12),
        1801,
        peak=False,
        rotation=0.28,
    )
    frozen._add_rock(
        collection,
        wet_material,
        "CINEMATIC_near_wet_skerry",
        (-2.60, -11.65, 0.20),
        (1.65, 2.35, 0.78),
        1807,
        peak=False,
        rotation=-0.20,
    )
    collection["purpose"] = "Near wet stone parallax and scale; procedural geometry only"
    return collection


def _animate_camera(camera, t):
    progress = max(0.0, min(1.0, t / DURATION_SECONDS))
    ease = progress * progress * (3.0 - 2.0 * progress)
    # First frame is the frozen composition exactly; the move eases into a
    # 1.25m lateral drift and 3m dolly for foreground parallax.
    camera.location = (1.25 * ease, -18.5 + 3.0 * ease, 1.42 + 0.08 * math.sin(math.pi * progress))
    target = (0.0 + 0.85 * ease, 28.0 + 3.0 * ease, 0.35 + 0.08 * math.sin(math.pi * progress))
    _look_at(camera, target)
    camera.data.lens = 32.5
    camera.data.dof.focus_distance = 19.0 + 2.4 * ease
    camera.data.dof.aperture_fstop = 7.1
    camera["cinematic_time_s"] = float(t)


def set_time(scene, t):
    """Apply one deterministic shot state at time ``t`` seconds."""
    t = float(t)
    water = bpy.data.objects.get("WATER_still_ripples")
    if water is not None:
        _animate_water(water, t)
    _setup_water_shader(t)
    _setup_mist_shader(t)
    camera = scene.camera or bpy.data.objects.get("CAM_low_waterline")
    if camera is not None:
        _animate_camera(camera, t)
    scene["cinematic_time_s"] = t
    scene["cinematic_frame"] = int(round(t * FPS))
    return t


def _frame_handler(scene, depsgraph=None):
    set_time(scene, float(scene.frame_current) / FPS)


def install_frame_handler():
    handlers = bpy.app.handlers.frame_change_pre
    for handler in list(handlers):
        if getattr(handler, "__name__", "") == "_frame_handler":
            handlers.remove(handler)
    handlers.append(_frame_handler)


def configure_shot(scene):
    scene.render.fps = FPS
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene["shot_schema"] = "tidelight-cinematic-shot-1"
    scene["shot_duration_seconds"] = DURATION_SECONDS
    scene["shot_fps"] = FPS
    scene["shot_motion_model"] = "deterministic frame_change_pre + set_time(t)"
    scene["water_wave_equation"] = "eta(x,y,t)=sum_i A_i*sin(kx_i*x+ky_i*y-sqrt(g*|k_i|)*(0.42*t)+phi_i)"
    scene["water_gravity_m_per_s2"] = GRAVITY
    scene["water_artistic_time_scale"] = WAVE_TIME_SCALE
    scene["mist_field_model"] = (
        "base_density*heightfalloff(z)*clamp(ramp(noise3D(" 
        "Generated*(0.85,0.85,1.05)+t*(0.075,0.030,0); "
        "Scale=2.2,Detail=4.0,Roughness=0.66; ramp(0.18)=0.18,ramp(0.78)=1.28),0.18,1.28)"
    )
    scene["mist_simulation_claim"] = "procedural advected density field; not a fluid simulation"
    scene["mist_display_color"] = [0.68, 0.80, 0.96]
    scene["frozen_scene_source"] = str(FROZEN_SOURCE)
    scene["frozen_scene_sha256"] = "03484bd17d1f9c3e0a280c0d1302462181d1b1ec1e348d643232afb1faa6562c"
    if scene.camera is not None:
        scene.camera.data.lens = 32.5
    install_frame_handler()
    set_time(scene, 0.0)
    return scene


def build_shot_scene():
    frozen = _load_frozen_scene()
    scene = frozen.build_scene()
    _add_foreground_detail(frozen)
    _setup_water_shader(0.0)
    _setup_mist_shader(0.0)
    configure_shot(scene)
    return scene


def save_shot(path):
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(path).resolve()))


if __name__ == "__main__":
    scene = build_shot_scene()
    out = Path(__file__).resolve().parent / "shot.blend"
    save_shot(out)
    print(f"CINEMATIC_SHOT_READY {out}")
