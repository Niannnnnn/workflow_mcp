import re
import os
import sys

def extract_pdbqt_from_dlg(dlg_file):
    # 创建 dock 文件夹（如果不存在的话）
    output_dir = "dock/adgpu"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(dlg_file, 'r') as f:
        content = f.read()

    # 获取输入文件名（不含扩展名）
    base_name = os.path.splitext(os.path.basename(dlg_file))[0]

    # 使用正则表达式匹配所有 DOCKED MODEL 块
    models = re.findall(r'DOCKED: MODEL\s+\d+\n(.*?)\nDOCKED: ENDMDL', content, re.DOTALL)

    for i, model in enumerate(models, 1):
        # 删除所有 "DOCKED: " 前缀
        pdbqt_content = model.replace("DOCKED: ", "")
        # 生成输出文件名，如 "3rfm_ligand_1.pdbqt"
        output_file = os.path.join(output_dir, f"{base_name}_{i}.pdbqt")
        # 写入文件
        with open(output_file, 'w') as f_out:
            f_out.write(pdbqt_content)
        print(f"Generated: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python dlg2pdbqt.py <input.dlg>")
        sys.exit(1)
    
    input_dlg = sys.argv[1]
    if not os.path.exists(input_dlg):
        print(f"Error: File '{input_dlg}' not found!")
        sys.exit(1)
    
    extract_pdbqt_from_dlg(input_dlg)
    print("Conversion completed!")
