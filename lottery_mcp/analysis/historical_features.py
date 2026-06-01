"""
历史数据特征工程模块
====================

第三阶段深化功能：
- 历史数据特征提取
- 赔率动态变化追踪
- 历史交锋模式分析
- 近期表现分析
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger("lottery_mcp")


class RecentFormTrend(Enum):
    """近期表现趋势"""
    STRONG_RISING = "强势上升"
    RISING = "上升"
    STABLE = "稳定"
    DECLINING = "下降"
    WEAK_DECLINING = "弱势下降"


class OddsMovement(Enum):
    """赔率走势"""
    SHARP_UP = "大幅上升"
    UP = "上升"
    STABLE = "稳定"
    DOWN = "下降"
    SHARP_DOWN = "大幅下降"
    VOLATILE = "波动剧烈"


@dataclass
class HistoricalFeatures:
    """历史比赛特征"""
    home_recent_form: Dict[str, Any]
    away_recent_form: Dict[str, Any]
    head_to_head: Dict[str, Any]
    home_goals_trend: Dict[str, float]
    away_goals_trend: Dict[str, float]
    home_defense_stability: float
    away_defense_stability: float
    key_markers: List[str]


@dataclass
class OddsDynamics:
    """赔率动态分析"""
    opening_odds: Dict[str, float]
    current_odds: Dict[str, float]
    odds_changes: Dict[str, float]
    movement_trend: OddsMovement
    market_sentiment: Dict[str, float]
    recommended_bet: Optional[str]
    confidence: str


@dataclass
class HeadToHeadPattern:
    """历史交锋模式"""
    pattern_type: str
    match_count: int
    win_rate: float
    avg_goals_home: float
    avg_goals_away: float
    key_findings: List[str]
    recommendation: str


class HistoricalFeatureExtractor:
    """历史数据特征提取器"""
    
    @staticmethod
    def extract_features_from_recent(
        recent_matches: List[Dict],
        team_name: str
    ) -> Dict[str, Any]:
        """
        从近期比赛中提取特征
        
        Args:
            recent_matches: 近期比赛列表
            team_name: 球队名称
        
        Returns:
            特征字典
        """
        if not recent_matches:
            return {
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "win_rate": 0.33,
                "avg_goals_scored": 1.2,
                "avg_goals_conceded": 1.2,
                "form_trend": RecentFormTrend.STABLE,
                "last_5_matches": ["?", "?", "?", "?", "?"],
                "key_markers": ["近期数据不足"]
            }
        
        wins = 0
        draws = 0
        losses = 0
        goals_scored = []
        goals_conceded = []
        results = []
        
        for match in recent_matches[:10]:  # 最近10场
            home_team = match.get("home_team", "")
            away_team = match.get("away_team", "")
            home_score = match.get("home_score", 0)
            away_score = match.get("away_score", 0)
            
            is_home = team_name == home_team
            scored = home_score if is_home else away_score
            conceded = away_score if is_home else home_score
            
            goals_scored.append(scored)
            goals_conceded.append(conceded)
            
            if scored > conceded:
                wins += 1
                results.append("W")
            elif scored == conceded:
                draws += 1
                results.append("D")
            else:
                losses += 1
                results.append("L")
        
        total = len(recent_matches[:10])
        win_rate = wins / total if total > 0 else 0.33
        
        avg_scored = sum(goals_scored) / len(goals_scored) if goals_scored else 1.2
        avg_conceded = sum(goals_conceded) / len(goals_conceded) if goals_conceded else 1.2
        
        # 计算趋势
        if len(results) >= 5:
            last_5 = results[:5]
            prev_5 = results[5:10] if len(results) >= 10 else results[:5]
            
            last_wins = last_5.count("W")
            prev_wins = prev_5.count("W")
            
            if last_wins >= 4 and prev_wins <= 2:
                trend = RecentFormTrend.STRONG_RISING
            elif last_wins >= 3 and prev_wins < 3:
                trend = RecentFormTrend.RISING
            elif abs(last_wins - prev_wins) <= 1:
                trend = RecentFormTrend.STABLE
            elif last_wins <= 1 and prev_wins >= 3:
                trend = RecentFormTrend.WEAK_DECLINING
            else:
                trend = RecentFormTrend.DECLINING
        else:
            trend = RecentFormTrend.STABLE
        
        key_markers = []
        if avg_scored > 2.0:
            key_markers.append("进攻火力强")
        if avg_conceded < 0.8:
            key_markers.append("防守稳固")
        if win_rate > 0.7:
            key_markers.append("状态火热")
        elif win_rate < 0.3:
            key_markers.append("状态低迷")
        
        return {
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "win_rate": win_rate,
            "avg_goals_scored": avg_scored,
            "avg_goals_conceded": avg_conceded,
            "form_trend": trend,
            "last_5_matches": results[:5],
            "key_markers": key_markers
        }
    
    @staticmethod
    def analyze_head_to_head(
        h2h_matches: List[Dict],
        home_team: str,
        away_team: str
    ) -> HeadToHeadPattern:
        """
        分析历史交锋模式
        
        Args:
            h2h_matches: 历史交锋列表
            home_team: 主队名
            away_team: 客队名
        
        Returns:
            历史交锋模式
        """
        if not h2h_matches:
            return HeadToHeadPattern(
                pattern_type="交锋数据不足",
                match_count=0,
                win_rate=0.5,
                avg_goals_home=1.3,
                avg_goals_away=1.3,
                key_findings=["无历史交锋数据"],
                recommendation="参考双方近期表现"
            )
        
        home_wins = 0
        draws = 0
        away_wins = 0
        home_goals = []
        away_goals = []
        
        for match in h2h_matches:
            h_score = match.get("home_score", 0)
            a_score = match.get("away_score", 0)
            home_goals.append(h_score)
            away_goals.append(a_score)
            
            if h_score > a_score:
                home_wins += 1
            elif h_score == a_score:
                draws += 1
            else:
                away_wins += 1
        
        total = len(h2h_matches)
        home_win_rate = home_wins / total if total > 0 else 0.33
        
        avg_home_goals = sum(home_goals) / len(home_goals) if home_goals else 1.3
        avg_away_goals = sum(away_goals) / len(away_goals) if away_goals else 1.3
        
        key_findings = []
        pattern_type = "均衡交锋"
        
        if home_win_rate > 0.7:
            pattern_type = "主队占优"
            key_findings.append(f"主队交锋胜率达{home_win_rate:.0%}")
        elif (1 - home_win_rate - (draws/total if total else 0)) > 0.7:
            pattern_type = "客队占优"
            key_findings.append(f"客队交锋胜率显著")
        elif draws / total > 0.4:
            pattern_type = "平局高发"
            key_findings.append("交锋平局比例高")
        
        if avg_home_goals + avg_away_goals > 3.0:
            key_findings.append("交锋进球较多")
        elif avg_home_goals + avg_away_goals < 2.0:
            key_findings.append("交锋进球偏少")
        
        recommendation = "参考交锋模式选择玩法"
        if pattern_type == "平局高发":
            recommendation = "优先考虑平局相关玩法"
        elif pattern_type == "主队占优":
            recommendation = "主队优势明显，考虑主胜相关"
        elif pattern_type == "客队占优":
            recommendation = "客队交锋占优，关注客队机会"
        
        return HeadToHeadPattern(
            pattern_type=pattern_type,
            match_count=total,
            win_rate=home_win_rate,
            avg_goals_home=avg_home_goals,
            avg_goals_away=avg_away_goals,
            key_findings=key_findings,
            recommendation=recommendation
        )
    
    @staticmethod
    def analyze_odds_dynamics(
        opening_odds: Dict[str, float],
        current_odds: Dict[str, float],
        time_elapsed_hours: float = 24.0
    ) -> OddsDynamics:
        """
        分析赔率动态变化
        
        Args:
            opening_odds: 初始赔率
            current_odds: 当前赔率
            time_elapsed_hours: 经过时间
        
        Returns:
            赔率动态分析结果
        """
        odds_changes = {}
        avg_change = 0.0
        change_count = 0
        
        for key, opening in opening_odds.items():
            if key in current_odds:
                change = current_odds[key] - opening
                odds_changes[key] = change
                avg_change += abs(change)
                change_count += 1
        
        if change_count > 0:
            avg_change /= change_count
        
        # 判断走势
        if avg_change > 0.3:
            trend = OddsMovement.SHARP_UP
        elif avg_change > 0.1:
            trend = OddsMovement.UP
        elif avg_change < -0.3:
            trend = OddsMovement.SHARP_DOWN
        elif avg_change < -0.1:
            trend = OddsMovement.DOWN
        else:
            trend = OddsMovement.STABLE
        
        # 计算市场情绪
        market_sentiment = {}
        recommended_bet = None
        max_value = 0.0
        
        for key in opening_odds.keys():
            if key in current_odds and key in odds_changes:
                change = odds_changes[key]
                opening = opening_odds[key]
                current = current_odds[key]
                
                if opening > 0:
                    value_score = (opening - current) / opening  # 赔率下降表示看好
                    market_sentiment[key] = value_score
                    
                    if value_score > max_value:
                        max_value = value_score
                        recommended_bet = key
        
        confidence = "高" if abs(avg_change) > 0.2 else "中" if abs(avg_change) > 0.1 else "低"
        
        return OddsDynamics(
            opening_odds=opening_odds,
            current_odds=current_odds,
            odds_changes=odds_changes,
            movement_trend=trend,
            market_sentiment=market_sentiment,
            recommended_bet=recommended_bet,
            confidence=confidence
        )


class EnhancedHistoricalAnalyzer:
    """增强的历史数据分析器"""
    
    @staticmethod
    def comprehensive_historical_analysis(
        home_recent: Optional[List[Dict]] = None,
        away_recent: Optional[List[Dict]] = None,
        h2h_matches: Optional[List[Dict]] = None,
        opening_odds: Optional[Dict[str, float]] = None,
        current_odds: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        综合历史数据分析
        
        Args:
            home_recent: 主队近期比赛
            away_recent: 客队近期比赛
            h2h_matches: 历史交锋
            opening_odds: 初始赔率
            current_odds: 当前赔率
        
        Returns:
            综合分析结果
        """
        result = {
            "success": True,
            "generated_at": datetime.now().isoformat(),
        }
        
        # 近期表现分析
        if home_recent:
            result["home_form"] = HistoricalFeatureExtractor.extract_features_from_recent(
                home_recent, "home"
            )
        if away_recent:
            result["away_form"] = HistoricalFeatureExtractor.extract_features_from_recent(
                away_recent, "away"
            )
        
        # 历史交锋分析
        if h2h_matches:
            h2h_analysis = HistoricalFeatureExtractor.analyze_head_to_head(
                h2h_matches, "home", "away"
            )
            result["head_to_head"] = {
                "pattern_type": h2h_analysis.pattern_type,
                "match_count": h2h_analysis.match_count,
                "home_win_rate": round(h2h_analysis.win_rate * 100, 2),
                "avg_goals_home": round(h2h_analysis.avg_goals_home, 2),
                "avg_goals_away": round(h2h_analysis.avg_goals_away, 2),
                "key_findings": h2h_analysis.key_findings,
                "recommendation": h2h_analysis.recommendation
            }
        
        # 赔率动态分析
        if opening_odds and current_odds:
            odds_analysis = HistoricalFeatureExtractor.analyze_odds_dynamics(
                opening_odds, current_odds
            )
            result["odds_dynamics"] = {
                "movement_trend": odds_analysis.movement_trend.value,
                "recommended_bet": odds_analysis.recommended_bet,
                "confidence": odds_analysis.confidence,
                "market_sentiment": {
                    k: round(v * 100, 1) for k, v in odds_analysis.market_sentiment.items()
                }
            }
        
        # 综合建议
        recommendations = []
        if "home_form" in result:
            if result["home_form"]["win_rate"] > 0.7:
                recommendations.append("主队近期状态佳")
        if "away_form" in result:
            if result["away_form"]["win_rate"] > 0.7:
                recommendations.append("客队近期表现强势")
        if "head_to_head" in result:
            recommendations.append(result["head_to_head"]["recommendation"])
        
        result["key_recommendations"] = recommendations
        
        return result
