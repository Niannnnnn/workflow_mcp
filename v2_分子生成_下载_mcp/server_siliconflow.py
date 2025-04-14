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

@mcp.tool()
def download_molecule(params: Dict[str, Any]) -> Dict:
    """下载生成的分子文件
    
    Args:
        params: 包含以下字段的字典:
            molecule_name: 分子文件名 (如 "3rfm_mol.sdf")
            output_path: 保存文件的本地路径 (可选，默认为当前目录下的同名文件)
    
    Returns:
        包含状态和结果的字典: {"status": "success/failure", "message": 操作结果或错误信息, "file_path": 保存的文件路径}
    """
    # 显式定义 inputSchema
    download_molecule.inputSchema = {
        "type": "object",
        "properties": {
            "params": {
                "type": "object",
                "properties": {
                    "molecule_name": {
                        "type": "string",
                        "description": "要下载的分子文件名 (如 '3rfm_mol.sdf')"
                    },
                    "output_path": {
                        "type": "string",
                        "description": "保存文件的本地路径 (可选，默认为当前目录下的同名文件)"
                    }
                },
                "required": ["molecule_name"]
            }
        },
        "required": ["params"]
    }
    
    logging.debug(f"收到分子下载请求，参数: {params}")
    
    # 参数校验
    molecule_name = params.get('molecule_name')
    if not molecule_name:
        return {"status": "error", "message": "未提供分子文件名"}
    
    # 获取输出路径，如未提供则使用当前目录和原始文件名
    output_path = params.get('output_path')
    if not output_path:
        output_path = os.path.join(os.getcwd(), molecule_name)
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except Exception as e:
            return {"status": "error", "message": f"无法创建输出目录: {str(e)}"}
    
    # 构建下载URL
    try:
        # 从文件名中提取PDB ID (假设命名格式为 "xxxx_mol.sdf")
        pdb_id = molecule_name.split('_')[0] if '_' in molecule_name else molecule_name.split('.')[0]
        download_url = f"http://localhost:5000/api/download/molecule_generation/{molecule_name}"
        
        logging.debug(f"正在从 {download_url} 下载分子文件...")
        response = requests.get(download_url, stream=True, timeout=60)
        
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return {
                "status": "success",
                "message": f"分子文件成功下载到 {output_path}",
                "file_path": output_path
            }
        else:
            return {
                "status": "error",
                "message": f"下载失败，服务器返回: {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        logging.error(f"分子下载失败: {str(e)}")
        return {"status": "error", "message": f"下载失败: {str(e)}"}

def main():
    logging.info("分子生成服务器启动，使用stdio通信...")
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()