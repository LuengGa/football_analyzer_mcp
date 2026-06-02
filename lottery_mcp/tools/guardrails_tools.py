"""
MCP Server Guardrails Tools - Mandatory rule enforcement tools.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from .helpers import raise_tool_error, _to_json
from lottery_mcp.models import (
    RejectInput,
    RuleGuardInput,
    ValidateBetInput,
    ValidatePlanInput,
    ValidateScenarioInput,
)

logger = logging.getLogger("lottery_mcp")


# ============================================================
# Guardrails Engine
# ============================================================

class GuardrailsEngine:
    """强制规则引擎 - 实现硬性风控规则"""
    
    def __init__(self):
        """初始化守卫引擎，从 system_tools 读取用户配置"""
        # 延迟导入避免循环依赖（system_tools 可能也导入 guardrails_tools）
        from .system_tools import _user_config

        self._bet_history: List[Dict] = []
        self._daily_bets: List[Dict] = []

        # 从用户配置读取硬性限制，若配置缺失则使用默认值
        self.HARD_LIMITS = {
            "max_daily_stake": _user_config.get("max_daily_stake", 99999.0),
            "max_single_stake": _user_config.get("max_single_stake", 99999.0),
            "min_age": 18,
            "max_chase_rounds": 10,
        }

    # 按彩种区分的串关场次上限
    MAX_PARLAY_MATCHES = {
        "竞彩足球": 8,
        "北京单场": 15,
    }
    DEFAULT_MAX_PARLAY_MATCHES = 8  # 默认值（兼容未知彩种）
    
    # 警告阈值 - 需要确认
    WARNING_THRESHOLDS = {
        "daily_stake_warning": 1000.0,    # 单日超过1000元警告
        "single_stake_warning": 1000.0,   # 单注超过1000元警告
        "chase_rounds_warning": 5,        # 追号超过5期警告
        "high_risk_matches_warning": 3,   # 高风险比赛超过3场警告
    }
    
    # 风险等级定义
    RISK_LEVELS = {
        "low": {"max_stake_ratio": 0.05, "description": "低风险"},
        "medium": {"max_stake_ratio": 0.03, "description": "中风险"},
        "high": {"max_stake_ratio": 0.01, "description": "高风险"},
        "extreme": {"max_stake_ratio": 0.0, "description": "极高风险 - 禁止投注"},
    }
    
    def check_hard_limits(self, scenario: ValidateScenarioInput) -> Dict[str, Any]:
        """检查硬性限制
        
        返回是否通过检查及违规详情
        """
        violations = []
        
        # 检查单日限额
        if scenario.total_stake > self.HARD_LIMITS["max_daily_stake"]:
            violations.append({
                "type": "daily_limit_exceeded",
                "message": f"单日投注金额 {scenario.total_stake} 元超过限额 {self.HARD_LIMITS['max_daily_stake']} 元",
                "severity": "critical",
            })
        
        # 检查单注限额
        for bet in scenario.bets:
            if bet.stake > self.HARD_LIMITS["max_single_stake"]:
                violations.append({
                    "type": "single_bet_limit_exceeded",
                    "message": f"单注金额 {bet.stake} 元超过限额 {self.HARD_LIMITS['max_single_stake']} 元",
                    "severity": "critical",
                    "match_id": bet.match_id,
                })
        
        # 检查串关场次（按彩种区分上限）
        max_matches = self.MAX_PARLAY_MATCHES.get(
            scenario.lottery_type, self.DEFAULT_MAX_PARLAY_MATCHES
        )
        if len(scenario.bets) > max_matches:
            violations.append({
                "type": "parlay_matches_exceeded",
                "message": f"串关场次 {len(scenario.bets)} 超过最大限制 {max_matches}（{scenario.lottery_type}）",
                "severity": "critical",
            })
        
        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "violation_count": len(violations),
        }
    
    def check_warning_thresholds(self, scenario: ValidateScenarioInput) -> Dict[str, Any]:
        """检查警告阈值
        
        返回警告列表
        """
        warnings = []
        
        # 检查单日警告阈值
        if scenario.total_stake > self.WARNING_THRESHOLDS["daily_stake_warning"]:
            warnings.append({
                "type": "daily_stake_warning",
                "message": f"单日投注金额 {scenario.total_stake} 元超过警告阈值 {self.WARNING_THRESHOLDS['daily_stake_warning']} 元",
                "severity": "warning",
            })
        
        # 检查单注警告阈值
        for bet in scenario.bets:
            if bet.stake > self.WARNING_THRESHOLDS["single_stake_warning"]:
                warnings.append({
                    "type": "single_stake_warning",
                    "message": f"单注金额 {bet.stake} 元超过警告阈值 {self.WARNING_THRESHOLDS['single_stake_warning']} 元",
                    "severity": "warning",
                    "match_id": bet.match_id,
                })
        
        return {
            "has_warnings": len(warnings) > 0,
            "warnings": warnings,
            "warning_count": len(warnings),
        }
    
    def validate_scenario(self, scenario: ValidateScenarioInput) -> Dict[str, Any]:
        """验证场景
        
        综合检查场景的各种限制
        """
        # 确保 bets 都是 ValidateBetInput 实例
        if scenario.bets:
            scenario.bets = [ValidateBetInput(**b) if isinstance(b, dict) else b for b in scenario.bets]
        # 硬性限制检查
        hard_check = self.check_hard_limits(scenario)
        
        # 警告阈值检查
        warning_check = self.check_warning_thresholds(scenario)
        
        # 场景特定检查
        scenario_specific = self._check_scenario_specific(scenario)
        
        # 综合评估
        approved = hard_check["passed"] and scenario_specific["passed"]
        
        # 确定风险等级
        risk_level = self._determine_risk_level(scenario, hard_check, warning_check)
        
        return {
            "approved": approved,
            "scenario_type": scenario.scenario_type,
            "risk_level": risk_level,
            "hard_limits": hard_check,
            "warnings": warning_check,
            "scenario_checks": scenario_specific,
            "recommendations": self._generate_recommendations(
                approved, hard_check, warning_check, risk_level
            ),
            "timestamp": datetime.now().isoformat(),
        }
    
    def _check_scenario_specific(self, scenario: ValidateScenarioInput) -> Dict[str, Any]:
        """场景特定检查"""
        checks = []
        passed = True
        
        if scenario.scenario_type == "parlay":
            # 串关特定检查
            # P1-X1: 允许单关通过（min_matches=1），但比分/总进球/半全场不支持单关
            if len(scenario.bets) < 1:
                checks.append({
                    "check": "min_matches",
                    "passed": False,
                    "message": "串关至少需要1场比赛",
                })
                passed = False
            else:
                # 检查比分/总进球/半全场是否尝试单关
                no_single_plays = {"比分", "总进球", "半全场"}
                play_types_in_scenario = set()
                for bet in scenario.bets:
                    play_type = getattr(bet, 'play_type', None)
                    if play_type:
                        # 简单映射英文缩写到中文
                        from .rules_tools import _resolve_play_type_cn
                        play_types_in_scenario.add(_resolve_play_type_cn(play_type))

                if len(scenario.bets) == 1 and (play_types_in_scenario & no_single_plays):
                    checks.append({
                        "check": "min_matches",
                        "passed": False,
                        "message": f"玩法 {', '.join(play_types_in_scenario & no_single_plays)} 不支持单关，至少需要2场比赛",
                    })
                    passed = False
                else:
                    checks.append({
                        "check": "min_matches",
                        "passed": True,
                        "message": "串关场次符合要求",
                    })
        
        elif scenario.scenario_type == "chase":
            # 追号特定检查
            chase_rounds = scenario.context.get("chase_rounds", 0) if scenario.context else 0
            if chase_rounds > self.HARD_LIMITS["max_chase_rounds"]:
                checks.append({
                    "check": "max_chase_rounds",
                    "passed": False,
                    "message": f"追号期数 {chase_rounds} 超过最大限制 {self.HARD_LIMITS['max_chase_rounds']}",
                })
                passed = False
            else:
                checks.append({
                    "check": "max_chase_rounds",
                    "passed": True,
                    "message": "追号期数符合要求",
                })
        
        elif scenario.scenario_type == "daily_plan":
            # 日计划特定检查
            if scenario.total_stake > self.HARD_LIMITS["max_daily_stake"] * 0.8:
                checks.append({
                    "check": "daily_plan_budget",
                    "passed": True,
                    "message": "日计划预算接近单日限额，请注意控制",
                    "warning": True,
                })
            else:
                checks.append({
                    "check": "daily_plan_budget",
                    "passed": True,
                    "message": "日计划预算在合理范围内",
                })
        
        return {
            "passed": passed,
            "checks": checks,
        }
    
    def _determine_risk_level(self, scenario: ValidateScenarioInput, 
                             hard_check: Dict, warning_check: Dict) -> str:
        """确定风险等级"""
        if not hard_check["passed"]:
            return "extreme"
        
        warning_count = warning_check.get("warning_count", 0)
        total_stake = scenario.total_stake
        
        if warning_count >= 3 or total_stake > 5000:
            return "high"
        elif warning_count >= 1 or total_stake > 500:
            return "medium"
        else:
            return "low"
    
    def _generate_recommendations(self, approved: bool, hard_check: Dict, 
                                  warning_check: Dict, risk_level: str) -> List[str]:
        """生成建议"""
        recommendations = []
        
        if not approved:
            recommendations.append("❌ 投注未通过硬性限制检查，请调整投注方案")
            for v in hard_check.get("violations", []):
                recommendations.append(f"   - {v['message']}")
        
        if warning_check.get("has_warnings"):
            recommendations.append("⚠️  投注触发了警告阈值，请注意风险")
            for w in warning_check.get("warnings", []):
                recommendations.append(f"   - {w['message']}")
        
        if risk_level == "high":
            recommendations.append("🔴 当前投注风险等级较高，建议减少投注金额或场次")
        elif risk_level == "medium":
            recommendations.append("🟡 当前投注风险等级中等，请谨慎投注")
        elif risk_level == "low":
            recommendations.append("🟢 当前投注风险等级较低")
        
        return recommendations
    
    def validate_plan(self, plan: ValidatePlanInput) -> Dict[str, Any]:
        """验证投注计划"""
        # 计算日均投注
        daily_avg = plan.total_budget / plan.period_days if plan.period_days > 0 else plan.total_budget
        
        # 检查预算
        budget_check = daily_avg <= self.HARD_LIMITS["max_daily_stake"]
        
        # 检查投注数量
        bet_count = len(plan.bets)
        
        return {
            "approved": budget_check,
            "plan_type": plan.plan_type,
            "total_budget": plan.total_budget,
            "period_days": plan.period_days,
            "daily_average": round(daily_avg, 2),
            "budget_check": budget_check,
            "bet_count": bet_count,
            "message": "计划验证通过" if budget_check else f"日均投注 {daily_avg:.2f} 元超过单日限额",
            "timestamp": datetime.now().isoformat(),
        }
    
    def reject(self, reason: str, scenario: Optional[str] = None) -> Dict[str, Any]:
        """强制拒绝"""
        return {
            "approved": False,
            "rejected": True,
            "reason": reason,
            "scenario": scenario,
            "timestamp": datetime.now().isoformat(),
            "message": f"投注已被强制拒绝: {reason}",
        }
    
    def guard_check(self, guard_type: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """规则守卫检查"""
        checks = {
            "pre_bet": self._pre_bet_guard,
            "post_bet": self._post_bet_guard,
            "daily": self._daily_guard,
            "emergency": self._emergency_guard,
        }
        
        guard_func = checks.get(guard_type, self._default_guard)
        return guard_func(data or {})
    
    def _pre_bet_guard(self, data: Dict) -> Dict[str, Any]:
        """投注前守卫 - 检查单注限额、单日限额、串关场次、赔率范围"""
        checks = []
        violations = []
        passed = True

        # 检查单注限额
        stake = data.get("stake", 0)
        single_stake_ok = stake <= self.HARD_LIMITS["max_single_stake"]
        checks.append({
            "check": "single_stake_limit",
            "passed": single_stake_ok,
            "message": (f"单注金额 {stake} 元在限额 {self.HARD_LIMITS['max_single_stake']} 元以内"
                        if single_stake_ok
                        else f"单注金额 {stake} 元超过限额 {self.HARD_LIMITS['max_single_stake']} 元"),
        })
        if not single_stake_ok:
            violations.append({
                "type": "single_stake_exceeded",
                "message": f"单注金额 {stake} 元超过限额 {self.HARD_LIMITS['max_single_stake']} 元",
            })
            passed = False

        # 检查单日累计限额
        total_stake = data.get("total_stake", 0)
        daily_stake_ok = total_stake <= self.HARD_LIMITS["max_daily_stake"]
        checks.append({
            "check": "daily_stake_limit",
            "passed": daily_stake_ok,
            "message": (f"单日累计 {total_stake} 元在限额 {self.HARD_LIMITS['max_daily_stake']} 元以内"
                        if daily_stake_ok
                        else f"单日累计 {total_stake} 元超过限额 {self.HARD_LIMITS['max_daily_stake']} 元"),
        })
        if not daily_stake_ok:
            violations.append({
                "type": "daily_stake_exceeded",
                "message": f"单日累计 {total_stake} 元超过限额 {self.HARD_LIMITS['max_daily_stake']} 元",
            })
            passed = False

        # 检查串关场次（1-15场合理范围）
        bet_count = data.get("bet_count", 0)
        parlay_ok = 1 <= bet_count <= 15
        checks.append({
            "check": "parlay_matches",
            "passed": parlay_ok,
            "message": (f"串关场次 {bet_count} 场在合理范围（1-15）内"
                        if parlay_ok
                        else f"串关场次 {bet_count} 场不在合理范围（1-15）内"),
        })
        if not parlay_ok:
            violations.append({
                "type": "invalid_parlay_matches",
                "message": f"串关场次 {bet_count} 场不在合理范围（1-15）内",
            })
            passed = False

        # 检查赔率范围（1.01-1000）
        odds = data.get("odds", 0)
        odds_ok = 1.01 <= odds <= 1000
        checks.append({
            "check": "odds_range",
            "passed": odds_ok,
            "message": (f"赔率 {odds} 在有效范围（1.01-1000）内"
                        if odds_ok
                        else f"赔率 {odds} 不在有效范围（1.01-1000）内"),
        })
        if not odds_ok:
            violations.append({
                "type": "invalid_odds",
                "message": f"赔率 {odds} 不在有效范围（1.01-1000）内",
            })
            passed = False

        return {
            "guard_type": "pre_bet",
            "passed": passed,
            "checks": checks,
            "violations": violations,
            "message": "投注前检查通过" if passed else "投注前检查未通过，存在违规项",
        }
    
    def _post_bet_guard(self, data: Dict) -> Dict[str, Any]:
        """投注后守卫 - 验证投注数据有效性并记录投注历史"""
        checks = []
        passed = True

        # 检查投注金额是否有效（>0）
        stake = data.get("stake", 0)
        stake_valid = stake > 0
        checks.append({
            "check": "stake_valid",
            "passed": stake_valid,
            "message": (f"投注金额 {stake} 元有效"
                        if stake_valid
                        else f"投注金额 {stake} 元无效，必须大于0"),
        })
        if not stake_valid:
            passed = False

        # 检查投注结果是否为有效值
        result = data.get("result", "")
        valid_results = ("won", "lost", "pending")
        result_valid = result in valid_results
        checks.append({
            "check": "result_valid",
            "passed": result_valid,
            "message": (f"投注结果 '{result}' 有效"
                        if result_valid
                        else f"投注结果 '{result}' 无效，有效值为: {', '.join(valid_results)}"),
        })
        if not result_valid:
            passed = False

        # 记录投注到内部历史列表
        record_id = f"bet_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self._bet_history)}"
        bet_record = {
            "record_id": record_id,
            "stake": stake,
            "result": result,
            "timestamp": datetime.now().isoformat(),
            **{k: v for k, v in data.items() if k not in ("stake", "result")},
        }
        self._bet_history.append(bet_record)

        # 同步记录到当日投注列表
        self._daily_bets.append(bet_record)

        return {
            "guard_type": "post_bet",
            "passed": passed,
            "checks": checks,
            "record_id": record_id,
            "message": "投注后检查通过，已记录投注" if passed else "投注后数据验证未通过",
        }
    
    def _daily_guard(self, data: Dict) -> Dict[str, Any]:
        """日检查守卫 - 检查单日限额、投注次数、亏损止损、连续亏损预警"""
        checks = []
        violations = []
        passed = True

        # 1. 检查单日累计限额
        daily_total = data.get("daily_total", 0)
        daily_limit_ok = daily_total <= self.HARD_LIMITS["max_daily_stake"]
        checks.append({
            "check": "daily_stake_limit",
            "passed": daily_limit_ok,
            "message": (f"单日累计投注 {daily_total} 元在限额 {self.HARD_LIMITS['max_daily_stake']} 元以内"
                        if daily_limit_ok
                        else f"单日累计投注 {daily_total} 元超过限额 {self.HARD_LIMITS['max_daily_stake']} 元"),
        })
        if not daily_limit_ok:
            violations.append({
                "type": "daily_stake_exceeded",
                "message": f"单日累计投注 {daily_total} 元超过限额 {self.HARD_LIMITS['max_daily_stake']} 元",
            })
            passed = False

        # 2. 检查当日投注次数（防止过度投注，上限50次）
        daily_bet_count = len(self._daily_bets)
        max_daily_bets = 50
        bet_count_ok = daily_bet_count < max_daily_bets
        checks.append({
            "check": "daily_bet_count",
            "passed": bet_count_ok,
            "message": (f"当日投注次数 {daily_bet_count} 次在合理范围内（上限 {max_daily_bets} 次）"
                        if bet_count_ok
                        else f"当日投注次数 {daily_bet_count} 次已达上限 {max_daily_bets} 次，请停止投注"),
        })
        if not bet_count_ok:
            violations.append({
                "type": "daily_bet_count_exceeded",
                "message": f"当日投注次数 {daily_bet_count} 次已达上限 {max_daily_bets} 次",
            })
            passed = False

        # 3. 检查当日亏损是否超过止损线（3000元）
        daily_loss = 0.0
        for bet in self._daily_bets:
            result = bet.get("result", "")
            stake = bet.get("stake", 0)
            if result == "lost":
                daily_loss += stake
            elif result == "won":
                # 中奖时用赔率计算收益，扣除本金
                odds = bet.get("odds", 0)
                daily_loss -= stake * (odds - 1) if odds > 0 else 0

        max_daily_loss = 3000.0
        loss_ok = daily_loss <= max_daily_loss
        checks.append({
            "check": "daily_loss_limit",
            "passed": loss_ok,
            "message": (f"当日亏损 {daily_loss:.2f} 元在止损线 {max_daily_loss} 元以内"
                        if loss_ok
                        else f"当日亏损 {daily_loss:.2f} 元已超过止损线 {max_daily_loss} 元，建议停止投注"),
        })
        if not loss_ok:
            violations.append({
                "type": "daily_loss_exceeded",
                "message": f"当日亏损 {daily_loss:.2f} 元已超过止损线 {max_daily_loss} 元",
            })
            passed = False

        # 4. 检查连续亏损次数（情绪化投注预警，连续5次以上）
        consecutive_losses = 0
        for bet in reversed(self._daily_bets):
            if bet.get("result") == "lost":
                consecutive_losses += 1
            else:
                break

        max_consecutive_losses = 5
        consecutive_ok = consecutive_losses < max_consecutive_losses
        checks.append({
            "check": "consecutive_losses",
            "passed": consecutive_ok,
            "message": (f"连续亏损 {consecutive_losses} 次，未触发情绪化投注预警"
                        if consecutive_ok
                        else f"连续亏损 {consecutive_losses} 次，已触发情绪化投注预警，建议冷静后继续"),
        })
        if not consecutive_ok:
            violations.append({
                "type": "consecutive_loss_warning",
                "message": f"连续亏损 {consecutive_losses} 次，存在情绪化投注风险",
            })
            passed = False

        return {
            "guard_type": "daily",
            "passed": passed,
            "checks": checks,
            "violations": violations,
            "daily_total": daily_total,
            "daily_bet_count": daily_bet_count,
            "daily_loss": round(daily_loss, 2),
            "consecutive_losses": consecutive_losses,
            "limit": self.HARD_LIMITS["max_daily_stake"],
            "message": "日检查通过" if passed else "日检查未通过，存在风险项",
        }
    
    def _emergency_guard(self, data: Dict) -> Dict[str, Any]:
        """紧急守卫"""
        emergency_level = data.get("level", "low")
        
        if emergency_level == "high":
            return {
                "guard_type": "emergency",
                "passed": False,
                "level": emergency_level,
                "message": "触发高级别紧急限制，暂停所有投注",
            }
        
        return {
            "guard_type": "emergency",
            "passed": True,
            "level": emergency_level,
            "message": "紧急检查通过",
        }
    
    def _default_guard(self, data: Dict) -> Dict[str, Any]:
        """默认守卫"""
        return {
            "guard_type": "unknown",
            "passed": True,
            "message": "未知守卫类型，默认通过",
        }


# 全局强制规则引擎实例
_guardrails_engine: Optional[GuardrailsEngine] = None


def get_guardrails_engine() -> GuardrailsEngine:
    """获取强制规则引擎实例（单例模式）"""
    global _guardrails_engine
    if _guardrails_engine is None:
        _guardrails_engine = GuardrailsEngine()
    return _guardrails_engine


# ============================================================
# Tool Functions
# ============================================================

async def lottery_validate_scenario(params: ValidateScenarioInput, ctx: Context) -> str:
    """场景验证 - 验证特定投注场景"""
    try:
        await ctx.report_progress(0.5, "正在验证场景...")
        await ctx.log_info(f"[场景验证] 类型: {params.scenario_type}, 投注数: {len(params.bets)}")
        
        engine = get_guardrails_engine()
        result = engine.validate_scenario(params)
        
        await ctx.report_progress(1.0, "验证完成")
        
        return _to_json({
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"场景验证失败: {e}")
        raise_tool_error(f"场景验证失败: {str(e)}")


async def lottery_validate_plan(params: ValidatePlanInput, ctx: Context) -> str:
    """计划验证 - 验证投注计划"""
    try:
        await ctx.report_progress(0.5, "正在验证计划...")
        await ctx.log_info(f"[计划验证] 类型: {params.plan_type}, 预算: {params.total_budget}")
        
        engine = get_guardrails_engine()
        result = engine.validate_plan(params)
        
        await ctx.report_progress(1.0, "验证完成")
        
        return _to_json({
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"计划验证失败: {e}")
        raise_tool_error(f"计划验证失败: {str(e)}")


async def lottery_reject(params: RejectInput, ctx: Context) -> str:
    """强制拒绝 - 对违规操作执行强制拒绝"""
    try:
        await ctx.report_progress(0.5, "执行强制拒绝...")
        await ctx.log_info(f"[强制拒绝] 原因: {params.reason}")
        
        engine = get_guardrails_engine()
        result = engine.reject(params.reason, params.scenario)
        
        await ctx.report_progress(1.0, "拒绝执行完成")
        
        return _to_json({
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"强制拒绝执行失败: {e}")
        raise_tool_error(f"强制拒绝执行失败: {str(e)}")


async def lottery_rule_guard(params: RuleGuardInput, ctx: Context) -> str:
    """规则守卫 - 多阶段规则检查"""
    try:
        await ctx.report_progress(0.5, f"执行{params.guard_type}守卫检查...")
        await ctx.log_info(f"[规则守卫] 类型: {params.guard_type}")
        
        engine = get_guardrails_engine()
        result = engine.guard_check(params.guard_type, params.data)

        # 风险警报事件：通过日志通知 + 返回值中的 events 字段
        events = []
        if not result.get("passed", True):
            violations = result.get("violations", [])
            for v in violations:
                event = {
                    "event_type": "risk_alert",
                    "level": "high" if v.get("severity") == "critical" else "medium",
                    "reason": v.get("message", ""),
                    "match_id": v.get("match_id", ""),
                    "rule": v.get("rule", ""),
                }
                events.append(event)
                await ctx.log_warning(
                    f"[风险警报] {v.get('severity', '')} | "
                    f"规则:{v.get('rule', '')} 原因:{v.get('message', '')} "
                    f"比赛:{v.get('match_id', '')}"
                )

        await ctx.report_progress(1.0, "守卫检查完成")
        
        return _to_json({
            "success": True,
            "data": result,
            "events": events,
            "timestamp": datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"规则守卫检查失败: {e}")
        raise_tool_error(f"规则守卫检查失败: {str(e)}")


# ============================================================
# Tool Registration
# ============================================================

def register_guardrails_tools(mcp):
    """注册强制规则工具
    
    Args:
        mcp: FastMCP 实例
    """
    from mcp.server.fastmcp import Context
    
    @mcp.tool(
        name="lottery_validate_scenario",
        description="""场景验证 - 验证特定投注场景的合规性

检查场景是否满足硬性限制：
- 单日/单注限额检查
- 串关场次限制
- 年龄限制
- 场景特定规则

返回风险等级和建议。

Use when: 需要评估整体投注场景的风险时。

Workflow: generate_recommendation(生成建议) → validate_scenario(验证合规) → generate_betting_slips(生成投注单)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_validate_scenario(params: ValidateScenarioInput, ctx: Context) -> str:
        return await lottery_validate_scenario(params, ctx)
    
    @mcp.tool(
        name="lottery_validate_plan",
        description="""计划验证 - 验证投注计划的合规性

验证长期投注计划：
- 总预算合理性
- 日均投注限额
- 计划周期合理性

Use when: 制定日/周/月投注计划时。

Workflow: 在制定投注计划时调用，与 manage_config(设置限额) 配合使用。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_validate_plan(params: ValidatePlanInput, ctx: Context) -> str:
        return await lottery_validate_plan(params, ctx)
    
    @mcp.tool(
        name="lottery_reject",
        description="""强制拒绝 - 对违规操作执行强制拒绝

当检测到严重违规时，使用此工具明确拒绝投注请求。
记录拒绝原因和场景，用于后续审计。

Use when: 检测到硬性规则违规时。

Workflow: 当 validate_scenario 或 rule_guard 检测到严重违规时，调用 reject 强制拒绝。""",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def _lottery_reject(params: RejectInput, ctx: Context) -> str:
        return await lottery_reject(params, ctx)
    
    @mcp.tool(
        name="lottery_rule_guard",
        description="""规则守卫 - 多阶段规则检查

支持四种守卫类型：
- pre_bet: 投注前检查（限额、年龄、时间）
- post_bet: 投注后检查（记录、余额）
- daily: 日检查（单日累计）
- emergency: 紧急检查（异常检测）

Use when: 需要在特定阶段执行规则检查时。

Workflow: 在任何投注操作前调用，作为最后一道防线。与 validate_scenario 配合使用。""",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_rule_guard(params: RuleGuardInput, ctx: Context) -> str:
        return await lottery_rule_guard(params, ctx)

    @mcp.tool(
        name="lottery_enforce_constraints",
        description="""AI推理防护 - 对AI生成的投注方案进行硬性约束验证

在AI给出任何投注建议后，必须调用此工具对方案进行约束检查。
检查15条内置约束(C001-C015)，FATAL级别违规将导致方案被拒绝。

验证内容：
- 选项有效性 (C001): 选项是否属于该玩法
- 串关场次上限 (C002): 混合过关≤8场，比分≤4场
- 单场重复限制 (C003): 同一场比赛不能出现在多个串关位置
- 赔率范围 (C004): 赔率必须在合理范围内
- 资金限额 (C005): 单注≤1万（理论），单日≤1万
- 混合过关 (C006): 仅SPF/RQSPF/ZJQ/BQC互混，BF不能混
- 比分格式 (C007): 必须为X:Y格式
- 让球盘口 (C008): 让球盘口必须存在
- 单关限制 (C009): 单关仅限SPF/RQSPF/ZJQ/BQC
- 资金比例 (C010): 单注≤总资金10%
- 日亏损上限 (C011): 不超日止损线
- 串关多样性 (C012): 不全是同一玩法
- 赔率异动 (C013): 检测赔率偏离市场
- 伤停检查 (C014): 检查是否有主力伤停
- 赔率可用性 (C015): 赔率不为空

Use when: 任何投注建议生成后，必须调用此工具验证。
约束力: 这是整个系统最高优先级的保护机制，AI必须遵守。
如果approved为false，AI必须拒绝该方案并重新推理。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_enforce_constraints(
        bet_proposal: str, ctx: Context
    ) -> str:
        from lottery_mcp.rules.constraint_compiler import enforce_constraints
        import json as _json
        try:
            proposal = _json.loads(bet_proposal) if isinstance(bet_proposal, str) else bet_proposal
        except _json.JSONDecodeError:
            proposal = {}
        result = enforce_constraints(proposal)
        return _to_json(result)

    @mcp.tool(
        name="lottery_check_bankroll_health",
        description="""资金健康检查 - 全面评估资金状态

检查维度：
- 回撤率: 是否超过最大回撤上限
- 日亏损: 是否触发日止损线
- 连续亏损: 是否触发强制冷却期
- 资金利用率: 当前资金是否足够支持投注计划

返回：
- healthy: 资金是否健康
- can_continue: 是否可以继续投注
- issues: 致命问题列表
- warnings: 警告列表
- drawdown_pct: 回撤百分比
- total_pnl: 总盈亏

Use when: 每次投注前、每日开始前、制定投注计划时。
如果can_continue为false，必须停止所有投注活动。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_check_bankroll_health(
        bankroll: float,
        initial_bankroll: float,
        daily_pnl: float = 0.0,
        weekly_pnl: float = 0.0,
        consecutive_losses: int = 0,
        ctx: Context = None,
    ) -> str:
        from lottery_mcp.rules.guardrails import check_bankroll_health
        result = check_bankroll_health(
            bankroll=bankroll,
            initial_bankroll=initial_bankroll,
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl,
            consecutive_losses=consecutive_losses,
        )
        return _to_json(result)

    @mcp.tool(
        name="lottery_check_match_deadline",
        description="""比赛截止检查 - 检查比赛是否已过投注截止时间

竞彩通常在比赛开始前5分钟停止销售。
此工具检查指定比赛是否还能投注。

返回：
- can_bet: 是否还能投注
- match_time: 比赛时间
- deadline: 投注截止时间
- minutes_remaining: 剩余分钟数
- reason: 不能投注的原因

Use when: 在生成投注单前，检查所有涉及比赛是否还能投注。
如果can_bet为false，该比赛不能包含在投注方案中。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_check_match_deadline(
        match_time: str, ctx: Context = None
    ) -> str:
        from lottery_mcp.rules.guardrails import check_match_deadline
        result = check_match_deadline(match_time)
        return _to_json(result)
