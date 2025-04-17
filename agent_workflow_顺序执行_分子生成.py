from openai import OpenAI, AsyncOpenAI
from agents import OpenAIChatCompletionsModel, Agent, Runner, set_default_openai_client, function_tool
from agents.model_settings import ModelSettings
import os
from dotenv import load_dotenv
from IPython.display import display, Code, Markdown, Image
import requests, json
import os.path
from typing import Dict, Any, List
import asyncio
load_dotenv(override=True)

API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")
MODEL = os.getenv("MODEL")

external_client = AsyncOpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

set_default_openai_client(external_client)

deepseek_model = OpenAIChatCompletionsModel(
    model=MODEL,
    openai_client=external_client
)

# 移除function_tool装饰器，变为普通函数
def molecule_generation(pdb_file, ref_ligand="A:330", n_samples=1):
    """执行分子生成计算
    
    Args:
        pdb_file: 受体文件绝对路径（必须为.pdb格式）
        ref_ligand: 参考配体信息，可以是"A:330"（默认值，无参考配体）或者SDF文件的绝对路径
        n_samples: 生成样本数量（可选，默认为1）
    
    Returns:
        包含状态和结果的字典: {"status": "success/failure", "result": 计算结果或错误信息}
    """
    # 构建params字典
    params = {
        'pdb_file': pdb_file,
        'ref_ligand': ref_ligand,
        'n_samples': n_samples
    }

    print(f"收到分子生成请求，参数: {params}")
    
    # 参数校验
    if not params.get('pdb_file'):
        return {"status": "error", "message": "未提供PDB文件路径"}
    
    pdb_path = params['pdb_file']
    if not os.path.exists(pdb_path):
        return {"status": "error", "message": f"PDB文件不存在: {pdb_path}"}
    
    if not pdb_path.endswith('.pdb'):
        return {"status": "error", "message": f"文件格式错误，必须是.pdb格式: {pdb_path}"}
    
    # 检查参考配体
    ref_ligand = params.get('ref_ligand', 'A:330')
    if ref_ligand != 'A:330' and (not os.path.exists(ref_ligand) or not ref_ligand.endswith('.sdf')):
        return {"status": "error", "message": f"参考配体文件不存在或格式错误(应为.sdf): {ref_ligand}"}
    
    n_samples = params.get('n_samples', 1)
    
    # 构建API请求负载
    try:
        with open(pdb_path, 'rb') as f:
            pdb_content = f.read()
        
        files = {'pdb_file': (os.path.basename(pdb_path), pdb_content)}
        
        data = {'n_samples': n_samples}
        
        # 如果是SDF文件，也读取到内存中
        if ref_ligand != 'A:330' and os.path.exists(ref_ligand):
            with open(ref_ligand, 'rb') as ref_file:
                ref_content = ref_file.read()
            files['ref_ligand_file'] = (os.path.basename(ref_ligand), ref_content)
        else:
            data['ref_ligand'] = ref_ligand
        
        # 调用Flask API
        print(f"正在调用分子生成API...")
        response = requests.post(
            "http://localhost:5000/api/molecule_generation",
            files=files,
            data=data,
            timeout=300
        )
            
        print(f"API响应: {response.text}")
        if response.status_code == 200:
            result = response.json()
            # 从下载URL中提取分子文件名
            molecule_name = os.path.basename(result.get('download_url', ''))
            result['molecule_name'] = molecule_name  # 添加分子名称到结果中
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
        print(f"API调用失败: {str(e)}")
        return {"status": "error", "message": f"API调用失败: {str(e)}"}

# 移除function_tool装饰器，变为普通函数
def download_molecule(molecule_name, output_path):
    """下载生成的分子文件
    
    Args:
        molecule_name: 分子文件名 (如 "3rfm_mol.sdf")
        output_path: 保存文件的本地路径 (可选，默认为当前目录下的同名文件)
    
    Returns:
        包含状态和结果的字典: {"status": "success/failure", "message": 操作结果或错误信息, "file_path": 保存的文件路径}
    """
    print(f"收到分子下载请求，参数: molecule_name={molecule_name}, output_path={output_path}")
    
    # 参数校验
    if not molecule_name:
        return {"status": "error", "message": "未提供分子文件名"}
    
    # 获取输出路径，如未提供则使用当前目录和原始文件名
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
        download_url = f"http://localhost:5000/api/download/molecule_generation/{molecule_name}"
        
        print(f"正在从 {download_url} 下载分子文件...")
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
        print(f"分子下载失败: {str(e)}")
        return {"status": "error", "message": f"下载失败: {str(e)}"}

def molecular_docking(params: Dict[str, Any]) -> Dict:
    """执行分子对接计算
    
    Args:
        params: 包含以下字段的字典:
            ligand_sdf: 配体文件绝对路径（必须为.sdf格式）
            protein_pdb: 受体文件绝对路径（必须为.pdb格式）
            dock_mode: 对接模式，可选值为"adgpu"或"vina"
    
    Returns:
        包含状态和结果的字典: {"status": "success/failure", "result": 计算结果或错误信息}
    """
    # 显式定义 inputSchema
    molecular_docking.inputSchema = {
        "type": "object",
        "properties": {
            "params": {
                "type": "object",
                "properties": {
                    "ligand_sdf": {
                        "type": "string",
                        "description": "配体文件绝对路径（必须为.sdf格式）"
                    },
                    "protein_pdb": {
                        "type": "string",
                        "description": "受体文件绝对路径（必须为.pdb格式）"
                    },
                    "dock_mode": {
                        "type": "string",
                        "description": "对接模式，可选值为'adgpu'或'vina'",
                        "enum": ["adgpu", "vina"]
                    }
                },
                "required": ["ligand_sdf", "protein_pdb", "dock_mode"]
            }
        },
        "required": ["params"]
    }
    
    logging.debug(f"收到分子对接请求，参数: {params}")
    
    # 参数校验
    if not params.get('ligand_sdf'):
        return {"status": "error", "message": "未提供配体SDF文件路径"}
    
    if not params.get('protein_pdb'):
        return {"status": "error", "message": "未提供受体PDB文件路径"}
    
    if not params.get('dock_mode'):
        return {"status": "error", "message": "未提供对接模式"}
    
    ligand_path = params['ligand_sdf']
    protein_path = params['protein_pdb']
    dock_mode = params['dock_mode']
    
    # 文件存在性检查
    if not os.path.exists(ligand_path):
        return {"status": "error", "message": f"配体文件不存在: {ligand_path}"}
    
    if not os.path.exists(protein_path):
        return {"status": "error", "message": f"受体文件不存在: {protein_path}"}
    
    # 文件格式检查
    if not ligand_path.endswith('.sdf'):
        return {"status": "error", "message": f"配体文件格式错误，必须是.sdf格式: {ligand_path}"}
    
    if not protein_path.endswith('.pdb'):
        return {"status": "error", "message": f"受体文件格式错误，必须是.pdb格式: {protein_path}"}
    
    # 对接模式检查
    if dock_mode not in ['adgpu', 'vina']:
        return {"status": "error", "message": f"对接模式错误，必须是'adgpu'或'vina': {dock_mode}"}
    
    # 构建API请求负载
    try:
        with open(ligand_path, 'rb') as ligand_file, open(protein_path, 'rb') as protein_file:
            files = {
                'ligand_sdf': ligand_file,
                'protein_pdb': protein_file
            }
            
            data = {
                'dock_mode': dock_mode
            }
            
            # 调用Flask API
            logging.debug(f"正在调用分子对接API，模式: {dock_mode}...")
            response = requests.post(
                "http://localhost:5000/api/molecular_docking",
                files=files,
                data=data,
                timeout=600  # 根据计算时长调整，分子对接可能需要更长时间
            )
            
            logging.debug(f"API响应: {response.text}")
            if response.status_code == 200:
                result = response.json()

                result_files = result.get('result_files', [])
                
                return {
                    "status": "success", 
                    "message": f"分子对接计算完成 ({dock_mode}模式)",
                    "result": result,
                    "result_files": result_files  # 确保返回文件列表
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


# 为了向外部暴露API，创建带装饰器的版本
@function_tool
def molecule_generation_tool(pdb_file, ref_ligand="A:330", n_samples=1):
    """执行分子生成计算
    
    Args:
        pdb_file: 受体文件绝对路径（必须为.pdb格式）
        ref_ligand: 参考配体信息，可以是"A:330"（默认值，无参考配体）或者SDF文件的绝对路径
        n_samples: 生成样本数量（可选，默认为1）
    
    Returns:
        包含状态和结果的字典: {"status": "success/failure", "result": 计算结果或错误信息}
    """
    return molecule_generation(pdb_file, ref_ligand, n_samples)

@function_tool
def download_molecule_tool(molecule_name, output_path):
    """下载生成的分子文件
    
    Args:
        molecule_name: 分子文件名 (如 "3rfm_mol.sdf")
        output_path: 保存文件的本地路径 (可选，默认为当前目录下的同名文件)
    
    Returns:
        包含状态和结果的字典: {"status": "success/failure", "message": 操作结果或错误信息, "file_path": 保存的文件路径}
    """
    return download_molecule(molecule_name, output_path)

# 改进的组合工具函数，调用现有的模块化函数
@function_tool
def generate_and_download_molecule(pdb_file, output_path, ref_ligand="A:330", n_samples=1):
    """生成分子并下载结果到指定路径
    
    Args:
        pdb_file: 受体文件绝对路径（必须为.pdb格式）
        output_path: 保存分子文件的本地路径
        ref_ligand: 参考配体信息，可以是"A:330"（默认值，无参考配体）或者SDF文件的绝对路径
        n_samples: 生成样本数量（可选，默认为1）
    
    Returns:
        包含状态和结果的字典
    """
    print(f"执行组合操作：生成分子并下载")
    
    # 调用分子生成函数
    gen_result = molecule_generation(pdb_file, ref_ligand, n_samples)
    
    # 检查生成结果
    if gen_result["status"] != "success":
        return {
            "status": "error",
            "message": f"分子生成失败: {gen_result.get('message', '未知错误')}",
            "generation_result": gen_result
        }
    
    # 从生成结果中提取分子名称
    molecule_name = gen_result.get("result", {}).get("molecule_name")
    if not molecule_name:
        return {
            "status": "error",
            "message": "无法从生成结果中提取分子名称",
            "generation_result": gen_result
        }
    
    # 调用下载函数
    download_result = download_molecule(molecule_name, output_path)
    
    # 返回组合结果
    if download_result["status"] == "success":
        return {
            "status": "success",
            "message": f"分子成功生成并下载到 {output_path}",
            "generation_result": gen_result.get("result", {}),
            "file_path": download_result.get("file_path")
        }
    else:
        return {
            "status": "error",
            "message": f"分子生成成功但下载失败: {download_result.get('message', '未知错误')}",
            "generation_result": gen_result.get("result", {}),
            "download_result": download_result
        }

# 创建一个复合操作助手
complex_agent = Agent(
    name="ComplexAssistant", 
    instructions="""你是一个能够处理复合文件操作请求的助手。你可以：
    1. 执行分子生成操作
    2. 对生成的分子文件执行下载操作
    3. 一步完成分子生成和下载（使用generate_and_download_molecule工具）
    
    对于用户的复合请求，请按照正确的顺序执行操作。例如，如果用户要求在新文件夹中创建文件，
    你应该先创建文件夹，然后再在该文件夹中创建文件。
    
    分析用户请求，提取出所有需要执行的操作，然后按正确的顺序调用相应的工具函数。
    
    请确保准确理解用户的路径需求，例如"在1文件夹下创建test.txt"意味着路径应该是"1/test.txt"。

    重要提示：如果用户请求既要生成分子又要下载分子文件，请优先使用generate_and_download_molecule工具，这是一个组合工具，可以在一步中完成生成和下载，避免分开执行两个操作可能出现的问题。

    如果用户只需要分子生成，没有提到下载，那么只需要使用molecule_generation_tool这个工具。
    
    如果用户只需要下载已经生成的分子文件，则使用download_molecule_tool工具。
    """,
    tools=[molecule_generation_tool, download_molecule_tool, generate_and_download_molecule],
    model=deepseek_model
)

# 改进的异步函数，增强了对工具调用的处理
async def chat(agent):
    input_items = []
    while True:
        try:
            user_input = input("💬 请输入你的消息（输入quit退出）：")
            if user_input.lower() in ["exit", "quit"]:
                print("✅ 对话已结束")
                return
            
            input_items.append({"content": user_input, "role": "user"})
            
            # 运行智能体并处理工具调用
            result = await Runner.run(agent, input_items)
            
            # 显示结果
            if hasattr(result, 'final_output') and result.final_output:
                display(Markdown(result.final_output))
            
            # 如果有回复，则将其添加到输入列表中
            if hasattr(result, 'to_input_list'):
                input_items = result.to_input_list()
                
                # 打印中间结果（调试用）
                print("处理后的输入列表:")
                for item in input_items:
                    if item.get('role') == 'assistant':
                        print(f"Assistant: {item.get('content', '')[:100]}...")
                    elif item.get('type') == 'function_call':
                        print(f"Function Call: {item.get('name')}")
                    elif item.get('type') == 'function_call_output':
                        print(f"Function Output: {item.get('output', '')[:100]}...")
                    else:
                        print(f"{item.get('role', 'unknown')}: {item.get('content', '')[:100]}...")
                
                print("*****************************")
                if hasattr(result, 'final_output'):
                    print(result.final_output[:200])
                    if len(result.final_output) > 200:
                        print("...")
            
        except Exception as e:
            print(f"发生错误：{e}")
            import traceback
            traceback.print_exc()
            return

# 异步函数
async def main():
    try:
        await chat(complex_agent)
    finally:
        # 关闭客户端连接
        try:
            print("正在关闭连接...")
            await external_client.close()
            print("连接已关闭")
        except Exception as e:
            print(f"关闭客户端时发生错误: {e}")

if __name__ == '__main__':
    # 运行异步函数
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"程序运行时发生错误：{e}")
    finally:
        # 确保程序退出
        print("程序结束")
        os._exit(0)