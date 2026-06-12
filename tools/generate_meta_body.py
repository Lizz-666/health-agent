import bpy
import math
import os
import sys

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

# ========== 创建所有 Metaball（先只定位，不合并）==========

positions = [
    # 头部
    ("BALL", 0, 0, 4.0, 0.62, 0, 0, 0),
    ("BALL", 0, 0, 3.35, 0.28, 0, 0, 0),
    # 躯干
    ("CAPSULE", 0, 0, 2.3, 0.65, 1.8, 0, 0),
    ("CAPSULE", 0, 0, 1.4, 0.55, 1.1, 0, 0),
    ("CAPSULE", 0, -0.08, 2.8, 0.72, 1.0, 0, 0),
    # 肩膀
    ("BALL", -0.65, 0, 3.2, 0.35, 0, 0, 0),
    ("BALL", 0.65, 0, 3.2, 0.35, 0, 0, 0),
    # 臀部
    ("BALL", -0.25, -0.2, 1.0, 0.42, 0, 0, 0),
    ("BALL", 0.25, -0.2, 1.0, 0.42, 0, 0, 0),
    # 左上臂+前臂+手
    ("CAPSULE", -0.65, -0.05, 2.95, 0.26, 0.85, 0, 0),
    ("CAPSULE", -0.72, 0, 2.15, 0.20, 0.75, 0, 0),
    ("BALL", -0.75, 0.05, 1.55, 0.16, 0, 0, 0),
    # 右上臂+前臂+手
    ("CAPSULE", 0.65, -0.05, 2.95, 0.26, 0.85, 0, 0),
    ("CAPSULE", 0.72, 0, 2.15, 0.20, 0.75, 0, 0),
    ("BALL", 0.75, 0.05, 1.55, 0.16, 0, 0, 0),
    # 左腿
    ("CAPSULE", -0.22, 0.05, 0.6, 0.38, 1.3, 0, 0),
    ("CAPSULE", -0.22, 0, -0.7, 0.28, 1.2, 0, 0),
    ("CAPSULE", -0.22, 0.15, -1.75, 0.15, 0.5, 0, 0),
    # 右腿
    ("CAPSULE", 0.22, 0.05, 0.6, 0.38, 1.3, 0, 0),
    ("CAPSULE", 0.22, 0, -0.7, 0.28, 1.2, 0, 0),
    ("CAPSULE", 0.22, 0.15, -1.75, 0.15, 0.5, 0, 0),
]

for i, (ptype, x, y, z, r, sx, sy, sz) in enumerate(positions):
    bpy.ops.object.metaball_add(type=ptype, location=(x, y, z))
    elem = bpy.context.object.data.elements[0]
    elem.radius = r
    if ptype == "CAPSULE" and sx > 0:
        elem.size_x = sx

# ========== 选中所有 Metaball ==========
bpy.ops.object.select_all(action="SELECT")
all_objs = [obj for obj in bpy.context.selected_objects if obj.type == "META"]
print(f"Found {len(all_objs)} metaball objects")

# ========== 提高 Metaball 分辨率 ==========
for obj in bpy.data.objects:
    if obj.type == "META":
        for elem in obj.data.elements:
            pass
        obj.data.resolution = 0.8
        obj.data.render_resolution = 1.0

bpy.context.view_layer.update()

# ========== 批量选中所有 Metaball 并转为 Mesh ==========
bpy.ops.object.select_all(action="DESELECT")
for obj in bpy.data.objects:
    if obj.type == "META":
        obj.select_set(True)

bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
print(f"Converting {len(bpy.context.selected_objects)} metaballs to mesh...")
bpy.ops.object.convert(target="MESH")

# ========== 合并所有 Mesh ==========
bpy.ops.object.select_all(action="DESELECT")
mesh_objs = [obj for obj in bpy.data.objects if obj.type == "MESH"]
print(f"Found {len(mesh_objs)} mesh objects, joining...")

for obj in mesh_objs:
    obj.select_set(True)
bpy.context.view_layer.objects.active = mesh_objs[0]
bpy.ops.object.join()

body = bpy.context.object
body.name = "Human_Body"
print(f"Joined into {body.name}")

# ========== 平滑 + 细分增加细节 ==========
bpy.ops.object.shade_smooth()

# Subdivision Surface 可以大幅增加面数，使模型更圆滑
mod = body.modifiers.new("Subdivision", "SUBSURF")
mod.levels = 2
mod.render_levels = 3
bpy.ops.object.modifier_apply(modifier="Subdivision")

bpy.ops.object.shade_smooth()

# ========== 材质 ==========
mat = bpy.data.materials.new("SkinMaterial")
mat.use_nodes = True
nodes = mat.node_tree.nodes
nodes.clear()

bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
bsdf.inputs["Base Color"].default_value = (0.91, 0.79, 0.63, 1.0)
bsdf.inputs["Roughness"].default_value = 0.55
bsdf.inputs["Subsurface Weight"].default_value = 0.22

output = nodes.new(type="ShaderNodeOutputMaterial")
mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
body.data.materials.append(mat)

# ========== 场景 ==========
bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = (
    0.10,
    0.10,
    0.15,
    1.0,
)

bpy.ops.object.light_add(type="SUN", location=(8, -3, 12))
bpy.ops.object.camera_add(location=(0, -6, 2.5))
bpy.context.object.rotation_euler = (math.radians(78), 0, 0)
bpy.context.scene.camera = bpy.context.object

# ========== 导出 GLB ==========
output_dir = os.getcwd()
try:
    idx = sys.argv.index("--")
    if idx + 1 < len(sys.argv):
        output_dir = sys.argv[idx + 1]
except ValueError:
    pass

output_path = os.path.join(output_dir, "human_body.glb")
print(f"Exporting to: {output_path}")

bpy.ops.export_scene.gltf(
    filepath=output_path,
    export_format="GLB",
    export_apply=True,
)

print(f"Done! {output_path}")
