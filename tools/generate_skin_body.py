"""
Body via Skin Modifier - simplified
"""

import bpy
import bmesh
import math
import os
import sys

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

coords = [
    (0, 0, 4.8),
    (0, 0, 4.2),
    (0, 0, 3.8),
    (0, 0, 3.4),  # 0-3: 头顶→颈
    (0, 0, 2.9),
    (0, 0, 2.3),
    (0, 0, 1.5),
    (0, 0, 0.6),  # 4-7: 肩→胸→腰→臀
    (0, 0, 0.0),  # 8: 裆分叉
    (-0.45, 0, 3.0),
    (-0.7, 0, 2.2),
    (-0.6, 0, 1.4),  # 9-11: 左臂
    (0.45, 0, 3.0),
    (0.7, 0, 2.2),
    (0.6, 0, 1.4),  # 12-14: 右臂
    (-0.2, 0, -0.4),
    (-0.2, 0, -1.2),
    (-0.2, 0, -2.0),  # 15-17: 左腿
    (0.2, 0, -0.4),
    (0.2, 0, -1.2),
    (0.2, 0, -2.0),  # 18-20: 右腿
]

edges = [
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (4, 5),
    (5, 6),
    (6, 7),  # 躯干
    (4, 9),
    (9, 10),
    (10, 11),  # 左臂
    (4, 12),
    (12, 13),
    (13, 14),  # 右臂
    (7, 8),
    (8, 15),
    (15, 16),
    (16, 17),  # 左腿
    (8, 18),
    (18, 19),
    (19, 20),  # 右腿
]

mesh = bpy.data.meshes.new("Skeleton")
bm = bmesh.new()
verts = [bm.verts.new(c) for c in coords]
bm.verts.ensure_lookup_table()
for e in edges:
    bm.edges.new((verts[e[0]], verts[e[1]]))
bm.to_mesh(mesh)
bm.free()

obj = bpy.data.objects.new("Human_Body", mesh)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj

# Skin Modifier
skin = obj.modifiers.new("Skin", "SKIN")
bpy.context.view_layer.update()

# Apply
bpy.ops.object.modifier_apply(modifier="Skin")

# Subdiv
subdiv = obj.modifiers.new("Subdiv", "SUBSURF")
subdiv.levels = 2
subdiv.render_levels = 3
bpy.ops.object.modifier_apply(modifier="Subdiv")

bpy.ops.object.shade_smooth()

# Material
mat = bpy.data.materials.new("Skin")
mat.use_nodes = True
nodes = mat.node_tree.nodes
nodes.clear()
bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
bsdf.inputs["Base Color"].default_value = (0.91, 0.79, 0.63, 1.0)
bsdf.inputs["Roughness"].default_value = 0.55
out_node = nodes.new(type="ShaderNodeOutputMaterial")
mat.node_tree.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
obj.data.materials.append(mat)

# Scene
bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = (
    0.10,
    0.10,
    0.15,
    1.0,
)
bpy.ops.object.light_add(type="SUN", location=(8, -3, 12))
bpy.context.object.data.energy = 6
bpy.ops.object.camera_add(location=(0, -6, 3))
bpy.context.object.rotation_euler = (math.radians(75), 0, 0)
bpy.context.scene.camera = bpy.context.object

# Export
output_dir = os.getcwd()
try:
    idx = sys.argv.index("--")
    if idx + 1 < len(sys.argv):
        output_dir = sys.argv[idx + 1]
except ValueError:
    pass

output_path = os.path.join(output_dir, "human_body.glb")
bpy.ops.export_scene.gltf(filepath=output_path, export_format="GLB", export_apply=True)
print(f"Done! {os.path.getsize(output_path) / 1024:.0f} KB")
