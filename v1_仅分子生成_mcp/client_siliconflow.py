import asyncio
import os
import json
from typing import Optional, Dict, Any
from contextlib import AsyncExitStack

from openai import OpenAI  
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 加载 .env 文件，确保 API Key 受到保护
load_dotenv()

class MCPMoleculeClient:
    def __init__(self):
        """初始化分子生成 MCP 客户端"""
        self.exit_stack = AsyncExitStack()
        self.api_key = os.getenv("API_KEY")  # 读取 OpenAI API Key
        self.base_url = os.getenv("BASE_URL")  # 读取 BASE URL，默认为OpenAI
        self.model = os.getenv("MODEL")  # 读取 model，默认为gpt-4

        print(f"api_key = {self.api_key}, base_url = {self.base_url}, model = {self.model}")
        
        if not self.api_key:
            raise ValueError("❌ 未找到 OpenAI API Key，请在 .env 文件中设置 API_KEY")
        
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)  # 创建OpenAI client
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()        

    async def connect_to_server(self, server_script_path: str):
        """连接到分子生成 MCP 服务器并列出可用工具"""
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本必须是 .py 或 .js 文件")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        # 启动 MCP 服务器并建立通信
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # 列出 MCP 服务器上的工具
        response = await self.session.list_tools()
        tools = response.tools
        print("\n已连接到服务器，支持以下工具:", [tool.name for tool in tools])
        
        # 打印每个工具的详细信息，包括输入参数
        for tool in tools:
            print(f"\n工具名称: {tool.name}")
            print(f"描述: {tool.description}")
            print("输入参数:")
            if tool.inputSchema:
                schema = tool.inputSchema
                if 'properties' in schema:
                    for param_name, param_info in schema['properties'].items():
                        param_type = param_info.get('type', '未指定')
                        param_desc = param_info.get('description', '无描述')
                        print(f"  - {param_name} ({param_type}): {param_desc}")
        
    async def process_query(self, query: str) -> str:
        """
        使用大模型处理查询并调用分子生成相关的 MCP 工具
        """
        # 检查输入是否可能是直接的PDB文件路径
        if query.endswith('.pdb') and os.path.exists(query):
            print(f"检测到PDB文件路径: {query}")
            # 修改查询使其更明确
            query = f"请使用这个PDB文件进行分子生成: {query}"
        
        # 设置系统提示，引导模型更好地理解分子生成相关查询
        system_prompt = """
        你是一个专业的分子生成助手，可以帮助用户处理分子对接和生成任务。
        你可以调用以下工具:
        
        1. molecule_generation - 用于执行分子生成计算，需要提供PDB文件路径
        
        当用户提供PDB文件路径时，请调用molecule_generation工具并将参数格式设置为{'params': {'pdb_file': '用户提供的路径'}}。
        
        请理解用户的意图，并调用适当的工具来完成任务。确保参数格式正确。
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        try:
            response = await self.session.list_tools()
            
            # 打印所有可用工具及其参数结构以便调试
            print("可用工具列表:")
            for tool in response.tools:
                print(f"- {tool.name}: {tool.inputSchema}")
            
            # 手动构造 tools 参数，符合 SiliconFlow 的要求
            available_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "molecule_generation",
                        "description": "执行分子生成计算，需要提供 PDB 文件路径",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "params": {
                                    "type": "object",
                                    "properties": {
                                        "pdb_file": {
                                            "type": "string",
                                            "description": "受体文件的绝对路径，必须为 .pdb 格式"
                                        }
                                    },
                                    "required": ["pdb_file"]
                                }
                            },
                            "required": ["params"]
                        }
                    }
                }
            ]
            
            # 打印发送的请求参数以便调试
            print("发送的请求参数：")
            print(json.dumps({
                "model": self.model,
                "messages": messages,
                "tools": available_tools,
                "tool_choice": "auto"
            }, indent=2, ensure_ascii=False))
            
            # 调用 OpenAI API 进行工具调用
            print(f"发送请求给大模型: {self.model}")
            response = self.client.chat.completions.create(
                model=self.model,            
                messages=messages,
                tools=available_tools,
                tool_choice="auto"
            )
            
            # 处理返回的内容
            content = response.choices[0]
            print(f"模型响应类型: {content.finish_reason}")
            
            if content.message.tool_calls:
                # 如果需要使用工具，解析工具调用
                tool_call = content.message.tool_calls[0]
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                print(f"\n\n[正在调用工具 {tool_name}，参数: {tool_args}]\n")
                
                # 执行工具
                try:
                    result = await self.session.call_tool(tool_name, tool_args)
                    print(f"工具调用结果: {result}")
                    
                    # 将模型返回的调用工具数据和工具执行结果都存入messages中
                    messages.append(content.message.model_dump())
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(result.content[0].text) if isinstance(result.content[0].text, dict) else result.content[0].text,
                        "tool_call_id": tool_call.id,
                    })
                    
                    # 将工具调用结果再返回给大模型用于生成最终结果
                    final_response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                    )
                    return final_response.choices[0].message.content
                    
                except Exception as e:
                    error_msg = f"工具调用失败: {str(e)}"
                    print(f"\n⚠️ {error_msg}")
                    return error_msg
            else:
                print("模型没有调用工具，直接返回响应")
                
            return content.message.content
        except Exception as e:
            error_msg = f"处理查询时发生错误: {str(e)}"
            print(f"\n⚠️ {error_msg}")
            import traceback
            traceback.print_exc()
            return error_msg
    
    async def chat_loop(self):
        """运行交互式分子生成聊天循环"""
        print("\n🧪 分子生成 MCP 客户端已启动！输入 'quit' 退出")
        print("💡 提示: 你可以请求执行分子生成，例如 '请使用位于/home/zhangfn/workflow/3rfm.pdb的蛋白质文件生成分子'")

        while True:
            try:
                query = input("\n你: ").strip()
                if query.lower() in ['quit', 'exit', '退出']:
                    break
                
                response = await self.process_query(query)
                print(f"\n🤖 助手: {response}")

            except Exception as e:
                print(f"\n⚠️ 发生错误: {str(e)}")

    async def cleanup(self):
        """清理资源"""
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("使用方法: python molecule_client.py <服务器脚本路径>")
        sys.exit(1)

    client = MCPMoleculeClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())