"""
分析引擎核心模块

提供比赛分析的核心功能，整合统计模型和策略分析。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("lottery_mcp")


class StatisticalEngine:
    """统计分析引擎
    
    整合多种统计模型进行比赛分析。
    """
    
    def __init__(self):
        """初始化分析引擎"""
        from .models import PoissonModel, EloRatingSystem
        self.poisson = PoissonModel()
        self.elo = EloRatingSystem()
    
    def analyze(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析单场比赛
        
        Args:
            match_data: 比赛数据
            
        Returns:
            分析结果
        """
        result = {
            "match_id": match_data.get("match_id", ""),
            "timestamp": datetime.now().isoformat(),
            "analysis": {},
        }
        
        # 提取赔率
        had = match_data.get("had", {})
        if had:
            # 泊松分析
            home_odds = had.get("win", 2.0)
            draw_odds = had.get("draw", 3.3)
            away_odds = had.get("lose", 3.0)
            
            poisson_result = self.poisson.analyze(
                home_odds=home_odds,
                draw_odds=draw_odds,
                away_odds=away_odds,
            )
            result["analysis"]["poisson"] = poisson_result
        
        return result
    
    def batch_analyze(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量分析比赛
        
        Args:
            matches: 比赛列表
            
        Returns:
            分析结果列表
        """
        return [self.analyze(m) for m in matches]


def analyze_match(match_id: str, match_data: Optional[Dict] = None) -> Dict[str, Any]:
    """分析单场比赛
    
    Args:
        match_id: 比赛ID
        match_data: 比赛数据（可选）
        
    Returns:
        分析结果
    """
    engine = StatisticalEngine()
    
    if match_data is None:
        # 尝试获取比赛数据
        from lottery_mcp.data import fetch_today_matches
        matches = fetch_today_matches("jingcai")
        for m in matches:
            if m.get("match_id") == match_id:
                match_data = m
                break
    
    if match_data is None:
        return {
            "success": False,
            "error": f"未找到比赛: {match_id}",
        }
    
    return engine.analyze(match_data)


def analyze_all_matches(filter: Optional[str] = None, max_matches: int = 20) -> Dict[str, Any]:
    """分析所有比赛
    
    Args:
        filter: 筛选条件
        max_matches: 最大分析场次
        
    Returns:
        分析结果
    """
    from lottery_mcp.data import fetch_today_matches
    
    matches = fetch_today_matches("jingcai")
    
    if filter == "high_value":
        # 筛选高价值比赛
        matches = [m for m in matches if m.get("value_score", 0) > 0.1]
    elif filter == "low_risk":
        # 筛选低风险比赛
        matches = [m for m in matches if m.get("risk_level", "中") in ["低", "中"]]
    
    matches = matches[:max_matches]
    
    engine = StatisticalEngine()
    results = engine.batch_analyze(matches)
    
    return {
        "success": True,
        "total_analyzed": len(results),
        "results": results,
    }


def detect_risk_signals(
    match_id: str,
    signal_types: Optional[List[str]] = None,
    current_odds: Optional[Dict[str, float]] = None,
    previous_odds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """检测风险信号
    
    Args:
        match_id: 比赛ID
        signal_types: 信号类型列表
        current_odds: 当前赔率
        previous_odds: 历史赔率
        
    Returns:
        风险信号检测结果
    """
    signals = []
    
    if signal_types is None:
        signal_types = ["odds_drift", "lineup", "weather", "market"]
    
    # 赔率异动检测
    if "odds_drift" in signal_types and current_odds and previous_odds:
        for selection, current in current_odds.items():
            if selection in previous_odds:
                previous = previous_odds[selection]
                change_pct = abs(current - previous) / previous
                if change_pct > 0.15:
                    signals.append({
                        "type": "odds_drift",
                        "selection": selection,
                        "severity": "高" if change_pct > 0.25 else "中",
                        "change_pct": round(change_pct * 100, 2),
                        "direction": "上升" if current > previous else "下降",
                    })
    
    return {
        "match_id": match_id,
        "signals": signals,
        "signal_count": len(signals),
        "has_high_risk": any(s["severity"] == "高" for s in signals),
    }


def comprehensive_analysis(match_ids: List[str]) -> Dict[str, Any]:
    """综合分析多场比赛
    
    Args:
        match_ids: 比赛ID列表
        
    Returns:
        综合分析结果
    """
    results = []
    for match_id in match_ids:
        result = analyze_match(match_id)
        results.append(result)
    
    return {
        "success": True,
        "total_matches": len(match_ids),
        "results": results,
    }


def generate_analysis_report(
    match_id: str,
    style: str = "professional",
    include_reasoning: bool = True,
) -> Dict[str, Any]:
    """生成分析报告
    
    Args:
        match_id: 比赛ID
        style: 报告风格
        include_reasoning: 是否包含推理过程
        
    Returns:
        分析报告
    """
    analysis = analyze_match(match_id)
    
    report = {
        "match_id": match_id,
        "style": style,
        "generated_at": datetime.now().isoformat(),
        "analysis": analysis.get("analysis", {}),
    }
    
    if include_reasoning:
        report["reasoning_chain"] = {
            "steps": [
                {"step": 1, "description": "获取比赛基础数据"},
                {"step": 2, "description": "计算泊松分布概率"},
                {"step": 3, "description": "生成分析结论"},
            ],
        }
    
    return report


def batch_analyze_matches(match_ids: List[str], parallel: bool = True) -> Dict[str, Any]:
    """批量分析比赛
    
    Args:
        match_ids: 比赛ID列表
        parallel: 是否并行执行
        
    Returns:
        批量分析结果
    """
    results = []
    for match_id in match_ids:
        result = analyze_match(match_id)
        results.append(result)
    
    return {
        "success": True,
        "total_matches": len(match_ids),
        "results": results,
    }
