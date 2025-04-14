from flask import Flask, request, send_file, jsonify
import subprocess
import os
from pathlib import Path
from werkzeug.utils import secure_filename
from typing import List, Optional
import logging
from datetime import datetime
from openbabel import pybel
import shutil

# 配置日志
logging.basicConfig(
    filename="workflow_api.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

app = Flask(__name__)

# 工作目录
WORKING_DIR = Path("/home/zhangfn/workflow")
UPLOAD_FOLDER = WORKING_DIR / "uploads"
DOWNLOAD_FOLDER = WORKING_DIR / "downloads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['DOWNLOAD_FOLDER'] = str(DOWNLOAD_FOLDER)

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'pdb', 'sdf', 'pdbqt'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class WorkflowStep:
    """工作流中的单个步骤基类"""
    def __init__(self, name: str, working_dir: str):
        self.name = name
        self.working_dir = Path(working_dir)
        self.checkpoint_file = self.working_dir / f"{name}_checkpoint.txt"

    def run(self) -> bool:
        raise NotImplementedError

    def save_checkpoint(self):
        """保存检查点，包含当前时间"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.checkpoint_file, "w") as f:
            f.write(f"completed at {current_time}")
        logging.info(f"Checkpoint saved for {self.name} at {current_time}")

    # def check_checkpoint(self) -> bool:
    #     """检查是否已完成"""
    #     return self.checkpoint_file.exists()

class MoleculeGeneration(WorkflowStep):
    """分子生成步骤"""
    def __init__(self, working_dir: str, pdb_file: str, outfile: str, ref_ligand: str = "A:330", n_samples: int = 1):
        super().__init__("mol_generate", working_dir)
        self.pdb_file = pdb_file
        self.outfile = outfile
        self.ref_ligand = ref_ligand
        self.n_samples = n_samples

    def run(self) -> bool:
        # if self.check_checkpoint():
        #     logging.info("Molecule generation already completed, skipping...")
        #     return True

        cmd = [
            "python3", "/home/zhangfn/DiffSBDD/generate_ligands.py",
            "/home/zhangfn/DiffSBDD/checkpoints/crossdocked_fullatom_cond.ckpt",
            "--pdbfile", self.pdb_file,
            "--outfile", self.outfile,
            "--ref_ligand", self.ref_ligand,
            "--n_samples", str(self.n_samples)
        ]
        try:
            subprocess.run(cmd, check=True, cwd=self.working_dir)
            self.save_checkpoint()
            logging.info("Molecule generation completed successfully")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Molecule generation failed: {e}")
            return False

class MolecularDocking(WorkflowStep):
    """分子对接步骤"""
    def __init__(self, working_dir: str, ligand_sdf: str, protein_pdb: str, dock_mode: str = "adgpu"):
        super().__init__("dock", working_dir)
        self.ligand_sdf = ligand_sdf
        self.protein_pdb = protein_pdb
        self.dock_mode = dock_mode
        self.grid_center = None
        
        # 从 protein_pdb 文件名中提取 base_name
        protein_pdb_filename = Path(self.protein_pdb).stem
        self.protein_pdbqt = self.working_dir / f"{protein_pdb_filename}_protein.pdbqt"
        self.gpf_prefix = protein_pdb_filename.split('_')[0]  # 提取第一个下划线前的前缀
        
        # 初始化 ligand_pdbqt 为 None
        self.ligand_pdbqt = None
        
        # 为 Vina 创建输出目录
        if self.dock_mode == "vina":
            self.vina_output_dir = self.working_dir / "dock" / "vina"
            self.vina_output_dir.mkdir(parents=True, exist_ok=True)
            self.vina_output_file = self.vina_output_dir / "3rfm_vina.pdbqt"  # 临时输出文件
            self.output_file = self.working_dir / "downloads" / "3rfm_vina.pdbqt"  # 最终下载文件
        # 为 ADGPU 创建输出目录
        if self.dock_mode == "adgpu":
            self.adgpu_output_dir = self.working_dir / "dock" / "adgpu"
            self.adgpu_output_dir.mkdir(parents=True, exist_ok=True)
            self.output_file = None  # 在 convert_dlg_to_pdbqt 中动态设置

    def get_ligand_pdbqt_files(self):
        """动态获取所有 ligand_pdbqt 文件"""
        # 从 ligand_sdf 文件名中提取 base_name
        ligand_sdf_filename = Path(self.ligand_sdf).stem
        base_name = ligand_sdf_filename.split('_')[0]
        print(f"base_name : {base_name} ****************************************")
        # 匹配所有 ligand_pdbqt 文件
        pattern = f"{base_name}_ligand_*.pdbqt"
        pdbqt_files = list(self.working_dir.glob(pattern))
        
        if not pdbqt_files:
            raise FileNotFoundError(f"No PDBQT files found matching {pattern} in {self.working_dir}")
        
        return pdbqt_files

    def run(self) -> bool:
        steps = [
            (self.convert_ligand_format, "Convert ligand format"),
            (self.convert_receptor_format, "Convert receptor format"),
            (self.calculate_grid_center, "Calculate grid center"),
            (self.generate_gpf_file, "Generate GPF file"),
            (self.generate_fld_file, "Generate FLD file"),
            (self.organize_gpf_files, "Organize GPF files"),  # 新增步骤
            (self.run_docking, f"Run {self.dock_mode.upper()} docking")
        ]

        if self.dock_mode == "adgpu":
            steps.append((self.convert_dlg_to_pdbqt, "Convert DLG to PDBQT"))

        for step, step_name in steps:
            try:
                step()
                logging.info(f"{step_name} completed")
            except Exception as e:
                logging.error(f"{step_name} failed: {e}")
                return False

        self.save_checkpoint()
        logging.info("Molecular docking completed successfully")
        return True


    def organize_gpf_files(self):
        """将生成的 GPF 和相关文件组织到以 gpf_prefix 命名的目录中，并确保 protein_pdbqt 文件可用"""
        # 获取所有 GPF 文件（现在它们在 gpf 子目录中）
        gpf_dir = self.working_dir / "gpf"
        if not gpf_dir.exists():
            raise FileNotFoundError("GPF directory not found")

        gpf_subdirs = list(gpf_dir.glob("*"))
        if not gpf_subdirs:
            raise FileNotFoundError("No GPF subdirectories found")

        for gpf_subdir in gpf_subdirs:
            if not gpf_subdir.is_dir():
                continue

            # 确保 protein_pdbqt 文件存在于当前 GPF 子目录中
            protein_pdbqt_in_subdir = gpf_subdir / self.protein_pdbqt.name
            if not protein_pdbqt_in_subdir.exists():
                # 复制 protein_pdbqt 到当前 GPF 子目录
                import shutil
                shutil.copy(self.protein_pdbqt, protein_pdbqt_in_subdir)
                logging.info(f"Copied {self.protein_pdbqt} to {protein_pdbqt_in_subdir}")

            # 匹配所有相关文件
            patterns = [
                f"{self.gpf_prefix}_protein_ligand.gpf",
                f"{self.gpf_prefix}_protein.*.map",
                f"{self.gpf_prefix}_protein.maps.fld",
                f"{self.gpf_prefix}_protein.maps.xyz",
            ]

            moved_files = []
            for pattern in patterns:
                files = list(gpf_subdir.glob(pattern))
                for file in files:
                    moved_files.append(file)
                    logging.info(f"Found {file} in {gpf_subdir}")

            if not moved_files:
                logging.warning(f"No files found to organize for {gpf_subdir}")

    


    def convert_dlg_to_pdbqt(self):
        """将 ADGPU 生成的 DLG 文件转换为 PDBQT，并移动所有相关模型到 downloads 目录"""
        if not isinstance(self.ligand_pdbqt, list):
            raise ValueError("self.ligand_pdbqt should be a list of Path objects")

        for ligand_pdbqt in self.ligand_pdbqt:
            dlg_file = self.working_dir / f"{ligand_pdbqt.stem}.dlg"
            
            if not dlg_file.exists():
                raise FileNotFoundError(f"DLG file not found: {dlg_file}")

            cmd = [
                "python3", 
                "/home/zhangfn/workflow/dlg2pdbqt.py",
                str(dlg_file)
            ]
            
            try:
                subprocess.run(cmd, check=True, cwd=self.working_dir)
                output_dir = self.working_dir / "dock" / "adgpu"
                base_name = ligand_pdbqt.stem
                
                # 移动生成的 PDBQT 文件到 downloads 目录
                pattern = f"{base_name}_*.pdbqt"
                generated_files = list(output_dir.glob(pattern))
                
                if not generated_files:
                    raise FileNotFoundError(f"No PDBQT files found matching {pattern} in {output_dir}")
                
                moved_files = []
                for dlg_output in generated_files:
                    target_file = self.working_dir / "downloads" / dlg_output.name
                    os.rename(dlg_output, target_file)
                    moved_files.append(target_file)
                    logging.info(f"Converted and moved {dlg_output} to {target_file}")
                
                logging.info(f"Converted {dlg_file} to {len(moved_files)} PDBQT files: {moved_files}")
                
                # 新增：将 DLG、XML 和 _adgpu.log 文件转移到 dock/adgpu 目录
                target_dir = self.working_dir / "dock" / "adgpu"
                os.makedirs(target_dir, exist_ok=True)  # 确保目标目录存在
                
                # 匹配 DLG 文件
                dlg_files = list(self.working_dir.glob(f"{base_name}.dlg"))
                # 匹配 XML 文件
                xml_files = list(self.working_dir.glob(f"{base_name}.xml"))
                # 匹配 _adgpu.log 文件
                log_files = list(self.working_dir.glob(f"{base_name}_adgpu.log"))
                
                # 合并所有需要转移的文件
                files_to_move = dlg_files + xml_files + log_files
                
                if not files_to_move:
                    logging.warning(f"No files found to move for {base_name}")
                    continue
                
                moved_files = []
                for file in files_to_move:
                    target_file = target_dir / file.name
                    os.rename(file, target_file)
                    moved_files.append(target_file)
                    logging.info(f"Moved {file} to {target_file}")
                
                logging.info(f"Moved {len(moved_files)} files to {target_dir}: {moved_files}")
                
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"DLG to PDBQT conversion failed: {e}")





    def calculate_grid_center(self):
        """计算网格中心并存储坐标"""
        cmd = ["python3", "/home/zhangfn/workflow/grid_center.py"]
        subprocess.run(cmd, check=True, cwd=self.working_dir)
        
        pocket_file = self.working_dir / "pocket_center.txt"
        if pocket_file.exists():
            with open(pocket_file, 'r') as f:
                center_coords = f.read().strip().split(',')
                if len(center_coords) == 3:
                    self.grid_center = [float(coord) for coord in center_coords]
                    logging.info(f"Grid center coordinates read: {self.grid_center}")
                else:
                    raise ValueError("pocket_center.txt does not contain valid x,y,z coordinates")
        else:
            raise FileNotFoundError("pocket_center.txt was not generated")


    def generate_gpf_file(self):
        """动态生成每个配体文件对应的 GPF 文件"""
        if self.grid_center is None:
            raise ValueError("Grid center not calculated yet")
        
        if not isinstance(self.ligand_pdbqt, list):
            raise ValueError("self.ligand_pdbqt should be a list of Path objects")
        
        gridcenter_str = f"{self.grid_center[0]},{self.grid_center[1]},{self.grid_center[2]}"
        
        for idx, ligand_pdbqt in enumerate(self.ligand_pdbqt):
            # 动态生成 GPF 文件名
            ligand_base_name = ligand_pdbqt.stem
            gpf_file = self.working_dir / f"{ligand_base_name}_protein_ligand.gpf"
            
            cmd = [
                "/home/zhangfn/.conda/envs/targetdiff/bin/python",
                "/home/zhangfn/mgltools_x86_64Linux2_1.5.7/MGLToolsPckgs/AutoDockTools/Utilities24/prepare_gpf4.py",
                "-l", str(ligand_pdbqt),  # 使用当前配体文件
                "-r", str(self.protein_pdbqt),
                "-o", str(gpf_file),
                "-p", "npts=30,30,30",
                "-p", "ligand_types=C,SA,N,HD,OA,Br,NA,I,A,Cl,F,P,S",
                "-p", f"gridcenter={gridcenter_str}"
            ]
            subprocess.run(cmd, check=True, cwd=self.working_dir)
            logging.info(f"Generated GPF file for ligand {ligand_pdbqt}: {gpf_file}")
            
            # 提取 GPF 文件的前缀（例如 "3rfm_ligand_0"）
            gpf_prefix = '_'.join(gpf_file.stem.split('_')[:3])
            
            # 创建 gpf 文件夹
            gpf_dir = self.working_dir / "gpf"
            gpf_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建基于前缀的子文件夹
            prefix_dir = gpf_dir / gpf_prefix
            prefix_dir.mkdir(parents=True, exist_ok=True)
            
            # 将 GPF 文件移动到子文件夹中
            target_path = prefix_dir / gpf_file.name
            shutil.move(str(gpf_file), str(target_path))
            logging.info(f"Moved GPF file to {target_path}")


    def run_docking(self):
        """运行对接，动态处理每个配体文件"""
        if self.dock_mode == "adgpu":
            self.run_docking_adgpu()
        elif self.dock_mode == "vina":
            self.run_docking_vina()
        else:
            raise ValueError(f"Unsupported dock_mode: {self.dock_mode}")

    def run_docking_vina(self):
        """运行 AutoDock Vina 对接，处理每个配体文件"""
        if self.grid_center is None:
            raise ValueError("Grid center not calculated yet")

        for ligand_pdbqt in self.ligand_pdbqt:
            output_pdbqt = self.vina_output_dir / f"{ligand_pdbqt.stem}_vina.pdbqt"
            cmd = [
                "vina",
                "--receptor", str(self.protein_pdbqt),
                "--ligand", str(ligand_pdbqt),
                "--out", str(output_pdbqt),
                "--center_x", str(self.grid_center[0]),
                "--center_y", str(self.grid_center[1]),
                "--center_z", str(self.grid_center[2]),
                "--size_x", "30",
                "--size_y", "30",
                "--size_z", "30"
            ]
            subprocess.run(cmd, check=True, cwd=self.working_dir)
            logging.info(f"Vina docking completed for {ligand_pdbqt}")

    def run_docking_adgpu(self):
        """运行 AutoDock GPU 对接，处理每个配体文件"""
        for ligand_pdbqt in self.ligand_pdbqt:
            log_prefix = ligand_pdbqt.stem.split('.')[0]
            fld_prefix = ligand_pdbqt.stem.split('_')[0]
            log_file = self.working_dir / f"{log_prefix}_adgpu.log"

            # 获取对应的 FLD 文件
            fld_file = self.working_dir / "gpf" / log_prefix / f"{fld_prefix}_protein.maps.fld"

            cmd = [
                "/home/zhangfn/AutoDock-GPU-develop/bin/autodock_gpu_64wi",
                "--ffile", str(fld_file),  # 使用对应的 FLD 文件
                "--lfile", str(ligand_pdbqt),
                "-nrun", "1"
            ]
            
            with open(log_file, 'w') as f:
                subprocess.run(cmd, check=True, cwd=self.working_dir, stdout=f, stderr=subprocess.STDOUT)
            logging.info(f"AutoDock GPU docking completed for {ligand_pdbqt}, output redirected to {log_file}")



    def convert_ligand_format(self):
        """使用 openbabel 转换配体格式，处理 SDF 文件中的每个分子"""
        # 从 ligand_sdf 文件名中提取第一个下划线前的字段
        ligand_sdf_filename = Path(self.ligand_sdf).stem  # 获取文件名（不带扩展名）
        base_name = ligand_sdf_filename.split('_')[0]      # 提取第一个下划线前的字段

        mol_generator = pybel.readfile("sdf", self.ligand_sdf)
        ligand_pdbqt_base = self.working_dir / f"{base_name}_ligand"
        ligand_pdbqt_files = []

        for idx, molecule in enumerate(mol_generator):
            output_pdbqt = ligand_pdbqt_base.with_name(f"{base_name}_ligand_{idx}.pdbqt")
            molecule.write("pdbqt", str(output_pdbqt), overwrite=True)
            ligand_pdbqt_files.append(output_pdbqt)
            logging.info(f"Converted molecule {idx} to {output_pdbqt}")

        if not ligand_pdbqt_files:
            raise ValueError("No molecules found in the SDF file")

        # 动态获取 ligand_pdbqt 文件
        self.ligand_pdbqt = self.get_ligand_pdbqt_files()
        logging.info(f"Converted {len(ligand_pdbqt_files)} molecules to PDBQT format")

    def convert_receptor_format(self):
        """使用 MGLTools 转换受体格式"""
        cmd = [
            "/home/zhangfn/.conda/envs/targetdiff/bin/python",
            "/home/zhangfn/mgltools_x86_64Linux2_1.5.7/MGLToolsPckgs/AutoDockTools/Utilities24/prepare_receptor4.py",
            "-r", self.protein_pdb,
            "-A", "hydrogens",
            "-v",
            "-o", str(self.protein_pdbqt)
        ]
        subprocess.run(cmd, check=True, cwd=self.working_dir)

    def generate_fld_file(self):
        """动态生成每个 GPF 文件对应的 FLD 文件，并确保 protein_pdbqt 文件可用"""
        # 获取所有 GPF 子目录
        gpf_dir = self.working_dir / "gpf"
        if not gpf_dir.exists():
            raise FileNotFoundError("GPF directory not found")

        gpf_subdirs = list(gpf_dir.glob("*"))
        if not gpf_subdirs:
            raise FileNotFoundError("No GPF subdirectories found")

        for gpf_subdir in gpf_subdirs:
            if not gpf_subdir.is_dir():
                continue

            # 确保 protein_pdbqt 文件存在于当前 GPF 子目录中
            protein_pdbqt_in_subdir = gpf_subdir / self.protein_pdbqt.name
            if not protein_pdbqt_in_subdir.exists():
                # 复制 protein_pdbqt 到当前 GPF 子目录
                import shutil
                shutil.copy(self.protein_pdbqt, protein_pdbqt_in_subdir)
                logging.info(f"Copied {self.protein_pdbqt} to {protein_pdbqt_in_subdir}")

            # 获取 GPF 文件
            gpf_files = list(gpf_subdir.glob("*.gpf"))
            if not gpf_files:
                logging.warning(f"No GPF files found in {gpf_subdir}")
                continue

            for gpf_file in gpf_files:
                # 在子目录中生成 FLD 文件
                cmd = ["/home/zhangfn/x86_64Linux2/autogrid4", "-p", str(gpf_file)]
                try:
                    subprocess.run(cmd, check=True, cwd=str(gpf_subdir))
                    logging.info(f"Generated FLD file for {gpf_file}")
                except subprocess.CalledProcessError as e:
                    logging.error(f"Failed to generate FLD file for {gpf_file}: {e}")
                    raise



class ConformationEvaluation(WorkflowStep):
    """构象评估步骤"""
    def __init__(self, working_dir: str, mode: str, mol_file: str, dock_mode: str, true_file: str, cond_file: str):
        super().__init__("eval", working_dir)
        self.mode = mode
        self.mol_file = mol_file
        self.dock_mode = dock_mode
        self.true_file = true_file
        self.cond_file = cond_file
        self.output_csv = self.working_dir / "pb" / "posebusters_results.csv"  # pb.py 的输出位置
        self.downloads_dir = self.working_dir / "downloads"
        self.downloads_dir.mkdir(exist_ok=True)  # 确保 downloads 目录存在

    def run(self) -> bool:
        # 获取文件名的前缀部分
        mol_file_stem = Path(self.mol_file).stem  # 获取 mol_file 的文件名前缀
        true_file_stem = Path(self.true_file).stem  # 获取 true_file 的文件名前缀

        # 根据 dock_mode 调用不同的脚本处理 pred_file 和 true_file
        if self.dock_mode == "adgpu":
            # 处理 ADGPU 模式下的 pred_file 和 true_file
            pred_processed = f"{mol_file_stem}_processed.sdf"
            true_processed = f"{true_file_stem}_processed.sdf"
            
            cmd1 = [
                "python3", "/home/zhangfn/workflow/pdbqt2sdf_adgpu.py",
                "--input", self.mol_file,
                "--output", pred_processed
            ]
            
            cmd2 = [
                "python3", "/home/zhangfn/workflow/pdbqt2sdf_adgpu.py",
                "--input", self.true_file,
                "--output", true_processed
            ]
        elif self.dock_mode == "vina":
            # 处理 Vina 模式下的 pred_file 和 true_file
            pred_processed = f"{mol_file_stem}_processed.sdf"
            true_processed = f"{true_file_stem}_processed.sdf"
            
            cmd1 = [
                "python3", "/home/zhangfn/workflow/pdbqt2sdf_vina.py",
                "--input", self.mol_file,
                "--output", pred_processed
            ]
            
            cmd2 = [
                "python3", "/home/zhangfn/workflow/pdbqt2sdf_vina.py",
                "--input", self.true_file,
                "--output", true_processed
            ]
        else:
            return False

        # 调用 pb.py 进行评估
        cmd3 = [
            "python3", "/home/zhangfn/workflow/pb.py",
            "--config", "redock",
            "--pred_file", pred_processed,
            "--true_file", true_processed,
            "--cond_file", self.cond_file
        ]

        try:
            # 执行 pred_file 和 true_file 处理
            subprocess.run(cmd1, check=True, cwd=self.working_dir)
            logging.info("PDBQT to SDF conversion for pred_file completed")
            
            subprocess.run(cmd2, check=True, cwd=self.working_dir)
            logging.info("PDBQT to SDF conversion for true_file completed")

            # 执行 pb.py 评估
            subprocess.run(cmd3, check=True, cwd=self.working_dir)
            logging.info("PoseBusters evaluation completed")

            # 确保 pb.py 的输出文件存在
            if not self.output_csv.exists():
                logging.error(f"PoseBusters results file not found: {self.output_csv}")
                return False

            # 将结果文件移动到 downloads 目录
            result_filename = "posebusters_results.csv"
            result_path = self.downloads_dir / result_filename
            shutil.move(str(self.output_csv), str(result_path))
            logging.info(f"Moved results file to {result_path}")

            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Conformation evaluation failed: {e}")
            return False


# MoleculeGeneration 接口
@app.route('/api/molecule_generation', methods=['POST'])
def molecule_generation():
    if 'pdb_file' not in request.files:
        return jsonify({"error": "未提供 pdb_file"}), 400

    pdb_file = request.files['pdb_file']
    if pdb_file.filename == '' or not allowed_file(pdb_file.filename):
        return jsonify({"error": "无效的文件或格式，仅支持 .pdb"}), 400

    # 保存上传的文件
    filename = secure_filename(pdb_file.filename)
    pdb_path = UPLOAD_FOLDER / filename
    pdb_file.save(pdb_path)

    # 设置输出文件路径
    pdb_base = os.path.splitext(filename)[0]
    outfile = DOWNLOAD_FOLDER / f"{pdb_base}_mol.sdf"
    
    # 获取参考配体(如有)
    ref_ligand = "A:330"  # 默认值
    if 'ref_ligand_file' in request.files:
        ref_file = request.files['ref_ligand_file']
        if ref_file.filename != '' and ref_file.filename.endswith('.sdf'):
            ref_filename = secure_filename(ref_file.filename)
            ref_path = UPLOAD_FOLDER / ref_filename
            ref_file.save(ref_path)
            ref_ligand = str(ref_path)
    elif request.form.get('ref_ligand'):
        ref_ligand = request.form.get('ref_ligand')

    # 执行分子生成
    step = MoleculeGeneration(
        working_dir=str(WORKING_DIR),
        pdb_file=str(pdb_path),
        outfile=str(outfile),
        ref_ligand=ref_ligand,
        n_samples=int(request.form.get('n_samples', 2))
    )
    if step.run():
        return jsonify({
            "message": "molecular generated successfully",
            "download_url": f"/api/download/molecule_generation/{outfile.name}"
        })
    else:
        return jsonify({"error": "分子生成失败"}), 500



@app.route('/api/molecular_docking', methods=['POST'])
def molecular_docking():
    if 'ligand_sdf' not in request.files or 'protein_pdb' not in request.files:
        return jsonify({"error": "需要提供 ligand_sdf 和 protein_pdb"}), 400

    ligand_sdf = request.files['ligand_sdf']
    protein_pdb = request.files['protein_pdb']

    if ligand_sdf.filename == '' or not allowed_file(ligand_sdf.filename) or \
       protein_pdb.filename == '' or not allowed_file(protein_pdb.filename):
        return jsonify({"error": "无效的文件或格式，仅支持 .sdf 和 .pdb"}), 400

    ligand_filename = secure_filename(ligand_sdf.filename)
    protein_filename = secure_filename(protein_pdb.filename)
    ligand_path = UPLOAD_FOLDER / ligand_filename
    protein_path = UPLOAD_FOLDER / protein_filename
    ligand_sdf.save(ligand_path)
    protein_pdb.save(protein_path)

    dock_mode = request.form.get('dock_mode', 'adgpu')

    step = MolecularDocking(
        working_dir=str(WORKING_DIR),
        ligand_sdf=str(ligand_path),
        protein_pdb=str(protein_path),
        dock_mode=dock_mode
    )
    if step.run():
        output_dir = WORKING_DIR / "downloads"
        
        if dock_mode == "vina":
            # Vina 模式：只返回单一文件 3rfm_vina.pdbqt
            vina_file = output_dir / "3rfm_vina.pdbqt"
            if vina_file.exists():
                download_urls = [f"/api/download/molecular_docking/{vina_file.name}"]
            else:
                return jsonify({"error": "Vina 输出文件未找到"}), 500
        elif dock_mode == "adgpu":
            # ADGPU 模式：返回所有匹配的 PDBQT 文件
            base_name = Path(step.ligand_sdf).stem.split('_')[0]
            pattern = f"{base_name}_ligand_*.pdbqt"
            moved_files = list(output_dir.glob(pattern))
            if not moved_files:
                return jsonify({"error": "ADGPU 输出文件未找到"}), 500
            download_urls = [f"/api/download/molecular_docking/{f.name}" for f in moved_files]
        else:
            return jsonify({"error": f"不支持的对接模式: {dock_mode}"}), 400

        return jsonify({
            "message": "docking successfully",
            "download_urls": download_urls  # 根据模式返回对应的下载链接
        })
    else:
        return jsonify({"error": "分子对接失败"}), 500



@app.route('/api/conformation_evaluation', methods=['POST'])
def conformation_evaluation():
    # 检查上传的文件
    required_files = ['pred_file', 'true_file', 'cond_file']
    for file_name in required_files:
        if file_name not in request.files:
            return jsonify({"error": f"未提供 {file_name}"}), 400

    pred_file = request.files['pred_file']
    true_file = request.files['true_file']
    cond_file = request.files['cond_file']

    # 检查文件名是否为空或格式不正确
    if (pred_file.filename == '' or not allowed_file(pred_file.filename) or
        true_file.filename == '' or not allowed_file(true_file.filename) or
        cond_file.filename == '' or not allowed_file(cond_file.filename)):
        return jsonify({"error": "无效的文件或格式，仅支持 .pdbqt 或 .sdf"}), 400

    # 保存上传的文件到工作目录
    pred_filename = secure_filename(pred_file.filename)
    true_filename = secure_filename(true_file.filename)
    cond_filename = secure_filename(cond_file.filename)

    pred_path = WORKING_DIR / pred_filename
    true_path = WORKING_DIR / true_filename
    cond_path = WORKING_DIR / cond_filename

    pred_file.save(pred_path)
    true_file.save(true_path)
    cond_file.save(cond_path)

    # 获取对接模式
    dock_mode = request.form.get('dock_mode', 'adgpu')  # 默认为 adgpu 模式

    # 执行构象评估
    step = ConformationEvaluation(
        working_dir=str(WORKING_DIR),
        mode="redock",
        mol_file=str(pred_path),
        dock_mode=dock_mode,
        true_file=str(true_path),
        cond_file=str(cond_path)
    )
    if step.run():
        # 检查结果内容
        result_filename = "posebusters_results.csv"
        result_path = DOWNLOAD_FOLDER / result_filename

        try:
            with open(result_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if len(lines) >= 2:
                    second_line = lines[1].strip().split(",")
                    result_flags = second_line[:26]
                    if all(flag.strip() == "True" for flag in result_flags):
                        msg = "conformation evaluated successfully, *****PASS ALL!*****"
                    else:
                        msg = "conformation evaluated successfully, *****NOT PASS ALL.*****"
                else:
                    msg = "conformation evaluated successfully, but result file is incomplete."
        except Exception as e:
            return jsonify({"error": f"无法读取结果文件: {str(e)}"}), 500

        return jsonify({
            "message": msg,
            "download_url": f"/api/download/conformation_evaluation/{result_filename}"
        })

    else:
        return jsonify({"error": "构象评估失败"}), 500




# 文件下载通用接口
@app.route('/api/download/<step_name>/<filename>', methods=['GET'])
def download_file(step_name: str, filename: str):
    file_path = DOWNLOAD_FOLDER / filename
    if file_path.exists():
        return send_file(file_path, as_attachment=True)
    else:
        return jsonify({"error": "文件不存在"}), 404

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)