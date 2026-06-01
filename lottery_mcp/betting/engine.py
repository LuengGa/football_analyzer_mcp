"""
投注引擎核心模块

提供投注推荐和投注单生成功能。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("lottery_mcp")


def calculate_kelly(
    odds: float,
    probability: float,
    fraction: float = 0.5,
) -> Dict[str, float]:
    """计算凯利公式
    
    凯利公式: f* = (bp - q) / b
    其中: b = 赔率-1, p = 胜率, q = 败率 = 1-p
    
    这是凯利公式的核心实现，所有投注工具都应调用此函数。
    
    Args:
        odds: 赔率
        probability: 胜率 (0-1)
        fraction: 凯利分数（默认0.5，即半凯利）
        
    Returns:
        包含凯利计算结果的字典
    """
    if odds <= 1:
        return {
            "kelly_fraction": 0.0,
            "adjusted_fraction": 0.0,
            "stake_percentage": 0.0,
            "recommendation": "赔率无效",
        }
    
    b = odds - 1
    p = probability
    q = 1 - p
    
    kelly = (b * p - q) / b if b > 0 else 0
    kelly = max(0, min(1, kelly))
    
    adjusted_kelly = kelly * fraction
    
    return {
        "kelly_fraction": round(kelly, 4),
        "adjusted_fraction": round(adjusted_kelly, 4),
        "stake_percentage": round(adjusted_kelly * 100, 2),
        "recommendation": "投注" if kelly > 0 else "不投注",
    }


def calculate_parlay_kelly(
    odds_list: List[float],
    probabilities: List[float],
    fraction: float = 0.5,
) -> Dict[str, Any]:
    """计算串关的凯利投注额
    
    Args:
        odds_list: 各场赔率列表
        probabilities: 各场胜率列表
        fraction: 凯利分数
        
    Returns:
        包含投注建议的字典
    """
    if not odds_list or not probabilities or len(odds_list) != len(probabilities):
        return {
            "kelly_fraction": 0.0,
            "adjusted_fraction": 0.0,
            "stake_percentage": 0.0,
            "recommendation": "参数无效",
        }
    
    total_odds = 1.0
    for o in odds_list:
        total_odds *= o
    
    total_prob = 1.0
    for p in probabilities:
        total_prob *= p
    
    result = calculate_kelly(total_odds, total_prob, fraction)
    result["total_odds"] = round(total_odds, 2)
    result["total_probability"] = round(total_prob, 6)
    
    return result


def get_daily_recommendations(
    count: int = 5,
    strategy: str = "balanced",
    min_confidence: float = 60.0,
    lottery_type: str = "竞彩足球",
) -> Dict[str, Any]:
    """获取每日推荐
    
    Args:
        count: 推荐数量
        strategy: 策略类型
        min_confidence: 最低置信度
        lottery_type: 彩种类型
        
    Returns:
        推荐结果
    """
    from lottery_mcp.data import fetch_today_matches
    from lottery_mcp.analysis import analyze_match
    
    matches = fetch_today_matches(lottery_type)
    
    recommendations = []
    for match in matches[:count * 2]:  # 多取一些用于筛选
        analysis = analyze_match(match.get("match_id", ""), match)
        confidence = analysis.get("analysis", {}).get("poisson", {}).get("confidence", 50)
        
        if confidence >= min_confidence:
            recommendations.append({
                "match_id": match.get("match_id"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "league": match.get("league"),
                "recommendation": analysis.get("analysis", {}).get("recommendation", {}),
                "confidence": confidence,
            })
    
    # 按置信度排序
    recommendations.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return {
        "success": True,
        "count": len(recommendations[:count]),
        "recommendations": recommendations[:count],
        "strategy": strategy,
        "lottery_type": lottery_type,
    }


def generate_betting_slips(
    match_ids: List[str],
    strategy: str = "single",
    bankroll: float = 1000.0,
    lottery_type: str = "竞彩足球",
) -> Dict[str, Any]:
    """生成投注单
    
    Args:
        match_ids: 比赛ID列表
        strategy: 策略类型
        bankroll: 可用资金
        lottery_type: 彩种类型
        
    Returns:
        投注单
    """
    slips = []
    
    for match_id in match_ids:
        from lottery_mcp.analysis import analyze_match
        analysis = analyze_match(match_id)
        
        if analysis.get("success", False):
            slips.append({
                "match_id": match_id,
                "selection": analysis.get("analysis", {}).get("recommendation", {}).get("selection", "待定"),
                "odds": analysis.get("analysis", {}).get("recommendation", {}).get("odds", 1.0),
                "confidence": analysis.get("analysis", {}).get("confidence", 50),
            })
    
    return {
        "success": True,
        "strategy": strategy,
        "bankroll": bankroll,
        "slips": slips,
        "total_stake": min(bankroll * 0.05, 100) * len(slips),  # 每注5%资金
        "lottery_type": lottery_type,
    }


def generate_kelly_slips(
    match_id: str,
    edge: float,
    odds: float,
    bankroll: float = 1000.0,
    fraction: float = 0.5,
) -> Dict[str, Any]:
    """生成凯利投注单
    
    Args:
        match_id: 比赛ID
        edge: 期望优势
        odds: 赔率
        bankroll: 可用资金
        fraction: 凯利分数
        
    Returns:
        凯利投注单
    """
    # 凯利公式: f* = (bp - q) / b
    b = odds - 1
    p = edge
    q = 1 - p
    
    kelly = (b * p - q) / b if b > 0 else 0
    kelly = max(0, min(1, kelly))
    
    adjusted_kelly = kelly * fraction
    stake = bankroll * adjusted_kelly
    
    return {
        "success": True,
        "match_id": match_id,
        "kelly_fraction": round(kelly, 4),
        "adjusted_fraction": round(adjusted_kelly, 4),
        "stake": round(stake, 2),
        "odds": odds,
        "edge": edge,
        "recommendation": "投注" if kelly > 0 else "不投注",
    }


def cross_match_analysis(
    match_ids: List[str],
    analysis_type: str = "correlation",
) -> Dict[str, Any]:
    """跨比赛分析
    
    Args:
        match_ids: 比赛ID列表
        analysis_type: 分析类型
        
    Returns:
        分析结果
    """
    from lottery_mcp.analysis import analyze_match
    
    results = []
    for match_id in match_ids:
        analysis = analyze_match(match_id)
        results.append(analysis)
    
    return {
        "success": True,
        "analysis_type": analysis_type,
        "match_count": len(match_ids),
        "results": results,
    }


def auto_parlay_recommendation(
    match_ids: Optional[List[str]] = None,
    strategy: str = "balanced",
    parlay_type: str = "2x1",
    max_matches: int = 4,
    min_confidence: float = 60.0,
    bankroll: float = 1000.0,
) -> Dict[str, Any]:
    """自动串关推荐
    
    Args:
        match_ids: 比赛ID列表（可选）
        strategy: 策略类型
        parlay_type: 串关类型
        max_matches: 最多选择场次
        min_confidence: 最低置信度
        bankroll: 可用资金
        
    Returns:
        串关推荐
    """
    from lottery_mcp.data import fetch_today_matches
    from lottery_mcp.analysis import analyze_match
    
    if match_ids is None:
        matches = fetch_today_matches("竞彩足球")
        match_ids = [m.get("match_id") for m in matches[:max_matches * 2]]
    
    # 分析并筛选
    qualified = []
    for match_id in match_ids[:max_matches * 2]:
        analysis = analyze_match(match_id)
        confidence = analysis.get("analysis", {}).get("confidence", 0)
        if confidence >= min_confidence:
            qualified.append({
                "match_id": match_id,
                "confidence": confidence,
                "recommendation": analysis.get("analysis", {}).get("recommendation", {}),
            })
    
    # 按置信度排序并取前N场
    qualified.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    selected = qualified[:max_matches]
    
    # 计算串关赔率
    total_odds = 1.0
    for item in selected:
        odds = item.get("recommendation", {}).get("odds", 1.0)
        total_odds *= odds
    
    return {
        "success": True,
        "parlay_type": parlay_type,
        "selected_matches": selected,
        "total_matches": len(selected),
        "total_odds": round(total_odds, 2),
        "recommended_stake": round(bankroll * 0.02, 2),  # 2%资金
        "strategy": strategy,
    }
