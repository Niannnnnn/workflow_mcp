import subprocess
import os
import logging
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime  # 新增，用于获取当前时间
import tkinter as tk
from tkinter import filedialog
from openbabel import pybel

# 配置日志
logging.basicConfig(
    filename="workflow.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

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

    def check_checkpoint(self) -> bool:
        """检查是否已完成"""
        return self.checkpoint_file.exists()


def select_pdb_file(default_path: str = "/home/zhangfn/workflow/3rfm.pdb") -> str:
    path = input(f"请输入PDB文件路径（回车则默认: {default_path}），输入 'exit' 退出程序:\n> ").strip().lower()
    if path == "exit":  # 判断是否输入 exit
        print("Exiting the program.")  # 提示用户退出
        exit(0)  # 退出程序
    if not path:
        print(f"未输入路径，使用默认路径: {default_path}")
        return default_path
    if os.path.exists(path) and path.endswith(".pdb"):
        return path
    else:
        print(f"无效路径或文件格式错误，使用默认路径: {default_path}")
        return default_path




class MoleculeGeneration(WorkflowStep):
    """分子生成步骤"""
    def __init__(self, working_dir: str, pdb_file: str, outfile: str, ref_ligand: str, n_samples: int = 1):
        super().__init__("mol_generate", working_dir)
        self.pdb_file = pdb_file
        self.outfile = outfile
        self.ref_ligand = ref_ligand
        self.n_samples = n_samples

    def run(self) -> bool:
        if self.check_checkpoint():
            logging.info("Molecule generation already completed, skipping...")
            return True

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
        self.ligand_pdbqt = self.working_dir / "3rfm_ligand.pdbqt"
        self.protein_pdbqt = self.working_dir / "3rfm_protein.pdbqt"
        self.dock_mode = dock_mode
        self.grid_center = None
        
        # 为 Vina 创建输出目录
        if self.dock_mode == "vina":
            self.vina_output_dir = self.working_dir / "dock" / "vina"
            self.vina_output_dir.mkdir(parents=True, exist_ok=True)
        # 为 ADGPU 创建输出目录
        if self.dock_mode == "adgpu":
            self.adgpu_output_dir = self.working_dir / "dock" / "adgpu"
            self.adgpu_output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> bool:
        if self.check_checkpoint():
            logging.info("Molecular docking already completed, skipping...")
            return True

        steps = [
            (self.convert_ligand_format, "Convert ligand format"),
            (self.convert_receptor_format, "Convert receptor format"),
            (self.calculate_grid_center, "Calculate grid center"),
            (self.generate_gpf_file, "Generate GPF file"),
            (self.generate_fld_file, "Generate FLD file"),
            (self.run_docking, f"Run {self.dock_mode.upper()} docking")
        ]

        # 如果是 adgpu 模式，添加 DLG 转换步骤
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

    def convert_dlg_to_pdbqt(self):
        """将 ADGPU 生成的 DLG 文件转换为 PDBQT"""
        # 假设 DLG 文件名与 ligand_pdbqt 同名，只是扩展名不同
        dlg_file = self.working_dir / f"{self.ligand_pdbqt.stem}.dlg"
        
        if not dlg_file.exists():
            raise FileNotFoundError(f"DLG file not found: {dlg_file}")

        cmd = [
            "python3", 
            "/home/zhangfn/workflow/dlg2pdbqt.py",  # 假设脚本在 workflow 目录下
            str(dlg_file)
        ]
        
        try:
            subprocess.run(cmd, check=True, cwd=self.working_dir)
            logging.info(f"Converted {dlg_file} to PDBQT files in {self.adgpu_output_dir}")
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
        """生成 GPF 文件，使用从 pocket_center.txt 读取的网格中心"""
        if self.grid_center is None:
            raise ValueError("Grid center not calculated yet")
            
        gridcenter_str = f"{self.grid_center[0]},{self.grid_center[1]},{self.grid_center[2]}"
        cmd = [
            "/home/zhangfn/.conda/envs/targetdiff/bin/python",
            "/home/zhangfn/mgltools_x86_64Linux2_1.5.7/MGLToolsPckgs/AutoDockTools/Utilities24/prepare_gpf4.py",
            "-l", str(self.ligand_pdbqt), 
            "-r", str(self.protein_pdbqt),
            "-o", str(self.working_dir / "3rfm_protein_ligand.gpf"),
            "-p", "npts=30,30,30",
            "-p", "ligand_types=C,SA,N,HD,OA,Br,NA,I,A,Cl,F,P,S",
            "-p", f"gridcenter={gridcenter_str}"
        ]
        subprocess.run(cmd, check=True, cwd=self.working_dir)

    def run_docking_vina(self):
        """运行 AutoDock Vina 对接，使用从 pocket_center.txt 读取的网格中心"""
        if self.grid_center is None:
            raise ValueError("Grid center not calculated yet")
            
        cmd = [
            "vina",
            "--receptor", str(self.protein_pdbqt),
            "--ligand", str(self.ligand_pdbqt),
            "--out", str(self.vina_output_dir / "3rfm_vina.pdbqt"),
            "--center_x", str(self.grid_center[0]),
            "--center_y", str(self.grid_center[1]),
            "--center_z", str(self.grid_center[2]),
            "--size_x", "30",
            "--size_y", "30",
            "--size_z", "30"
        ]
        subprocess.run(cmd, check=True, cwd=self.working_dir)

    def run_docking(self):
        """运行对接，根据 dock_mode 选择对接工具"""
        if self.dock_mode == "adgpu":
            self.run_docking_adgpu()
        elif self.dock_mode == "vina":
            self.run_docking_vina()
        else:
            raise ValueError(f"Unsupported dock_mode: {self.dock_mode}")

    def run_docking_adgpu(self):
        """运行 AutoDock GPU 对接"""
        # 从 ligand_pdbqt 文件名中提取第一个下划线之前的字段
        ligand_base_name = self.ligand_pdbqt.stem
        log_prefix = ligand_base_name.split('_')[0]
        log_file = self.working_dir / f"{log_prefix}_adgpu.log"

        cmd = [
            "/home/zhangfn/AutoDock-GPU-develop/bin/autodock_gpu_64wi",
            "--ffile", str(self.working_dir / "3rfm_protein.maps.fld"),
            "--lfile", str(self.ligand_pdbqt),
            "-nrun", "5"
        ]
        
        with open(log_file, 'w') as f:
            subprocess.run(cmd, check=True, cwd=self.working_dir, stdout=f, stderr=subprocess.STDOUT)
        logging.info(f"AutoDock GPU docking completed, output redirected to {log_file}")

    def convert_ligand_format(self):
        """使用 openbabel 转换配体格式"""
        mol = pybel.readfile("sdf", self.ligand_sdf)
        molecule = next(mol)
        molecule.write("pdbqt", str(self.ligand_pdbqt), overwrite=True)
        logging.info("Ligand format conversion completed successfully")

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
        """生成 FLD 文件"""
        cmd = ["/home/zhangfn/x86_64Linux2/autogrid4", "-p", "3rfm_protein_ligand.gpf"]
        subprocess.run(cmd, check=True, cwd=self.working_dir)







class ConformationEvaluation(WorkflowStep):
    """构象评估步骤"""
    def __init__(self, working_dir: str, mode: str, mol_file: Optional[str] = None, dock_mode: Optional[str] = None):
        super().__init__("eval", working_dir)
        self.mode = mode
        self.mol_file = mol_file
        self.dock_mode = dock_mode  # 可能为 None

    def run(self) -> bool:
        if self.check_checkpoint():
            logging.info("Conformation evaluation already completed, skipping...")
            return True

        steps = []

        if self.mode == "redock":
            if self.dock_mode == "adgpu":
                steps = [
                    (["python3", "/home/zhangfn/workflow/pdbqt2sdf_adgpu.py"], "Convert PDBQT to SDF"),
                    (["python3", "/home/zhangfn/workflow/pb.py", "--dock_mode", self.dock_mode, "--config", "redock"], "Run PB evaluation (redock mode)")
                ]
            elif self.dock_mode == "vina":
                steps = [
                    (["python3", "/home/zhangfn/workflow/pdbqt2sdf_vina.py"], "Convert PDBQT to SDF"),
                    (["python3", "/home/zhangfn/workflow/pb.py", "--dock_mode", self.dock_mode, "--config", "redock"], "Run PB evaluation (redock mode)")
                ]
        elif self.mode == "mol":
            if self.mol_file is None:
                # user_input_path = input("请输入待评估的分子文件路径（如 /home/zhangfn/workflow/3rfm_ligand.pdbqt），输入 'exit' 退出程序:\n> ").strip().lower()
                if user_input_path == "exit":  # 判断是否输入 exit
                    print("Exiting the program.")  # 提示用户退出
                    exit(0)  # 退出程序
                self.mol_file = user_input_path
            steps = [
                (["python3", "/home/zhangfn/workflow/pb.py", "--config", "mol", "--input", self.mol_file], "Run PB evaluation (mol mode)")
            ]

        for cmd, step_name in steps:
            try:
                subprocess.run(cmd, check=True, cwd=self.working_dir)
                logging.info(f"{step_name} completed")
            except subprocess.CalledProcessError as e:
                logging.error(f"{step_name} failed: {e}")
                return False

        self.save_checkpoint()
        logging.info("Conformation evaluation completed successfully")
        return True




        


class WorkflowManager:
    """工作流管理器"""
    def __init__(self, working_dir: str, max_retries: int = 3):
        self.working_dir = Path(working_dir)
        self.max_retries = max_retries
        self.available_steps = {
            "mol_generate": MoleculeGeneration,
            "dock": MolecularDocking,
            "eval": ConformationEvaluation
        }
        self.clear_checkpoints()  # 在初始化时清除遗留的checkpoint文件

    def clear_checkpoints(self):
        """清除工作目录下所有以checkpoint.txt结尾的文件"""
        for file in self.working_dir.glob("*checkpoint.txt"):
            try:
                file.unlink()
                logging.info(f"Cleared previous checkpoint file: {file}")
            except OSError as e:
                logging.warning(f"Failed to clear checkpoint file {file}: {e}")

    def get_user_input(self) -> List[str]:
        """获取用户输入并验证"""
        print("Available steps: mol_generate, dock, eval")
        print("Enter the steps you want to run (space-separated, in desired order):")
        print("Example: 'mol_generate dock' or 'mol_generate dock eval'")
        print("Type 'exit' to quit the program.")  # 提示用户输入 exit 退出

        while True:
            user_input = input("> ").strip().lower()  # 将输入转换为小写，方便比较
            if user_input == "exit":  # 判断是否输入 exit
                print("Exiting the program.")  # 提示用户退出
                exit(0)  # 退出程序
            user_steps = user_input.split()
            invalid_steps = [step for step in user_steps if step not in self.available_steps]
            if invalid_steps:
                print(f"Invalid steps: {invalid_steps}. Please use only: mol_generate, dock, eval")
            elif not user_steps:
                print("Please enter at least one step.")
            else:
                return user_steps

    def create_workflow(self, steps: List[str]) -> List[WorkflowStep]:
        workflow = []
        executed_steps = set()

        # 🧠 新增：只询问一次 PDB 文件路径，其他步骤共享
        pdb_file = select_pdb_file(default_path=str(self.working_dir / "3rfm.pdb"))

        for step_name in steps:
            if step_name == "mol_generate":
                step = MoleculeGeneration(
                    working_dir=str(self.working_dir),
                    pdb_file=pdb_file,
                    outfile=str(self.working_dir / "3rfm_mol.sdf"),
                    ref_ligand="A:330",
                    n_samples=1
                )
            elif step_name == "dock":
                # 默认对接模式为 adgpu
                dock_mode = input("请输入对接模式 (adgpu 或 vina，默认 adgpu): ").strip().lower() or "adgpu"
                step = MolecularDocking(
                    working_dir=str(self.working_dir),
                    ligand_sdf=str(self.working_dir / "3rfm_mol.sdf"),
                    protein_pdb=pdb_file,
                    dock_mode=dock_mode
                )
            elif step_name == "eval":
                # 判断是否执行过 dock 或 mol_generate
                if not executed_steps or all(s not in executed_steps for s in ["dock", "mol_generate"]):
                    # 第一个步骤就是 eval，或者前面没执行过 dock/mol_generate
                    mode = "mol"
                    default_mol_file = "/home/zhangfn/workflow/3rfm_ligand.pdbqt"
                    user_input_path = input(f"请输入待评估的分子文件路径（如 {default_mol_file}），输入 'exit' 退出程序:\n> ").strip().lower()
                    if user_input_path == "exit":  # 判断是否输入 exit
                        print("Exiting the program.")  # 提示用户退出
                        exit(0)  # 退出程序
                    if not user_input_path:
                        print(f"未输入路径，使用默认路径: {default_mol_file}")
                        mol_file = default_mol_file
                    else:
                        mol_file = user_input_path

                    # 设置 dock_mode 为 None，表示没有执行过对接
                    dock_mode = None
                else:
                    # 已执行过 dock，则使用 redock 模式
                    mode = "redock"
                    mol_file = None

                    # 获取对接模式
                    dock_mode = "adgpu"  # 默认值，可以根据实际情况调整

                # 初始化 ConformationEvaluation
                step = ConformationEvaluation(
                    working_dir=str(self.working_dir),
                    mode=mode,
                    mol_file=mol_file,
                    dock_mode=dock_mode
                )

            workflow.append(step)
            executed_steps.add(step_name)
        return workflow

    def run(self, steps: List[WorkflowStep]):
        """执行工作流"""
        for step in steps:
            retries = 0
            while retries < self.max_retries:
                if step.run():
                    break
                retries += 1
                logging.warning(f"Retry {retries}/{self.max_retries} for {step.name}")
                if retries == self.max_retries:
                    logging.error(f"Step {step.name} failed after {self.max_retries} retries")
                    return False
        logging.info("Workflow completed successfully")
        return True


if __name__ == "__main__":
    working_dir = "/home/zhangfn/workflow"
    os.makedirs(working_dir, exist_ok=True)

    # 创建工作流管理器
    workflow_manager = WorkflowManager(working_dir)

    # 获取用户输入
    print("【****************************************************】")
    print("Welcome to the Workflow Manager.")
    print("Type 'exit' at any input prompt to quit the program.")  # 提示用户输入 exit 退出
    user_steps = workflow_manager.get_user_input()

    # 创建并运行工作流
    workflow = workflow_manager.create_workflow(user_steps)
    workflow_manager.run(workflow)