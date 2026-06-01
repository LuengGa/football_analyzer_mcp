"""
规则引擎模块 (lottery_mcp.rules)
==============================

提供投注规则验证、风控守卫等功能。

模块结构:
    - engine: 规则引擎核心（验证、计算）
    - guardrails: 风控守卫（强制规则执行）

使用方法:
    from lottery_mcp.rules import validate_bet, validate_parlay, calculate_bonus
    
    # 验证投注
    result = validate_bet(bet_data)
    
    # 验证串关
    result = validate_parlay(parlay_data)
"""

from .engine import (
    validate_bet,
    validate_parlay,
    validate_mixed_parlay,
    calculate_bonus,
    query_rules,
    explain_rule,
)

from .guardrails import (
    validate_scenario,
    validate_plan,
    reject_bet,
    rule_guard,
    check_daily_limit,
    check_risk_alert,
)

__all__ = [
    # 规则验证
    "validate_bet",
    "validate_parlay",
    "validate_mixed_parlay",
    "calculate_bonus",
    "query_rules",
    "explain_rule",
    
    # 风控守卫
    "validate_scenario",
    "validate_plan",
    "reject_bet",
    "rule_guard",
    "check_daily_limit",
    "check_risk_alert",
]
