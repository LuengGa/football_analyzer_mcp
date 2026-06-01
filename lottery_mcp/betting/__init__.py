"""
投注推荐模块 (lottery_mcp.betting)
================================

提供投注建议、价值发现、AI分析等功能。

模块结构:
    - engine: 投注引擎核心（推荐生成、投注单生成）
    - value: 价值发现（价值投注识别）
    - ai: AI分析（智能推荐）

使用方法:
    from lottery_mcp.betting import get_daily_recommendations, generate_betting_slips
    
    # 获取每日推荐
    recommendations = get_daily_recommendations(count=5)
    
    # 生成投注单
    slips = generate_betting_slips(match_ids=["m1", "m2"])
"""

from .engine import (
    get_daily_recommendations,
    generate_betting_slips,
    generate_kelly_slips,
    cross_match_analysis,
    auto_parlay_recommendation,
)

from .value import (
    ValueDiscoveryEngine,
    ValueSignal,
    ValueSignalType,
    ValueDiscoveryResult,
    batch_analyze,
)

from .ai import (
    AIAnalyzer,
)

__all__ = [
    # 投注引擎
    "get_daily_recommendations",
    "generate_betting_slips",
    "generate_kelly_slips",
    "cross_match_analysis",
    "auto_parlay_recommendation",
    
    # 价值发现
    "ValueDiscoveryEngine",
    "ValueSignal",
    "ValueSignalType",
    "ValueDiscoveryResult",
    "batch_analyze",
    
    # AI分析
    "AIAnalyzer",
]
