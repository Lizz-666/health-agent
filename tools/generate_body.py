import bpy
import bmesh
import math
import os
import sys

# 清空场景
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

# ========== 用 Primitive 组装人体 ==========
# 策略：用变形后的立方体/球体/圆柱体拼出一个人体

# --- 头部 ---
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.35, location=(0, 0, 3.8))
head = bpy.context.object
head.name = "Head_Neck"
bpy.ops.object.shade_smooth()

# --- 颈部 ---
bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=0.4, location=(0, 0, 3.3))
neck = bpy.context.object
neck.name = "Neck"

# --- 躯干（胸廓+腹部+骨盆） ---
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 2.8))
torso = bpy.context.object
torso.scale = (0.55, 0.3, 1.3)
torso.name = "Shoulder_Thorax"
bpy.ops.object.transform_apply(scale=True)

# 骨盆区域（下半截躯干）
bpy.ops.mesh.primitive_cylinder_add(radius=0.45, depth=0.9, location=(0, 0, 1.5))
pelvis = bpy.context.object
pelvis.name = "Pelvis_Spine"

# --- 左上臂 ---
bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=1.0, location=(-0.65, 0, 3.0))
l_upper = bpy.context.object
l_upper.name = "L_UpperArm"
l_upper.rotation_euler = (0, 0, math.radians(15))

# --- 左前臂 ---
bpy.ops.mesh.primitive_cylinder_add(radius=0.10, depth=0.9, location=(-0.75, 0, 2.1))
l_forearm = bpy.context.object
l_forearm.name = "L_Forearm"

# --- 右上臂 ---
bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=1.0, location=(0.65, 0, 3.0))
r_upper = bpy.context.object
r_upper.name = "R_UpperArm"
r_upper.rotation_euler = (0, 0, math.radians(-15))

# --- 右前臂 ---
bpy.ops.mesh.primitive_cylinder_add(radius=0.10, depth=0.9, location=(0.75, 0, 2.1))
r_forearm = bpy.context.object
r_forearm.name = "R_Forearm"

# --- 左大腿 ---
bpy.ops.mesh.primitive_cylinder_add(radius=0.16, depth=1.2, location=(-0.22, 0, 0.8))
l_thigh = bpy.context.object
l_thigh.name = "L_Thigh"

# --- 左小腿 ---
bpy.ops.mesh.primitive_cylinder_add(radius=0.13, depth=1.1, location=(-0.22, 0, -0.4))
l_calf = bpy.context.object
l_calf.name = "L_Calf"

# --- 右大腿 ---
bpy.ops.mesh.primitive_cylinder_add(radius=0.16, depth=1.2, location=(0.22, 0, 0.8))
r_thigh = bpy.context.object
r_thigh.name = "R_Thigh"

# --- 右小腿 ---
bpy.ops.mesh.primitive_cylinder_add(radius=0.13, depth=1.1, location=(0.22, 0, -0.4))
r_calf = bpy.context.object
r_calf.name = "R_Calf"

# --- 脚 ---
for x in [-0.22, 0.22]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0.12, -1.1))
    foot = bpy.context.object
    foot.scale = (0.13, 0.3, 0.08)
    bpy.ops.object.transform_apply(scale=True)

# ========== 合并所有身体部件为单一 Mesh ==========
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.join()
body = bpy.context.object
body.name = "Human_Body"

# ========== 设置材质（骨骼质感） ==========
mat = bpy.data.materials.new("BodyMaterial")
mat.use_nodes = True
nodes = mat.node_tree.nodes
nodes.clear()

# Principled BSDF
bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
bsdf.inputs["Base Color"].default_value = (0.75, 0.73, 0.70, 1.0)  # 骨白色
bsdf.inputs["Roughness"].default_value = 0.45
bsdf.inputs["Subsurface Weight"].default_value = 0.15

output = nodes.new(type="ShaderNodeOutputMaterial")
mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

body.data.materials.append(mat)

# ========== 设置场景（深色背景） ==========
bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = (
    0.08,
    0.08,
    0.12,
    1.0,
)

# 添加光照
bpy.ops.object.light_add(type="SUN", location=(5, 5, 10))
sun = bpy.context.object
sun.data.energy = 5

# 摄像机
bpy.ops.object.camera_add(location=(0, -5, 3))
cam = bpy.context.object
cam.rotation_euler = (math.radians(80), 0, 0)

# ========== 导出 GLB ==========
# Blender 传参方式: blender --background --python script.py -- output_dir
output_dir = os.getcwd()
try:
    idx = sys.argv.index("--")
    if idx + 1 < len(sys.argv):
        output_dir = sys.argv[idx + 1]
except ValueError:
    pass

output_path = os.path.join(output_dir, "human_body.glb")
print(f"Exporting GLB to: {output_path}")

bpy.ops.export_scene.gltf(
    filepath=output_path,
    export_format="GLB",
    export_apply=True,
    export_texcoords=False,
    export_normals=True,
    use_selection=False,
)

print(f"GLB exported to: {output_path}")
