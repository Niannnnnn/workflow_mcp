import os
from pathlib import Path
from posebusters import PoseBusters
import pandas as pd
import argparse

# 解析命令行参数
parser = argparse.ArgumentParser(description="PoseBusters evaluation script")
parser.add_argument("--config", type=str, default="dock", choices=["dock", "mol"], help="PoseBusters configuration mode (dock or mol)")
parser.add_argument("--pred_file", type=str, required=True, help="Path to the predicted SDF file (required for dock mode)")
parser.add_argument("--true_file", type=str, required=True, help="Path to the true SDF file (required for dock mode)")
parser.add_argument("--cond_file", type=str, required=True, help="Path to the condition PDB file (required for dock mode)")
parser.add_argument("--dock_mode", type=str, required=True, help="dock mode(adgpu or vina)")
args = parser.parse_args()

# 设置输出目录
output_dir = Path("pb")
output_dir.mkdir(exist_ok=True)

# 验证输入文件存在
pred_file = Path(args.pred_file)
true_file = Path(args.true_file)
cond_file = Path(args.cond_file)

if not pred_file.exists():
    raise FileNotFoundError(f"Predicted file {pred_file} does not exist.")
if not true_file.exists():
    raise FileNotFoundError(f"True file {true_file} does not exist.")
if not cond_file.exists():
    raise FileNotFoundError(f"Condition file {cond_file} does not exist.")

# 初始化 PoseBusters
buster = PoseBusters(config=args.config)

# 单文件评估
result_df = buster.bust(pred_file, true_file, cond_file)
result_df["sdf_file"] = pred_file.name  # 记录文件名

# 保存为 CSV
output_csv = output_dir / "posebusters_results.csv"
result_df.to_csv(output_csv, index=False)
print(f"Results saved to: {output_csv}")

# 打印结果摘要
print("\n=== Summary ===")
print(f"Evaluated SDF file: {pred_file.name}")
print(f"Number of molecules evaluated: {len(result_df)}")
print(result_df.describe())