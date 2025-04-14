# from rdkit import Chem
# from openbabel import pybel
# import argparse
# import os

# # 解析命令行参数
# parser = argparse.ArgumentParser(description="Convert PDBQT to SDF")
# parser.add_argument("--input", type=str, help="Path to the input PDBQT file")
# parser.add_argument("--output", type=str, help="Path to the output SDF file")
# args = parser.parse_args()

# def convert_pdbqt_to_sdf(input_pdbqt: str, output_sdf: str) -> bool:
#     try:
#         # 使用 Open Babel (pybel) 转换 PDBQT 到 PDB 格式
#         mol = pybel.readfile("pdbqt", input_pdbqt).__next__()  # 读取文件
#         temp_pdb_file = input_pdbqt.replace('.pdbqt', '.pdb')
#         mol.write("pdb", temp_pdb_file, overwrite=True)  # 保存为 PDB 格式
        
#         # 使用 RDKit 读取 PDB 文件并保存为 SDF
#         mol_rdkit = Chem.MolFromPDBFile(temp_pdb_file, sanitize=False)
        
#         if mol_rdkit:
#             writer = Chem.SDWriter(output_sdf)
#             writer.write(mol_rdkit)
#             writer.close()
#             print(f'转换成功: {input_pdbqt} -> {output_sdf}')
#             return True
#         else:
#             print(f'读取失败: {input_pdbqt}')
#             return False
#     except Exception as e:
#         print(f'转换失败: {e}')
#         return False
#     finally:
#         # 删除临时 PDB 文件
#         if os.path.exists(temp_pdb_file):
#             os.remove(temp_pdb_file)

# if __name__ == "__main__":
#     if args.input and args.output:
#         convert_pdbqt_to_sdf(args.input, args.output)
#     else:
#         print("请提供输入和输出文件路径")






import argparse
import os
import subprocess
from rdkit import Chem

# 命令行参数解析
parser = argparse.ArgumentParser(description="Convert PDBQT to SDF via MOL2")
parser.add_argument("--input", type=str, help="Path to the input PDBQT file")
parser.add_argument("--output", type=str, help="Path to the output SDF file")
args = parser.parse_args()

def convert_pdbqt_to_sdf(input_pdbqt: str, output_sdf: str) -> bool:
    temp_mol2_file = input_pdbqt.replace(".pdbqt", ".mol2")

    try:
        # Step 1: 用 obabel 命令行转换 PDBQT -> MOL2
        print(f"🌀 使用 obabel 转换: {input_pdbqt} -> {temp_mol2_file}")
        subprocess.run(["obabel", input_pdbqt, "-O", temp_mol2_file], check=True)

        # Step 2: 用 RDKit 读取 MOL2
        print(f"📥 使用 RDKit 读取 mol2: {temp_mol2_file}")
        mol_rdkit = Chem.MolFromMol2File(temp_mol2_file, sanitize=True)

        if mol_rdkit is None:
            print(f"❌ RDKit 无法读取 mol2 文件（结构可能有问题）：{temp_mol2_file}")
            return False

        # Step 3: 写入 SDF 文件
        print(f"📤 写入 SDF 文件: {output_sdf}")
        writer = Chem.SDWriter(output_sdf)
        writer.write(mol_rdkit)
        writer.close()

        print(f"✅ 转换成功: {temp_mol2_file} -> {output_sdf}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ obabel 转换失败：{e}")
        return False
    except Exception as e:
        print(f"❌ 其他异常：{e}")
        return False
    finally:
        # 清理中间文件
        if os.path.exists(temp_mol2_file):
            os.remove(temp_mol2_file)
            print(f"🧹 删除临时文件: {temp_mol2_file}")

if __name__ == "__main__":
    if args.input and args.output:
        success = convert_pdbqt_to_sdf(args.input, args.output)
        if not success:
            print("⚠️ 转换过程中出现问题，未生成 SDF 文件")
    else:
        print("🚫 请提供输入和输出文件路径，例如：--input a.pdbqt --output a.sdf")
