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

# 创建文件夹的工具函数
@function_tool
def create_folder(folder_name):
    """
    创建一个文件夹
    :param folder_name: 文件夹名称
    :return: 文件夹创建的结果，成功返回提示消息，否则返回错误信息
    """
    try:
        # 检查文件夹是否已存在
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
            return f"文件夹 '{folder_name}' 创建成功!"
        else:
            return f"文件夹 '{folder_name}' 已经存在!"
    except Exception as e:
        return f"发生错误：{e}"

# 创建文件的工具函数
@function_tool 
def create_file(file_path, content=""):     
    """     
    创建一个文件并写入内容     
    :param file_path: 文件路径，可以是相对路径或绝对路径
    :param content: 文件内容，默认为空字符串     
    :return: 文件创建的结果，成功返回提示消息，否则返回错误信息     
    """     
    try:
        # 确保文件所在目录存在
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            
        # 检查文件是否已存在         
        if not os.path.exists(file_path):            
            with open(file_path, "w") as file:                 
                file.write(content)             
            return f"文件 '{file_path}' 创建成功!"     
        else:             
            return f"文件 '{file_path}' 已经存在!"     
    except Exception as e:         
        return f"发生错误：{e}"

@function_tool 
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

@function_tool 
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

# 添加新的组合工具函数
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
    
    # 第一步：手动执行分子生成操作（不调用装饰后的函数）
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
            
            # 生成成功后，执行下载操作
            print(f"分子生成成功，文件名: {molecule_name}")
            
            # 第二步：手动执行下载操作（不调用装饰后的函数）
            print(f"收到分子下载请求，参数: molecule_name={molecule_name}, output_path={output_path}")
            
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir)
                except Exception as e:
                    return {"status": "error", "message": f"无法创建输出目录: {str(e)}"}
            
            # 构建下载URL
            download_url = f"http://localhost:5000/api/download/molecule_generation/{molecule_name}"
            
            print(f"正在从 {download_url} 下载分子文件...")
            download_response = requests.get(download_url, stream=True, timeout=60)
            
            if download_response.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in download_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return {
                    "status": "success",
                    "message": f"分子成功生成并下载到 {output_path}",
                    "generation_result": result,
                    "file_path": output_path
                }
            else:
                return {
                    "status": "error",
                    "message": f"分子生成成功但下载失败，服务器返回: {download_response.status_code}",
                    "generation_result": result,
                    "download_response": download_response.text
                }
        else:
            return {
                "status": "error", 
                "message": f"分子生成API返回错误: {response.status_code}", 
                "response": response.text
            }
    except Exception as e:
        print(f"组合操作失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"组合操作失败: {str(e)}"}

# 创建一个复合操作助手
complex_agent = Agent(
    name="ComplexAssistant", 
    instructions="""你是一个能够处理复合文件操作请求的助手。你可以：
    1. 创建文件夹
    2. 创建文件并写入内容
    3. 在指定文件夹中创建文件
    4. 执行分子生成操作
    5. 对生成的分子文件执行下载操作
    6. 一步完成分子生成和下载（使用generate_and_download_molecule工具）
    
    对于用户的复合请求，请按照正确的顺序执行操作。例如，如果用户要求在新文件夹中创建文件，
    你应该先创建文件夹，然后再在该文件夹中创建文件。
    
    分析用户请求，提取出所有需要执行的操作，然后按正确的顺序调用相应的工具函数。
    
    请确保准确理解用户的路径需求，例如"在1文件夹下创建test.txt"意味着路径应该是"1/test.txt"。

    重要提示：如果用户请求既要生成分子又要下载分子文件，请优先使用generate_and_download_molecule工具，这是一个组合工具，可以在一步中完成生成和下载，避免分开执行两个操作可能出现的问题。

    如果用户只需要分子生成，没有提到下载，那么只需要使用molecule_generation这个工具。
    
    如果用户只需要下载已经生成的分子文件，则使用download_molecule工具。
    """,
    tools=[create_folder, create_file, molecule_generation, download_molecule, generate_and_download_molecule],
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