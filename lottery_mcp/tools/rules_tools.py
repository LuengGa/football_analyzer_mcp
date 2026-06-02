"""
MCP Server Rules Tools - Rule engine validation tools.
集成完整规则引擎，支持混合过关验证和奖金计算。
按彩种区分规则（竞彩 vs 北单）。
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mcp.server.fastmcp import Context
from pydantic import ValidationError

from .helpers import raise_tool_error, _to_json, _validate_stake
from lottery_mcp.models import (
    CalculateBonusInput,
    ExplainRuleInput,
    QueryRulesInput,
    ValidateBetInput,
    ValidateMixedParlayInput,
    ValidateParlayInput,
)
from .output_schemas import (
    BonusCalculationOutput,
    QueryRulesOutput,
    ValidateBetOutput,
    ValidateParlayOutput,
)

logger = logging.getLogger("lottery_mcp")


# ============================================================
# 玩法名称映射（英文缩写 <-> 中文名称）
# ============================================================

PLAY_TYPE_EN_TO_CN = {
    "SPF": "胜平负",
    "RQSPF": "让球胜平负",
    "BF": "比分",
    "JQS": "总进球",
    "ZJQ": "总进球",
    "BQC": "半全场",
    "HHGG": "混合过关",
    # 北单
    "SXDS": "上下单双",
    "SFGG": "胜负过关",
    # 传统足彩
    "SFC14": "胜负彩14场",
    "RX9": "任选9场",
    "BQC6": "6场半全场",
    "JQ4": "4场进球",
}

PLAY_TYPE_CN_TO_EN = {v: k for k, v in PLAY_TYPE_EN_TO_CN.items()}


def _resolve_play_type_cn(play_type: str) -> str:
    """将玩法类型统一转为中文名称"""
    normalized = _normalize_play_type(play_type)
    if normalized in PLAY_TYPE_EN_TO_CN:
        return PLAY_TYPE_EN_TO_CN[normalized]
    return play_type  # 已经是中文名


def _normalize_play_type(play_type: str) -> str:
    """统一玩法类型缩写，消除别名冗余

    JQS -> ZJQ（总进球统一使用 ZJQ）
    """
    ALIASES = {
        "JQS": "ZJQ",
        "胜平负": "SPF",
        "让球胜平负": "RQSPF",
        "比分": "BF",
        "总进球": "ZJQ",
        "半全场": "BQC",
        "混合过关": "MIXED",
    }
    return ALIASES.get(play_type, play_type)


# ============================================================
# 串关类型常量
# ============================================================

# 竞彩单关
JINGCAI_SINGLE = ["1x1"]

# 竞彩M串1
JINGCAI_MX1 = ["2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1"]

# 竞彩32种官方M串N组合（不含单关）
JINGCAI_MXN = [
    "2x2", "2x3",
    "3x3", "3x4", "3x7",
    "4x4", "4x5", "4x6", "4x11", "4x14", "4x15",
    "5x5", "5x6", "5x10", "5x16", "5x20", "5x26", "5x31",
    "6x6", "6x7", "6x15", "6x20", "6x22", "6x35", "6x42", "6x50", "6x57",
    "7x7", "7x8", "7x21", "7x35", "7x120", "7x127",
    "8x8", "8x9", "8x28", "8x56", "8x70", "8x247", "8x255",
]

# 竞彩所有允许的串关类型（含单关和M串1）
JINGCAI_ALL_TYPES = JINGCAI_SINGLE + JINGCAI_MX1 + JINGCAI_MXN

# 北单胜平负57种（含单关）
BEIDAN_SPF_TYPES = [
    "单场", "2x1", "2x3",
    "3x1", "3x3", "3x4", "3x6", "3x7",
    "4x1", "4x4", "4x5", "4x6", "4x10", "4x11", "4x14", "4x15",
    "5x1", "5x5", "5x6", "5x10", "5x15", "5x16", "5x20", "5x25", "5x26", "5x30", "5x31",
    "6x1", "6x6", "6x7", "6x15", "6x20", "6x21", "6x22", "6x35", "6x41", "6x42", "6x50", "6x56", "6x57", "6x62", "6x63",
    "7x1", "7x7", "7x8", "7x21", "7x35", "7x120", "7x127",
    "8x1", "8x8", "8x9", "8x28", "8x56", "8x70", "8x247", "8x255",
]

# 北单胜负过关19种
BEIDAN_SFGG_TYPES = [
    "3x1", "4x1", "4x5", "5x1", "5x6", "5x16", "6x1", "6x7", "6x22", "6x42",
    "7x1", "8x1", "9x1", "10x1", "11x1", "12x1", "13x1", "14x1", "15x1",
]


# ============================================================
# 混合过关规则常量
# ============================================================

# 可混合的玩法列表（竞彩）
MIXABLE_PLAYS_JINGCAI = ["胜平负", "让球胜平负", "总进球", "比分", "半全场"]

# 可混合的玩法列表（北单）
MIXABLE_PLAYS_BEIDAN = ["胜平负", "上下单双", "总进球", "比分", "半全场"]


# ============================================================
# 各玩法最大串关数（按彩种区分）
# ============================================================

# 竞彩各玩法最大串关数（传统M串N）
MAX_LEGS_BY_PLAY_JINGCAI = {
    "胜平负": 8,
    "让球胜平负": 8,
    "总进球": 6,
    "比分": 6,   # 竞彩比分最多6关（官方规则）
    "半全场": 4,  # 竞彩半全场最多4关（官方规则）
}

# 北单各玩法最大串关数
MAX_LEGS_BY_PLAY_BEIDAN = {
    "胜平负": 8,       # 传统M串N 8关, 自由过关 15关
    "上下单双": 6,
    "总进球": 6,
    "比分": 3,         # 北单比分最多3关
    "半全场": 6,       # 北单半全场最多6关
    "胜负过关": 15,    # 胜负过关最少3场, 最多15关
}


# ============================================================
# 奖金封顶规则（按场次数）
# ============================================================

BONUS_CAP_BY_LEGS = {
    1: 100000,       # 单关 10 万
    2: 200000,       # 2-3 关 20 万
    3: 200000,
    4: 500000,       # 4-5 关 50 万
    5: 500000,
    # 6 关及以上 100 万
}


# ============================================================
# 返还率（从 JSON 知识库加载）
# ============================================================

RETURN_RATES = {
    "竞彩足球": 0.70,
    "北京单场": 0.65,
    "传统足彩": 0.65,
}

# 税金规则
TAX_THRESHOLD = 10000.0  # 1 万元起征
TAX_RATE = 0.20          # 20%


# ============================================================
# Rules Engine (Enhanced)
# ============================================================

class RulesEngine:
    """彩票规则引擎（增强版，按彩种区分规则）"""

    # 玩法限额配置（按彩种区分）
    PLAY_LIMITS = {
        "竞彩足球": {
            "SPF": {"min": 2, "max": 99999},
            "RQSPF": {"min": 2, "max": 99999},
            "BF": {"min": 2, "max": 99999},
            "ZJQ": {"min": 2, "max": 99999},
            "BQC": {"min": 2, "max": 99999},
        },
        "北京单场": {
            "SPF": {"min": 2, "max": 99999},
            "RQSPF": {"min": 2, "max": 99999},
            "BF": {"min": 2, "max": 99999},
            "ZJQ": {"min": 2, "max": 99999},
            "BQC": {"min": 2, "max": 99999},
            "SXDS": {"min": 2, "max": 99999},
            "SFGG": {"min": 2, "max": 99999},
        },
    }

    # 串关限制（按彩种区分）
    PARLAY_LIMITS = {
        "竞彩足球": {
            "max_matches": 8,
            "min_matches": 1,  # 竞彩支持单关
            "max_multiplier": 50,
            "min_multiplier": 2,
            "single_ticket_limit": 6000,
            "allowed_types": JINGCAI_ALL_TYPES,
        },
        "北京单场": {
            "max_matches": 15,
            "min_matches": 1,  # 北单支持单关
            "max_multiplier": 99,
            "min_multiplier": 2,
            "single_ticket_limit": 20000,
            "allowed_types": BEIDAN_SPF_TYPES,
            "sfgg_types": BEIDAN_SFGG_TYPES,
            "sfgg_min_matches": 3,
        },
    }

    def _is_beidan(self, lottery_type: str) -> bool:
        """判断是否为北京单场"""
        return lottery_type in ("北京单场",)

    def _get_parlay_limits(self, lottery_type: str) -> Dict[str, Any]:
        """获取串关限制配置"""
        return self.PARLAY_LIMITS.get(lottery_type, self.PARLAY_LIMITS["竞彩足球"])

    def _get_max_legs_by_play(self, lottery_type: str) -> Dict[str, int]:
        """获取各玩法最大串关数"""
        if self._is_beidan(lottery_type):
            return MAX_LEGS_BY_PLAY_BEIDAN
        return MAX_LEGS_BY_PLAY_JINGCAI

    def _get_mixable_plays(self, lottery_type: str) -> List[str]:
        """获取可混合的玩法列表"""
        if self._is_beidan(lottery_type):
            return MIXABLE_PLAYS_BEIDAN
        return MIXABLE_PLAYS_JINGCAI

    def _get_allowed_types(self, lottery_type: str, play_type: Optional[str] = None) -> List[str]:
        """获取允许的串关类型"""
        limits = self._get_parlay_limits(lottery_type)
        if self._is_beidan(lottery_type) and play_type:
            pt_cn = _resolve_play_type_cn(play_type)
            if pt_cn == "胜负过关":
                return limits.get("sfgg_types", BEIDAN_SFGG_TYPES)
        return limits["allowed_types"]

    def get_return_rate(self, lottery_type: str) -> float:
        """获取返还率"""
        return RETURN_RATES.get(lottery_type, 0.70)

    def validate_bet(self, bet: ValidateBetInput) -> Dict[str, Any]:
        """验证单注投注"""
        # 兼容 dict 传入
        if isinstance(bet, dict):
            try:
                bet = ValidateBetInput(**bet)
            except ValidationError as e:
                errors = []
                for err in e.errors():
                    field = err.get("loc", ("unknown",))[-1]
                    msg = err.get("msg", "验证失败")
                    errors.append(f"字段 '{field}' 验证失败: {msg}")
                return {
                    "valid": False,
                    "errors": errors,
                    "warnings": None,
                    "bet_summary": None,
                }
        errors = []
        warnings = []

        lottery_type = bet.lottery_type
        normalized_play = _normalize_play_type(bet.play_type)

        # 验证玩法
        lottery_limits = self.PLAY_LIMITS.get(lottery_type, {})
        if normalized_play not in lottery_limits:
            errors.append(f"不支持的玩法: {bet.play_type}")

        # P1-3: 验证 selection 合法性（白名单）
        # 别名映射：将常见别名转换为标准选项名
        SELECTION_ALIASES = {
            "平局": "平",
            "主胜": "胜",
            "客胜": "负",
            "让平": "平",
            "让胜": "胜",
            "让负": "负",
        }
        normalized_selection = SELECTION_ALIASES.get(bet.selection, bet.selection)

        VALID_SELECTIONS = {
            "SPF": ["胜", "平", "负", "主胜", "客胜"],
            "RQSPF": ["胜", "平", "负", "让球主胜", "让球平", "让球客胜", "主胜", "客胜",
                      "让球主胜(+1)", "让球主胜(+2)", "让球主胜(+3)", "让球主胜(-1)", "让球主胜(-2)", "让球主胜(-3)",
                      "让球平(+1)", "让球平(-1)", "让球客胜(+1)", "让球客胜(+2)", "让球客胜(+3)",
                      "让球客胜(-1)", "让球客胜(-2)", "让球客胜(-3)"],
            "BF": ["1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2",
                   "5:0", "5:1", "5:2", "胜其他",
                   "0:0", "1:1", "2:2", "3:3", "平其他",
                   "0:1", "0:2", "1:2", "0:3", "1:3", "2:3",
                   "0:4", "1:4", "2:4", "0:5", "1:5", "2:5", "负其他"],
            "ZJQ": ["0", "1", "2", "3", "4", "5", "6", "7+"],
            "BQC": ["胜-胜", "胜-平", "胜-负", "平-胜", "平-平", "平-负",
                    "负-胜", "负-平", "负-负",
                    "胜胜", "胜平", "胜负", "平胜", "平平", "平负",
                    "负胜", "负平", "负负"],
        }
        allowed_selections = VALID_SELECTIONS.get(normalized_play)
        if allowed_selections and normalized_selection not in allowed_selections:
            errors.append(
                f"不合法的投注选项: '{bet.selection}'，"
                f"玩法 {normalized_play} 的合法选项: {allowed_selections}"
            )

        # 验证限额（使用 _validate_stake 统一验证）
        play_limit = lottery_limits.get(normalized_play, {"min": 2, "max": 100000})
        stake_valid, stake_msg = _validate_stake(
            bet.stake, min_stake=play_limit["min"], max_stake=play_limit["max"]
        )
        if not stake_valid:
            errors.append(stake_msg)

        # 验证赔率
        if bet.odds < 1.01:
            errors.append("赔率不能低于 1.01")
        if bet.odds > 1000:
            errors.append("赔率不能超过 1000")

        # 让球类型校验
        if bet.play_type == "RQSPF":
            if bet.handicap is None:
                errors.append("让球胜平负玩法必须提供让球数(handicap)")
            else:
                # 竞彩足球让球数必须为整数
                if lottery_type == "竞彩足球":
                    if bet.handicap != int(bet.handicap):
                        errors.append(
                            f"竞彩足球让球数必须为整数，当前值: {bet.handicap}"
                        )
                    elif bet.handicap == 0:
                        warnings.append("让球数为0时，让球胜平负等同于胜平负")
                # 北京单场让球数可为小数（如-1.5, -0.5, +0.5）
                elif lottery_type == "北京单场":
                    if bet.handicap == 0:
                        warnings.append("让球数为0时，让球胜平负等同于胜平负")

        # 计算预期奖金
        expected_bonus = bet.stake * bet.odds

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "bet_summary": {
                "match_id": bet.match_id,
                "play_type": bet.play_type,
                "play_type_cn": _resolve_play_type_cn(bet.play_type),
                "selection": bet.selection,
                "odds": bet.odds,
                "stake": bet.stake,
                "expected_bonus": round(expected_bonus, 2),
                "lottery_type": lottery_type,
            }
        }

    def validate_parlay(self, parlay=None, *, bets=None, parlay_type=None,
                         total_stake=None, lottery_type=None) -> Dict[str, Any]:
        """验证串关投注（自动检测混合过关）

        支持三种调用方式:
        1. validate_parlay(ValidateParlayInput(...))
        2. validate_parlay({"bets": [...], "parlay_type": "2x1", ...})
        3. validate_parlay(bets=[...], parlay_type="2x1", ...)
        """
        # 兼容关键字参数传入
        if parlay is None and bets is not None:
            parlay = {
                "bets": bets,
                "parlay_type": parlay_type or "2x1",
                "total_stake": total_stake or 2,
                "lottery_type": lottery_type or "竞彩足球",
            }
        # 兼容 dict 传入
        if isinstance(parlay, dict):
            parlay = ValidateParlayInput(**parlay)
        # 确保 bets 都是 ValidateBetInput 实例
        if parlay.bets:
            parlay.bets = [ValidateBetInput(**b) if isinstance(b, dict) else b for b in parlay.bets]
        errors = []
        warnings = []

        lottery_type = parlay.lottery_type
        limits = self._get_parlay_limits(lottery_type)
        bet_count = len(parlay.bets)

        # 验证场次数量
        if bet_count < limits["min_matches"]:
            errors.append(f"串关至少需要 {limits['min_matches']} 场")
        if bet_count > limits["max_matches"]:
            errors.append(f"串关最多支持 {limits['max_matches']} 场")

        # P1-A1: 比分/总进球/半全场不支持单关（1x1），只支持2串1及以上
        NO_SINGLE_PLAYS = {"比分", "总进球", "半全场"}
        if parlay.parlay_type == "1x1" and bet_count == 1:
            play_types_in_parlay = set()
            for bet in parlay.bets:
                pt_cn = _resolve_play_type_cn(bet.play_type)
                play_types_in_parlay.add(pt_cn)
            disallowed = play_types_in_parlay & NO_SINGLE_PLAYS
            if disallowed:
                errors.append(
                    f"玩法 {', '.join(disallowed)} 不支持单关（1x1），"
                    f"至少需要2串1"
                )

        # 验证串关类型（支持自由过关格式）
        allowed_types = self._get_allowed_types(lottery_type)
        normalized_parlay_type = self._normalize_parlay_type(parlay.parlay_type, bet_count)
        if normalized_parlay_type != parlay.parlay_type:
            # 自由过关被规范化为等效的 MxN 格式
            parlay.parlay_type = normalized_parlay_type
        if normalized_parlay_type not in allowed_types:
            errors.append(f"不支持的串关类型: {parlay.parlay_type}，"
                          f"允许的类型: {allowed_types}")

        # P2-F3: 验证 M串N 的注数 N <= C(M, k)（组合数上限）
        try:
            parts = normalized_parlay_type.split("x")
            if len(parts) == 2:
                m = int(parts[0])
                n = int(parts[1])
                if m != bet_count and "x1" not in normalized_parlay_type:
                    warnings.append(
                        f"串关类型 {normalized_parlay_type} 表示 {m} 场组合，"
                        f"但当前选择了 {bet_count} 场"
                    )
                # 验证 N 不超过最大可能组合数 C(M, M-1) = M
                # 对于 M串N，N 的理论最大值 = sum(C(M,k) for k in range(2, M+1))
                max_possible = sum(self._combination(m, k) for k in range(2, m + 1))
                if n > max_possible and n > 1:
                    errors.append(
                        f"串关类型 {normalized_parlay_type} 的注数 {n} 超过"
                        f"{m} 场最大可能组合数 {max_possible}"
                    )
        except (ValueError, IndexError):
            pass

        # P0-02: 验证单票限额
        single_ticket_limit = limits["single_ticket_limit"]
        if parlay.total_stake > single_ticket_limit:
            errors.append(f"单票投注金额不能超过 {single_ticket_limit:,} 元")

        # 验证总投注额最低（使用 PLAY_LIMITS 中的 min）
        min_stake = 2  # 默认最低投注
        if parlay.bets:
            first_play = _normalize_play_type(parlay.bets[0].play_type)
            lottery_limits = self.PLAY_LIMITS.get(lottery_type, {})
            min_stake = lottery_limits.get(first_play, {}).get("min", 2)
        if parlay.total_stake < min_stake:
            errors.append(f"总投注金额不能低于 {min_stake} 元")

        # 检测是否为混合过关
        play_types_used = set()
        match_play_map: Dict[str, set] = {}

        for bet in parlay.bets:
            pt_cn = _resolve_play_type_cn(bet.play_type)
            play_types_used.add(pt_cn)

            if bet.match_id not in match_play_map:
                match_play_map[bet.match_id] = set()
            match_play_map[bet.match_id].add(pt_cn)

        is_mixed = len(play_types_used) >= 2

        # 混合过关专项校验
        if is_mixed:
            mixed_validation = self._validate_mixed_parlay_rules(
                play_types_used, match_play_map, bet_count, lottery_type
            )
            errors.extend(mixed_validation["errors"])
            warnings.extend(mixed_validation["warnings"])
        else:
            mixed_validation = None

        # 计算串关赔率
        total_odds = 1.0
        for bet in parlay.bets:
            total_odds *= bet.odds

        expected_bonus = parlay.total_stake * total_odds

        # 验证单场
        bet_results = []
        for bet in parlay.bets:
            result = self.validate_bet(bet)
            bet_results.append(result)
            if not result["valid"]:
                errors.extend([f"[{bet.match_id}] {e}" for e in result["errors"]])

        result = {
            "valid": len(errors) == 0,
            "errors": list(set(errors)),
            "warnings": warnings,
            "is_mixed_parlay": is_mixed,
            "parlay_summary": {
                "match_count": bet_count,
                "parlay_type": parlay.parlay_type,
                "play_types_used": list(play_types_used),
                "total_odds": round(total_odds, 2),
                "total_stake": parlay.total_stake,
                "expected_bonus": round(expected_bonus, 2),
                "single_ticket_limit": single_ticket_limit,
                "lottery_type": lottery_type,
                "label": "混合过关" if is_mixed else (
                    list(play_types_used)[0] if play_types_used else "串关"
                ),
            },
            "bet_details": bet_results,
        }

        if mixed_validation:
            result["mixed_parlay_detail"] = mixed_validation

        return result

    def validate_mixed_parlay(self, params: ValidateMixedParlayInput) -> Dict[str, Any]:
        """混合过关专项验证

        三大约束：
        1. 同一场比赛不可选择多个玩法
        2. 不同运动项目不能混合（本系统仅足球，自动通过）
        3. 串关数以所选玩法中限制最低者为准（木桶原则）
        """
        errors = []
        warnings = []

        lottery_type = params.lottery_type
        limits = self._get_parlay_limits(lottery_type)
        bet_count = len(params.bets)

        # 收集玩法和场次映射
        play_types_used = set()
        match_play_map: Dict[str, set] = {}

        for bet in params.bets:
            pt_cn = _resolve_play_type_cn(bet.play_type)
            play_types_used.add(pt_cn)

            if bet.match_id not in match_play_map:
                match_play_map[bet.match_id] = set()
            match_play_map[bet.match_id].add(pt_cn)

        # 混合过关专项校验
        mixed_validation = self._validate_mixed_parlay_rules(
            play_types_used, match_play_map, bet_count, lottery_type
        )
        errors.extend(mixed_validation["errors"])
        warnings.extend(mixed_validation["warnings"])

        # 验证单票限额
        single_ticket_limit = limits["single_ticket_limit"]
        if params.total_stake > single_ticket_limit:
            errors.append(f"单票投注金额不能超过 {single_ticket_limit:,} 元")

        # 验证各场投注
        bet_results = []
        for bet in params.bets:
            result = self.validate_bet(bet)
            bet_results.append(result)
            if not result["valid"]:
                errors.extend([f"[{bet.match_id}] {e}" for e in result["errors"]])

        # 计算串关赔率
        total_odds = 1.0
        for bet in params.bets:
            total_odds *= bet.odds

        expected_bonus = params.total_stake * total_odds

        return {
            "valid": len(errors) == 0,
            "errors": list(set(errors)),
            "warnings": warnings,
            "is_mixed_parlay": len(play_types_used) >= 2,
            "parlay_summary": {
                "match_count": bet_count,
                "parlay_type": params.parlay_type,
                "play_types_used": list(play_types_used),
                "total_odds": round(total_odds, 2),
                "total_stake": params.total_stake,
                "expected_bonus": round(expected_bonus, 2),
                "single_ticket_limit": single_ticket_limit,
                "lottery_type": lottery_type,
            },
            "mixed_parlay_detail": mixed_validation,
            "bet_details": bet_results,
        }

    def _validate_mixed_parlay_rules(
        self,
        play_types_used: set,
        match_play_map: Dict[str, set],
        match_count: int,
        lottery_type: str = "竞彩足球",
    ) -> Dict[str, Any]:
        """混合过关三大规则校验（内部方法）"""
        errors = []
        warnings = []

        max_legs_by_play = self._get_max_legs_by_play(lottery_type)
        mixable_plays = self._get_mixable_plays(lottery_type)

        # 规则1：同一场次不能混合不同玩法
        for match_id, plays in match_play_map.items():
            if len(plays) > 1:
                errors.append(
                    f"同场多玩法违规: 场次[{match_id}]混合了{list(plays)}，"
                    f"同一场比赛不可选择多个玩法"
                )

        # 规则2：检查玩法是否可混合
        for pt in play_types_used:
            if pt not in mixable_plays:
                errors.append(f"玩法[{pt}]不支持混合过关")

        # 规则3：木桶原则 - 最大串关数 = 各玩法最大串关数的最小值
        max_parlays = []
        for pt in play_types_used:
            mp = max_legs_by_play.get(pt)
            if mp is None:
                errors.append(f"未知玩法[{pt}]的最大串关数")
            else:
                max_parlays.append(mp)

        bucket_limit = None
        limiting_plays = []

        if max_parlays:
            bucket_limit = min(max_parlays)
            limiting_plays = [
                pt for pt, mp in zip(play_types_used, max_parlays)
                if mp == bucket_limit
            ]

            if match_count > bucket_limit:
                errors.append(
                    f"木桶原则违规: 所选玩法{list(play_types_used)}中，"
                    f"{limiting_plays}最大仅支持{bucket_limit}关，"
                    f"当前{match_count}场超出限制"
                )
            elif match_count == bucket_limit:
                warnings.append(
                    f"木桶原则提示: 已达{limiting_plays}的最大串关数{bucket_limit}关"
                )

        return {
            "errors": errors,
            "warnings": warnings,
            "play_types_used": list(play_types_used),
            "match_count": match_count,
            "bucket_limit": bucket_limit,
            "limiting_plays": limiting_plays,
            "max_legs_by_play": {
                pt: max_legs_by_play.get(pt) for pt in play_types_used
            },
            "lottery_type": lottery_type,
        }

    def calculate_bonus(self, bets: List[ValidateBetInput],
                        parlay_type: str,
                        results: Optional[Dict[str, str]] = None,
                        lottery_type: str = "竞彩足球",
                        multiplier: int = 1) -> Dict[str, Any]:
        """计算奖金（增强版，按彩种区分奖金公式，含税金和封顶）

        P0-01 奖金公式:
        - 竞彩单关: 2元 x 浮动奖金额 x 倍数
        - 竞彩过关: 2元 x 各场固定奖金连乘 x 倍数（不乘返还率）
        - 北单: 2元 x SP值连乘 x 65% x 倍数

        P1-09 税金按单注计算:
        - 单注奖金 = 总奖金 / 总注数
        - 单注 >= 1万元起征20%税
        """
        # 兼容 dict 传入
        if bets and isinstance(bets[0], dict):
            bets = [ValidateBetInput(**b) if isinstance(b, dict) else b for b in bets]

        is_beidan = self._is_beidan(lottery_type)
        bet_count = len(bets)

        # 计算各场赔率（SP值）
        odds_list = [bet.odds for bet in bets]

        # 计算SP连乘
        sp_product = 1.0
        for odds in odds_list:
            sp_product *= odds

        # P0-03: 倍数范围校验
        limits = self._get_parlay_limits(lottery_type)
        min_mult = limits["min_multiplier"]
        max_mult = limits["max_multiplier"]
        if multiplier < min_mult:
            return {
                "status": "error",
                "message": f"倍数不能低于 {min_mult} 倍",
                "multiplier": multiplier,
                "valid_range": [min_mult, max_mult],
            }
        if multiplier > max_mult:
            return {
                "status": "error",
                "message": f"倍数不能超过 {max_mult} 倍",
                "multiplier": multiplier,
                "valid_range": [min_mult, max_mult],
            }

        # 判断是否为单关
        is_single = (parlay_type == "1x1") or (bet_count == 1)

        # 计算总注数（M串N的注数由串关类型决定）
        total_bets = self._calculate_parlay_bets(parlay_type, bet_count)

        # 计算总投注额 = 2元 x 注数 x 倍数
        total_stake = 2 * total_bets * multiplier

        # P0-02: 单票限额校验
        single_ticket_limit = limits["single_ticket_limit"]
        if total_stake > single_ticket_limit:
            return {
                "status": "error",
                "message": f"单票金额 {total_stake:.0f} 元超过限额 {single_ticket_limit:,} 元",
                "total_stake": total_stake,
                "single_ticket_limit": single_ticket_limit,
            }

        # P0-01: 按彩种计算奖金
        if is_beidan:
            # 北单: 2元 x SP值连乘 x 65% x 倍数
            single_bonus = 2 * sp_product * 0.65 * multiplier
            gross_bonus = single_bonus * total_bets
            bonus_formula = "2元 x SP值连乘 x 65% x 倍数"
        elif is_single:
            # 竞彩单关: 2元 x 浮动奖金额 x 倍数
            single_bonus = 2 * sp_product * multiplier
            gross_bonus = single_bonus * total_bets
            bonus_formula = "2元 x 浮动奖金额 x 倍数"
        else:
            # 竞彩过关: 2元 x 各场固定奖金连乘 x 倍数（不乘返奖率）
            single_bonus = 2 * sp_product * multiplier
            gross_bonus = single_bonus * total_bets
            bonus_formula = "2元 x 各场固定奖金连乘 x 倍数"

        # 如果没有结果，返回预期奖金
        if not results:
            # P1-09: 税金按单注计算
            per_bet_bonus = gross_bonus / total_bets if total_bets > 0 else 0
            net_bonus, tax = self._calculate_tax_per_bet(gross_bonus, total_bets)

            return {
                "status": "simulation",
                "lottery_type": lottery_type,
                "parlay_type": parlay_type,
                "match_count": bet_count,
                "multiplier": multiplier,
                "total_bets": total_bets,
                "total_stake": total_stake,
                "sp_product": round(sp_product, 4),
                "single_bonus": round(single_bonus, 2),
                "gross_bonus": round(gross_bonus, 2),
                "per_bet_bonus": round(per_bet_bonus, 2),
                "tax": round(tax, 2),
                "net_bonus": round(net_bonus, 2),
                "return_rate": self.get_return_rate(lottery_type),
                "bonus_formula": bonus_formula,
                "message": "未提供比赛结果，返回预期奖金",
            }

        # 检查是否中奖
        won = True
        won_bets = []
        lost_bets = []

        for bet in bets:
            match_result = results.get(bet.match_id)
            if match_result and match_result == bet.selection:
                won_bets.append(bet.match_id)
            else:
                lost_bets.append(bet.match_id)
                won = False

        if won:
            # 封顶检查
            cap = self._get_bonus_cap(bet_count)
            capped = gross_bonus > cap
            actual_payout = min(gross_bonus, cap) if capped else gross_bonus

            # P1-09: 税金按单注计算
            per_bet_bonus = actual_payout / total_bets if total_bets > 0 else 0
            actual_net, actual_tax = self._calculate_tax_per_bet(actual_payout, total_bets)

            return {
                "status": "won",
                "lottery_type": lottery_type,
                "parlay_type": parlay_type,
                "match_count": bet_count,
                "multiplier": multiplier,
                "total_bets": total_bets,
                "total_stake": total_stake,
                "sp_product": round(sp_product, 4),
                "single_bonus": round(single_bonus, 2),
                "gross_bonus": round(gross_bonus, 2),
                "per_bet_bonus": round(per_bet_bonus, 2),
                "tax": round(actual_tax, 2),
                "net_bonus": round(actual_net, 2),
                "profit": round(actual_net - total_stake, 2),
                "capped": capped,
                "cap_amount": cap,
                "won_matches": won_bets,
                "bonus_formula": bonus_formula,
                "return_rate": self.get_return_rate(lottery_type),
            }
        else:
            return {
                "status": "lost",
                "lottery_type": lottery_type,
                "total_stake": total_stake,
                "lost_matches": lost_bets,
                "bonus": 0,
                "profit": -total_stake,
            }

    @staticmethod
    def _combination(n: int, k: int) -> int:
        """计算组合数 C(n, k)"""
        if k < 0 or k > n:
            return 0
        if k == 0 or k == n:
            return 1
        # 使用较小的 k 值优化计算
        k = min(k, n - k)
        result = 1
        for i in range(k):
            result = result * (n - i) // (i + 1)
        return result

    def _normalize_parlay_type(self, parlay_type: str, match_count: int) -> str:
        """规范化串关类型，支持自由过关格式

        自由过关 = 所有M场全部组合（如3场自由过关 = 3串1+3串2+3串3）
        格式: "M串N" 或 "M自由过关"

        Args:
            parlay_type: 串关类型字符串
            match_count: 场次数

        Returns:
            规范化后的串关类型（MxN 格式）
        """
        # 检查 "M自由过关" 格式
        if "自由过关" in parlay_type:
            try:
                m = int(parlay_type.replace("自由过关", "").replace("串", "").strip())
                # 自由过关的注数 = sum(C(m, k) for k in 2..m) + C(m, 1)（含单关）
                # 但通常自由过关不含单关，从2串1开始
                total_bets = sum(self._combination(m, k) for k in range(2, m + 1))
                return f"{m}x{total_bets}"
            except (ValueError, IndexError):
                pass

        # 检查 "M串N" 中文格式
        if "串" in parlay_type and "x" not in parlay_type:
            try:
                parts = parlay_type.split("串")
                m = int(parts[0].strip())
                n = int(parts[1].strip())
                return f"{m}x{n}"
            except (ValueError, IndexError):
                pass

        return parlay_type

    def _calculate_parlay_bets(self, parlay_type: str, match_count: int) -> int:
        """根据串关类型计算注数

        Args:
            parlay_type: 串关类型，如 "3x4", "1x1"
            match_count: 场次数

        Returns:
            注数
        """
        # 单关
        if parlay_type == "1x1" or parlay_type == "单场":
            return 1

        # M串1
        if "x1" in parlay_type and parlay_type != "1x1":
            return 1

        # 解析 MxN 格式
        try:
            parts = parlay_type.split("x")
            if len(parts) == 2:
                m = int(parts[0])
                n = int(parts[1])
                return n
        except (ValueError, IndexError):
            pass

        # 默认：M串N 的注数就是 N
        return 1

    def _calculate_tax_per_bet(self, gross_bonus: float, total_bets: int) -> Tuple[float, float]:
        """P1-09: 按单注计算税金

        单注奖金 = 总奖金 / 总注数
        单注 >= 1万元起征20%税

        Args:
            gross_bonus: 总奖金
            total_bets: 总注数

        Returns:
            (税后奖金, 税金)
        """
        if total_bets <= 0:
            return gross_bonus, 0.0

        per_bet_bonus = gross_bonus / total_bets

        if per_bet_bonus >= TAX_THRESHOLD:
            tax = gross_bonus * TAX_RATE
            return gross_bonus - tax, tax
        return gross_bonus, 0.0

    def _calculate_tax(self, gross_bonus: float) -> tuple:
        """计算税后奖金（旧方法，保留兼容）"""
        if gross_bonus >= TAX_THRESHOLD:
            tax = gross_bonus * TAX_RATE
            return gross_bonus - tax, tax
        return gross_bonus, 0.0

    def _get_bonus_cap(self, legs: int) -> float:
        """获取奖金封顶金额"""
        if legs >= 6:
            return 1000000
        return BONUS_CAP_BY_LEGS.get(legs, 1000000)

    def query_mixed_parlay_rules(self, play_types: List[str],
                                  lottery_type: str = "竞彩足球") -> Dict[str, Any]:
        """查询混合过关规则

        Args:
            play_types: 玩法列表（英文缩写或中文名）
            lottery_type: 彩种类型

        Returns:
            混合过关规则详情
        """
        # 统一转为中心名称
        play_types_cn = [_resolve_play_type_cn(pt) for pt in play_types]

        max_legs_by_play = self._get_max_legs_by_play(lottery_type)
        mixable_plays = self._get_mixable_plays(lottery_type)

        # 检查各玩法是否可混合
        mixable_status = {}
        for pt in play_types_cn:
            mixable_status[pt] = pt in mixable_plays

        all_mixable = all(mixable_status.values())

        # 木桶原则计算
        max_legs_list = []
        for pt in play_types_cn:
            ml = max_legs_by_play.get(pt)
            max_legs_list.append({"play_type": pt, "max_legs": ml})
            if ml is None:
                mixable_status[pt] = False
                all_mixable = False

        valid_max_legs = [ml["max_legs"] for ml in max_legs_list if ml["max_legs"] is not None]
        bucket_limit = min(valid_max_legs) if valid_max_legs else 0
        limiting_plays = [
            ml["play_type"] for ml in max_legs_list
            if ml["max_legs"] == bucket_limit
        ]

        # 封顶金额
        cap = self._get_bonus_cap(bucket_limit)

        # 获取串关限制
        limits = self._get_parlay_limits(lottery_type)

        return {
            "lottery_type": lottery_type,
            "play_types_requested": play_types,
            "play_types_resolved": play_types_cn,
            "all_mixable": all_mixable,
            "mixable_status": mixable_status,
            "max_legs_by_play": max_legs_list,
            "bucket_limit": bucket_limit,
            "limiting_plays": limiting_plays,
            "bonus_cap": cap,
            "return_rate": self.get_return_rate(lottery_type),
            "tax_threshold": TAX_THRESHOLD,
            "tax_rate": TAX_RATE,
            "single_ticket_limit": limits["single_ticket_limit"],
            "multiplier_range": [limits["min_multiplier"], limits["max_multiplier"]],
            "max_matches": limits["max_matches"],
            "restrictions": [
                "同一场比赛不可选择多个玩法",
                "不同运动项目不能混合",
                f"串关数以所选玩法中限制最低者为准（当前: {bucket_limit}关）",
            ],
        }

    def query_rules(self, rule_type: str, lottery_type: str,
                    play_type: Optional[str] = None) -> Dict[str, Any]:
        """查询规则"""
        limits = self._get_parlay_limits(lottery_type)
        max_legs_by_play = self._get_max_legs_by_play(lottery_type)
        mixable_plays = self._get_mixable_plays(lottery_type)

        if rule_type == "limits":
            return {
                "rule_type": "limits",
                "lottery_type": lottery_type,
                "play_limits": self.PLAY_LIMITS.get(lottery_type, {}),
                "parlay_limits": limits,
                "single_ticket_limit": limits["single_ticket_limit"],
                "multiplier_range": [limits["min_multiplier"], limits["max_multiplier"]],
            }
        elif rule_type == "parlay":
            allowed_types = self._get_allowed_types(lottery_type, play_type)
            return {
                "rule_type": "parlay",
                "lottery_type": lottery_type,
                "limits": limits,
                "supported_types": allowed_types,
                "max_matches": limits["max_matches"],
                "min_matches": limits["min_matches"],
                "single_ticket_limit": limits["single_ticket_limit"],
                "multiplier_range": [limits["min_multiplier"], limits["max_multiplier"]],
                "mixed_parlay": {
                    "mixable_plays": mixable_plays,
                    "max_legs_by_play": max_legs_by_play,
                    "restrictions": [
                        "同一场比赛不可选择多个玩法",
                        "不同运动项目不能混合",
                        "串关数以所选玩法中限制最低者为准（木桶原则）",
                    ],
                },
            }
        elif rule_type == "play":
            plays = self.PLAY_LIMITS.get(lottery_type, {})
            return {
                "rule_type": "play",
                "lottery_type": lottery_type,
                "available_plays": list(plays.keys()),
                "play_details": plays,
                "max_legs_by_play": max_legs_by_play,
            }
        elif rule_type == "bonus":
            return {
                "rule_type": "bonus",
                "lottery_type": lottery_type,
                "return_rate": self.get_return_rate(lottery_type),
                "tax_rate": TAX_RATE,
                "tax_threshold": TAX_THRESHOLD,
                "bonus_cap_by_legs": BONUS_CAP_BY_LEGS,
                "bonus_formula": {
                    "竞彩单关": "2元 x 浮动奖金额 x 倍数",
                    "竞彩过关": "2元 x 各场固定奖金连乘 x 倍数",
                    "北京单场": "2元 x SP值连乘 x 65% x 倍数",
                },
            }
        elif rule_type == "mixed_parlay":
            return {
                "rule_type": "mixed_parlay",
                "lottery_type": lottery_type,
                "mixable_plays": mixable_plays,
                "max_legs_by_play": max_legs_by_play,
                "restrictions": [
                    "同一场比赛不可选择多个玩法",
                    "不同运动项目不能混合",
                    "串关数以所选玩法中限制最低者为准（木桶原则）",
                ],
            }
        else:
            return {
                "rule_type": rule_type,
                "error": "未知的规则类型",
            }

    # ============================================================
    # 规则解释知识库
    # ============================================================

    RULE_EXPLANATIONS: Dict[str, Dict[str, Dict[str, Any]]] = {
        "混合过关": {
            "竞彩足球": {
                "rule_description": (
                    "混合过关是指在一次串关投注中，同时选择多种不同的玩法进行组合。"
                    "例如，你可以将「胜平负」和「总进球」混合在同一张串关彩票中。"
                    "这样可以灵活搭配不同玩法的优势，提高中奖概率。"
                ),
                "specific_values": {
                    "可混合的玩法": "胜平负、让球胜平负、总进球、比分、半全场",
                    "最大串关数（木桶原则）": "以所选玩法中限制最低者为准",
                    "各玩法最大串关数": {
                        "胜平负": "8关",
                        "让球胜平负": "8关",
                        "总进球": "6关",
                        "比分": "6关",
                        "半全场": "6关",
                    },
                    "返还率": "70%",
                },
                "common_mistakes": [
                    "同一场比赛选择多个玩法（如同时选胜平负和比分），这是不允许的",
                    "忽略了木桶原则：如果混合了「比分」（最多6关）和「胜平负」（最多8关），"
                    "那么整个串关最多只能6关，而不是8关",
                    "误以为所有玩法都可以混合，实际上只有上述5种玩法支持混合过关",
                ],
                "examples": {
                    "correct": (
                        "正确示例：选择3场比赛，第1场玩「胜平负」，第2场玩「总进球」，"
                        "第3场玩「半全场」，组成3串1。木桶限制为 min(8,6,6)=6关，"
                        "3场未超限，合规。"
                    ),
                    "wrong": (
                        "错误示例：同一场比赛既选「胜平负」又选「比分」，"
                        "违反「同一场比赛不可选择多个玩法」规则。"
                    ),
                },
            },
            "北京单场": {
                "rule_description": (
                    "北京单场同样支持混合过关，允许在串关中组合不同玩法。"
                    "与竞彩足球的区别在于：可混合的玩法中用「上下单双」替代了「让球胜平负」，"
                    "且各玩法的最大串关数有所不同。"
                ),
                "specific_values": {
                    "可混合的玩法": "胜平负、上下单双、总进球、比分、半全场",
                    "最大串关数（木桶原则）": "以所选玩法中限制最低者为准",
                    "各玩法最大串关数": {
                        "胜平负": "8关（传统M串N）/ 15关（自由过关）",
                        "上下单双": "6关",
                        "总进球": "6关",
                        "比分": "3关",
                        "半全场": "6关",
                    },
                    "返还率": "65%",
                },
                "common_mistakes": [
                    "北单的「比分」玩法最多只能3关（比竞彩的6关更严格），混合时容易忽略",
                    "北单的「胜负过关」玩法不支持与其他玩法混合",
                    "混淆北单和竞彩的返还率：北单为65%，竞彩为70%",
                ],
                "examples": {
                    "correct": (
                        "正确示例：选择2场比赛，第1场玩「胜平负」，第2场玩「上下单双」，"
                        "组成2串1。木桶限制为 min(8,6)=6关，2场未超限，合规。"
                    ),
                    "wrong": (
                        "错误示例：混合「比分」（最多3关）+「胜平负」+「总进球」+「半全场」"
                        "共5场，超过「比分」的3关限制，违规。"
                    ),
                },
            },
        },
        "单票限额": {
            "竞彩足球": {
                "rule_description": (
                    "单票限额是指一张彩票（一注投注方案）的最大投注金额。"
                    "这是为了控制单次投注风险，防止过度投注。"
                    "总投注额 = 2元（单注基础金额）x 注数 x 倍数，"
                    "计算结果不能超过单票限额。"
                ),
                "specific_values": {
                    "单票最高限额": "6,000 元",
                    "单注最低金额": "2 元",
                    "倍数范围": "2-50 倍",
                    "计算公式": "总投注额 = 2元 x 注数 x 倍数",
                },
                "common_mistakes": [
                    "误以为单票限额是指单场投注金额，实际上是整张彩票的总金额",
                    "M串N组合的注数容易算错：例如3串4有4注，4串11有11注，"
                    "注数乘以倍数再乘以2元才是总投注额",
                    "使用高倍数时容易超限：例如4串11选50倍，"
                    "总投注额 = 2 x 11 x 50 = 1,100元，未超限；"
                    "但8串247选50倍，总投注额 = 2 x 247 x 50 = 24,700元，远超6,000元限额",
                ],
                "examples": {
                    "correct": (
                        "正确示例：3串1，10倍，总投注额 = 2 x 1 x 10 = 20 元，未超限。"
                    ),
                    "wrong": (
                        "错误示例：4串11，50倍，总投注额 = 2 x 11 x 50 = 1,100 元，未超限。"
                        "但如果选8串247，50倍，总投注额 = 2 x 247 x 50 = 24,700 元，超过6,000元限额。"
                    ),
                },
            },
            "北京单场": {
                "rule_description": (
                    "北京单场的单票限额与竞彩足球不同，限额更高。"
                    "同样，总投注额 = 2元 x 注数 x 倍数，不能超过限额。"
                ),
                "specific_values": {
                    "单票最高限额": "20,000 元",
                    "单注最低金额": "2 元",
                    "倍数范围": "2-99 倍",
                    "计算公式": "总投注额 = 2元 x 注数 x 倍数",
                },
                "common_mistakes": [
                    "北单的倍数上限是99倍（竞彩为50倍），高倍数更容易超限",
                    "北单胜负过关最多15场，注数计算更复杂",
                ],
                "examples": {
                    "correct": (
                        "正确示例：3串1，50倍，总投注额 = 2 x 1 x 50 = 100 元，未超限。"
                    ),
                    "wrong": (
                        "错误示例：8串255，99倍，总投注额 = 2 x 255 x 99 = 50,490 元，"
                        "超过20,000元限额。"
                    ),
                },
            },
        },
        "串关类型": {
            "竞彩足球": {
                "rule_description": (
                    "串关类型决定了投注的组合方式。常见的有："
                    "- M串1（如2串1、3串1）：所有场次必须全对才中奖，简单直接"
                    "- M串N（如3串4、4串11）：将M场比赛组合成N注不同的串关，"
                    "  不需要全对也能中奖，容错性更强"
                    "- 单关（1x1）：只选一场比赛，竞彩足球支持单关"
                    "竞彩足球共有35种串关类型（1种单关 + 7种M串1 + 32种M串N + 8种M串1 = 含单关共40种）。"
                ),
                "specific_values": {
                    "单关": "1x1（1种）",
                    "M串1": "2x1 ~ 8x1（7种）",
                    "M串N": "3x3, 3x4, 4x4~4x11, 5x5~5x26, 6x6~6x57, 7x7~7x120, 8x8~8x247（32种）",
                    "最多场次数": "8场",
                    "最少场次数": "1场（单关）",
                },
                "common_mistakes": [
                    "混淆M串1和M串N：3串1是1注（全对才中奖），3串4是4注（3场中猜对任意2场即可中奖1注）",
                    "误以为所有串关类型都可以用：比如2串2是不存在的，2场只能选2串1",
                    "M串N的注数计算：N就是注数，例如4串11就是11注，总投注额 = 2 x 11 x 倍数",
                ],
                "examples": {
                    "correct": (
                        "正确示例：选4场比赛，使用4串11（即4场中选3场的所有组合，共4注），"
                        "猜对3场即可中奖1注。"
                    ),
                    "wrong": (
                        "错误示例：选2场比赛想用2串2，但竞彩足球没有2串2这种类型。"
                        "2场只能选2串1。"
                    ),
                },
            },
            "北京单场": {
                "rule_description": (
                    "北京单场支持更多串关类型，分为胜平负玩法和胜负过关玩法两套体系。"
                    "胜平负玩法支持57种串关类型（含单关），胜负过关支持19种M串1类型。"
                ),
                "specific_values": {
                    "胜平负串关类型": "57种（含单关），如 单场、2x1、2x3、3x1~3x7、4x1~4x15 等",
                    "胜负过关串关类型": "19种，3x1 ~ 15x1",
                    "胜负过关最少场次": "3场",
                    "胜负过关最多场次": "15场",
                },
                "common_mistakes": [
                    "胜负过关至少需要3场，不能选2场或单关",
                    "北单的串关类型比竞彩更多，但不是所有类型都通用",
                    "胜负过关只能用M串1类型（3串1、4串1等），不支持M串N",
                ],
                "examples": {
                    "correct": (
                        "正确示例：胜负过关选5场比赛，使用5串1，全对才中奖。"
                    ),
                    "wrong": (
                        "错误示例：胜负过关选2场比赛，但胜负过关至少需要3场。"
                    ),
                },
            },
        },
        "奖金封顶": {
            "竞彩足球": {
                "rule_description": (
                    "奖金封顶是指一张彩票的最大可中奖金额。"
                    "即使计算出的理论奖金超过封顶值，实际也只能按封顶金额派奖。"
                    "封顶金额按串关的场次数（关数）分级设定，关数越多封顶越高。"
                ),
                "specific_values": {
                    "单关（1关）": "100,000 元（10万）",
                    "2-3关": "200,000 元（20万）",
                    "4-5关": "500,000 元（50万）",
                    "6关及以上": "1,000,000 元（100万）",
                },
                "common_mistakes": [
                    "高赔率串关容易触发封顶：例如8场低赔率串关，每场1.5倍赔率，"
                    "理论奖金可能超过100万，但实际只能拿到100万",
                    "封顶是按关数（场次数）而非按串关类型：4串11虽然11注，"
                    "但关数是4关，封顶仍为50万",
                    "税金在封顶之后计算：先封顶，再判断是否达到1万元起征点",
                ],
                "examples": {
                    "correct": (
                        "正确示例：3串1，投注2元，三场赔率分别为3.0、4.0、5.0，"
                        "理论奖金 = 2 x 3.0 x 4.0 x 5.0 = 120元，远低于20万封顶，不受影响。"
                    ),
                    "wrong": (
                        "注意示例：8串1，投注2元，每场赔率3.0，"
                        "理论奖金 = 2 x 3.0^8 = 13,122元，未超100万封顶。"
                        "但如果50倍投注，理论奖金 = 656,100元，仍未超100万。"
                        "若赔率更高则可能触发封顶。"
                    ),
                },
            },
            "北京单场": {
                "rule_description": (
                    "北京单场的奖金封顶规则与竞彩足球相同，按关数分级。"
                    "但由于北单返还率为65%（竞彩为70%），同等条件下理论奖金更低，"
                    "触发封顶的概率相对较小。"
                ),
                "specific_values": {
                    "单关（1关）": "100,000 元（10万）",
                    "2-3关": "200,000 元（20万）",
                    "4-5关": "500,000 元（50万）",
                    "6关及以上": "1,000,000 元（100万）",
                    "北单返还率": "65%",
                },
                "common_mistakes": [
                    "北单奖金公式含65%返还率：2元 x SP值连乘 x 65% x 倍数，"
                    "实际奖金比竞彩低",
                    "封顶金额与竞彩相同，但北单最多可串15场（竞彩8场），"
                    "15场串关更容易触发100万封顶",
                ],
                "examples": {
                    "correct": (
                        "正确示例：3串1，投注2元，三场赔率分别为3.0、4.0、5.0，"
                        "理论奖金 = 2 x 3.0 x 4.0 x 5.0 x 0.65 = 78元，未超封顶。"
                    ),
                    "wrong": (
                        "注意示例：15串1，每场赔率2.0，50倍投注，"
                        "理论奖金 = 2 x 2.0^15 x 0.65 x 50 = 2,124,903元，"
                        "超过100万封顶，实际只能获得100万元。"
                    ),
                },
            },
        },
        "税金": {
            "竞彩足球": {
                "rule_description": (
                    "彩票中奖需要缴纳个人所得税。税金按「单注奖金」计算，"
                    "而非按总奖金计算。单注奖金 = 总奖金 / 总注数，"
                    "当单注奖金达到或超过1万元时，对总奖金征收20%的个人所得税。"
                ),
                "specific_values": {
                    "起征点": "单注奖金 >= 10,000 元",
                    "税率": "20%",
                    "计算方式": "税金 = 总奖金 x 20%（当单注 >= 1万元时）",
                    "税后奖金": "总奖金 - 税金",
                },
                "common_mistakes": [
                    "起征点是按「单注」而非「总奖金」：如果总奖金10万元但注数有20注，"
                    "单注仅5,000元，未达起征点，不需要缴税",
                    "M串N的注数越多，单注奖金越低，越不容易达到起征点",
                    "税金是对总奖金征收20%，不是只对超过1万元的部分征税",
                ],
                "examples": {
                    "correct": (
                        "正确示例：2串1，投注2元，赔率连乘为8,000，"
                        "单注奖金 = 2 x 8,000 = 16,000元 >= 1万元，"
                        "需缴税：16,000 x 20% = 3,200元，税后到手 12,800元。"
                    ),
                    "wrong": (
                        "注意示例：4串11，投注2元，赔率连乘为5,000，"
                        "总奖金 = 2 x 5,000 x 11 = 110,000元，"
                        "但单注奖金 = 110,000 / 11 = 10,000元 >= 1万元，"
                        "需缴税：110,000 x 20% = 22,000元。"
                    ),
                },
            },
            "北京单场": {
                "rule_description": (
                    "北京单场的税金规则与竞彩足球完全相同："
                    "单注奖金 >= 1万元起征20%税。"
                    "但由于北单返还率为65%，同等条件下单注奖金更低，"
                    "达到起征点的门槛更高。"
                ),
                "specific_values": {
                    "起征点": "单注奖金 >= 10,000 元",
                    "税率": "20%",
                    "北单返还率": "65%",
                },
                "common_mistakes": [
                    "北单奖金已乘以65%返还率，所以更难达到1万元起征点",
                    "税金规则在竞彩和北单之间是一致的，没有区别",
                ],
                "examples": {
                    "correct": (
                        "正确示例：2串1，投注2元，赔率连乘为12,000，"
                        "北单单注奖金 = 2 x 12,000 x 0.65 = 15,600元 >= 1万元，"
                        "需缴税：15,600 x 20% = 3,120元，税后到手 12,480元。"
                    ),
                    "wrong": (
                        "注意示例：同样的赔率连乘12,000，"
                        "竞彩单注奖金 = 2 x 12,000 = 24,000元，"
                        "北单单注奖金 = 2 x 12,000 x 0.65 = 15,600元，"
                    ),
                },
            },
        },
        "让球规则": {
            "竞彩足球": {
                "rule_description": (
                    "让球胜平负（RQSPF）是竞彩足球的特色玩法。"
                    "官方会根据两队的实力差距设定让球数（如主队让1球、主队让2球等），"
                    "投注时需要将让球数加到实际比分中再判断胜负。"
                    "竞彩足球的让球数必须为整数（-1、-2、+1等），不能为小数。"
                ),
                "specific_values": {
                    "让球数范围": "整数，-10 到 +10",
                    "让球数格式": "必须为整数（如-1, -2, +1），不支持小数",
                    "让球方向": "正数表示主队让球，负数表示客队让球",
                    "让球数为0": "等同于普通胜平负",
                },
                "common_mistakes": [
                    "让球数为0时，让球胜平负的结果与胜平负完全相同，没有意义",
                    "竞彩足球不支持小数让球（如-1.5、-0.5），只有北京单场才支持",
                    "让球数是官方设定的，不是自己选的。投注时需要查看官方公布的让球数",
                    "让球胜平负可以与胜平负混合过关，但同一场比赛只能选其中一个",
                ],
                "examples": {
                    "correct": (
                        "正确示例：曼联 vs 利物浦，官方设定曼联让1球（+1）。"
                        "如果实际比分是1:1，加让球后为2:1，曼联让球胜。"
                    ),
                    "wrong": (
                        "错误示例：在竞彩足球中选择让球数为-1.5，"
                        "竞彩足球让球数必须为整数，小数让球仅北京单场支持。"
                    ),
                },
            },
            "北京单场": {
                "rule_description": (
                    "北京单场的让球规则与竞彩足球类似，但支持小数让球数"
                    "（如-1.5、-0.5、+0.5等），这是与竞彩足球的主要区别。"
                    "小数让球可以避免出现「走水」（退还本金）的情况。"
                ),
                "specific_values": {
                    "让球数范围": "-10 到 +10，支持整数和小数",
                    "小数让球": "支持（如-1.5, -0.5, +0.5, +1.5）",
                    "整数让球": "支持（如-1, -2, +1）",
                    "让球数为0": "等同于普通胜平负",
                },
                "common_mistakes": [
                    "小数让球不会出现走水：例如让1.5球，实际只赢1球，算让球负",
                    "北单的让球数范围更灵活，但同样由官方设定",
                ],
                "examples": {
                    "correct": (
                        "正确示例：北京单场，主队让1.5球。"
                        "实际比分2:1，主队只赢了1球，不够1.5球，算让球负。"
                    ),
                    "wrong": (
                        "注意示例：如果主队让1球（整数），实际比分1:0，"
                        "加让球后为2:0，主队让球胜。但如果实际比分2:1，"
                        "加让球后为2:2，算让球平。"
                    ),
                },
            },
        },
        "倍数限制": {
            "竞彩足球": {
                "rule_description": (
                    "倍数是指将同一注投注方案重复购买的次数。"
                    "例如选了3串1，投注2元，倍数选10倍，"
                    "相当于买了10注相同的方案，总投注额 = 2 x 1 x 10 = 20元。"
                    "如果中奖，奖金也乘以10倍。"
                    "竞彩足球的倍数范围为2-50倍。"
                ),
                "specific_values": {
                    "最低倍数": "2 倍",
                    "最高倍数": "50 倍",
                    "单注基础金额": "2 元",
                    "总投注额计算": "2元 x 注数 x 倍数",
                },
                "common_mistakes": [
                    "最低倍数是2倍，不能选1倍（即不能只买1注的方案）",
                    "高倍数会放大风险和收益，同时要注意不要超过单票限额",
                    "倍数与注数是乘法关系：4串11选10倍，总投注 = 2 x 11 x 10 = 220元",
                ],
                "examples": {
                    "correct": (
                        "正确示例：3串1，倍数10倍，总投注 = 2 x 1 x 10 = 20元。"
                        "如果三场全对且赔率连乘为5.0，奖金 = 2 x 5.0 x 10 = 100元。"
                    ),
                    "wrong": (
                        "错误示例：想选1倍投注，但竞彩足球最低倍数为2倍。"
                    ),
                },
            },
            "北京单场": {
                "rule_description": (
                    "北京单场的倍数范围比竞彩足球更宽，最低同样为2倍，"
                    "但最高可达99倍。这意味着北单可以用更高的倍数来放大收益，"
                    "但同时也要注意单票限额（20,000元）的约束。"
                ),
                "specific_values": {
                    "最低倍数": "2 倍",
                    "最高倍数": "99 倍",
                    "单注基础金额": "2 元",
                    "单票限额": "20,000 元",
                },
                "common_mistakes": [
                    "北单最高99倍，高倍数配合M串N很容易超过20,000元单票限额",
                    "例如8串255选99倍，总投注 = 2 x 255 x 99 = 50,490元，远超限额",
                ],
                "examples": {
                    "correct": (
                        "正确示例：3串1，倍数50倍，总投注 = 2 x 1 x 50 = 100元，"
                        "未超20,000元限额。"
                    ),
                    "wrong": (
                        "错误示例：8串255，倍数99倍，"
                        "总投注 = 2 x 255 x 99 = 50,490元，超过20,000元限额。"
                    ),
                },
            },
        },
    }

    def explain_rule(self, rule_topic: str, lottery_type: str = "竞彩足球",
                     context: Optional[str] = None) -> Dict[str, Any]:
        """用自然语言解释彩票规则

        Args:
            rule_topic: 要解释的规则主题
            lottery_type: 彩种类型
            context: 额外上下文信息

        Returns:
            包含规则解释的字典
        """
        # 查找知识库
        topic_data = self.RULE_EXPLANATIONS.get(rule_topic)

        if topic_data is None:
            # 主题不在知识库中，返回通用提示
            available_topics = list(self.RULE_EXPLANATIONS.keys())
            return {
                "found": False,
                "rule_topic": rule_topic,
                "lottery_type": lottery_type,
                "message": (
                    f"未找到「{rule_topic}」的规则解释。"
                    f"目前支持解释的主题有：{available_topics}。"
                    f"您也可以使用 lottery_query_rules 工具查询更详细的规则数据。"
                ),
                "available_topics": available_topics,
            }

        # 查找对应彩种的解释
        lottery_data = topic_data.get(lottery_type)
        if lottery_data is None:
            # 该主题没有对应彩种的解释，返回通用版本
            available_lotteries = list(topic_data.keys())
            # 尝试返回第一个可用的彩种解释
            fallback_lottery = available_lotteries[0] if available_lotteries else None
            if fallback_lottery:
                lottery_data = topic_data[fallback_lottery]
                return {
                    "found": True,
                    "rule_topic": rule_topic,
                    "lottery_type": lottery_type,
                    "fallback_lottery": fallback_lottery,
                    "message": f"未找到「{lottery_type}」的专属解释，以下为「{fallback_lottery}」的规则说明供参考。",
                    "explanation": lottery_data,
                }
            else:
                return {
                    "found": False,
                    "rule_topic": rule_topic,
                    "lottery_type": lottery_type,
                    "message": f"未找到「{rule_topic}」在「{lottery_type}」下的规则解释。",
                }

        result = {
            "found": True,
            "rule_topic": rule_topic,
            "lottery_type": lottery_type,
            "explanation": lottery_data,
        }

        # 如果有额外上下文，附加针对性说明
        if context:
            result["context"] = context
            result["context_note"] = (
                f"根据您提供的上下文「{context}」，以上规则解释供参考。"
                f"如需验证具体投注方案是否合规，请使用 lottery_validate_bet 或 lottery_validate_parlay 工具。"
            )

        return result


# 全局规则引擎实例
_rules_engine: Optional[RulesEngine] = None


def get_rules_engine() -> RulesEngine:
    """获取规则引擎实例（单例模式）"""
    global _rules_engine
    if _rules_engine is None:
        _rules_engine = RulesEngine()
    return _rules_engine


# ============================================================
# Tool Functions
# ============================================================

async def lottery_validate_bet(params: ValidateBetInput, ctx: Context) -> str:
    """验证单个投注"""
    try:
        await ctx.report_progress(0.5, "正在验证投注...")
        await ctx.log_info(f"[验证] 验证投注: {params.match_id} - {params.play_type}")

        engine = get_rules_engine()
        result = engine.validate_bet(params)

        await ctx.report_progress(1.0, "验证完成")

        return _to_json(ValidateBetOutput(
            valid=result["valid"],
            errors=result.get("errors", []),
            warnings=result.get("warnings", []),
            bet_summary=result["bet_summary"],
        ).model_dump())

    except Exception as e:
        logger.error(f"投注验证失败: {e}")
        raise


async def lottery_validate_parlay(params: ValidateParlayInput, ctx: Context) -> str:
    """验证串关投注（自动检测混合过关）"""
    try:
        await ctx.report_progress(0.3, "正在验证串关...")
        await ctx.log_info(f"[验证] 验证串关: {len(params.bets)}场 - {params.parlay_type}")

        engine = get_rules_engine()
        result = engine.validate_parlay(params)

        await ctx.report_progress(1.0, "验证完成")

        validated = ValidateParlayOutput(**result)
        return _to_json({"success": True, "data": validated.model_dump(), "timestamp": datetime.now().isoformat()})

    except Exception as e:
        logger.error(f"串关验证失败: {e}")
        raise_tool_error(f"串关验证失败: {str(e)}")


async def lottery_calculate_bonus(params: CalculateBonusInput, ctx: Context) -> str:
    """计算奖金（含税金和封顶）"""
    try:
        await ctx.report_progress(0.5, "正在计算奖金...")
        await ctx.log_info(f"[奖金] 计算奖金: {len(params.bets)}场 - {params.parlay_type}")

        engine = get_rules_engine()
        result = engine.calculate_bonus(
            params.bets, params.parlay_type, params.results, params.lottery_type
        )

        await ctx.report_progress(1.0, "计算完成")

        # 将引擎返回的 sp_product 映射为 total_odds
        if "sp_product" in result:
            result["total_odds"] = result.pop("sp_product")

        return _to_json(BonusCalculationOutput(**result).model_dump())

    except Exception as e:
        logger.error(f"奖金计算失败: {e}")
        raise


async def lottery_query_rules(params: QueryRulesInput, ctx: Context) -> str:
    """查询规则详情"""
    try:
        await ctx.report_progress(0.5, "正在查询规则...")
        await ctx.log_info(f"[规则] 查询规则: {params.rule_type} - {params.lottery_type}")

        engine = get_rules_engine()
        result = engine.query_rules(params.rule_type, params.lottery_type, params.play_type)

        await ctx.report_progress(1.0, "查询完成")

        return _to_json(QueryRulesOutput(**result).model_dump())

    except Exception as e:
        logger.error(f"规则查询失败: {e}")
        raise


async def lottery_explain_rule(params: ExplainRuleInput, ctx: Context) -> str:
    """用自然语言解释彩票规则"""
    try:
        await ctx.report_progress(0.5, "正在解释规则...")
        await ctx.log_info(f"[解释] 规则主题: {params.rule_topic} - {params.lottery_type}")

        engine = get_rules_engine()
        result = engine.explain_rule(params.rule_topic, params.lottery_type, params.context)

        await ctx.report_progress(1.0, "解释完成")

        return _to_json({
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"规则解释失败: {e}")
        raise_tool_error(f"规则解释失败: {str(e)}")


# ============================================================
# Tool Registration
# ============================================================

def register_rules_tools(mcp):
    """注册规则引擎工具"""
    from mcp.server.fastmcp import Context

    @mcp.tool(
        name="lottery_validate_bet",
        description="""验证单个投注的合法性

检查投注是否符合规则，包括：
- 玩法是否支持
- 投注金额是否在限额范围内
- 赔率是否在有效范围内
- 返回预期奖金

Use when: 用户提交投注前进行规则验证。

Workflow: 在 generate_betting_slips 之前或之后调用，验证投注合规性。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_validate_bet(params: ValidateBetInput, ctx: Context) -> str:
        return await lottery_validate_bet(params, ctx)

    @mcp.tool(
        name="lottery_validate_parlay",
        description="""验证串关投注的合法性（自动检测混合过关）

检查串关组合是否符合规则，包括：
- 场次数量限制（竞彩1-8场，北单1-15场）
- 串关类型支持（竞彩32种M串N+单关+M串1，北单57种胜平负/19种胜负过关）
- 单票限额（竞彩6000元，北单20000元）
- 倍数范围（竞彩2-50倍，北单2-99倍）
- 各单场投注的合法性
- 自动检测混合过关并执行三大规则校验：
  1. 同一场比赛不可选择多个玩法
  2. 不同运动项目不能混合
  3. 木桶原则：串关数以所选玩法中限制最低者为准

Use when: 用户提交串关投注前进行验证。

Workflow: generate_betting_slips(生成串关) → validate_parlay(验证) → calculate_bonus(计算奖金)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_validate_parlay(params: ValidateParlayInput, ctx: Context) -> str:
        return await lottery_validate_parlay(params, ctx)

    @mcp.tool(
        name="lottery_calculate_bonus",
        description="""计算投注奖金（含税金和封顶）

支持两种模式：
1. 模拟模式：未提供比赛结果，返回预期奖金
2. 结算模式：提供比赛结果，返回实际奖金

奖金公式（以2元为基数）：
- 竞彩单关: 2元 x 浮动奖金额 x 倍数
- 竞彩过关: 2元 x 各场固定奖金连乘 x 倍数（不乘返还率）
- 北单: 2元 x SP值连乘 x 65% x 倍数

税金规则（P1-09: 按单注计算）：
- 单注奖金 = 总奖金 / 总注数
- 单注 >= 1万元扣20%

封顶：按场次数分级（单关10万, 2-3关20万, 4-5关50万, 6+关100万）

单票限额：竞彩6000元，北单20000元
倍数范围：竞彩2-50倍，北单2-99倍
返还率：竞彩足球70%，北京单场65%

Use when: 需要计算预期收益或结算投注。

Workflow: validate_parlay(验证通过) → calculate_bonus(计算预期奖金)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_calculate_bonus(params: CalculateBonusInput, ctx: Context) -> str:
        return await lottery_calculate_bonus(params, ctx)

    @mcp.tool(
        name="lottery_query_rules",
        description="""查询彩票规则详情

支持查询的规则类型：
- limits: 限额规则（单注最低/最高、单票限额、倍数范围）
- parlay: 串关规则（场次限制、类型支持、混合过关规则）
- play: 玩法规则（支持的玩法列表、各玩法最大串关数）
- bonus: 奖金规则（返还率、税率、封顶、奖金公式）
- mixed_parlay: 混合过关专项规则

按彩种区分：竞彩足球 vs 北京单场

Use when: 需要了解具体规则细节时。

Workflow: 独立查询工具，可与 validate_parlay 配合理解违规原因。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_query_rules(params: QueryRulesInput, ctx: Context) -> str:
        return await lottery_query_rules(params, ctx)

    @mcp.tool(
        name="lottery_explain_rule",
        description="""用自然语言解释彩票规则，帮助理解为什么某个投注方案合规或不合规

支持解释的主题：
- 混合过关：混合过关的三大规则（同场不混、不同运动不混、木桶原则）
- 单票限额：单张彩票最大投注金额限制（竞彩6000元，北单20000元）
- 串关类型：M串1、M串N、单关等串关类型的含义和区别
- 奖金封顶：按关数分级的奖金上限（10万/20万/50万/100万）
- 税金：单注奖金1万元起征20%个人所得税
- 让球规则：竞彩整数让球 vs 北单支持小数让球
- 倍数限制：竞彩2-50倍 vs 北单2-99倍

每个解释包含：规则说明、具体数值、常见误区、正确/错误示例。
按彩种区分：竞彩足球 vs 北京单场。

Use when: 用户投注方案被拒绝后，需要向用户解释具体规则原因时。

Workflow: validate_parlay(发现违规) → explain_rule(解释原因) → 修正方案""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_explain_rule(params: ExplainRuleInput, ctx: Context) -> str:
        return await lottery_explain_rule(params, ctx)
