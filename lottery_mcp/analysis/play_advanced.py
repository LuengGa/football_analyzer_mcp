"""
玩法高级分析模块
================

实现各玩法的深化功能：
- 比分范围推荐
- 大小球辅助分析
- 半全场一致性优先
- 等等
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger("lottery_mcp")


@dataclass
class ScoreRange:
    """比分范围推荐"""
    range_name: str
    scores: List[str]
    probability: float
    avg_odds: float
    description: str


@dataclass
class OverUnderAnalysis:
    """大小球分析"""
    over_2_5_probability: float
    under_2_5_probability: float
    recommended_option: str  # "Over" 或 "Under"
    confidence: str
    key_zjq_recommendations: List[str]


@dataclass
class BQCConsistencyAnalysis:
    """半全场一致性分析"""
    consistent_probability: float  # 胜胜、平平、负负的总概率
    inconsistent_probability: float
    recommended_consistent: bool  # 是否推荐一致结果
    top_consistent_options: List[str]
    confidence: str


class PlayAdvancedAnalyzer:
    """玩法高级分析器"""
    
    @staticmethod
    def analyze_score_range(
        score_probs: Dict[str, float],
        odds: Optional[Dict[str, float]] = None
    ) -> List[ScoreRange]:
        """
        分析比分范围，而不是单个比分
        
        Args:
            score_probs: 比分概率字典 {比分: 概率}
            odds: 比分赔率字典（可选）
        
        Returns:
            比分范围推荐列表
        """
        ranges = []
        
        # 定义比分范围
        range_definitions = [
            {
                "name": "1-0, 0-1",
                "scores": ["1:0", "0:1"],
                "desc": "小比分主胜或客胜"
            },
            {
                "name": "1-1, 0-0",
                "scores": ["1:1", "0:0"],
                "desc": "小比分平局"
            },
            {
                "name": "2-1, 1-2",
                "scores": ["2:1", "1:2"],
                "desc": "中等比分"
            },
            {
                "name": "2-0, 0-2",
                "scores": ["2:0", "0:2"],
                "desc": "两球差距"
            },
            {
                "name": "2-2, 3-1, 1-3",
                "scores": ["2:2", "3:1", "1:3"],
                "desc": "高比分"
            },
            {
                "name": "3+球主胜",
                "scores": ["3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "胜其他"],
                "desc": "主胜其他"
            },
            {
                "name": "3+球客胜",
                "scores": ["0:3", "1:3", "2:3", "0:4", "1:4", "2:4", "负其他"],
                "desc": "客胜其他"
            },
        ]
        
        for range_def in range_definitions:
            total_prob = 0.0
            avg_odds = 0.0
            count = 0
            
            for score in range_def["scores"]:
                prob = score_probs.get(score, 0.0)
                total_prob += prob
                
                if odds and score in odds:
                    avg_odds += odds[score]
                    count += 1
            
            if count > 0:
                avg_odds /= count
            
            if total_prob > 0.01:  # 至少1%概率
                ranges.append(ScoreRange(
                    range_name=range_def["name"],
                    scores=range_def["scores"],
                    probability=total_prob,
                    avg_odds=avg_odds,
                    description=range_def["desc"]
                ))
        
        # 按概率排序
        ranges.sort(key=lambda x: x.probability, reverse=True)
        return ranges[:5]  # 返回Top 5个范围
    
    @staticmethod
    def analyze_over_under(
        score_probs: Dict[str, float],
        total_expected_goals: float
    ) -> OverUnderAnalysis:
        """
        大小球分析
        
        Args:
            score_probs: 比分概率字典
            total_expected_goals: 预期总进球
        
        Returns:
            大小球分析结果
        """
        under_prob = 0.0
        over_prob = 0.0
        
        for score, prob in score_probs.items():
            try:
                parts = score.split(":")
                if len(parts) == 2:
                    total = int(parts[0]) + int(parts[1])
                    if total <= 2:
                        under_prob += prob
                    else:
                        over_prob += prob
            except (ValueError, IndexError):
                # 处理"胜其他"等特殊比分
                if "胜" in score or "负" in score:
                    # 假设其他至少3+球
                    over_prob += prob * 0.8
        
        # 调整概率总和
        total = under_prob + over_prob
        if total > 0:
            under_prob /= total
            over_prob /= total
        
        recommendation = "Over 2.5" if over_prob > under_prob else "Under 2.5"
        
        # 生成对应的总进球推荐
        zjq_recs = []
        if over_prob > under_prob:
            if total_expected_goals < 3.0:
                zjq_recs = ["3", "4", "5"]
            elif total_expected_goals < 4.0:
                zjq_recs = ["3", "4", "5", "6"]
            else:
                zjq_recs = ["4", "5", "6", "7+"]
        else:
            if total_expected_goals < 2.0:
                zjq_recs = ["0", "1", "2"]
            else:
                zjq_recs = ["1", "2", "3"]
        
        confidence = "高" if max(over_prob, under_prob) > 0.65 else "中"
        
        return OverUnderAnalysis(
            over_2_5_probability=over_prob,
            under_2_5_probability=under_prob,
            recommended_option=recommendation,
            confidence=confidence,
            key_zjq_recommendations=zjq_recs
        )
    
    @staticmethod
    def analyze_bqc_consistency(
        bqc_probs: Dict[str, float],
        home_win_prob: float,
        draw_prob: float,
        away_win_prob: float
    ) -> BQCConsistencyAnalysis:
        """
        半全场一致性分析
        
        Args:
            bqc_probs: 半全场概率字典
            home_win_prob: 主胜概率
            draw_prob: 平局概率
            away_win_prob: 客胜概率
        
        Returns:
            一致性分析结果
        """
        # 一致结果
        consistent_options = ["胜胜", "平平", "负负"]
        
        consistent_total = 0.0
        inconsistent_total = 0.0
        
        for option in consistent_options:
            prob = bqc_probs.get(option, 0.0)
            consistent_total += prob
        
        # 计算不一致概率（总概率-一致概率）
        inconsistent_total = max(0.0, 1.0 - consistent_total)
        
        # 推荐一致结果的条件：
        # 1. 一致总概率 > 不一致概率
        # 2. 或者某个一致选项有较高概率
        recommend_consistent = consistent_total > inconsistent_total
        
        # 找出前几位一致选项
        valid_options = [k for k in consistent_options if bqc_probs.get(k, 0) > 0.05]
        top_consistent = sorted(
            valid_options,
            key=lambda x: bqc_probs.get(x, 0),
            reverse=True
        )[:3]
        
        confidence = "高" if consistent_total > 0.55 else "中" if consistent_total > 0.45 else "低"
        
        return BQCConsistencyAnalysis(
            consistent_probability=consistent_total,
            inconsistent_probability=inconsistent_total,
            recommended_consistent=recommend_consistent,
            top_consistent_options=top_consistent,
            confidence=confidence
        )
    
    @staticmethod
    def calculate_odds_value(
        probability: float,
        odds: float
    ) -> Dict[str, Any]:
        """
        计算赔率价值
        
        Args:
            probability: 概率
            odds: 赔率
        
        Returns:
            价值评估字典
        """
        fair_odds = 1.0 / probability if probability > 0 else float('inf')
        value = probability * odds
        
        return {
            "fair_odds": fair_odds,
            "value": value,
            "is_value": value > 1.0,
            "value_rating": "高价值" if value > 1.1 else "价值" if value > 1.0 else "公平" if value > 0.9 else "低估"
        }
