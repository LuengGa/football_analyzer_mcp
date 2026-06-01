"""
MCP Server Helpers - Shared utility functions.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
from scipy.special import factorial

from mcp.server.fastmcp.exceptions import ToolError

# ============================================================
# Logging Setup
# ============================================================

logger = logging.getLogger("lottery_mcp")


def raise_tool_error(message: str, code: str = "VALIDATION_ERROR", suggestion: str = "", details: Optional[Dict] = None):
    """抛出MCP协议级工具错误

    FastMCP 会捕获 ToolError 并设置协议级 isError 标志，
    使 LLM 能正确区分正常响应和错误响应。

    Args:
        message: 错误消息
        code: 错误代码
        suggestion: 建议操作
        details: 详细错误信息
    """
    error_msg = f"[{code}] {message}"
    if suggestion:
        error_msg += f"\n建议: {suggestion}"
    if details:
        error_msg += f"\n详情: {json.dumps(details, ensure_ascii=False, default=str)}"
    raise ToolError(error_msg)


def _to_json(data: Any) -> str:
    """将数据转换为JSON字符串
    
    Args:
        data: 要转换的数据
        
    Returns:
        JSON字符串
    """
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def format_output(data: Dict[str, Any], message: str = "", 
                  risk_level: Optional[str] = None, 
                  confidence: Optional[str] = None) -> str:
    """统一格式化工具输出
    
    所有工具应使用此函数格式化输出，确保输出格式一致性。
    
    Args:
        data: 分析数据字典
        message: 提示信息或说明
        risk_level: 风险等级（低/中/高）
        confidence: 置信度（低/中/高/极高）
        
    Returns:
        JSON格式的统一输出字符串
    """
    output = {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    
    if risk_level:
        output["risk_level"] = risk_level
    if confidence:
        output["confidence"] = confidence
    
    return json.dumps(output, ensure_ascii=False, indent=2, default=str)


# ============================================================
# Poisson Distribution Helpers (调用核心模块)
# ============================================================

def _calculate_poisson_probabilities(home_lambda: float, away_lambda: float, max_goals: int = 5) -> Dict[str, Any]:
    """计算泊松分布概率
    
    调用核心模块 PoissonModel 进行计算，避免代码重复。
    
    Args:
        home_lambda: 主队预期进球
        away_lambda: 客队预期进球
        max_goals: 最大计算进球数（已废弃，PoissonModel 内部使用固定值8）
        
    Returns:
        包含各种概率的字典
    """
    from lottery_mcp.analysis.models import PoissonModel
    
    model = PoissonModel(max_goals=max_goals)
    result = model.predict(home_lambda, away_lambda)
    
    return {
        "home_expected_goals": result.home_expected_goals,
        "away_expected_goals": result.away_expected_goals,
        "win_prob": result.home_win_prob,
        "draw_prob": result.draw_prob,
        "lose_prob": result.away_win_prob,
        "most_likely_score": result.most_likely_score,
        "most_likely_score_prob": result.most_likely_score_prob,
        "over_under_2_5": result.over_under_2_5,
        "under_over_2_5": round(1 - result.over_under_2_5, 4),
        "btts_prob": result.btts_prob,
        "score_probabilities": {k: round(v, 6) for k, v in sorted(result.score_probabilities.items(), key=lambda x: -x[1])[:10]},
    }


def _estimate_lambdas_from_odds(home_odds: float, draw_odds: float, away_odds: float, 
                                 return_rate: float = 0.70,
                                 lottery_type: str = "",
                                 ttg_odds: Optional[Dict[str, float]] = None,
                                 hhad_handicap: float = 0.0) -> Tuple[float, float]:
    """从赔率反推泊松参数
    
    优先使用总进球(ttg)赔率反推total_lambda，使不同比赛产生不同的预期进球数。
    回退时使用胜平负赔率 + 平局概率动态计算total_lambda。
    
    Args:
        home_odds: 主胜赔率
        draw_odds: 平局赔率
        away_odds: 客胜赔率
        return_rate: 返还率（默认0.70，竞彩足球标准值）
        lottery_type: 彩种类型（竞彩足球=0.70，北京单场/传统足彩=0.65）
        ttg_odds: 总进球赔率字典 {进球数: 赔率}，如 {"0": 12.0, "1": 5.5, ...}
        hhad_handicap: 让球胜平负的盘口值（负数=主队让球，正数=客队让球）
        
    Returns:
        (主队lambda, 客队lambda)
    """
    # 根据彩种确定返还率
    _RETURN_RATES = {
        "竞彩足球": 0.70,
        "北京单场": 0.65,
        "传统足彩": 0.65,
    }
    if lottery_type and lottery_type in _RETURN_RATES:
        return_rate = _RETURN_RATES[lottery_type]
    
    # 从赔率计算隐含概率
    home_prob = return_rate / home_odds
    draw_prob = return_rate / draw_odds
    away_prob = return_rate / away_odds
    
    # ===== 方法1: 从总进球(ttg)赔率反推total_lambda =====
    total_lambda = None
    if ttg_odds:
        try:
            weighted_sum = 0.0
            weight_total = 0.0
            for goals_key, odds_val in ttg_odds.items():
                if odds_val <= 0:
                    continue
                # 解析进球数: "0"->0, "1"->1, ..., "7+"->7
                try:
                    goals = int(str(goals_key).replace("+", ""))
                except (ValueError, TypeError):
                    continue
                implied = return_rate / odds_val
                weighted_sum += goals * implied
                weight_total += implied
            if weight_total > 0:
                total_lambda = weighted_sum / weight_total
                # 合理范围限制
                total_lambda = max(1.0, min(5.0, total_lambda))
        except Exception:
            total_lambda = None
    
    # ===== 方法2: 从胜平负赔率动态计算total_lambda =====
    if total_lambda is None:
        # 平局概率越高，总进球数越少（平局通常对应低比分）
        # 使用 -ln(draw_prob) 作为基准，再根据主客胜概率差调整
        import math
        draw_strength = draw_prob  # 已经过返还率调整
        
        # 基础total_lambda: 平局概率25%时约2.5球
        # 平局概率越高 -> total_lambda越低
        if draw_strength > 0:
            total_lambda = max(1.0, min(4.5, 3.5 - draw_strength * 4.0))
        else:
            total_lambda = 2.5
    
    # 根据胜负概率分配total_lambda
    # 使用对数几率比（log odds ratio）来分配，避免极端偏向
    import math
    total_non_draw = home_prob + away_prob
    if total_non_draw > 0:
        # home_strength 使用对数尺度，避免强队拿走过多进球
        home_ratio = home_prob / total_non_draw  # 0.5 = 势均力敌
        # 使用 logit 变换压缩极端值
        # home_ratio=0.67 -> strength=0.60 (压缩)
        # home_ratio=0.50 -> strength=0.50 (不变)
        # home_ratio=0.80 -> strength=0.69 (压缩)
        if 0 < home_ratio < 1:
            logit = math.log(home_ratio / (1 - home_ratio))
            home_strength = 1 / (1 + math.exp(-logit * 0.6))  # 0.6 = 压缩系数
        else:
            home_strength = home_ratio
    else:
        home_strength = 0.5
    
    home_lambda = total_lambda * home_strength
    away_lambda = total_lambda * (1 - home_strength)
    
    # 平局概率微调：高平局概率 -> 略微降低进球预期
    if draw_prob > 0.25:
        draw_adj = 1.0 - (draw_prob - 0.25) * 0.3
        home_lambda *= draw_adj
        away_lambda *= draw_adj
    
    return max(0.3, round(home_lambda, 3)), max(0.3, round(away_lambda, 3))


# ============================================================
# Elo Rating Helpers (调用核心模块)
# ============================================================

def _calculate_elo_probabilities(home_elo: int, away_elo: int, 
                                 home_advantage: int = 35) -> Dict[str, Any]:
    """计算基于Elo评级的胜率
    
    调用核心模块 EloRatingSystem 进行计算，避免代码重复。
    
    Args:
        home_elo: 主队Elo评级
        away_elo: 客队Elo评级
        home_advantage: 主场优势（默认35分）
        
    Returns:
        包含胜率和评级信息的字典
    """
    from lottery_mcp.analysis.models import EloRatingSystem
    
    system = EloRatingSystem()
    
    effective_home_elo = home_elo + home_advantage
    
    home_expected = system.expected_score(effective_home_elo, away_elo)
    away_expected = system.expected_score(away_elo, effective_home_elo)
    
    # 平局概率（基于Elo差距调整）
    elo_diff = abs(effective_home_elo - away_elo)
    draw_base = 0.25
    draw_adjustment = max(0, (100 - elo_diff) / 400)
    draw_prob = draw_base + draw_adjustment
    
    # 重新归一化
    total = home_expected + away_expected + draw_prob
    home_prob = home_expected / total
    away_prob = away_expected / total
    draw_prob = draw_prob / total
    
    return {
        "home_elo": home_elo,
        "away_elo": away_elo,
        "home_advantage": home_advantage,
        "rating_diff": effective_home_elo - away_elo,
        "win_prob": round(home_prob, 4),
        "draw_prob": round(draw_prob, 4),
        "lose_prob": round(away_prob, 4),
        "home_expected_score": round(home_expected, 4),
        "away_expected_score": round(away_expected, 4),
    }


def _update_elo(home_elo: int, away_elo: int, result: str, 
                k_factor: int = 20) -> Tuple[int, int]:
    """更新Elo评级
    
    Args:
        home_elo: 主队当前Elo
        away_elo: 客队当前Elo
        result: 比赛结果 ('home_win', 'draw', 'away_win')
        k_factor: K因子（评级变化幅度）
        
    Returns:
        (新主队Elo, 新客队Elo)
    """
    home_expected = 1 / (1 + 10 ** ((away_elo - home_elo) / 400))
    
    if result == 'home_win':
        home_score = 1
        away_score = 0
    elif result == 'draw':
        home_score = 0.5
        away_score = 0.5
    else:  # away_win
        home_score = 0
        away_score = 1
    
    new_home_elo = home_elo + k_factor * (home_score - home_expected)
    new_away_elo = away_elo + k_factor * (away_score - (1 - home_expected))
    
    return round(new_home_elo), round(new_away_elo)


# ============================================================
# Kelly Criterion Helpers (调用核心模块)
# ============================================================

def _calculate_kelly_stake(bankroll: float, edge: float, odds: float, 
                           fraction: float = 0.5) -> Dict[str, float]:
    """计算凯利公式投注额
    
    调用核心模块 calculate_kelly 进行计算，避免代码重复。
    
    Args:
        bankroll: 总资金
        edge: 预期优势 (0-1)
        odds: 赔率
        fraction: 凯利分数（默认半凯利）
        
    Returns:
        包含投注建议的字典
    """
    from lottery_mcp.betting.engine import calculate_kelly
    
    result = calculate_kelly(odds, edge, fraction)
    
    return {
        "kelly_fraction": result["kelly_fraction"],
        "adjusted_fraction": result["adjusted_fraction"],
        "stake": round(bankroll * result["adjusted_fraction"], 2),
        "stake_percentage": result["stake_percentage"],
        "recommendation": result["recommendation"],
    }


def _calculate_parlay_kelly(bankroll: float, edges: List[float], 
                            odds_list: List[float], fraction: float = 0.5) -> Dict[str, float]:
    """计算串关的凯利投注额
    
    调用核心模块 calculate_parlay_kelly 进行计算，避免代码重复。
    
    Args:
        bankroll: 总资金
        edges: 各场预期优势列表
        odds_list: 各场赔率列表
        fraction: 凯利分数
        
    Returns:
        包含投注建议的字典
    """
    from lottery_mcp.betting.engine import calculate_parlay_kelly as core_parlay_kelly
    
    result = core_parlay_kelly(odds_list, edges, fraction)
    
    return {
        "kelly_fraction": result["kelly_fraction"],
        "adjusted_fraction": result["adjusted_fraction"],
        "stake": round(bankroll * result["adjusted_fraction"], 2),
        "total_odds": result.get("total_odds", 0),
        "total_probability": result.get("total_probability", 0),
        "recommendation": result["recommendation"],
    }


# ============================================================
# Value Betting Helpers
# ============================================================

def _calculate_value_edge(true_prob: float, odds: float, 
                          return_rate: float = 0.70) -> float:
    """计算价值投注边缘
    
    价值 = 真实概率 - 隐含概率
    隐含概率 = 返还率 / 赔率
    
    Args:
        true_prob: 真实概率 (0-1)
        odds: 市场赔率
        return_rate: 返还率
        
    Returns:
        价值边缘（正数表示有价值）
    """
    if odds <= 1:
        return -1.0
    
    implied_prob = return_rate / odds
    edge = true_prob - implied_prob
    
    return edge


def _find_value_bets(probabilities: Dict[str, float], odds: Dict[str, float],
                     min_edge: float = 0.05, return_rate: float = 0.70) -> List[Dict[str, Any]]:
    """找出价值投注
    
    Args:
        probabilities: 真实概率字典 {selection: prob}
        odds: 市场赔率字典 {selection: odds}
        min_edge: 最小价值边缘
        return_rate: 返还率
        
    Returns:
        价值投注列表
    """
    value_bets = []
    
    for selection, prob in probabilities.items():
        if selection in odds:
            market_odds = odds[selection]
            edge = _calculate_value_edge(prob, market_odds, return_rate)
            
            if edge >= min_edge:
                value_bets.append({
                    "selection": selection,
                    "true_probability": round(prob, 4),
                    "market_odds": market_odds,
                    "implied_probability": round(return_rate / market_odds, 4),
                    "edge": round(edge, 4),
                    "expected_value": round(prob * market_odds - 1, 4),
                })
    
    # 按价值边缘排序
    value_bets.sort(key=lambda x: x["edge"], reverse=True)
    
    return value_bets


# ============================================================
# Analysis Helpers
# ============================================================

def _analyze_all_matches(matches: List[Dict[str, Any]], 
                         lottery_type: str = "竞彩足球") -> Dict[str, Any]:
    """分析所有比赛并生成摘要
    
    Args:
        matches: 比赛列表
        lottery_type: 彩种类型
        
    Returns:
        分析摘要字典
    """
    total = len(matches)
    if total == 0:
        return {
            "total_matches": 0,
            "analyzed": 0,
            "high_confidence": 0,
            "value_opportunities": 0,
            "risk_alerts": 0,
            "summary": "无比赛数据",
        }
    
    # 统计各种指标
    high_confidence = 0
    value_ops = 0
    risk_alerts = 0
    
    for match in matches:
        # 简化的置信度判断
        score = match.get("combined_score", 50)
        if score >= 70:
            high_confidence += 1
        
        # 价值机会
        if match.get("value_score", 0) > 0.1:
            value_ops += 1
        
        # 风险警报
        if match.get("risk_level") in ["高", "极高风险"]:
            risk_alerts += 1
    
    return {
        "total_matches": total,
        "analyzed": total,
        "high_confidence": high_confidence,
        "high_confidence_pct": round(high_confidence / total * 100, 1),
        "value_opportunities": value_ops,
        "risk_alerts": risk_alerts,
        "summary": f"分析了 {total} 场比赛，发现 {high_confidence} 场高置信度，{value_ops} 个价值机会",
    }


def _detect_odds_drift(current_odds: Dict[str, float], 
                       previous_odds: Dict[str, float],
                       threshold: float = 0.15) -> List[Dict[str, Any]]:
    """检测赔率异动
    
    Args:
        current_odds: 当前赔率
        previous_odds: 之前赔率
        threshold: 异动阈值（赔率变化百分比）
        
    Returns:
        异动列表
    """
    drifts = []
    
    for selection, current in current_odds.items():
        if selection in previous_odds:
            previous = previous_odds[selection]
            change_pct = (current - previous) / previous
            
            if abs(change_pct) >= threshold:
                drifts.append({
                    "selection": selection,
                    "previous_odds": previous,
                    "current_odds": current,
                    "change_pct": round(change_pct * 100, 2),
                    "direction": "上升" if change_pct > 0 else "下降",
                    "severity": "高" if abs(change_pct) > 0.25 else "中",
                })
    
    # 按变化幅度排序
    drifts.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    
    return drifts


def _generate_match_id(home_team: str, away_team: str, 
                       match_date: Optional[str] = None) -> str:
    """生成比赛ID
    
    Args:
        home_team: 主队名
        away_team: 客队名
        match_date: 比赛日期（可选）
        
    Returns:
        比赛ID
    """
    if match_date:
        return f"{match_date}_{home_team}_vs_{away_team}"
    else:
        today = datetime.now().strftime("%Y%m%d")
        return f"{today}_{home_team}_vs_{away_team}"


def _parse_match_id(match_id: str) -> Dict[str, str]:
    """解析比赛ID
    
    Args:
        match_id: 比赛ID
        
    Returns:
        解析结果字典
    """
    parts = match_id.split("_")
    
    if len(parts) >= 4:
        return {
            "date": parts[0],
            "home_team": parts[1],
            "away_team": parts[3] if parts[2] == "vs" else parts[2],
            "raw": match_id,
        }
    else:
        return {
            "date": "",
            "home_team": "",
            "away_team": "",
            "raw": match_id,
        }


# ============================================================
# Formatting Helpers
# ============================================================

def _safe_float(val, default=0.0):
    """安全转换为 float"""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0):
    """安全转换为 int"""
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _format_currency(amount: float, currency: str = "¥") -> str:
    """格式化货币金额
    
    Args:
        amount: 金额
        currency: 货币符号
        
    Returns:
        格式化后的字符串
    """
    return f"{currency}{amount:,.2f}"


def _format_percentage(value: float, decimals: int = 1) -> str:
    """格式化百分比
    
    Args:
        value: 小数形式的百分比 (0-1)
        decimals: 小数位数
        
    Returns:
        格式化后的字符串
    """
    return f"{value * 100:.{decimals}f}%"


def _format_odds(odds: float) -> str:
    """格式化赔率
    
    Args:
        odds: 赔率值
        
    Returns:
        格式化后的字符串
    """
    return f"{odds:.2f}"


def _truncate_for_context(data: dict, max_items: int = 20, max_depth: int = 3) -> dict:
    """截断大型数据以适应 agent 上下文窗口。

    Args:
        data: 原始数据字典
        max_items: 列表类型字段的最大保留数量
        max_depth: 最大递归深度

    Returns:
        截断后的数据字典
    """
    if not isinstance(data, dict) or max_depth <= 0:
        return data

    result = {}
    for key, value in data.items():
        if isinstance(value, list) and len(value) > max_items:
            result[key] = value[:max_items]
            result[f"{key}_truncated"] = True
            result[f"{key}_total"] = len(value)
        elif isinstance(value, dict):
            result[key] = _truncate_for_context(value, max_items, max_depth - 1)
        else:
            result[key] = value
    return result


def _truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """截断字符串
    
    Args:
        s: 原始字符串
        max_length: 最大长度
        suffix: 后缀
        
    Returns:
        截断后的字符串
    """
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


# ============================================================
# Validation Helpers
# ============================================================

def _validate_stake(stake: float, min_stake: float = 2.0, 
                    max_stake: float = 99999.0) -> Tuple[bool, str]:
    """验证投注金额
    
    Args:
        stake: 投注金额
        min_stake: 最小投注
        max_stake: 最大投注
        
    Returns:
        (是否有效, 错误消息)
    """
    if stake < min_stake:
        return False, f"投注金额不能低于 {min_stake} 元"
    if stake > max_stake:
        return False, f"投注金额不能超过 {max_stake} 元"
    if stake != round(stake, 2):
        return False, "投注金额最多保留两位小数"
    return True, ""


def _validate_odds(odds: float, min_odds: float = 1.01, 
                   max_odds: float = 1000.0) -> Tuple[bool, str]:
    """验证赔率
    
    Args:
        odds: 赔率
        min_odds: 最小赔率
        max_odds: 最大赔率
        
    Returns:
        (是否有效, 错误消息)
    """
    if odds < min_odds:
        return False, f"赔率不能低于 {min_odds}"
    if odds > max_odds:
        return False, f"赔率不能超过 {max_odds}"
    return True, ""


def _validate_match_id(match_id: str) -> Tuple[bool, str]:
    """验证比赛ID
    
    Args:
        match_id: 比赛ID
        
    Returns:
        (是否有效, 错误消息)
    """
    if not match_id:
        return False, "比赛ID不能为空"
    if len(match_id) > 100:
        return False, "比赛ID长度不能超过100字符"
    return True, ""
