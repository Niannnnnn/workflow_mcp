import numpy as np

def get_pocket_center(pocket_pdb):
    coords = []
    with open(pocket_pdb, "r") as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                x, y, z = map(float, [line[30:38], line[38:46], line[46:54]])
                coords.append((x, y, z))

    coords = np.array(coords)
    center = coords.mean(axis=0)
    return center

# 指定新的 pocket.pdb 文件路径
pocket_file = "/home/zhangfn/workflow/3rfm.pdb"
center = get_pocket_center(pocket_file)

# 输出计算得到的网格中心坐标
print(f"Grid center: {center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f}")
# 将计算得到的网格中心坐标保存到 txt 文件
output_file = "/home/zhangfn/workflow/pocket_center.txt"
with open(output_file, "w") as f:
    f.write(f"{center[0]:.3f},{center[1]:.3f},{center[2]:.3f}")

print(f"Grid center saved to {output_file}")
