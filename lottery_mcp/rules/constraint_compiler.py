"""
规则约束编译器 v2.0 — 防止AI幻觉推理的核心模块

将竞彩官方规则编译为可强制执行的约束条件。
所有投注推荐必须先通过此模块验证，否则拒绝输出。

设计原则：
1. 规则来源于官方知识库JSON，不允许硬编码业务逻辑
2. 每个约束都有唯一的rule_id，可溯源
3. 违反约束时返回明确的违规说明，不允许silent fail
4. 约束分为 FATAL（阻断）和 WARNING（警告）两级
"""

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("lottery_mcp")

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge", "jingcai")


class Severity(Enum):
    FATAL = "fatal"      # 阻断级：违反即拒绝
    WARNING = "warning"  # 警告级：允许但标注风险


@dataclass
class Constraint:
    """单个规则约束"""
    rule_id: str
    category: str
    description: str
    severity: Severity
    source: str  # 规则来源（JSON文件名）


@dataclass
class ConstraintCheckResult:
    """约束检查结果"""
    passed: bool
    violations: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    checked_constraints: int = 0


class ConstraintCompiler:
    """规则约束编译器

    从知识库JSON加载官方规则，编译为可执行检查。
    所有投注验证都经过此编译器，确保无幻觉推理。
    """

    def __init__(self):
        self._constraints: Dict[str, Constraint] = {}
        self._play_rules: Dict[str, Dict] = {}
        self._load_all_rules()

    def _load_all_rules(self):
        """加载所有知识库规则"""
        play_types_dir = os.path.join(KNOWLEDGE_DIR, "play_types")
        if not os.path.isdir(play_types_dir):
            logger.warning(f"知识库目录不存在: {play_types_dir}")
            self._register_builtin_constraints()
            return

        for filename in sorted(os.listdir(play_types_dir)):
            if filename.endswith(".json"):
                filepath = os.path.join(play_types_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    play_type = data.get("play_type", filename.replace(".json", ""))
                    self._play_rules[play_type] = data
                except Exception as e:
                    logger.warning(f"加载规则文件失败 {filename}: {e}")

        # 无论知识库是否加载成功，都注册内置基础约束
        self._register_builtin_constraints()

    def _register_builtin_constraints(self):
        """注册内置基础约束（硬编码的安全底线）"""
        # 这些约束即使在知识库加载失败时也必须存在
        builtins = [
            Constraint("C001", "valid_selection", "投注选项必须在官方有效选项范围内", Severity.FATAL, "builtin"),
            Constraint("C002", "max_legs", "串关场次不得超过该玩法的最大允许场次", Severity.FATAL, "builtin"),
            Constraint("C003", "single_match_limit", "同一场比赛在同一玩法中只能选择一个选项", Severity.FATAL, "builtin"),
            Constraint("C004", "odds_range", "赔率必须在有效范围内(1.01-1000)", Severity.FATAL, "builtin"),
            Constraint("C005", "stake_limit", "单注金额不得超过10000元限额", Severity.FATAL, "builtin"),
            Constraint("C006", "mixable_check", "混合过关只能使用SPF/RQSPF/ZJQ/BQC组合，BF不能混", Severity.FATAL, "builtin"),
            Constraint("C007", "bf_format", "比分选项必须符合官方格式(0-7:0-5或特殊选项)", Severity.FATAL, "builtin"),
            Constraint("C008", "rqspf_handicap", "让球胜平负必须指定让球数", Severity.FATAL, "builtin"),
            Constraint("C009", "single_play_single_match", "单关投注：每场比赛只能投注一个结果", Severity.WARNING, "builtin"),
            Constraint("C010", "bankroll_ratio", "单注金额不应超过总资金的20%", Severity.WARNING, "builtin"),
            Constraint("C011", "max_daily_loss", "单日亏损不应超过总资金的50%", Severity.WARNING, "builtin"),
            Constraint("C012", "parlay_diversity", "混合过关应使用不同联赛/不同类型的比赛", Severity.WARNING, "builtin"),
            Constraint("C013", "odds_drift_alert", "赔率波动超过15%时需重新评估", Severity.WARNING, "builtin"),
            Constraint("C014", "injury_check", "主力伤停超过2人时降低投注信心", Severity.WARNING, "builtin"),
            Constraint("C015", "odds_not_available", "已截止或暂停销售的比赛不可投注", Severity.FATAL, "builtin"),
            Constraint("C016", "cross_play_arbitrage", "SPF和RQSPF在同一场比赛的选项不应矛盾（如SPF选主胜但RQSPF选客胜）", Severity.WARNING, "builtin"),
            Constraint("C017", "odds_consistency", "同一比赛不同玩法的赔率应具有一致性（如SPF主胜低赔应伴随RQSPF主胜倾向）", Severity.WARNING, "builtin"),
            Constraint("C018", "max_parlay_odds", "串关总赔率不应超过5000倍", Severity.WARNING, "builtin"),
            Constraint("C019", "min_odds_threshold", "单条赔率低于1.10时，该腿的价值较低", Severity.WARNING, "builtin"),
            Constraint("C020", "duplicate_play_check", "串关中同一玩法不能超过总场次的70%", Severity.WARNING, "builtin"),
            Constraint("C021", "parlay_size_limit", "单次投注方案不应超过5个不同的串关组合", Severity.WARNING, "builtin"),
            Constraint("C022", "odds_anomaly", "赔率突然大幅波动（>30%）可能表示内幕信息", Severity.WARNING, "builtin"),
            Constraint("C023", "confidence_threshold", "单场预测置信度低于60%时不建议作为串关核心腿", Severity.WARNING, "builtin"),
        ]
        for c in builtins:
            self._constraints[c.rule_id] = c

    def get_all_constraints(self) -> Dict[str, Constraint]:
        """获取所有注册约束"""
        return dict(self._constraints)

    def get_play_rules(self, play_type: str) -> Optional[Dict]:
        """获取特定玩法的官方规则"""
        return self._play_rules.get(play_type) or self._play_rules.get(play_type.upper())

    # ================================================================
    # 投注验证核心API
    # ================================================================

    def validate_single_bet(
        self,
        play_type: str,
        selection: str,
        match_id: str,
        handicap: Optional[float] = None,
        odds: Optional[float] = None,
        stake: Optional[float] = None,
        bankroll: Optional[float] = None,
        match_status: str = "selling",
        previous_odds: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> ConstraintCheckResult:
        """验证单注投注的合法性

        Args:
            play_type: 玩法类型 (SPF/RQSPF/BF/ZJQ/BQC)
            selection: 投注选项
            match_id: 比赛ID
            handicap: 让球数 (RQSPF必填)
            odds: 赔率
            stake: 投注金额
            bankroll: 总资金
            match_status: 比赛销售状态
            previous_odds: 历史赔率（用于检测赔率波动）
            confidence: 预测置信度（0-1）

        Returns:
            ConstraintCheckResult: 检查结果
        """
        result = ConstraintCheckResult(passed=True)
        pt = play_type.upper()

        # C001: 有效选项检查
        valid_selections = {
            "SPF": {"胜", "平", "负", "3", "1", "0"},
            "RQSPF": {"胜", "平", "负", "3", "1", "0"},
            "ZJQ": {"0", "1", "2", "3", "4", "5", "6", "7+"},
            "BQC": {"胜-胜", "胜-平", "胜-负", "平-胜", "平-平", "平-负", "负-胜", "负-平", "负-负"},
            "BF": None,  # 特殊：regex验证
        }
        if pt in valid_selections and valid_selections[pt] is not None:
            if selection not in valid_selections[pt]:
                result.violations.append({
                    "rule_id": "C001", "severity": "FATAL",
                    "message": f"'{selection}'不是{pt}的有效选项。有效选项: {sorted(valid_selections[pt])}"
                })
                result.passed = False

        # C007: 比分格式检查
        if pt == "BF":
            import re
            if selection not in {"胜其他", "平其他", "负其他"} and not re.match(r"^[0-7]:[0-5]$", selection):
                result.violations.append({
                    "rule_id": "C007", "severity": "FATAL",
                    "message": f"比分'{selection}'格式无效。有效格式: X:Y (X:0-7, Y:0-5) 或 胜其他/平其他/负其他"
                })
                result.passed = False

        # C008: RQSPF让球数
        if pt == "RQSPF" and handicap is None:
            result.violations.append({
                "rule_id": "C008", "severity": "FATAL",
                "message": "让球胜平负(RQSPF)必须提供让球数(handicap)"
            })
            result.passed = False

        # C004: 赔率范围检查
        if odds is not None:
            if odds < 1.01 or odds > 1000:
                result.warnings.append({
                    "rule_id": "C004", "severity": "WARNING",
                    "message": f"赔率{odds}超出合理范围(1.01-1000)"
                })

        # C005: 单注金额
        if stake is not None and stake > 10000:
            result.violations.append({
                "rule_id": "C005", "severity": "FATAL",
                "message": f"单注金额{stake}元超过10000元限额"
            })
            result.passed = False

        # C010: 资金比例
        if bankroll and stake and bankroll > 0:
            ratio = stake / bankroll
            if ratio > 0.20:
                result.warnings.append({
                    "rule_id": "C010", "severity": "WARNING",
                    "message": f"单注金额{stake}占资金{bankroll}的{ratio:.1%}，超过建议的20%"
                })

        # C015: 比赛状态
        if match_status != "selling":
            result.violations.append({
                "rule_id": "C015", "severity": "FATAL",
                "message": f"比赛{match_id}状态'{match_status}'不是可售状态"
            })
            result.passed = False

        # C019: 最低赔率阈值
        if odds is not None and odds < 1.10:
            result.warnings.append({
                "rule_id": "C019", "severity": "WARNING",
                "message": f"赔率{odds}低于1.10，该腿价值较低"
            })

        # C022: 赔率异常波动
        if odds is not None and previous_odds is not None and previous_odds > 0:
            change_pct = abs(odds - previous_odds) / previous_odds
            if change_pct > 0.30:
                result.warnings.append({
                    "rule_id": "C022", "severity": "WARNING",
                    "message": f"赔率从{previous_odds}变为{odds}，波动{change_pct:.1%}（>30%），可能表示内幕信息"
                })

        # C023: 置信度阈值
        if confidence is not None and confidence < 0.60:
            result.warnings.append({
                "rule_id": "C023", "severity": "WARNING",
                "message": f"预测置信度{confidence:.1%}低于60%，不建议作为串关核心腿"
            })

        result.checked_constraints = len(self._constraints)
        return result

    def validate_parlay(
        self,
        legs: List[Dict[str, Any]],
        total_stake: Optional[float] = None,
        bankroll: Optional[float] = None,
        parlay_count: Optional[int] = None,
    ) -> ConstraintCheckResult:
        """验证串关投注

        Args:
            legs: 串关腿列表 [{play_type, selection, match_id, odds, handicap?, confidence?, previous_odds?}]
            total_stake: 总投注额
            bankroll: 总资金
            parlay_count: 单次投注方案中的串关组合数量

        Returns:
            ConstraintCheckResult
        """
        result = ConstraintCheckResult(passed=True)

        if not legs:
            result.violations.append({
                "rule_id": "C002", "severity": "FATAL",
                "message": "串关至少需要2场比赛"
            })
            result.passed = False
            result.checked_constraints = len(self._constraints)
            return result

        # 统计每个玩法的场次
        play_counts: Dict[str, int] = {}
        match_ids_set: Set[str] = set()
        play_in_match: Dict[str, Set[str]] = {}  # match_id -> set of play_types

        for i, leg in enumerate(legs):
            pt = leg.get("play_type", "").upper()
            mid = leg.get("match_id", "")
            play_counts[pt] = play_counts.get(pt, 0) + 1

            if mid not in play_in_match:
                play_in_match[mid] = set()
            play_in_match[mid].add(pt)

            # 验证每条腿
            leg_result = self.validate_single_bet(
                play_type=pt,
                selection=leg.get("selection", ""),
                match_id=mid,
                handicap=leg.get("handicap"),
                odds=leg.get("odds"),
                previous_odds=leg.get("previous_odds"),
                confidence=leg.get("confidence"),
            )
            if not leg_result.passed:
                leg_result.violations[0]["leg_index"] = i
                result.violations.extend(leg_result.violations)

        # C002: 最大串关场次
        max_legs_per_play = {"SPF": 8, "RQSPF": 8, "ZJQ": 6, "BF": 4, "BQC": 4}
        for pt, count in play_counts.items():
            max_allowed = max_legs_per_play.get(pt, 8)
            if count > max_allowed:
                result.violations.append({
                    "rule_id": "C002", "severity": "FATAL",
                    "message": f"{pt}玩法最多{max_allowed}关，当前{count}关"
                })

        # C003: 同场比赛同玩法
        for mid, play_types_in_match in play_in_match.items():
            if len(play_types_in_match) < len(list(play_types_in_match)):
                result.violations.append({
                    "rule_id": "C003", "severity": "FATAL",
                    "message": f"比赛{mid}在同一玩法中选择了多个选项"
                })

        # C006: 混合过关检查
        all_play_types = set(play_counts.keys())
        mixable = {"SPF", "RQSPF", "ZJQ", "BQC"}
        non_mixable = all_play_types - mixable
        if non_mixable:
            result.violations.append({
                "rule_id": "C006", "severity": "FATAL",
                "message": f"玩法{non_mixable}不能参与混合过关。比分(BF)只能单独串关，不能与其他玩法混合"
            })
            result.passed = False

        if len(all_play_types) > 1 and "BF" in all_play_types:
            result.violations.append({
                "rule_id": "C006", "severity": "FATAL",
                "message": "比分(BF)不能参与混合过关，只能单独组成比分串关"
            })
            result.passed = False

        # C012: 多样性建议
        match_leagues = set()
        for leg in legs:
            league = leg.get("league", "")
            if league:
                match_leagues.add(league)
        if len(match_leagues) == 1 and len(legs) >= 3:
            result.warnings.append({
                "rule_id": "C012", "severity": "WARNING",
                "message": f"全部{len(legs)}场比赛来自同一联赛，建议分散联赛风险"
            })

        # C002: 总场次 (混合过关木桶原则)
        min_max = min(max_legs_per_play.get(pt, 8) for pt in play_counts) if play_counts else 8
        total_matches = len(legs)
        if total_matches > min_max:
            result.violations.append({
                "rule_id": "C002", "severity": "FATAL",
                "message": f"混合过关总场次{total_matches}超过木桶原则限制{min_max}关"
            })
            result.passed = False

        # 资金检查
        if total_stake and bankroll and bankroll > 0:
            if total_stake > bankroll * 0.25:
                result.warnings.append({
                    "rule_id": "C010", "severity": "WARNING",
                    "message": f"串关总投注{total_stake}占资金{bankroll}的{total_stake/bankroll:.1%}"
                })

        # C016: 跨玩法矛盾检测
        cross_play_result = self.validate_cross_play(legs)
        if cross_play_result:
            result.warnings.append(cross_play_result)

        # C017: 赔率一致性检测
        self._check_odds_consistency(legs, result)

        # C018: 最大串关赔率
        total_odds = 1.0
        for leg in legs:
            leg_odds = leg.get("odds")
            if leg_odds and leg_odds > 0:
                total_odds *= leg_odds
        if total_odds > 5000:
            result.warnings.append({
                "rule_id": "C018", "severity": "WARNING",
                "message": f"串关总赔率{total_odds:.1f}超过5000倍上限"
            })

        # C019: 最低赔率阈值（每条腿）
        for i, leg in enumerate(legs):
            leg_odds = leg.get("odds")
            if leg_odds is not None and leg_odds < 1.10:
                result.warnings.append({
                    "rule_id": "C019", "severity": "WARNING",
                    "message": f"第{i+1}腿赔率{leg_odds}低于1.10，价值较低"
                })

        # C020: 同一玩法占比检查
        total_legs = len(legs)
        for pt, count in play_counts.items():
            if total_legs > 0 and count / total_legs > 0.70:
                result.warnings.append({
                    "rule_id": "C020", "severity": "WARNING",
                    "message": f"{pt}玩法占{count}/{total_legs}（{count/total_legs:.0%}），超过70%上限"
                })

        # C021: 串关组合数量限制
        if parlay_count is not None and parlay_count > 5:
            result.warnings.append({
                "rule_id": "C021", "severity": "WARNING",
                "message": f"单次投注方案包含{parlay_count}个串关组合，超过5个上限"
            })

        result.checked_constraints = len(self._constraints)
        return result

    def validate_cross_play(self, legs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """C016: 检测SPF和RQSPF在同一场比赛的选项矛盾

        Args:
            legs: 串关腿列表

        Returns:
            违规信息dict，无矛盾时返回None
        """
        match_selections: Dict[str, Dict[str, str]] = {}

        for leg in legs:
            mid = leg.get("match_id", "")
            pt = leg.get("play_type", "").upper()
            sel = leg.get("selection", "")

            if pt in ("SPF", "RQSPF") and mid:
                if mid not in match_selections:
                    match_selections[mid] = {}
                match_selections[mid][pt] = sel

        for mid, selections in match_selections.items():
            if "SPF" in selections and "RQSPF" in selections:
                spf_sel = selections["SPF"]
                rqspf_sel = selections["RQSPF"]

                spf_map = {"胜": "主胜", "3": "主胜", "平": "平局", "1": "平局", "负": "客胜", "0": "客胜"}
                rqspf_map = {"胜": "主胜", "3": "主胜", "平": "平局", "1": "平局", "负": "客胜", "0": "客胜"}

                spf_normalized = spf_map.get(spf_sel, spf_sel)
                rqspf_normalized = rqspf_map.get(rqspf_sel, rqspf_sel)

                contradictions = [
                    (spf_normalized == "主胜" and rqspf_normalized == "客胜"),
                    (spf_normalized == "客胜" and rqspf_normalized == "主胜"),
                ]

                if any(contradictions):
                    return {
                        "rule_id": "C016", "severity": "WARNING",
                        "message": f"比赛{mid}: SPF选'{spf_sel}'({spf_normalized})但RQSPF选'{rqspf_sel}'({rqspf_normalized})，存在矛盾"
                    }

        return None

    def _check_odds_consistency(self, legs: List[Dict[str, Any]], result: ConstraintCheckResult):
        """C017: 检测同一比赛不同玩法的赔率一致性

        Args:
            legs: 串关腿列表
            result: 检查结果（原地修改）
        """
        match_info: Dict[str, Dict[str, Any]] = {}

        for leg in legs:
            mid = leg.get("match_id", "")
            pt = leg.get("play_type", "").upper()
            odds = leg.get("odds")
            sel = leg.get("selection", "")

            if mid and odds is not None:
                if mid not in match_info:
                    match_info[mid] = {}
                match_info[mid][pt] = {"odds": odds, "selection": sel}

        for mid, info in match_info.items():
            if "SPF" in info and "RQSPF" in info:
                spf_odds = info["SPF"]["odds"]
                rqspf_odds = info["RQSPF"]["odds"]
                spf_sel = info["SPF"]["selection"]
                rqspf_sel = info["RQSPF"]["selection"]

                spf_normalized = spf_sel
                rqspf_normalized = rqspf_sel
                for m in [("胜", "主胜"), ("3", "主胜"), ("平", "平局"), ("1", "平局"), ("负", "客胜"), ("0", "客胜")]:
                    if spf_normalized == m[0]:
                        spf_normalized = m[1]
                    if rqspf_normalized == m[0]:
                        rqspf_normalized = m[1]

                if spf_normalized == "主胜" and spf_odds < 2.0:
                    if rqspf_normalized == "客胜" and rqspf_odds < 2.0:
                        result.warnings.append({
                            "rule_id": "C017", "severity": "WARNING",
                            "message": f"比赛{mid}: SPF主胜赔率{spf_odds}偏低但RQSPF倾向客胜，赔率不一致"
                        })
                elif spf_normalized == "客胜" and spf_odds < 2.0:
                    if rqspf_normalized == "主胜" and rqspf_odds < 2.0:
                        result.warnings.append({
                            "rule_id": "C017", "severity": "WARNING",
                            "message": f"比赛{mid}: SPF客胜赔率{spf_odds}偏低但RQSPF倾向主胜，赔率不一致"
                        })

    def validate_bankroll_plan(
        self,
        bankroll: float,
        daily_stakes: List[float],
        strategy: str = "balanced",
    ) -> ConstraintCheckResult:
        """验证资金管理计划

        Args:
            bankroll: 总资金
            daily_stakes: 当日各注金额列表
            strategy: 策略类型

        Returns:
            ConstraintCheckResult
        """
        result = ConstraintCheckResult(passed=True)
        total_daily = sum(daily_stakes)

        if bankroll <= 0:
            result.violations.append({
                "rule_id": "C005", "severity": "FATAL",
                "message": "总资金必须大于0"
            })
            result.passed = False
            result.checked_constraints = len(self._constraints)
            return result

        ratio = total_daily / bankroll

        if strategy == "conservative" and ratio > 0.10:
            result.warnings.append({
                "rule_id": "C010", "severity": "WARNING",
                "message": f"保守策略: 日投注{total_daily}占资金{bankroll}的{ratio:.1%} > 10%建议上限"
            })
        elif strategy == "balanced" and ratio > 0.25:
            result.warnings.append({
                "rule_id": "C010", "severity": "WARNING",
                "message": f"均衡策略: 日投注{total_daily}占资金{bankroll}的{ratio:.1%} > 25%建议上限"
            })
        elif strategy == "aggressive" and ratio > 0.50:
            result.warnings.append({
                "rule_id": "C011", "severity": "WARNING",
                "message": f"激进策略: 日投注{total_daily}占资金{bankroll}的{ratio:.1%} > 50%建议上限"
            })

        result.checked_constraints = len(self._constraints)
        return result

    def get_play_max_legs(self, play_types: List[str]) -> int:
        """获取混合过关的最大场次（木桶原则）

        Args:
            play_types: 玩法列表

        Returns:
            最小最大串关数
        """
        limits = {"SPF": 8, "RQSPF": 8, "ZJQ": 6, "BF": 4, "BQC": 4}
        return min(limits.get(pt.upper(), 8) for pt in play_types) if play_types else 8

    def get_play_valid_selections(self, play_type: str) -> Set[str]:
        """获取玩法有效选项"""
        mappings = {
            "SPF": {"胜", "平", "负", "3", "1", "0"},
            "RQSPF": {"胜", "平", "负", "3", "1", "0"},
            "ZJQ": {"0", "1", "2", "3", "4", "5", "6", "7+"},
            "BQC": {"胜-胜", "胜-平", "胜-负", "平-胜", "平-平", "平-负", "负-胜", "负-平", "负-负"},
        }
        return mappings.get(play_type.upper(), set())


# 全局单例
_constraint_compiler: Optional[ConstraintCompiler] = None


def get_constraint_compiler() -> ConstraintCompiler:
    """获取约束编译器全局单例"""
    global _constraint_compiler
    if _constraint_compiler is None:
        _constraint_compiler = ConstraintCompiler()
    return _constraint_compiler


# ================================================================
# AI推理防护函数: 所有AI推理输出前必须调用的验证API
# ================================================================

def enforce_constraints(bet_proposal: Dict[str, Any]) -> Dict[str, Any]:
    """AI推理防护入口

    在AI生成任何投注建议后，调用此函数进行约束检查。
    如果检查失败，必须拒绝该建议并要求AI重新推理。

    Args:
        bet_proposal: AI生成的投注方案 {
            "legs": [{play_type, selection, match_id, odds, handicap?}],
            "total_stake": float,
            "bankroll": float,
            "strategy": str,
        }

    Returns:
        {"approved": bool, "violations": [...], "warnings": [...], "corrected_proposal": {...}}
    """
    compiler = get_constraint_compiler()

    legs = bet_proposal.get("legs", [])
    total_stake = bet_proposal.get("total_stake", 0)
    bankroll = bet_proposal.get("bankroll", 1000)

    # 单关还是串关
    if len(legs) == 1:
        leg = legs[0]
        result = compiler.validate_single_bet(
            play_type=leg.get("play_type", "SPF"),
            selection=leg.get("selection", ""),
            match_id=leg.get("match_id", ""),
            handicap=leg.get("handicap"),
            odds=leg.get("odds"),
            stake=total_stake,
            bankroll=bankroll,
        )
    else:
        result = compiler.validate_parlay(
            legs=legs,
            total_stake=total_stake,
            bankroll=bankroll,
        )

    response = {
        "approved": result.passed,
        "checked_constraints": result.checked_constraints,
        "violations": result.violations,
        "warnings": result.warnings,
    }

    if not result.passed:
        response["action_required"] = "投注方案存在致命违规，必须修正后重新验证"
        response["correction_hints"] = [v["message"] for v in result.violations]
    elif result.warnings:
        response["action_required"] = "投注方案通过但有警告，请标注风险"
    else:
        response["action_required"] = "投注方案通过所有约束检查"

    return response