# from rdkit import Chem
# import os
# from openbabel import pybel

# def split_and_convert_pdbqt_to_sdf(input_pdbqt: str, output_folder: str):
#     """
#     将包含多个模型的 PDBQT 文件拆分为多个单独的 PDBQT 文件，并将每个文件转换为 SDF 格式。
    
#     :param input_pdbqt: 包含多个模型的 PDBQT 文件路径
#     :param output_folder: 输出文件夹路径
#     """
#     # 确保输出文件夹存在
#     os.makedirs(output_folder, exist_ok=True)

#     # 读取输入的 PDBQT 文件
#     with open(input_pdbqt, 'r') as f:
#         content = f.read()

#     # 按模型拆分内容
#     models = content.split("ENDMDL\n")
#     for i, model in enumerate(models):
#         if not model.strip():
#             continue  # 跳过空模型

#         # 创建单独的 PDBQT 文件
#         model_pdbqt = os.path.join(output_folder, f"model_{i + 1}.pdbqt")
#         with open(model_pdbqt, 'w') as f:
#             f.write(model.strip() + "\nENDMDL\n")

#         # 使用 Open Babel 将 PDBQT 转换为 PDB
#         mol = pybel.readfile("pdbqt", model_pdbqt).__next__()
#         model_pdb = model_pdbqt.replace('.pdbqt', '.pdb')
#         mol.write("pdb", model_pdb, overwrite=True)

#         # 使用 RDKit 将 PDB 转换为 SDF
#         mol_rdkit = Chem.MolFromPDBFile(model_pdb)
#         if mol_rdkit:
#             model_sdf = model_pdbqt.replace('.pdbqt', '.sdf')
#             writer = Chem.SDWriter(model_sdf)
#             writer.write(mol_rdkit)
#             writer.close()
#             print(f'转换成功: {model_pdbqt} -> {model_sdf}')
#         else:
#             print(f'读取失败: {model_pdbqt}')

# # 示例用法
# # input_pdbqt = "/home/zhangfn/workflow/dock/vina/3rfm_vina.pdbqt"  # 替换为 Vina 输出文件路径
# # output_folder = "/home/zhangfn/workflow/dock/vina"  # 替换为输出文件夹路径

# split_and_convert_pdbqt_to_sdf(input_pdbqt, output_folder)



















from rdkit import Chem
from openbabel import pybel
import argparse
import os

# 解析命令行参数
parser = argparse.ArgumentParser(description="Convert PDBQT to SDF for Vina mode")
parser.add_argument("--input", type=str, help="Path to the input PDBQT file")
parser.add_argument("--output", type=str, help="Path to the output SDF file")
args = parser.parse_args()

def split_and_convert_pdbqt_to_sdf(input_pdbqt: str, output_sdf: str) -> bool:
    """
    将包含多个模型的 PDBQT 文件拆分为多个单独的 SDF 文件。
    
    :param input_pdbqt: 包含多个模型的 PDBQT 文件路径
    :param output_sdf: 输出 SDF 文件路径
    """
    try:
        # 读取输入的 PDBQT 文件
        with open(input_pdbqt, 'r') as f:
            content = f.read()

        # 按模型拆分内容
        models = content.split("ENDMDL\n")
        sdf_writer = Chem.SDWriter(output_sdf)

        for i, model in enumerate(models):
            if not model.strip():
                continue  # 跳过空模型

            # 创建临时 PDBQT 文件
            temp_pdbqt = f"temp_model_{i + 1}.pdbqt"
            with open(temp_pdbqt, 'w') as f:
                f.write(model.strip() + "\nENDMDL\n")

            # 使用 Open Babel 将 PDBQT 转换为 PDB
            mol = pybel.readfile("pdbqt", temp_pdbqt).__next__()
            temp_pdb = temp_pdbqt.replace('.pdbqt', '.pdb')
            mol.write("pdb", temp_pdb, overwrite=True)

            # 使用 RDKit 将 PDB 转换为 SDF
            mol_rdkit = Chem.MolFromPDBFile(temp_pdb)
            if mol_rdkit:
                sdf_writer.write(mol_rdkit)
                print(f'转换成功: {temp_pdbqt} -> {output_sdf}')
            else:
                print(f'读取失败: {temp_pdbqt}')

        sdf_writer.close()

        # 清理临时文件
        for temp_file in [f"temp_model_{i + 1}.pdbqt" for i in range(len(models))]:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return True
    except Exception as e:
        print(f'转换失败: {e}')
        return False

if __name__ == "__main__":
    if args.input and args.output:
        split_and_convert_pdbqt_to_sdf(args.input, args.output)
    else:
        print("请提供输入和输出文件路径")