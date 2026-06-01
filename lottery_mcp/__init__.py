"""
Lottery MCP - 竞彩足球 MCP 服务包

基于中国体育彩票（竞彩足球/北京单场/传统足彩）官方规则，
提供投注验证、风控规则、数据分析、投注建议等服务。

模块结构:
    - data: 数据获取模块（竞彩/北单/传统足彩数据获取）
    - analysis: 分析引擎模块（统计分析、玩法分析）
    - betting: 投注推荐模块（投注建议、价值发现、AI分析）
    - rules: 规则引擎模块（规则验证、风控守卫）
    - tools: MCP工具注册（所有工具的注册入口）
    - models: Pydantic模型（输入输出模型定义）
    - knowledge: 知识库（规则文档、玩法说明）

使用方法:
    # 作为 MCP 服务器运行
    python -m lottery_mcp
    
    # 或使用入口命令
    lottery-mcp
    
    # 编程方式使用
    from lottery_mcp import create_server
    server = create_server()
    server.run()
"""

__version__ = "2.0.0"
__author__ = "Lottery MCP Team"

# 延迟导入，避免循环依赖
def create_server():
    """创建 MCP 服务器实例
    
    Returns:
        FastMCP 实例
    """
    from .server import create_mcp_server
    return create_mcp_server()


def run_server():
    """运行 MCP 服务器（入口点函数）"""
    from .server import run_mcp_server
    run_mcp_server()


# 便捷导出
__all__ = [
    "create_server",
    "run_server",
    "__version__",
    "__author__",
]
