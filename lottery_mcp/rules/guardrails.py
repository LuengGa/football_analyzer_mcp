"""
风控守卫模块 v2.0 — 多维度风险控制

升级内容：
- 资金管理（止损/回撤/马丁格尔检测）
- 比赛截止时间检测
- 盈亏追踪
- 心理风险检测
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger("lottery_mcp")

GUARDRAILS_CONFIG = {
    "max_daily_stake": 10000,
    "max_single_stake": 10000,
    "max_parlay_matches": 8,
    "warning_threshold": 1000,
    "chase_limit": 5,
    "max_drawdown_pct": 0.50,       # 最大回撤50%
    "stop_loss_daily_pct": 0.30,    # 日止损30%
    "stop_loss_weekly_pct": 0.50,   # 周止损50%
    "martingale_threshold": 2.5,    # 马丁格尔检测倍数
    "max_consecutive_losses": 5,    # 最大连续亏损次数
    "cooling_off_hours": 24,         # 冷却时间(小时)
    "match_deadline_minutes": 5,    # 比赛截止前5分钟不可投注
}


@dataclass
class BankrollState:
    """资金状态追踪"""
    initial_bankroll: float
    current_bankroll: float
    peak_bankroll: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    total_pnl: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    last_bet_timestamp: Optional[datetime] = None
    bet_history: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        self.peak_bankroll = self.initial_bankroll

    def record_bet(self, stake: float, result: Optional[float] = None):
        """记录一笔投注"""
        self.last_bet_timestamp = datetime.now()
        self.bet_history.append({
            "timestamp": self.last_bet_timestamp.isoformat(),
            "stake": stake,
            "result": result,
        })
        if result is not None:
            self.daily_pnl += result
            self.weekly_pnl += result
            self.total_pnl += result
            self.current_bankroll = self.initial_bankroll + self.total_pnl
            self.peak_bankroll = max(self.peak_bankroll, self.current_bankroll)

            if result > 0:
                self.consecutive_wins += 1
                self.consecutive_losses = 0
            else:
                self.consecutive_losses += 1
                self.consecutive_wins = 0

    def get_drawdown(self) -> float:
        """当前回撤百分比"""
        if self.peak_bankroll <= 0:
            return 0.0
        return (self.peak_bankroll - self.current_bankroll) / self.peak_bankroll


# ================================================================
# 核心风控API
# ================================================================

def validate_scenario(
    scenario_type: str,
    bets: List[Dict[str, Any]],
    total_stake: float,
    lottery_type: str = "竞彩足球",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """场景验证（增强版）"""
    errors = []
    warnings = []

    if scenario_type == "single_bet":
        if total_stake > GUARDRAILS_CONFIG["max_single_stake"]:
            errors.append(f"单注金额超过限额 {GUARDRAILS_CONFIG['max_single_stake']} 元")
        if total_stake > GUARDRAILS_CONFIG["warning_threshold"]:
            warnings.append(f"单注金额 {total_stake} 元较高，请确认")

    elif scenario_type == "parlay":
        # 串关验证
        if len(bets) > GUARDRAILS_CONFIG["max_parlay_matches"]:
            errors.append(f"串关场次超过限制 {GUARDRAILS_CONFIG['max_parlay_matches']} 场")
        # 检查是否有重复比赛
        match_ids = [b.get("match_id") for b in bets if b.get("match_id")]
        if len(match_ids) != len(set(match_ids)):
            errors.append("串关中包含重复比赛")

    elif scenario_type == "daily_plan":
        if total_stake > GUARDRAILS_CONFIG["max_daily_stake"]:
            errors.append(f"日投注总额超过限额 {GUARDRAILS_CONFIG['max_daily_stake']} 元")

    elif scenario_type == "chase":
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
    """投注计划验证"""
    errors = []
    warnings = []

    daily_budget = total_budget / period_days
    if daily_budget > GUARDRAILS_CONFIG["max_daily_stake"]:
        errors.append(f"日均预算超过限额 {GUARDRAILS_CONFIG['max_daily_stake']} 元")

    if plan_type == "chase":
        if period_days > GUARDRAILS_CONFIG["chase_limit"]:
            errors.append(f"追号期数超过限制 {GUARDRAILS_CONFIG['chase_limit']} 期")

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


def reject_bet(reason: str, scenario: Optional[str] = None) -> Dict[str, Any]:
    """强制拒绝投注"""
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
    """规则守卫（增强版）"""
    errors = []
    warnings = []
    data = data or {}

    if guard_type == "pre_bet":
        stake = data.get("stake", 0)
        if stake > GUARDRAILS_CONFIG["max_single_stake"]:
            errors.append("投注金额超限")

        # 马丁格尔检测
        prev_stakes = data.get("last_stakes", [])
        if len(prev_stakes) >= 2 and stake > prev_stakes[-1] * GUARDRAILS_CONFIG["martingale_threshold"]:
            errors.append("疑似马丁格尔加倍策略，已被系统拦截")

        # 连续亏损检测
        consecutive_losses = data.get("consecutive_losses", 0)
        if consecutive_losses >= GUARDRAILS_CONFIG["max_consecutive_losses"]:
            errors.append(f"连续亏损{consecutive_losses}次，触发强制冷却。建议休息{GUARDRAILS_CONFIG['cooling_off_hours']}小时")

    elif guard_type == "post_bet":
        # 检查是否需要冷却
        if data.get("consecutive_losses", 0) >= GUARDRAILS_CONFIG["max_consecutive_losses"]:
            warnings.append("已触发冷却期，建议暂停投注")

    elif guard_type == "daily":
        daily_total = data.get("daily_total", 0)
        bankroll = data.get("bankroll", 0)

        if daily_total > GUARDRAILS_CONFIG["max_daily_stake"]:
            errors.append("日投注总额超限")

        # 日止损检查
        daily_loss = data.get("daily_loss", 0)
        if bankroll > 0 and abs(daily_loss) / bankroll > GUARDRAILS_CONFIG["stop_loss_daily_pct"]:
            errors.append(f"日亏损超过止损线{GUARDRAILS_CONFIG['stop_loss_daily_pct']:.0%}，今日停止投注")

    elif guard_type == "weekly":
        weekly_loss = data.get("weekly_loss", 0)
        bankroll = data.get("bankroll", 0)
        if bankroll > 0 and abs(weekly_loss) / bankroll > GUARDRAILS_CONFIG["stop_loss_weekly_pct"]:
            errors.append(f"周亏损超过止损线{GUARDRAILS_CONFIG['stop_loss_weekly_pct']:.0%}，本周停止投注")

    elif guard_type == "emergency":
        drawdown = data.get("drawdown", 0)
        if drawdown > GUARDRAILS_CONFIG["max_drawdown_pct"]:
            errors.append(f"回撤{drawdown:.1%}超过最大回撤{GUARDRAILS_CONFIG['max_drawdown_pct']:.0%}，触发紧急停止")

    return {
        "guard_type": guard_type,
        "passed": len(errors) == 0,
        "errors": errors if errors else None,
        "warnings": warnings if warnings else None,
    }


def check_daily_limit(current_total: float, new_stake: float) -> Dict[str, Any]:
    """检查日限额"""
    limit = GUARDRAILS_CONFIG["max_daily_stake"]
    new_total = current_total + new_stake
    return {
        "current_total": current_total,
        "new_stake": new_stake,
        "new_total": new_total,
        "limit": limit,
        "remaining": max(0, limit - current_total),
        "exceeded": new_total > limit,
    }


def check_risk_alert(match_id: str, risk_factors: List[str]) -> Dict[str, Any]:
    """检查风险警报"""
    high_risk_factors = {"赔率异动", "主力伤停", "天气恶劣", "连续三轮不胜", "教练下课危机"}
    alerts = []
    for factor in risk_factors:
        severity = "高" if factor in high_risk_factors else "中"
        alerts.append({"factor": factor, "severity": severity, "action": "建议谨慎投注" if severity == "高" else "请注意风险"})
    return {
        "match_id": match_id,
        "alerts": alerts,
        "alert_count": len(alerts),
        "has_high_risk": any(a["severity"] == "高" for a in alerts),
    }


def check_match_deadline(match_time: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """检查比赛是否已过投注截止时间

    竞彩通常在比赛开始前5分钟停止销售。
    """
    if now is None:
        now = datetime.now()

    try:
        if isinstance(match_time, str):
            mt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
        else:
            mt = match_time
    except (ValueError, TypeError):
        return {"can_bet": False, "reason": "无法解析比赛时间"}

    deadline = mt - timedelta(minutes=GUARDRAILS_CONFIG["match_deadline_minutes"])
    can_bet = now < deadline

    return {
        "can_bet": can_bet,
        "match_time": mt.isoformat(),
        "deadline": deadline.isoformat(),
        "minutes_remaining": max(0, (deadline - now).total_seconds() / 60) if can_bet else 0,
        "reason": None if can_bet else f"比赛已截止（{mt.strftime('%H:%M')}开赛，{GUARDRAILS_CONFIG['match_deadline_minutes']}分钟前截止）",
    }


def check_bankroll_health(
    bankroll: float,
    initial_bankroll: float,
    daily_pnl: float,
    weekly_pnl: float,
    consecutive_losses: int = 0,
) -> Dict[str, Any]:
    """全面资金健康检查"""
    issues = []
    warnings = []

    total_pnl = bankroll - initial_bankroll
    drawdown = max(0, initial_bankroll - bankroll) / initial_bankroll if initial_bankroll > 0 else 0

    if drawdown > GUARDRAILS_CONFIG["max_drawdown_pct"]:
        issues.append({
            "type": "drawdown_exceeded",
            "severity": "FATAL",
            "detail": f"回撤{drawdown:.1%}超过{GUARDRAILS_CONFIG['max_drawdown_pct']:.0%}上限",
            "action": "立即停止投注，重新评估策略",
        })
    elif drawdown > GUARDRAILS_CONFIG["max_drawdown_pct"] * 0.7:
        warnings.append({
            "type": "drawdown_warning",
            "severity": "WARNING",
            "detail": f"回撤{drawdown:.1%}接近上限",
            "action": "减少投注规模",
        })

    if bankroll > 0 and abs(daily_pnl) / bankroll > GUARDRAILS_CONFIG["stop_loss_daily_pct"]:
        issues.append({
            "type": "daily_stop_loss",
            "severity": "FATAL",
            "detail": f"日亏损超过{abs(daily_pnl)}元",
            "action": "今日停止投注",
        })

    if consecutive_losses >= GUARDRAILS_CONFIG["max_consecutive_losses"]:
        issues.append({
            "type": "consecutive_losses",
            "severity": "FATAL",
            "detail": f"连续亏损{consecutive_losses}次",
            "action": "触发强制冷却期",
        })

    return {
        "healthy": len(issues) == 0,
        "bankroll": bankroll,
        "initial_bankroll": initial_bankroll,
        "total_pnl": total_pnl,
        "drawdown_pct": round(drawdown * 100, 2),
        "daily_pnl": daily_pnl,
        "weekly_pnl": weekly_pnl,
        "consecutive_losses": consecutive_losses,
        "issues": issues,
        "warnings": warnings,
        "can_continue": len([i for i in issues if i["severity"] == "FATAL"]) == 0,
    }


def check_martingale_pattern(stakes: List[float], threshold: float = None) -> Dict[str, Any]:
    """检测马丁格尔加倍模式"""
    if threshold is None:
        threshold = GUARDRAILS_CONFIG["martingale_threshold"]

    if len(stakes) < 2:
        return {"detected": False, "reason": "投注记录不足"}

    recent = stakes[-3:]
    doublings = 0
    for i in range(1, len(recent)):
        if recent[i - 1] > 0 and recent[i] >= recent[i - 1] * threshold:
            doublings += 1

    detected = doublings >= 2

    return {
        "detected": detected,
        "reason": "检测到加倍投注模式" if detected else "正常",
        "doublings_found": doublings,
        "last_stakes": recent,
        "action": "建议停止当前策略，采用固定比例投注" if detected else None,
    }