"""Procedural cinematic basalt sea inlet for the equation-art challenge.

This file is intentionally self-contained.  It can be executed by Blender in
background mode to build, save, and render the scene, or imported into a long
running Blender Python process.  Geometry and shader variation are generated
from fixed integer seeds; no external assets are needed.
"""

import math
import os
import random
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector, noise as mnoise


DEFAULTS = {
    "mist_density": 0.028,
    "key_energy": 5.5,
    "water_roughness": 0.14,
    "camera_shift": 0.0,
}
BOUNDS = {
    "mist_density": (0.012, 0.06),
    "key_energy": (3.0, 8.0),
    "water_roughness": (0.08, 0.25),
    "camera_shift": (-0.6, 0.6),
}


def _clamp(name, value):
    lo, hi = BOUNDS[name]
    return max(lo, min(hi, float(value)))


def _set_input(node, names, value):
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return socket
    return None


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _material_output(material):
    return material.node_tree.nodes.get("Material Output")


def _make_rock_material():
    mat = bpy.data.materials.new("MAT_slate_wet_basalt")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (680, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (410, 0)
    _set_input(bsdf, ["Metallic"], 0.0)
    _set_input(bsdf, ["Roughness"], 0.38)
    _set_input(bsdf, ["Coat Weight"], 0.12)
    _set_input(bsdf, ["Coat Roughness"], 0.22)
    _set_input(bsdf, ["IOR"], 1.46)
    _set_input(bsdf, ["Specular IOR Level", "Specular"], 0.52)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-600, 100)
    noise.inputs["Scale"].default_value = 3.4
    noise.inputs["Detail"].default_value = 9.0
    noise.inputs["Roughness"].default_value = 0.72
    noise.inputs["Distortion"].default_value = 0.16
    noise.name = "Slate macro grain"
    noise2 = nodes.new("ShaderNodeTexNoise")
    noise2.location = (-600, -230)
    noise2.inputs["Scale"].default_value = 145.0
    noise2.inputs["Detail"].default_value = 4.0
    noise2.inputs["Roughness"].default_value = 0.65
    noise2.name = "Slate fine grain"
    tex = nodes.new("ShaderNodeTexCoord")
    tex.location = (-850, 70)
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-120, 130)
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    e0 = ramp.color_ramp.elements[0]
    e0.position = 0.18
    e0.color = (0.012, 0.014, 0.017, 1)
    e1 = ramp.color_ramp.elements.new(0.48)
    e1.color = (0.045, 0.052, 0.057, 1)
    e2 = ramp.color_ramp.elements.new(0.76)
    e2.color = (0.15, 0.16, 0.16, 1)
    e3 = ramp.color_ramp.elements.new(0.94)
    e3.color = (0.29, 0.28, 0.25, 1)
    bump_mix = nodes.new("ShaderNodeMixRGB")
    bump_mix.blend_type = "MULTIPLY"
    bump_mix.inputs[0].default_value = 0.72
    bump_mix.location = (-120, -150)
    bump = nodes.new("ShaderNodeBump")
    bump.location = (175, -150)
    bump.inputs["Strength"].default_value = 0.65
    bump.inputs["Distance"].default_value = 0.038
    links.new(tex.outputs["Generated"], noise.inputs["Vector"])
    links.new(tex.outputs["Generated"], noise2.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(noise.outputs["Fac"], bump_mix.inputs[1])
    links.new(noise2.outputs["Fac"], bump_mix.inputs[2])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bump_mix.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _make_water_material():
    mat = bpy.data.materials.new("MAT_teal_inlet_water")
    mat.use_nodes = True
    mat["water_roughness"] = DEFAULTS["water_roughness"]
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (680, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (410, 0)
    bsdf.name = "Water Principled"
    _set_input(bsdf, ["Base Color"], (0.008, 0.027, 0.032, 1))
    _set_input(bsdf, ["Metallic"], 0.0)
    _set_input(bsdf, ["Transmission Weight"], 0.25)
    _set_input(bsdf, ["Roughness"], DEFAULTS["water_roughness"])
    _set_input(bsdf, ["IOR"], 1.333)
    _set_input(bsdf, ["Specular IOR Level", "Specular"], 0.50)
    tex = nodes.new("ShaderNodeTexCoord")
    tex.location = (-980, 80)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-800, 80)
    # Object coordinates stay in physical water scale; the previous Generated
    # mapping made the entire 64x116m inlet read as one soft plastic gradient.
    mapping.inputs["Scale"].default_value = (0.22, 0.22, 1.0)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-590, 160)
    noise.inputs["Scale"].default_value = 3.6
    noise.inputs["Detail"].default_value = 7.0
    noise.inputs["Roughness"].default_value = 0.56
    noise.inputs["Distortion"].default_value = 0.45
    short = nodes.new("ShaderNodeTexNoise")
    short.location = (-590, -110)
    short.inputs["Scale"].default_value = 14.0
    short.inputs["Detail"].default_value = 3.0
    short.inputs["Roughness"].default_value = 0.55
    wave_x = nodes.new("ShaderNodeTexWave")
    wave_x.location = (-590, -340)
    wave_x.wave_type = "BANDS"
    wave_x.bands_direction = "X"
    wave_x.inputs["Scale"].default_value = 4.2
    wave_x.inputs["Distortion"].default_value = 6.0
    wave_x.inputs["Detail"].default_value = 5.0
    wave_y = nodes.new("ShaderNodeTexWave")
    wave_y.location = (-380, -340)
    wave_y.wave_type = "BANDS"
    wave_y.bands_direction = "Y"
    wave_y.inputs["Scale"].default_value = 2.7
    wave_y.inputs["Distortion"].default_value = 4.0
    wave_y.inputs["Detail"].default_value = 4.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-80, 135)
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[1].position = 0.68
    ramp.color_ramp.elements[0].color = (0.003, 0.032, 0.050, 1)
    ramp.color_ramp.elements[1].color = (0.045, 0.25, 0.28, 1)
    ripple_ramp = nodes.new("ShaderNodeValToRGB")
    ripple_ramp.location = (-90, -330)
    ripple_ramp.color_ramp.elements[0].color = (0.004, 0.028, 0.042, 1)
    ripple_ramp.color_ramp.elements[1].color = (0.025, 0.18, 0.20, 1)
    color_mix = nodes.new("ShaderNodeMixRGB")
    color_mix.blend_type = "ADD"
    color_mix.inputs[0].default_value = 0.22
    color_mix.location = (170, 80)
    bump_mix = nodes.new("ShaderNodeMixRGB")
    bump_mix.blend_type = "MULTIPLY"
    bump_mix.inputs[0].default_value = 0.62
    bump_mix.location = (100, -120)
    bump = nodes.new("ShaderNodeBump")
    bump.location = (250, -100)
    bump.inputs["Strength"].default_value = 0.32
    bump.inputs["Distance"].default_value = 0.085
    links.new(tex.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], short.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave_x.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave_y.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(wave_x.outputs["Color"], bump_mix.inputs[1])
    links.new(wave_y.outputs["Color"], bump_mix.inputs[2])
    links.new(wave_x.outputs["Fac"], ripple_ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], color_mix.inputs[1])
    links.new(ripple_ramp.outputs["Color"], color_mix.inputs[2])
    links.new(bump_mix.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _make_sand_material():
    mat = bpy.data.materials.new("MAT_wet_shore_silt")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    _set_input(bsdf, ["Base Color"], (0.08, 0.105, 0.10, 1))
    _set_input(bsdf, ["Roughness"], 0.34)
    _set_input(bsdf, ["Specular IOR Level", "Specular"], 0.3)
    return mat


def _make_volume_material(density):
    mat = bpy.data.materials.new("MAT_mist_volume")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    vol = nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (0.80, 0.87, 0.94, 1)
    _set_input(vol, ["Anisotropy"], 0.35)
    tex = nodes.new("ShaderNodeTexCoord")
    tex.location = (-720, -80)
    sep = nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-520, -80)
    height = nodes.new("ShaderNodeMapRange")
    height.location = (-320, -80)
    height.inputs["From Min"].default_value = 0.0
    height.inputs["From Max"].default_value = 1.0
    height.inputs["To Min"].default_value = 0.65
    height.inputs["To Max"].default_value = 0.03
    height.clamp = True
    base = nodes.new("ShaderNodeValue")
    base.name = "Mist Density"
    base.label = "Mist Density control"
    base.outputs[0].default_value = density
    mult = nodes.new("ShaderNodeMath")
    mult.operation = "MULTIPLY"
    mult.location = (-40, -40)
    links.new(tex.outputs["Generated"], sep.inputs[0])
    links.new(sep.outputs["Z"], height.inputs["Value"])
    links.new(base.outputs[0], mult.inputs[0])
    links.new(height.outputs["Result"], mult.inputs[1])
    links.new(mult.outputs[0], vol.inputs["Density"])
    links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return mat


def _rock_mesh(name, scale=(1, 1, 1), segments=18, rings=8, seed=1, peak=False):
    """Eroded rock: broad asymmetric shape plus deterministic fractal relief."""
    rng = random.Random(seed)
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=5 if max(scale) < 3 else 6, radius=1.0)
    bm.to_mesh(mesh)
    bm.free()
    phase = rng.random() * math.tau
    sx, sy, sz = scale
    for vert in mesh.vertices:
        p = vert.co.normalized()
        low = 0.12 * math.sin(2.7 * p.x + phase) + 0.10 * math.cos(3.4 * p.y - phase)
        q = p * 3.2 + Vector((phase, phase * 1.7, -phase))
        coarse = mnoise.noise(q, noise_basis='PERLIN_ORIGINAL')
        medium = mnoise.noise(q * 3.8, noise_basis='PERLIN_ORIGINAL')
        fine = mnoise.noise(q * 15.1, noise_basis='PERLIN_ORIGINAL')
        relief = 0.12 * coarse + 0.035 * medium + 0.012 * fine
        radius = 1.0 + low + relief
        x = p.x * radius
        y = p.y * radius
        z = p.z * (1.0 + relief + 0.13 * math.sin(3.0 * p.x - 2.0 * p.y + phase))
        if z > 0.56:
            z = 0.56 + (z - 0.56) * 0.52
        if z < -0.70:
            z = -0.70 + (z + 0.70) * 0.45
        vert.co = (x * sx, y * sy, z * sz)
    mesh.update()
    return bpy.data.objects.new(name, mesh)


def _add_rock(collection, mat, name, location, scale, seed, peak=False, rotation=0.0):
    obj = _rock_mesh(name, scale, segments=22 if scale[2] < 3 else 18, rings=9, seed=seed, peak=peak)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler[2] = rotation
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def _add_shoreline(collection, mat, side, seed):
    rng = random.Random(seed)
    # A low irregular shelf at either edge keeps the water framed right down to
    # the lens without making the scene read as a dry valley.
    for i in range(8):
        x = side * (4.5 + 1.0 * i + rng.uniform(-0.35, 0.35))
        y = -7.5 + i * 5.2 + rng.uniform(-1.0, 1.0)
        scale = (1.7 + rng.uniform(-0.2, 0.45), 2.0 + rng.uniform(-0.2, 0.5), 0.45 + rng.uniform(-0.12, 0.3))
        _add_rock(collection, mat, f"shore_{side:+d}_{i:02d}", (x, y, 0.10), scale, seed + i, peak=False, rotation=rng.random() * math.tau)


def _add_sun(scene):
    data = bpy.data.lights.new("KEY_amber_dawn", "SUN")
    data.energy = DEFAULTS["key_energy"]
    data.angle = math.radians(1.2)
    data.color = (1.0, 0.69, 0.40)
    obj = bpy.data.objects.new("KEY_amber_dawn", data)
    scene.collection.objects.link(obj)
    # Low backlight from the warm horizon, grazing across wet planes toward the
    # camera instead of flattening the scene from overhead.
    obj.rotation_euler = Vector((-0.4, -1.0, -0.18)).to_track_quat("-Z", "Y").to_euler()
    return obj


def _add_fill(scene):
    data = bpy.data.lights.new("FILL_cyan_sky", "AREA")
    data.energy = 6500
    data.shape = "DISK"
    data.size = 18
    data.color = (0.53, 0.70, 1.0)
    obj = bpy.data.objects.new("FILL_cyan_sky", data)
    scene.collection.objects.link(obj)
    obj.location = (-10, -8, 15)
    _look_at(obj, (0, 18, 1.5))
    return obj


def _add_water_skim(scene):
    data = bpy.data.lights.new("SKIM_cyan_ripples", "AREA")
    data.energy = 260
    data.shape = "RECTANGLE"
    data.size = 8
    data.size_y = 4
    data.color = (0.12, 0.40, 0.46)
    obj = bpy.data.objects.new("SKIM_cyan_ripples", data)
    scene.collection.objects.link(obj)
    obj.location = (-7, -12, 4.5)
    _look_at(obj, (0, 9, 0))
    return obj


def _add_warm_window(scene):
    data = bpy.data.lights.new("GLOW_horizon_window", "AREA")
    data.energy = 42
    data.shape = "RECTANGLE"
    data.size = 10
    data.size_y = 3
    data.color = (1.0, 0.16, 0.035)
    obj = bpy.data.objects.new("GLOW_horizon_window", data)
    scene.collection.objects.link(obj)
    obj.location = (2, 52, 12)
    _look_at(obj, (0, 18, 1.0))
    return obj


def _add_camera(scene):
    data = bpy.data.cameras.new("CAM_low_waterline")
    data.lens = 31
    data.sensor_width = 36
    data.dof.use_dof = True
    data.dof.focus_distance = 18
    data.dof.aperture_fstop = 16.0
    cam = bpy.data.objects.new("CAM_low_waterline", data)
    scene.collection.objects.link(cam)
    cam.location = (0.0, -18.5, 1.42)
    _look_at(cam, (0, 28, 0.35))
    scene.camera = cam
    return cam


def _add_water(collection, mat):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=120, y_subdivisions=180, size=2, location=(0, 25, -0.04))
    water = bpy.context.object
    water.name = "WATER_still_ripples"
    water.scale = (32, 58, 1)
    # Subtle deterministic displacement gives the water a real, low-frequency
    # surface break in addition to the layered shader normals.
    for vert in water.data.vertices:
        wx = vert.co.x * 32.0
        wy = vert.co.y * 58.0
        vert.co.z = (0.060 * math.sin(0.42 * wx + 0.095 * wy) +
                     0.030 * math.sin(0.93 * wx - 0.16 * wy + 1.7) +
                     0.015 * math.sin(1.8 * wx + 0.41 * wy))
    water.data.update()
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for poly in water.data.polygons:
        poly.use_smooth = True
    water.data.materials.append(mat)
    # Grid normals are stable and the shader bump supplies the small ripples.
    return water


def _make_sky_backdrop_material():
    mat = bpy.data.materials.new("MAT_procedural_dawn_backdrop")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    tex = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    e0 = ramp.color_ramp.elements[0]
    e0.position = 0.0
    e0.color = (0.52, 0.12, 0.035, 1)
    e1 = ramp.color_ramp.elements.new(0.25)
    e1.color = (0.34, 0.11, 0.10, 1)
    e2 = ramp.color_ramp.elements.new(0.58)
    e2.color = (0.10, 0.16, 0.38, 1)
    e3 = ramp.color_ramp.elements.new(1.0)
    e3.color = (0.02, 0.055, 0.20, 1)
    emission = nodes.new("ShaderNodeEmission")
    _set_input(emission, ["Strength"], 1.10)
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(tex.outputs["Generated"], sep.inputs[0])
    links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], out.inputs["Surface"])
    return mat


def _add_sky_backdrop(collection):
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 92, 35), rotation=(math.pi / 2, 0, 0))
    sky = bpy.context.object
    sky.name = "SKY_procedural_dawn_gradient"
    sky.scale = (72, 50, 1)
    sky.data.materials.append(_make_sky_backdrop_material())
    return sky


def _add_volume(scene, density):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 24, 12))
    volume = bpy.context.object
    volume.name = "ATMOSPHERE_mist_volume"
    volume.scale = (34, 42, 13)
    volume.data.materials.append(_make_volume_material(density))
    volume.display_type = "WIRE"
    return volume


def _configure_sky(scene):
    """Set a clear cool-overhead, warm-horizon dawn sky in world nodes."""
    world = scene.world or bpy.data.worlds.new("WORLD_dawn_inlet")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(7.0)
    sky.sun_rotation = math.radians(170)
    sky.altitude = 0.35
    if hasattr(sky, "air_density"):
        sky.air_density = 1.15
    if hasattr(sky, "turbidity"):
        sky.turbidity = 2.2
    if hasattr(sky, "dust_density"):
        sky.dust_density = 0.55
    if hasattr(sky, "ozone_density"):
        sky.ozone_density = 0.28
    sky.location = (-320, 40)
    bg = nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.045
    bg.location = (-40, 40)
    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-720, -180)
    sep = nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-520, -180)
    horizon = nodes.new("ShaderNodeMapRange")
    horizon.location = (-340, -180)
    horizon.inputs["From Min"].default_value = -0.16
    horizon.inputs["From Max"].default_value = 0.30
    horizon.inputs["To Min"].default_value = 0.0
    horizon.inputs["To Max"].default_value = 1.0
    horizon.clamp = True
    gradient = nodes.new("ShaderNodeValToRGB")
    gradient.location = (-100, -170)
    gradient.color_ramp.elements.remove(gradient.color_ramp.elements[1])
    g0 = gradient.color_ramp.elements[0]
    g0.position = 0.0
    g0.color = (0.16, 0.045, 0.026, 1)
    g1 = gradient.color_ramp.elements.new(0.22)
    g1.color = (0.17, 0.075, 0.065, 1)
    g2 = gradient.color_ramp.elements.new(0.56)
    g2.color = (0.050, 0.075, 0.145, 1)
    g3 = gradient.color_ramp.elements.new(1.0)
    g3.color = (0.008, 0.018, 0.055, 1)
    # A small contribution from the physically based sky keeps the gradient
    # atmosphere alive while the authored ramp preserves the filmic palette.
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MIX"
    mix.inputs[0].default_value = 0.16
    mix.location = (80, -50)
    links.new(coord.outputs["Normal"], sep.inputs[0])
    links.new(sep.outputs["Z"], horizon.inputs["Value"])
    links.new(horizon.outputs["Result"], gradient.inputs["Fac"])
    links.new(gradient.outputs["Color"], mix.inputs[1])
    links.new(sky.outputs["Color"], mix.inputs[2])
    out = nodes.new("ShaderNodeOutputWorld")
    out.location = (220, 40)
    links.new(sky.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], out.inputs["Surface"])


def _configure_render(scene):
    scene.render.engine = "BLENDER_EEVEE"
    # The direct render command switches to Cycles below after the scene is
    # built. Eevee remains a responsive viewport fallback for inspection.
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    scene.render.filepath = "inlet_preview.png"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.65
    scene.render.use_compositing = True
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.004, 0.012, 0.02)
    scene["scene_schema"] = "cinematic-inlet-1"
    scene["defaults"] = str(DEFAULTS)


def _build_compositor(scene):
    # Blender 5.1's compositor API has moved to the new node-group interface;
    # the scene deliberately keeps the render path dependency-free.  The
    # atmospheric bloom comes from the physical volume and wide area window.
    return None


def build_scene(scene=None):
    """Clear and build the deterministic inlet. Returns the Blender scene."""
    if scene is None:
        scene = bpy.context.scene
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        # Do not remove data blocks from unrelated linked scenes when imported.
        pass
    for child in list(scene.collection.children):
        scene.collection.children.unlink(child)
    scene.render.engine = "BLENDER_EEVEE"
    rock_mat = _make_rock_material()
    water_mat = _make_water_material()
    shore_mat = _make_sand_material()
    rocks = bpy.data.collections.new("ROCKS_procedural_basalt")
    scene.collection.children.link(rocks)
    water_collection = bpy.data.collections.new("WATER_and_SHORE")
    scene.collection.children.link(water_collection)

    _add_water(water_collection, water_mat)
    _add_shoreline(rocks, rock_mat, -1, 110)
    # The left wall is a dominant, broken cliff; the right bank is deliberately
    # lower and discontinuous so the inlet opens toward the dawn.
    foreground = [
        (-7.1, -5.2, 0.55, (4.6, 5.2, 6.6), 17),
        (-7.8, 4.0, 0.20, (3.3, 3.8, 5.0), 41),
        (-5.8, 11.0, 0.08, (2.6, 3.4, 3.6), 67),
        (5.2, -6.0, 0.18, (2.6, 3.1, 2.0), 29),
        (6.8, -0.8, 0.14, (2.1, 2.6, 2.4), 53),
        (5.4, 7.6, 0.12, (2.0, 2.7, 2.1), 79),
        (3.7, 13.3, 0.05, (1.3, 1.8, 1.5), 87),
    ]
    for i, (x, y, z, sc, seed) in enumerate(foreground):
        _add_rock(rocks, rock_mat, f"foreground_mass_{i:02d}", (x, y, z), sc, seed, peak=True, rotation=0.2 * i)
    # Distant staggered stacks create depth and scale.  Their smaller geometry
    # is still fully procedural, with no impostor images or external assets.
    distant = [
        (-12.5, 38.0, 0.0, (3.5, 3.0, 8.0), 301),
        (-5.6, 46.0, 0.0, (2.1, 2.2, 5.5), 313),
        (1.8, 55.0, 0.0, (1.8, 2.1, 4.2), 327),
        (7.5, 41.0, 0.0, (2.6, 2.4, 6.5), 337),
        (13.5, 49.0, 0.0, (3.7, 3.0, 7.5), 349),
        (-1.8, 64.0, 0.0, (2.5, 2.8, 5.7), 359),
    ]
    for i, (x, y, z, sc, seed) in enumerate(distant):
        _add_rock(rocks, rock_mat, f"sea_stack_{i:02d}", (x, y, z), sc, seed, peak=True, rotation=0.13 * i)
    # Small mid-channel rocks break the otherwise perfect reflection line.
    for i, (x, y, sc) in enumerate([(-2.1, 15.0, (0.9, 1.6, 1.1)), (2.0, 22.5, (1.2, 1.4, 1.6)), (-3.2, 29.5, (1.1, 1.4, 1.9))]):
        _add_rock(rocks, rock_mat, f"channel_rock_{i:02d}", (x, y, 0.0), sc, 501 + i, peak=True, rotation=0.4 * i)

    cam = _add_camera(scene)
    _add_sun(scene)
    _add_fill(scene)
    _add_water_skim(scene)
    _add_warm_window(scene)
    _add_volume(scene, DEFAULTS["mist_density"])
    _configure_sky(scene)
    _configure_render(scene)
    _build_compositor(scene)
    apply_parameters(scene, DEFAULTS)
    return scene


def apply_parameters(scene_or_params, params=None):
    """Apply bounded visible controls to an existing scene.

    Supports both ``apply_parameters(scene, params)`` and the convenient
    persistent-process form ``apply_parameters(params)``.
    """
    if params is None:
        scene = bpy.context.scene
        params = scene_or_params
    else:
        scene = scene_or_params
    merged = dict(DEFAULTS)
    if params:
        merged.update(params)
    for key in BOUNDS:
        merged[key] = _clamp(key, merged[key])
    scene["parameters"] = str(merged)
    # The node names are stable because this script builds them exactly once.
    sun = bpy.data.objects.get("KEY_amber_dawn")
    if sun and sun.data:
        sun.data.energy = merged["key_energy"]
    volume = bpy.data.objects.get("ATMOSPHERE_mist_volume")
    if volume and volume.data and volume.data.materials:
        mat = volume.data.materials[0]
        density_node = mat.node_tree.nodes.get("Mist Density")
        if density_node:
            density_node.outputs[0].default_value = merged["mist_density"]
        else:
            node = next((n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeVolumePrincipled"), None)
            if node:
                _set_input(node, ["Density"], merged["mist_density"])
    water = bpy.data.materials.get("MAT_teal_inlet_water")
    if water:
        water["water_roughness"] = merged["water_roughness"]
        node = water.node_tree.nodes.get("Water Principled")
        if node:
            _set_input(node, ["Roughness"], merged["water_roughness"])
    set_camera_shift(scene, merged["camera_shift"])
    return merged


def set_camera_shift(scene_or_shift, shift=None):
    if shift is None:
        scene = bpy.context.scene
        shift = scene_or_shift
    else:
        scene = scene_or_shift
    camera = scene.camera or bpy.data.objects.get("CAM_low_waterline")
    if camera and camera.data:
        value = _clamp("camera_shift", shift)
        # Held-out views use a real lateral camera displacement and re-aim at
        # the same distant target; lens shift stays neutral.
        camera.location.x = value * 2.4
        camera.data.shift_x = 0.0
        _look_at(camera, (0.0, 28.0, 0.35))
        camera["camera_shift"] = value
    return _clamp("camera_shift", shift)


def _configure_cycles(scene, samples=48):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = int(samples)
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 4
    scene.cycles.volume_bounces = 2
    scene.cycles.use_animated_seed = False
    scene.cycles.seed = 13579
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.refresh_devices()
        devices = getattr(prefs, "devices", [])
        metal = next((d for d in devices if getattr(d, "type", "") == "METAL"), None)
        if metal:
            prefs.compute_device_type = "METAL"
            scene.cycles.device = "GPU"
            scene["render_device"] = "METAL"
            return "METAL"
    except Exception as exc:
        scene["cycles_device_note"] = str(exc)
    scene.cycles.device = "CPU"
    scene["render_device"] = "CPU"
    return "CPU"


def render(scene, path, width=960, height=540, samples=48, seed=13579, exr=False, exr_path=None):
    """Render PNG/EXR, optionally saving both from one Render Result."""
    _configure_cycles(scene, samples=samples)
    scene.cycles.seed = int(seed)
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    scene.render.resolution_percentage = 100
    scene.render.filepath = os.fspath(path)
    if exr:
        scene.render.image_settings.file_format = "OPEN_EXR"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.image_settings.color_depth = "32"
        scene.render.image_settings.exr_codec = "ZIP"
    else:
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
    primary_path = os.fspath(path)
    bpy.ops.render.render(write_still=True)
    if exr_path is not None and not exr:
        result = bpy.data.images.get("Render Result")
        if result is not None:
            scene.render.filepath = os.fspath(exr_path)
            scene.render.image_settings.file_format = "OPEN_EXR"
            scene.render.image_settings.color_mode = "RGBA"
            scene.render.image_settings.color_depth = "32"
            scene.render.image_settings.exr_codec = "ZIP"
            result.save_render(filepath=os.fspath(exr_path), scene=scene)
            scene.render.filepath = primary_path
            scene.render.image_settings.file_format = "PNG"
            scene.render.image_settings.color_mode = "RGB"
    return os.fspath(path)


def _parse_command_line():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    outdir = Path(args[0]).expanduser().resolve() if args else Path.cwd()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def main():
    outdir = _parse_command_line()
    scene = build_scene()
    params = apply_parameters(scene, DEFAULTS)
    preview = outdir / "inlet_preview.png"
    render(scene, preview, width=960, height=540, samples=48, seed=13579)
    blend = outdir / "inlet_scene.blend"
    bpy.ops.wm.save_as_mainfile(filepath=os.fspath(blend))
    print("CINEMATIC_INLET_READY")
    print(f"BLENDER_VERSION={bpy.app.version_string}")
    print(f"RENDER_DEVICE={scene.get('render_device', 'unknown')}")
    print(f"PARAMETERS={params}")
    print(f"PREVIEW={preview}")
    print(f"BLEND={blend}")


if __name__ == "__main__":
    main()
