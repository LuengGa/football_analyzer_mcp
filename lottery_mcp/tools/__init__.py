"""
MCP 工具注册模块 (lottery_mcp.tools)
==================================

提供所有 MCP 工具的注册功能。

模块结构:
    - data_tools: 数据获取工具
    - analysis_tools: 分析引擎工具
    - betting_tools: 投注推荐工具
    - rules_tools: 规则验证工具
    - guardrails_tools: 风控守卫工具
    - system_tools: 系统管理工具
    - enhanced_tools_mcp: 增强工具（赔率监控、投注追踪、止损管理）
    - resources: MCP 资源注册
    - prompts: MCP 提示词注册
    - helpers: 共享工具函数

使用方法:
    from lottery_mcp.tools import register_all_tools
    
    mcp = FastMCP("lottery_mcp")
    register_all_tools(mcp)
"""

from .helpers import (
    # 错误处理
    raise_tool_error,
    _to_json,
    _truncate_for_context,
    
    # 泊松分布
    _calculate_poisson_probabilities,
    _estimate_lambdas_from_odds,
    
    # Elo评级
    _calculate_elo_probabilities,
    _update_elo,
    
    # 凯利公式
    _calculate_kelly_stake,
    _calculate_parlay_kelly,
    
    # 价值投注
    _calculate_value_edge,
    _find_value_bets,
    
    # 分析辅助
    _analyze_all_matches,
    _detect_odds_drift,
    _generate_match_id,
    _parse_match_id,
    
    # 格式化
    _format_currency,
    _format_percentage,
    _format_odds,
    _truncate_string,
    
    # 验证
    _validate_stake,
    _validate_odds,
    _validate_match_id,
)

# 导入注册函数
from .data_tools import register_data_tools, register_live_odds_tools, register_jingcai_info_tools
from .analysis_tools import register_analysis_tools
from .betting_tools import register_betting_tools
from .rules_tools import register_rules_tools
from .guardrails_tools import register_guardrails_tools
from .system_tools import register_system_tools
from .enhanced_tools_mcp import register_enhanced_tools
from .prediction_tools import register_prediction_tools
from .historical_tools import register_historical_tools
from .workflows import register_workflow_tools
from .resources import register_resources
from .prompts import register_prompts


def register_all_tools(mcp):
    """注册所有工具
    
    一次性注册所有模块的工具函数。
    
    Args:
        mcp: FastMCP 实例
    """
    # ⭐ 首先注册端到端工作流工具（最优先！
    register_workflow_tools(mcp)
    
    register_rules_tools(mcp)
    register_guardrails_tools(mcp)
    register_data_tools(mcp)
    register_live_odds_tools(mcp)
    register_jingcai_info_tools(mcp)
    register_analysis_tools(mcp)
    register_betting_tools(mcp)
    register_system_tools(mcp)
    register_enhanced_tools(mcp)
    register_prediction_tools(mcp)
    register_historical_tools(mcp)


def register_all_resources(mcp):
    """注册所有资源
    
    Args:
        mcp: FastMCP 实例
    """
    register_resources(mcp)


def register_all_prompts(mcp):
    """注册所有提示词
    
    Args:
        mcp: FastMCP 实例
    """
    register_prompts(mcp)


__all__ = [
    # 注册函数
    "register_all_tools",
    "register_all_resources",
    "register_all_prompts",
    "register_workflow_tools",
    "register_data_tools",
    "register_analysis_tools",
    "register_betting_tools",
    "register_rules_tools",
    "register_guardrails_tools",
    "register_system_tools",
    "register_enhanced_tools",
    "register_prediction_tools",
    "register_historical_tools",
    "register_jingcai_info_tools",
    "register_resources",
    "register_prompts",
    
    # 错误处理
    "raise_tool_error",
    "_to_json",
    "_truncate_for_context",
    
    # 泊松分布
    "_calculate_poisson_probabilities",
    "_estimate_lambdas_from_odds",
    
    # Elo评级
    "_calculate_elo_probabilities",
    "_update_elo",
    
    # 凯利公式
    "_calculate_kelly_stake",
    "_calculate_parlay_kelly",
    
    # 价值投注
    "_calculate_value_edge",
    "_find_value_bets",
    
    # 分析辅助
    "_analyze_all_matches",
    "_detect_odds_drift",
    "_generate_match_id",
    "_parse_match_id",
    
    # 格式化
    "_format_currency",
    "_format_percentage",
    "_format_odds",
    "_truncate_string",
    
    # 验证
    "_validate_stake",
    "_validate_odds",
    "_validate_match_id",
]
