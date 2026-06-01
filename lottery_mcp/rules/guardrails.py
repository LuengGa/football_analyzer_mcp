"""
风控守卫模块

提供强制规则执行和风控检查功能。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("lottery_mcp")


# 风控配置
GUARDRAILS_CONFIG = {
    "max_daily_stake": 10000,
    "max_single_stake": 10000,
    "max_parlay_matches": 8,
    "warning_threshold": 1000,
    "chase_limit": 5,  # 追号期数限制
}


def validate_scenario(
    scenario_type: str,
    bets: List[Dict[str, Any]],
    total_stake: float,
    lottery_type: str = "竞彩足球",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """场景验证
    
    Args:
        scenario_type: 场景类型
        bets: 投注列表
        total_stake: 总投注金额
        lottery_type: 彩种类型
        context: 额外上下文
        
    Returns:
        验证结果
    """
    errors = []
    warnings = []
    
    if scenario_type == "single_bet":
        # 单注验证
        if total_stake > GUARDRAILS_CONFIG["max_single_stake"]:
            errors.append(f"单注金额超过限额 {GUARDRAILS_CONFIG['max_single_stake']} 元")
        if total_stake > GUARDRAILS_CONFIG["warning_threshold"]:
            warnings.append(f"单注金额 {total_stake} 元较高，请确认")
    
    elif scenario_type == "parlay":
        # 串关验证
        if len(bets) > GUARDRAILS_CONFIG["max_parlay_matches"]:
            errors.append(f"串关场次超过限制 {GUARDRAILS_CONFIG['max_parlay_matches']} 场")
    
    elif scenario_type == "daily_plan":
        # 日计划验证
        if total_stake > GUARDRAILS_CONFIG["max_daily_stake"]:
            errors.append(f"日投注总额超过限额 {GUARDRAILS_CONFIG['max_daily_stake']} 元")
    
    elif scenario_type == "chase":
        # 追号验证
        chase_periods = context.get("chase_periods", 1) if context else 1
        if chase_periods > GUARDRAILS_CONFIG["chase_limit"]:
            errors.append(f"追号期数超过限制 {GUARDRAILS_CONFIG['chase_limit']} 期")
    
    return {
        "valid": len(errors) == 0,
        "scenario_type": scenario_type,
        "errors": errors if errors else None,
        "warnings": warnings if warnings else None,
        "total_stake": total_stake,
    }


def validate_plan(
    plan_type: str,
    bets: List[Dict[str, Any]],
    total_budget: float,
    period_days: int = 1,
    lottery_type: str = "竞彩足球",
) -> Dict[str, Any]:
    """投注计划验证
    
    Args:
        plan_type: 计划类型
        bets: 投注列表
        total_budget: 总预算
        period_days: 计划周期
        lottery_type: 彩种类型
        
    Returns:
        验证结果
    """
    errors = []
    warnings = []
    
    # 验证预算
    daily_budget = total_budget / period_days
    if daily_budget > GUARDRAILS_CONFIG["max_daily_stake"]:
        errors.append(f"日均预算超过限额 {GUARDRAILS_CONFIG['max_daily_stake']} 元")
    
    # 验证计划类型
    if plan_type == "chase":
        if period_days > GUARDRAILS_CONFIG["chase_limit"]:
            errors.append(f"追号期数超过限制 {GUARDRAILS_CONFIG['chase_limit']} 期")
    
    # 警告检查
    if total_budget > 5000:
        warnings.append("总预算较高，请确保在可承受范围内")
    
    return {
        "valid": len(errors) == 0,
        "plan_type": plan_type,
        "total_budget": total_budget,
        "period_days": period_days,
        "daily_budget": round(daily_budget, 2),
        "errors": errors if errors else None,
        "warnings": warnings if warnings else None,
    }


def reject_bet(
    reason: str,
    scenario: Optional[str] = None,
) -> Dict[str, Any]:
    """强制拒绝投注
    
    Args:
        reason: 拒绝原因
        scenario: 触发场景
        
    Returns:
        拒绝结果
    """
    return {
        "rejected": True,
        "reason": reason,
        "scenario": scenario,
        "timestamp": datetime.now().isoformat(),
        "action": "投注已被系统拒绝",
    }


def rule_guard(
    guard_type: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """规则守卫
    
    Args:
        guard_type: 守卫类型
        data: 检查数据
        
    Returns:
        守卫检查结果
    """
    errors = []
    warnings = []
    
    if guard_type == "pre_bet":
        # 投注前检查
        if data:
            stake = data.get("stake", 0)
            if stake > GUARDRAILS_CONFIG["max_single_stake"]:
                errors.append("投注金额超限")
    
    elif guard_type == "post_bet":
        # 投注后检查
        pass
    
    elif guard_type == "daily":
        # 日检查
        if data:
            daily_total = data.get("daily_total", 0)
            if daily_total > GUARDRAILS_CONFIG["max_daily_stake"]:
                errors.append("日投注总额超限")
    
    elif guard_type == "emergency":
        # 紧急检查
        pass
    
    return {
        "guard_type": guard_type,
        "passed": len(errors) == 0,
        "errors": errors if errors else None,
        "warnings": warnings if warnings else None,
    }


def check_daily_limit(
    current_total: float,
    new_stake: float,
) -> Dict[str, Any]:
    """检查日限额
    
    Args:
        current_total: 当日已投注总额
        new_stake: 新投注金额
        
    Returns:
        检查结果
    """
    new_total = current_total + new_stake
    remaining = GUARDRAILS_CONFIG["max_daily_stake"] - current_total
    
    return {
        "current_total": current_total,
        "new_stake": new_stake,
        "new_total": new_total,
        "limit": GUARDRAILS_CONFIG["max_daily_stake"],
        "remaining": max(0, remaining),
        "exceeded": new_total > GUARDRAILS_CONFIG["max_daily_stake"],
    }


def check_risk_alert(
    match_id: str,
    risk_factors: List[str],
) -> Dict[str, Any]:
    """检查风险警报
    
    Args:
        match_id: 比赛ID
        risk_factors: 风险因素列表
        
    Returns:
        风险警报结果
    """
    high_risk_factors = ["赔率异动", "主力伤停", "天气恶劣"]
    
    alerts = []
    for factor in risk_factors:
        if factor in high_risk_factors:
            alerts.append({
                "factor": factor,
                "severity": "高",
                "action": "建议谨慎投注",
            })
        else:
            alerts.append({
                "factor": factor,
                "severity": "中",
                "action": "请注意风险",
            })
    
    return {
        "match_id": match_id,
        "alerts": alerts,
        "alert_count": len(alerts),
        "has_high_risk": any(a["severity"] == "高" for a in alerts),
    }
