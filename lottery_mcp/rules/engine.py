"""
规则引擎核心模块

提供投注验证、奖金计算等核心功能。
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("lottery_mcp")


# 规则常量
RULES = {
    "竞彩足球": {
        "max_single_stake": 10000,  # 单注最大金额
        "max_daily_stake": 10000,   # 单日最大金额
        "max_parlay_matches": 8,    # 最大串关场次
        "min_odds": 1.01,           # 最小赔率
        "max_odds": 1000.0,         # 最大赔率
        "return_rate": 0.70,        # 返还率
    },
    "北京单场": {
        "max_single_stake": 10000,
        "max_daily_stake": 10000,
        "max_parlay_matches": 15,
        "min_odds": 1.01,
        "max_odds": 1000.0,
        "return_rate": 0.65,
    },
    "传统足彩": {
        "max_single_stake": 20000,
        "max_daily_stake": 20000,
        "max_parlay_matches": 14,
        "min_odds": 1.01,
        "max_odds": 1000.0,
        "return_rate": 0.65,
    },
}

# 各玩法最大过关场次（官方规则，木桶原则用）
PLAY_MAX_LEGS = {
    "SPF": 8,
    "RQSPF": 8,
    "ZJQ": 6,
    "BF": 4,
    "BQC": 4,
}

# 各玩法有效选项
PLAY_VALID_SELECTIONS = {
    "SPF": ["胜", "平", "负", "3", "1", "0"],
    "RQSPF": ["胜", "平", "负", "3", "1", "0"],
    "ZJQ": ["0", "1", "2", "3", "4", "5", "6", "7+"],
    "BQC": [
        "胜-胜", "胜-平", "胜-负",
        "平-胜", "平-平", "平-负",
        "负-胜", "负-平", "负-负",
    ],
}

# 可混合过关的玩法
MIXABLE_PLAY_TYPES = {"SPF", "RQSPF", "BF", "ZJQ", "BQC"}


def validate_play_selection(
    play_type: str,
    selection: str,
    handicap: Optional[float] = None,
) -> Dict[str, Any]:
    """验证玩法选项的合法性

    根据不同玩法类型验证投注选项是否符合官方规则。

    Args:
        play_type: 玩法类型（SPF/RQSPF/BF/ZJQ/BQC）
        selection: 投注选项
        handicap: 让球数（仅 RQSPF 需要）

    Returns:
        验证结果字典，包含 valid、errors 字段
    """
    errors = []

    if not play_type or not selection:
        errors.append("玩法类型和投注选项不能为空")
        return {"valid": False, "errors": errors, "play_type": play_type, "selection": selection}

    play_type_upper = play_type.upper()

    if play_type_upper == "SPF":
        # 胜平负：胜/平/负 或 3/1/0
        valid_options = PLAY_VALID_SELECTIONS["SPF"]
        if selection not in valid_options:
            errors.append(
                f"胜平负（SPF）选项无效：'{selection}'，"
                f"有效选项为：{', '.join(valid_options)}"
            )

    elif play_type_upper == "RQSPF":
        # 让球胜平负：胜/平/负 或 3/1/0，且必须提供让球数
        valid_options = PLAY_VALID_SELECTIONS["RQSPF"]
        if selection not in valid_options:
            errors.append(
                f"让球胜平负（RQSPF）选项无效：'{selection}'，"
                f"有效选项为：{', '.join(valid_options)}"
            )
        if handicap is None:
            errors.append("让球胜平负（RQSPF）必须提供让球数（handicap）")

    elif play_type_upper == "BF":
        # 比分：X:Y 格式（X: 0-7, Y: 0-5）或 胜其他/平其他/负其他
        bf_pattern = r"^([0-7]):([0-5])$"
        bf_special = {"胜其他", "平其他", "负其他"}
        if selection in bf_special:
            pass  # 特殊比分选项，有效
        elif re.match(bf_pattern, selection):
            # 验证比分合理性
            home_goals, away_goals = selection.split(":")
            # 比分本身格式已通过正则验证
            pass
        else:
            errors.append(
                f"比分（BF）选项无效：'{selection}'，"
                f"有效格式为 'X:Y'（X:0-7, Y:0-5）或 '胜其他'/'平其他'/'负其他'"
            )

    elif play_type_upper == "ZJQ":
        # 总进球：0-7+
        valid_options = PLAY_VALID_SELECTIONS["ZJQ"]
        if selection not in valid_options:
            errors.append(
                f"总进球（ZJQ）选项无效：'{selection}'，"
                f"有效选项为：{', '.join(valid_options)}"
            )

    elif play_type_upper == "BQC":
        # 半全场：9种组合
        valid_options = PLAY_VALID_SELECTIONS["BQC"]
        if selection not in valid_options:
            errors.append(
                f"半全场（BQC）选项无效：'{selection}'，"
                f"有效选项为：{', '.join(valid_options)}"
            )

    else:
        errors.append(f"未知的玩法类型：'{play_type}'，有效玩法为：SPF, RQSPF, BF, ZJQ, BQC")

    if errors:
        logger.warning(f"玩法选项验证失败 [{play_type}]: {selection} - {'; '.join(errors)}")

    return {
        "valid": len(errors) == 0,
        "errors": errors if errors else None,
        "play_type": play_type,
        "selection": selection,
    }


def validate_mixed_parlay_compatibility(
    bets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """验证混合过关的组合兼容性

    检查多场投注是否可以组成合法的混合过关方案：
    1. 同一场比赛不可出现多次
    2. 所有玩法必须是可混合过关的类型
    3. 木桶原则：最大场次数 = 所有玩法最大场次数的最小值
    4. 所有投注必须是同一运动项目（足球）

    Args:
        bets: 投注列表，每个元素包含 match_id, play_type, selection 等字段

    Returns:
        验证结果字典
    """
    errors = []
    warnings = []

    if not bets:
        errors.append("投注列表不能为空")
        return {"valid": False, "errors": errors, "warnings": warnings}

    if len(bets) < 2:
        errors.append("混合过关至少需要 2 场比赛")
        return {"valid": False, "errors": errors, "warnings": warnings}

    # 规则1：同一场比赛不可出现多次
    match_ids = [bet.get("match_id", "") for bet in bets]
    seen_ids = set()
    for mid in match_ids:
        if mid in seen_ids:
            errors.append(
                f"同场比赛 '{mid}' 出现多次，混合过关中每场比赛只能选择一次"
            )
        seen_ids.add(mid)

    # 规则2：所有玩法必须是可混合过关的类型
    play_types = set()
    for i, bet in enumerate(bets):
        pt = bet.get("play_type", "")
        pt_upper = pt.upper() if pt else ""
        if pt_upper not in MIXABLE_PLAY_TYPES:
            errors.append(
                f"第 {i+1} 场的玩法 '{pt}' 不支持混合过关，"
                f"可混合过关的玩法为：{', '.join(sorted(MIXABLE_PLAY_TYPES))}"
            )
        play_types.add(pt_upper)

    # 规则3：木桶原则
    valid_play_types = play_types & MIXABLE_PLAY_TYPES
    if valid_play_types:
        max_legs_values = []
        for pt in valid_play_types:
            if pt in PLAY_MAX_LEGS:
                max_legs_values.append(PLAY_MAX_LEGS[pt])

        if max_legs_values:
            bucket_limit = min(max_legs_values)
            bet_count = len(bets)
            if bet_count > bucket_limit:
                errors.append(
                    f"木桶原则限制：当前方案包含 {bet_count} 场，"
                    f"涉及玩法 {', '.join(sorted(valid_play_types))}，"
                    f"其中 '{[pt for pt in valid_play_types if PLAY_MAX_LEGS.get(pt) == bucket_limit][0]}' "
                    f"最大场次数为 {bucket_limit} 场，超出限制"
                )

    # 规则4：所有投注必须是同一运动项目（足球）
    sports = set()
    for bet in bets:
        sport = bet.get("sport", bet.get("sport_type", "足球"))
        sports.add(sport)

    if len(sports) > 1:
        errors.append(
            f"混合过关中所有投注必须是同一运动项目，"
            f"当前包含：{', '.join(sorted(sports))}"
        )

    # 警告：场次较多时提醒
    if len(bets) >= 6:
        warnings.append("混合过关场次较多（>=6场），中奖概率较低，请谨慎投注")

    if errors:
        logger.warning(f"混合过关兼容性验证失败：{'; '.join(errors)}")

    return {
        "valid": len(errors) == 0,
        "errors": errors if errors else None,
        "warnings": warnings if warnings else None,
        "bet_count": len(bets),
        "play_types": sorted(valid_play_types),
        "bucket_limit": min(max_legs_values) if max_legs_values else None,
    }


def validate_bet(
    match_id: str,
    play_type: str,
    selection: str,
    odds: float,
    stake: float,
    handicap: Optional[float] = None,
    lottery_type: str = "竞彩足球",
) -> Dict[str, Any]:
    """验证单注投注

    Args:
        match_id: 比赛ID
        play_type: 玩法类型
        selection: 投注选项
        odds: 赔率
        stake: 投注金额
        handicap: 让球数
        lottery_type: 彩种类型

    Returns:
        验证结果
    """
    rules = RULES.get(lottery_type, RULES["竞彩足球"])
    errors = []
    warnings = []

    # 验证赔率
    if odds < rules["min_odds"]:
        errors.append(f"赔率不能低于 {rules['min_odds']}")
    if odds > rules["max_odds"]:
        errors.append(f"赔率不能超过 {rules['max_odds']}")

    # 验证金额
    if stake < 2:
        errors.append("投注金额不能低于 2 元")
    if stake > rules["max_single_stake"]:
        errors.append(f"单注金额不能超过 {rules['max_single_stake']} 元")

    # 验证玩法
    valid_plays = ["SPF", "RQSPF", "BF", "ZJQ", "BQC"]
    if play_type not in valid_plays:
        errors.append(f"无效玩法: {play_type}，有效玩法: {', '.join(valid_plays)}")

    # 验证玩法选项
    play_result = validate_play_selection(play_type, selection, handicap)
    if not play_result["valid"]:
        if play_result["errors"]:
            errors.extend(play_result["errors"])

    # 警告检查
    if stake > 1000:
        warnings.append("单注金额超过 1000 元，请确认")

    return {
        "valid": len(errors) == 0,
        "errors": errors if errors else None,
        "warnings": warnings if warnings else None,
        "lottery_type": lottery_type,
        "play_type": play_type,
    }


def validate_parlay(
    bets: List[Dict[str, Any]],
    parlay_type: str,
    total_stake: float,
    lottery_type: str = "竞彩足球",
) -> Dict[str, Any]:
    """验证串关投注

    Args:
        bets: 投注列表
        parlay_type: 串关类型
        total_stake: 总投注金额
        lottery_type: 彩种类型

    Returns:
        验证结果
    """
    rules = RULES.get(lottery_type, RULES["竞彩足球"])
    errors = []
    warnings = []

    # 验证场次数量
    match_count = len(bets)
    if match_count < 2:
        errors.append("串关至少需要 2 场比赛")
    if match_count > rules["max_parlay_matches"]:
        errors.append(f"串关最多 {rules['max_parlay_matches']} 场比赛")

    # 验证总金额
    if total_stake < 2:
        errors.append("投注金额不能低于 2 元")
    if total_stake > rules["max_single_stake"]:
        errors.append(f"总投注金额不能超过 {rules['max_single_stake']} 元")

    # 验证串关类型
    valid_parlay_types = ["2x1", "3x1", "4x1", "3x4", "4x11", "MxN"]
    if parlay_type not in valid_parlay_types:
        errors.append(f"无效串关类型: {parlay_type}")

    # 验证每场投注
    for i, bet in enumerate(bets):
        result = validate_bet(
            match_id=bet.get("match_id", ""),
            play_type=bet.get("play_type", "SPF"),
            selection=bet.get("selection", ""),
            odds=bet.get("odds", 1.0),
            stake=total_stake / len(bets),
            handicap=bet.get("handicap"),
            lottery_type=lottery_type,
        )
        if not result["valid"]:
            errors.append(f"第 {i+1} 场: {', '.join(result['errors'])}")

    # 警告检查
    if match_count >= 6:
        warnings.append("串关场次较多，中奖概率较低")

    return {
        "valid": len(errors) == 0,
        "errors": errors if errors else None,
        "warnings": warnings if warnings else None,
        "parlay_type": parlay_type,
        "match_count": match_count,
    }


def validate_mixed_parlay(
    bets: List[Dict[str, Any]],
    total_stake: float,
    lottery_type: str = "竞彩足球",
) -> Dict[str, Any]:
    """验证混合过关

    Args:
        bets: 投注列表
        total_stake: 总投注金额
        lottery_type: 彩种类型

    Returns:
        验证结果
    """
    # 先进行混合过关兼容性验证
    compatibility = validate_mixed_parlay_compatibility(bets)
    if not compatibility["valid"]:
        return {
            "valid": False,
            "errors": compatibility["errors"],
            "warnings": compatibility["warnings"],
            "compatibility": compatibility,
        }

    # 再进行通用串关验证
    parlay_result = validate_parlay(bets, "mixed", total_stake, lottery_type)

    # 合并结果
    all_errors = []
    if parlay_result.get("errors"):
        all_errors.extend(parlay_result["errors"])
    if compatibility.get("errors"):
        all_errors.extend(compatibility["errors"])

    all_warnings = []
    if parlay_result.get("warnings"):
        all_warnings.extend(parlay_result["warnings"])
    if compatibility.get("warnings"):
        all_warnings.extend(compatibility["warnings"])

    return {
        "valid": len(all_errors) == 0,
        "errors": all_errors if all_errors else None,
        "warnings": all_warnings if all_warnings else None,
        "compatibility": compatibility,
        "match_count": len(bets),
    }


def calculate_bonus(
    bets: List[Dict[str, Any]],
    parlay_type: str = "1x1",
    results: Optional[Dict[str, str]] = None,
    lottery_type: str = "竞彩足球",
) -> Dict[str, Any]:
    """计算奖金

    Args:
        bets: 投注列表
        parlay_type: 串关类型
        results: 比赛结果
        lottery_type: 彩种类型

    Returns:
        奖金计算结果
    """
    rules = RULES.get(lottery_type, RULES["竞彩足球"])

    # 计算总赔率
    total_odds = 1.0
    for bet in bets:
        odds = bet.get("odds", 1.0)
        total_odds *= odds

    # 计算奖金
    stake = bets[0].get("stake", 100) if bets else 100
    bonus = stake * total_odds * rules["return_rate"]

    # 2元起，向下取整到2的倍数
    bonus = int(bonus // 2) * 2

    return {
        "total_odds": round(total_odds, 2),
        "stake": stake,
        "bonus": bonus,
        "return_rate": rules["return_rate"],
        "lottery_type": lottery_type,
    }


def query_rules(
    rule_type: str,
    lottery_type: str = "竞彩足球",
    play_type: Optional[str] = None,
) -> Dict[str, Any]:
    """查询规则

    Args:
        rule_type: 规则类型
        lottery_type: 彩种类型
        play_type: 玩法类型

    Returns:
        规则信息
    """
    rules = RULES.get(lottery_type, RULES["竞彩足球"])

    if rule_type == "limits":
        return {
            "rule_type": rule_type,
            "lottery_type": lottery_type,
            "rules": {
                "max_single_stake": rules["max_single_stake"],
                "max_daily_stake": rules["max_daily_stake"],
                "max_parlay_matches": rules["max_parlay_matches"],
            },
        }
    elif rule_type == "parlay":
        return {
            "rule_type": rule_type,
            "lottery_type": lottery_type,
            "rules": {
                "max_matches": rules["max_parlay_matches"],
                "valid_types": ["2x1", "3x1", "4x1", "3x4", "4x11"],
            },
        }
    elif rule_type == "play_max_legs":
        """查询各玩法最大过关场次（木桶原则）"""
        return {
            "rule_type": rule_type,
            "lottery_type": lottery_type,
            "rules": PLAY_MAX_LEGS,
            "description": "混合过关的木桶原则：最大场次数由所选玩法中限制最严格的玩法决定",
        }
    else:
        return {
            "rule_type": rule_type,
            "lottery_type": lottery_type,
            "rules": rules,
        }


def explain_rule(
    rule_topic: str,
    lottery_type: str = "竞彩足球",
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """解释规则

    Args:
        rule_topic: 规则主题
        lottery_type: 彩种类型
        context: 上下文

    Returns:
        规则解释
    """
    explanations = {
        "混合过关": "混合过关允许在一张彩票中选择不同玩法的投注选项进行串关，最多可选择8场比赛。",
        "单票限额": f"单张彩票最大投注金额为 {RULES.get(lottery_type, {}).get('max_single_stake', 10000)} 元。",
        "串关类型": "支持2x1、3x1、4x1等串关类型，数字表示场次，x1表示单注。",
        "奖金封顶": "单注奖金最高封顶500万元。",
        "税金": "单注奖金超过1万元需缴纳20%个人所得税。",
        "让球规则": "让球胜平负中，主队让球为负数（如-1），客队让球为正数。",
        "倍数限制": "单场单注最大倍数为99倍。",
        "木桶原则": (
            "混合过关的木桶原则：当一张混合过关彩票中包含多种玩法时，"
            "最大过关场次数由所选用法中限制最严格的玩法决定。"
            f"各玩法最大场次数：胜平负/让球胜平负=8场，总进球=6场，比分/半全场=4场。"
        ),
        "单场限制": "混合过关中，同一场比赛只能选择一种玩法进行投注，不可对同一场比赛多次投注。",
    }

    explanation = explanations.get(rule_topic, f"未找到关于 '{rule_topic}' 的规则说明。")

    return {
        "rule_topic": rule_topic,
        "lottery_type": lottery_type,
        "explanation": explanation,
        "context": context,
    }
