"""Render a preview of a built scene. Not proof of a working mod.

  blender --background build/v1.blend --python-exit-code 1 --python scripts/render_preview.py -- \
      --config config/v1.json --profile surface --output renders/v1-preview.png [--view rear34|side]

Adds a render-only stand-in pickup (scripts/lib/proxy_truck.py: original, generic, debadged
low-poly geometry, painted with the shell's own paint spec), a road/ground plane, a sun and a
gradient sky. Nothing is saved: the .blend on disk is not modified and the stand-in is never
exported or packaged.
"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from lib.common import (  # noqa: E402
    PipelineError, load_json, make_parser, repo_path, run_main, script_args,
    sha256_file, write_run_record,
)
from lib.proxy_truck import build_truck  # noqa: E402

# Camera presets in the shell frame (origin = rail top, bed front wall; +Y toward the cab).
# Positions/targets are relative to the ground under the origin (z = 0 is the road surface).
VIEWS = {
    "rear34": {"location": (-3.9, -6.9, 1.6), "target": (0.1, 0.35, 1.02), "lens": 40},
    "detail": {"location": (-2.4, -4.0, 2.7), "target": (0.0, -0.9, 1.65), "lens": 38},
    "side": {"location": (-11.5, 1.05, 1.25), "target": (0.0, 1.05, 1.0), "lens": 52},
}


def node_mat(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat, mat.node_tree.nodes, mat.node_tree.links


def add_ground(ground_z, col):
    """Asphalt road strip with an edge line, on a dusty shoulder; procedural, no textures."""
    def plane(name, x0, x1, y0, y1, z, mat):
        me = bpy.data.meshes.new(name)
        me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        col.objects.link(ob)
        return ob

    def noisy(name, c0, c1, scale, rough):
        mat, nodes, links = node_mat(name)
        bsdf = nodes["Principled BSDF"]
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 8.0
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = c0
        ramp.color_ramp.elements[1].color = c1
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = rough
        return mat

    asphalt = noisy("pv_asphalt", (0.035, 0.035, 0.037, 1), (0.075, 0.074, 0.072, 1), 60.0, 0.85)
    shoulder = noisy("pv_shoulder", (0.16, 0.13, 0.09, 1), (0.27, 0.23, 0.16, 1), 6.0, 0.95)
    line = noisy("pv_lane_line", (0.55, 0.55, 0.52, 1), (0.72, 0.72, 0.68, 1), 40.0, 0.7)
    plane("pv_road", -4.5, 5.5, -60, 60, ground_z, asphalt)
    plane("pv_shoulder", -80, 80, -80, 80, ground_z - 0.01, shoulder)
    plane("pv_edge_line", -4.3, -4.18, -60, 60, ground_z + 0.002, line)
    hills, nodes, links = node_mat("pv_hills")  # flat hazy silhouette (aerial perspective), unlit
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (0.36, 0.42, 0.50, 1)
    emit.inputs["Strength"].default_value = 1.0
    links.new(emit.outputs["Emission"], nodes["Material Output"].inputs["Surface"])
    for i in range(9):  # distant low hills: flattened ico spheres on a fixed ring (deterministic)
        a = math.radians(-150 + i * 37)
        dist = 600 + 90 * ((i * 7) % 3)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.0,
                                              location=(dist * math.sin(a), dist * math.cos(a), ground_z - 4))
        h = bpy.context.active_object
        h.name = f"pv_hill_{i}"
        h.scale = (190 + 50 * (i % 3), 150 + 40 * (i % 2), 16 + 7 * ((i * 5) % 4))
        for poly in h.data.polygons:
            poly.use_smooth = True
        h.data.materials.append(hills)
        for c in h.users_collection:
            c.objects.unlink(h)
        col.objects.link(h)
    for i in range(-12, 13):  # dashed centre line
        y = i * 4.0
        plane(f"pv_dash_{i + 12:02d}", 2.44, 2.56, y, y + 2.0, ground_z + 0.002, line)


def setup_world():
    world = bpy.data.worlds.new("preview_world")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    bg = nodes["Background"]
    coord = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    ramp = nodes.new("ShaderNodeValToRGB")
    links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    # Generated Z of a world direction is 0 at the horizon and 1 at the zenith (negative clamps to 0).
    els[0].position, els[0].color = 0.0, (0.62, 0.62, 0.60, 1)      # hazy horizon / ground bounce
    els[1].position, els[1].color = 0.55, (0.14, 0.25, 0.50, 1)     # zenith blue
    near = els.new(0.08)
    near.color = (0.38, 0.52, 0.78, 1)
    links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.8
    bpy.context.scene.world = world


def setup_camera_and_light(view, ground_z):
    spec = VIEWS[view]
    cam_data = bpy.data.cameras.new("preview_cam")
    cam_data.lens = spec["lens"]
    cam_data.clip_start, cam_data.clip_end = 0.1, 2000
    cam = bpy.data.objects.new("preview_cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    lift = Vector((0, 0, ground_z))
    cam.location = Vector(spec["location"]) + lift
    target = Vector(spec["target"]) + lift
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    sun_data = bpy.data.lights.new("preview_sun", "SUN")
    sun_data.energy = 4.6
    sun_data.angle = math.radians(2.5)
    sun_data.color = (1.0, 0.96, 0.9)
    sun_data.use_contact_shadow = True
    sun = bpy.data.objects.new("preview_sun", sun_data)
    sun.rotation_euler = (math.radians(48), 0, math.radians(-150))
    bpy.context.scene.collection.objects.link(sun)
    setup_world()
    return {"view": view, "camera_location": [round(c, 3) for c in cam.location], "lens": cam_data.lens}


def configure_render(profile):
    scene = bpy.context.scene
    r = scene.render
    r.resolution_x, r.resolution_y = profile["resolution"]
    r.resolution_percentage = 100
    r.image_settings.file_format = "PNG"
    r.engine = profile["engine"]
    if profile["engine"] == "BLENDER_EEVEE":
        ee = scene.eevee
        ee.taa_render_samples = profile["samples"]
        ee.use_soft_shadows = True
        ee.shadow_cascade_size = "2048"
        ee.shadow_cube_size = "1024"
        ee.use_gtao = True
        ee.gtao_distance = 0.6
        ee.gtao_factor = 1.0
        ee.use_ssr = True
        ee.use_ssr_halfres = False
    elif profile["engine"] == "CYCLES":
        scene.cycles.samples = profile["samples"]
        scene.cycles.device = profile.get("device", "CPU")
        scene.cycles.seed = 0
    else:
        raise PipelineError(f"unsupported render engine {profile['engine']}")
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"


def main():
    p = make_parser("Render a preview image")
    p.add_argument("--config", required=True)
    p.add_argument("--profile", required=True, choices=["surface", "gaming", "surface-cpu"])
    p.add_argument("--output", required=True)
    p.add_argument("--view", default="rear34", choices=sorted(VIEWS))
    args = p.parse_args(script_args())

    if not bpy.data.filepath:
        raise PipelineError("open a built .blend before rendering")
    if bpy.data.collections.get("camper_shell") is None:
        raise PipelineError("collection 'camper_shell' missing; run build_scene.py first")
    cfg = load_json(args.config)
    if args.profile == "surface-cpu":
        profile = dict(cfg["render"]["surface"], engine="CYCLES", device="CPU")
    else:
        profile = cfg["render"][args.profile]

    objs, dims = build_truck(cfg)
    ground_z = -dims.rail
    add_ground(ground_z, bpy.data.collections["preview_context"])
    cam = setup_camera_and_light(args.view, ground_z)
    configure_render(profile)

    out = repo_path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(out)
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    elapsed = round(time.time() - t0, 2)
    if not out.is_file():
        raise PipelineError(f"render produced no file at {out}")
    rec = write_run_record("render_preview", {
        "blender": bpy.app.version_string, "source": bpy.data.filepath,
        "profile": args.profile, "settings": profile, "camera": cam,
        "seconds": elapsed, "output": str(args.output), "output_sha256": sha256_file(out),
    })
    print(f"rendered {out} in {elapsed}s\nrecord {rec}")


run_main(main)
