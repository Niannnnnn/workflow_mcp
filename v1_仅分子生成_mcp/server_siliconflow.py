import json
import os
import requests
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP

import logging
logging.basicConfig(level=logging.DEBUG)
logging.debug("分子生成服务器启动中...")

# 初始化 MCP 服务器
mcp = FastMCP("MoleculeGenerationServer")

@mcp.tool()
def molecule_generation(params: Dict[str, Any]) -> Dict:
    """执行分子生成计算
    
    Args:
        params: 包含以下字段的字典:
            pdb_file: 受体文件绝对路径（必须为.pdb格式）
    
    Returns:
        包含状态和结果的字典: {"status": "success/failure", "result": 计算结果或错误信息}
    """
    # 显式定义 inputSchema
    molecule_generation.inputSchema = {
        "type": "object",
        "properties": {
            "params": {
                "type": "object",
                "properties": {
                    "pdb_file": {
                        "type": "string",
                        "description": "受体文件绝对路径（必须为.pdb格式）"
                    }
                },
                "required": ["pdb_file"]
            }
        },
        "required": ["params"]
    }
    
    logging.debug(f"收到分子生成请求，参数: {params}")
    
    # 参数校验
    if not params.get('pdb_file'):
        return {"status": "error", "message": "未提供PDB文件路径"}
    
    pdb_path = params['pdb_file']
    if not os.path.exists(pdb_path):
        return {"status": "error", "message": f"PDB文件不存在: {pdb_path}"}
    
    if not pdb_path.endswith('.pdb'):
        return {"status": "error", "message": f"文件格式错误，必须是.pdb格式: {pdb_path}"}
    
    # 构建API请求负载
    try:
        with open(pdb_path, 'rb') as f:
            files = {'pdb_file': f}
            
            # 调用Flask API
            logging.debug(f"正在调用分子生成API...")
            response = requests.post(
                "http://localhost:5000/api/molecule_generation",
                files=files,
                timeout=300  # 根据计算时长调整
            )
            
            logging.debug(f"API响应: {response.text}")
            if response.status_code == 200:
                result = response.json()
                return {
                    "status": "success", 
                    "message": "分子生成计算完成",
                    "result": result
                }
            else:
                return {
                    "status": "error", 
                    "message": f"API返回错误: {response.status_code}", 
                    "response": response.text
                }
    except Exception as e:
        logging.error(f"API调用失败: {str(e)}")
        return {"status": "error", "message": f"API调用失败: {str(e)}"}

# @mcp.tool()
# def run_dock(params: Dict[str, Any]) -> Dict:
#     """执行分子对接计算
    
#     Args:
#         params: 包含以下字段的字典:
#             receptor_file: 受体文件绝对路径（必须为.pdb格式）
#             ligand_file: 配体文件绝对路径（必须为.mol2或.sdf格式）
#             center_x: 对接盒子中心X坐标 (可选)
#             center_y: 对接盒子中心Y坐标 (可选)
#             center_z: 对接盒子中心Z坐标 (可选)
#             size_x: 对接盒子X方向大小 (可选)
#             size_y: 对接盒子Y方向大小 (可选)
#             size_z: 对接盒子Z方向大小 (可选)
    
#     Returns:
#         包含状态和结果的字典: {"status": "success/failure", "result": 计算结果或错误信息}
#     """
#     logging.debug(f"收到分子对接请求，参数: {params}")
    
#     # 参数校验
#     required_files = ['receptor_file', 'ligand_file']
#     for key in required_files:
#         if not params.get(key):
#             return {"status": "error", "message": f"未提供{key}"}
#         if not os.path.exists(params[key]):
#             return {"status": "error", "message": f"{key}文件不存在: {params[key]}"}
    
#     receptor_path = params['receptor_file']
#     ligand_path = params['ligand_file']
    
#     if not receptor_path.endswith('.pdb'):
#         return {"status": "error", "message": f"受体文件格式错误，必须是.pdb格式: {receptor_path}"}
    
#     if not (ligand_path.endswith('.mol2') or ligand_path.endswith('.sdf')):
#         return {"status": "error", "message": f"配体文件格式错误，必须是.mol2或.sdf格式: {ligand_path}"}
    
#     # 构建API请求
#     try:
#         with open(receptor_path, 'rb') as receptor_file, open(ligand_path, 'rb') as ligand_file:
#             files = {
#                 'receptor_file': receptor_file,
#                 'ligand_file': ligand_file
#             }
            
#             # 准备请求参数
#             data = {k: v for k, v in params.items() if k not in ['receptor_file', 'ligand_file']}
            
#             # 调用Flask API
#             logging.debug(f"正在调用分子对接API...")
#             response = requests.post(
#                 "http://localhost:5000/api/dock",
#                 files=files,
#                 data=data,
#                 timeout=300
#             )
            
#             logging.debug(f"API响应: {response.text}")
#             if response.status_code == 200:
#                 result = response.json()
#                 return {
#                     "status": "success", 
#                     "message": "分子对接计算完成",
#                     "result": result
#                 }
#             else:
#                 return {
#                     "status": "error", 
#                     "message": f"API返回错误: {response.status_code}", 
#                     "response": response.text
#                 }
#     except Exception as e:
#         logging.error(f"API调用失败: {str(e)}")
#         return {"status": "error", "message": f"API调用失败: {str(e)}"}

def main():
    logging.info("分子生成服务器启动，使用stdio通信...")
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()