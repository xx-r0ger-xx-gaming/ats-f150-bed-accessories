"""V1 colour-matched cab-high bed shell (the exported mod geometry, rebuilt with render materials).

Uses the exact same builders as scripts/build_scene.py (lib/shell_v1.py), driven by the config
named in cfg["camper"]["config"] (default config/v1.json), so the render shows the real shell.
"""
from lib.common import load_json
from lib.meshkit import add_weighted_normals
from lib.shell_v1 import build_shell

TRUCK_TYPES = ("pickup",)
DESCRIPTION = "Colour-matched cab-high camper shell (V1 mod geometry)"


def build(cfg, collection, mats):
    shell_cfg = load_json(cfg["camper"].get("config", "config/v1.json"))
    role_mats = {"shell_paint": mats["paint"], "glass": mats["glass"], "trim": mats["trim"],
                 "lamp": mats["lamp_red_lens"]}
    objs = build_shell(shell_cfg, role_mats, collection)
    for ob in objs:
        if ob.name.startswith("shell_body"):
            add_weighted_normals(ob)
    return objs
