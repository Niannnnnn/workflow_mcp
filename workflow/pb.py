# import os
# from pathlib import Path
# from posebusters import PoseBusters
# import pandas as pd
# import argparse

# # 解析命令行参数
# parser = argparse.ArgumentParser(description="PoseBusters evaluation script")
# parser.add_argument("--dock_mode", type=str, default=None, choices=["adgpu", "vina"], help="Docking mode (adgpu or vina)")
# parser.add_argument("--config", type=str, default="redock", choices=["redock", "mol"], help="PoseBusters configuration mode (redock or mol)")
# parser.add_argument("--input", type=str, help="Path to the input PDBQT file (only for mol mode)")
# args = parser.parse_args()

# # 设置默认的 dock_mode 和 dock_dir
# if args.dock_mode is None:
#     # 如果 dock_mode 为 None，则默认选择当前目录下的 3rfm_ligand.pdbqt 文件
#     args.dock_mode = "mol"  # 设置为 "mol" 模式
#     args.input = "/home/zhangfn/workflow/3rfm_mol.sdf"  # 默认输入文件路径
#     dock_dir = Path(".")  # 当前目录
# else:
#     # 根据对接模式设置 dock_dir
#     if args.dock_mode == "adgpu":
#         dock_dir = Path("dock/adgpu")  # 存放 AutoDock GPU 对接结果的 SDF 文件
#     elif args.dock_mode == "vina":
#         dock_dir = Path("dock/vina")  # 存放 AutoDock Vina 对接结果的 SDF 文件
#     else:
#         raise ValueError(f"Unsupported dock_mode: {args.dock_mode}")

# true_file = Path("3rfm_mol.sdf")  # 原始配体
# cond_file = Path("3rfm.pdb")  # 受体蛋白
# output_dir = Path("pb")  # 输出目录

# # 确保输出目录存在
# output_dir.mkdir(exist_ok=True)

# # 获取所有对接后的 SDF 文件
# if args.config == "redock":
#     pred_files = list(dock_dir.glob("*.sdf"))
#     if not pred_files:
#         raise FileNotFoundError(f"No SDF files found in {dock_dir}")
# else:
#     # 如果是 "mol" 模式，直接使用输入文件
#     if args.input is None:
#         raise ValueError("Input file path must be provided for mol mode")
#     pred_files = [Path(args.input)]

# # 初始化 PoseBusters
# buster = PoseBusters(config=args.config)

# # 逐个评估并合并结果
# results = []
# for pred_file in pred_files:
#     if args.config == "redock":
#         # Redock 模式：需要原始配体和受体蛋白文件
#         df = buster.bust([pred_file], true_file, cond_file, full_report=True)
#     elif args.config == "mol":
#         # Mol 模式：不需要原始配体和受体蛋白文件
#         df = buster.bust([pred_file], None, None, full_report=True)
#     else:
#         raise ValueError(f"Unsupported config mode: {args.config}")

#     df["sdf_file"] = pred_file.name  # 记录文件名
#     results.append(df)

# # 合并所有结果
# result_df = pd.concat(results, ignore_index=True)

# # 保存为 CSV（包含数值型数据）
# output_csv = output_dir / "posebusters_results.csv"
# result_df.to_csv(output_csv, index=False)
# print(f"Results saved to: {output_csv}")

# # 打印结果摘要
# print("\n=== Summary ===")
# print(f"Evaluated {len(pred_files)} SDF files.")
# print(result_df.describe())  # 数值统计摘要























import os
from pathlib import Path
from posebusters import PoseBusters
import pandas as pd
import argparse

# 解析命令行参数
parser = argparse.ArgumentParser(description="PoseBusters evaluation script")
parser.add_argument("--config", type=str, default="redock", choices=["redock", "mol"], help="PoseBusters configuration mode (redock or mol)")
# parser.add_argument("--dock_mode", type=str, default="adgpu", choices=["adgpu", "vina"], help="Docking mode (adgpu or vina)")
parser.add_argument("--pred_file", type=str, help="Path to the predicted SDF file (required for redock mode)")
parser.add_argument("--true_file", type=str, help="Path to the true SDF file (required for redock mode)")
parser.add_argument("--cond_file", type=str, help="Path to the condition PDB file (required for redock mode)")
args = parser.parse_args()

# # 设置默认的 dock_dir
# if args.dock_mode == "adgpu":
#     dock_dir = Path("dock/adgpu")
# elif args.dock_mode == "vina":
#     dock_dir = Path("dock/vina")
# else:
#     raise ValueError(f"Unsupported dock_mode: {args.dock_mode}")

# 设置输出目录
output_dir = Path("pb")
output_dir.mkdir(exist_ok=True)

# 获取预测文件
if args.config == "redock":
    if args.pred_file is None or args.true_file is None or args.cond_file is None:
        raise ValueError("pred_file, true_file, and cond_file must be provided for redock mode")
    pred_files = [Path(args.pred_file)]
    true_file = Path(args.true_file)
    cond_file = Path(args.cond_file)
else:
    raise ValueError("mol mode is not supported in this configuration")

# 初始化 PoseBusters
buster = PoseBusters(config=args.config)

# 逐个评估并合并结果
results = []
for pred_file in pred_files:
    df = buster.bust([pred_file], true_file, cond_file)
    df["sdf_file"] = pred_file.name  # 记录文件名
    results.append(df)

# 合并所有结果
result_df = pd.concat(results, ignore_index=True)

# 保存为 CSV
output_csv = output_dir / "posebusters_results.csv"
result_df.to_csv(output_csv, index=False)
print(f"Results saved to: {output_csv}")

# 打印结果摘要
print("\n=== Summary ===")
print(f"Evaluated {len(pred_files)} SDF files.")
print(result_df.describe())