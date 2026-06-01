"""
MCP Server Betting Tools - Betting recommendation and slip generation tools.
"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from .analysis_tools import get_analysis_engine
from .data_tools import get_cached_matches, set_cached_matches
from .helpers import _calculate_kelly_stake, raise_tool_error, _to_json
from .rules_tools import RulesEngine
from lottery_mcp.analysis.strategy import MatchProfiler, StrategySelector, StrategyConfig
from lottery_mcp.betting.value import ValueDiscoveryEngine, ValueDiscoveryResult
from lottery_mcp.betting.ai import AIAnalyzer, AIInsight
from lottery_mcp.models import (
    GenerateBettingSlipsInput,
    GenerateKellySlipsInput,
    GetBettingStatsInput,
    GetDailyRecommendationsInput,
    TrackBettingRecordInput,
    ValidateParlayInput,
    ValidateBetInput,
)

logger = logging.getLogger("lottery_mcp")


# ============================================================
# Betting Engine
# ============================================================

class BettingEngine:
    """投注推荐引擎"""

    def __init__(self):
        self._betting_history: List[Dict] = []

    def record_bet(self, match_id: str, selection: str, odds: float,
                   stake: float, won: bool, profit: float) -> Dict[str, Any]:
        """记录单次投注结果"""
        record = {
            "match_id": match_id,
            "selection": selection,
            "odds": odds,
            "stake": stake,
            "won": won,
            "profit": profit,
            "timestamp": datetime.now().isoformat(),
        }
        self._betting_history.append(record)
        logger.info(f"[投注记录] 比赛: {match_id}, 选项: {selection}, "
                     f"金额: {stake}, 盈亏: {profit}, 结果: {'赢' if won else '输'}")
        return record

    def get_betting_stats(self, period: str = "all") -> Dict[str, Any]:
        """获取投注统计摘要"""
        records = self._filter_by_period(period)

        if not records:
            return {
                "total_bets": 0,
                "total_stake": 0.0,
                "total_profit": 0.0,
                "win_rate": 0.0,
                "max_win_streak": 0,
                "max_lose_streak": 0,
                "avg_profit": 0.0,
                "roi": 0.0,
                "roi_percentage": "0.00%",
                "avg_odds": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "expected_value": 0.0,
                "average_bet_size": 0.0,
                "recent_results": [],
            }

        total_bets = len(records)
        total_stake = sum(r["stake"] for r in records)
        total_profit = sum(r["profit"] for r in records)
        wins = sum(1 for r in records if r["won"])
        win_rate = round(wins / total_bets * 100, 2) if total_bets > 0 else 0.0
        avg_profit = round(total_profit / total_bets, 2) if total_bets > 0 else 0.0

        # 计算最大连赢和最大连败
        max_win_streak = 0
        max_lose_streak = 0
        current_win_streak = 0
        current_lose_streak = 0
        for r in records:
            if r["won"]:
                current_win_streak += 1
                current_lose_streak = 0
            else:
                current_lose_streak += 1
                current_win_streak = 0
            max_win_streak = max(max_win_streak, current_win_streak)
            max_lose_streak = max(max_lose_streak, current_lose_streak)

        # ========== ROI 统计指标 ==========
        
        # ROI (投资回报率) = 总利润 / 总投入 * 100%
        roi = total_profit / total_stake if total_stake > 0 else 0.0
        roi_percentage = f"{roi * 100:.2f}%"

        # 平均赔率
        avg_odds = sum(r["odds"] for r in records) / total_bets if total_bets > 0 else 0.0
        avg_odds = round(avg_odds, 2)

        # 盈亏比 (Profit Factor) = 总盈利 / 总亏损（取绝对值）
        total_winning = sum(r["profit"] for r in records if r["won"])
        total_losing = abs(sum(r["profit"] for r in records if not r["won"]))
        profit_factor = total_winning / total_losing if total_losing > 0 else float('inf')
        profit_factor = round(profit_factor, 2)

        # 夏普比率 (简化版，假设无风险收益率为0)
        # Sharpe Ratio = 平均收益 / 收益标准差
        profits = [r["profit"] for r in records]
        if len(profits) >= 2:
            mean_profit = sum(profits) / len(profits)
            variance = sum((p - mean_profit) ** 2 for p in profits) / len(profits)
            std_dev = variance ** 0.5
            sharpe_ratio = mean_profit / std_dev if std_dev > 0 else 0.0
            sharpe_ratio = round(sharpe_ratio, 2)
        else:
            sharpe_ratio = 0.0

        # 期望值 (Expected Value) per bet
        # EV = (胜率 × 平均赢金额) - (败率 × 平均输金额)
        if wins > 0:
            avg_win_amount = total_winning / wins
        else:
            avg_win_amount = 0.0
        losses = total_bets - wins
        if losses > 0:
            avg_lose_amount = total_losing / losses
        else:
            avg_lose_amount = 0.0
        expected_value = (wins / total_bets) * avg_win_amount - (losses / total_bets) * avg_lose_amount
        expected_value = round(expected_value, 2)

        # 平均投注金额
        average_bet_size = round(total_stake / total_bets, 2) if total_bets > 0 else 0.0

        # 最近10条记录
        recent_results = records[-10:] if len(records) > 10 else list(records)

        return {
            "total_bets": total_bets,
            "total_stake": round(total_stake, 2),
            "total_profit": round(total_profit, 2),
            "win_rate": win_rate,
            "max_win_streak": max_win_streak,
            "max_lose_streak": max_lose_streak,
            "avg_profit": avg_profit,
            # ROI 统计指标
            "roi": round(roi, 4),
            "roi_percentage": roi_percentage,
            "avg_odds": avg_odds,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe_ratio,
            "expected_value": expected_value,
            "average_bet_size": average_bet_size,
            "recent_results": recent_results,
        }

    def clear_history(self) -> Dict[str, Any]:
        """清空投注记录"""
        count = len(self._betting_history)
        self._betting_history.clear()
        logger.info(f"[投注记录] 已清空 {count} 条记录")
        return {"cleared_count": count, "message": f"已清空 {count} 条投注记录"}

    def _filter_by_period(self, period: str) -> List[Dict]:
        """根据周期筛选投注记录"""
        if period == "all":
            return list(self._betting_history)

        now = datetime.now()
        filtered = []
        for record in self._betting_history:
            try:
                ts = datetime.fromisoformat(record["timestamp"])
                if period == "today":
                    if ts.date() == now.date():
                        filtered.append(record)
                elif period == "week":
                    from datetime import timedelta
                    week_ago = now - timedelta(days=7)
                    if ts >= week_ago:
                        filtered.append(record)
            except (ValueError, KeyError):
                continue
        return filtered

    # ----------------------------------------------------------
    # 综合评分辅助方法
    # ----------------------------------------------------------

    @staticmethod
    def _sigmoid(x: float) -> float:
        """计算 sigmoid 函数，带溢出保护"""
        if x >= 20:
            return 1.0
        if x <= -20:
            return 0.0
        return 1.0 / (1.0 + math.exp(-x))

    def _calculate_ev_score(self, analysis: Dict[str, Any]) -> float:
        """计算 EV（期望值）评分

        EV = (隐含概率 × 赔率 - 1) × 100
        EV_score = sigmoid(EV / 10) × 100（归一化到0-100）

        从 recommendation 中获取推荐选项及其概率，
        从 match_data.odds 中获取对应赔率。
        """
        rec = analysis.get("recommendation", {})
        match_data = analysis.get("match_data", {})
        odds = match_data.get("odds", {})

        pick = rec.get("pick", "")
        model_prob = rec.get("probability", 0.33)

        # 根据推荐选项获取对应赔率
        if pick == "主胜":
            market_odds = odds.get("home_win", odds.get("win", 2.0))
        elif pick == "平局":
            market_odds = odds.get("draw", 2.0)
        elif pick == "客胜":
            market_odds = odds.get("away_win", odds.get("lose", 2.0))
        else:
            market_odds = 2.0

        # 计算隐含概率（使用竞彩官方固定返还率 70%）
        home_o = odds.get("home_win", odds.get("win", 2.0))
        draw_o = odds.get("draw", 2.0)
        away_o = odds.get("away_win", odds.get("lose", 2.0))

        # 竞彩足球固定返还率 70%（不使用动态计算）
        return_rate = 0.70

        # 隐含概率 = 1 / 赔率 × 返还率
        implied_prob = (1.0 / market_odds * return_rate) if market_odds > 0 else 0.5

        # EV = (隐含概率 × 赔率 - 1) × 100
        ev = (implied_prob * market_odds - 1.0) * 100

        # EV_score = sigmoid(EV / 10) × 100
        ev_score = self._sigmoid(ev / 10.0) * 100

        return round(ev_score, 2), round(ev, 2)

    def _calculate_model_consistency(self, analysis: Dict[str, Any]) -> float:
        """计算模型一致性评分

        从 statistical_models 中提取各模型（泊松/Elo/xG）的胜平负概率，
        计算各模型之间的标准差。
        标准差越小 = 模型越一致 = 信心越高。
        consistency_score = (1 - std_dev / max_std) × 100

        max_std 设为 0.20（完全不一致时的理论最大标准差）。
        """
        models = analysis.get("statistical_models", {})
        if not models:
            return 50.0  # 无模型数据时返回中性分

        # 收集各模型的胜平负概率
        model_probs = []
        for model_name in ("poisson", "elo", "xg"):
            model = models.get(model_name)
            if model and "win_prob" in model:
                model_probs.append({
                    "name": model_name,
                    "win": model.get("win_prob", 0.33),
                    "draw": model.get("draw_prob", 0.33),
                    "lose": model.get("lose_prob", 0.33),
                })

        if len(model_probs) < 2:
            # 只有一个模型，无法计算一致性，返回中性分
            return 50.0

        # 计算各结果方向上模型概率的标准差，取平均
        max_std = 0.20
        std_devs = []
        for outcome in ("win", "draw", "lose"):
            probs = [m[outcome] for m in model_probs]
            mean = sum(probs) / len(probs)
            variance = sum((p - mean) ** 2 for p in probs) / len(probs)
            std_devs.append(math.sqrt(variance))

        avg_std = sum(std_devs) / len(std_devs)

        # consistency_score = (1 - avg_std / max_std) × 100
        consistency = (1.0 - min(avg_std / max_std, 1.0)) * 100

        return round(consistency, 2)

    @staticmethod
    def _get_risk_multiplier(risk_level: str) -> float:
        """根据风险等级返回调整系数"""
        risk_map = {"低": 1.0, "中": 0.8, "高": 0.5}
        return risk_map.get(risk_level, 0.8)

    def _calculate_fundamentals_modifier(self, fundamentals: Dict) -> float:
        """根据基本面数据计算评分修正系数 (0.7 ~ 1.3)"""
        if not fundamentals:
            return 1.0

        modifier = 1.0

        # 排名差：排名差距越大，强队推荐越有信心
        home_rank = fundamentals.get('home_rank', 0)
        away_rank = fundamentals.get('away_rank', 0)
        if home_rank > 0 and away_rank > 0:
            rank_diff = away_rank - home_rank  # 正值=主队排名更高
            modifier += rank_diff * 0.01  # 每个排名差+1%
            modifier = max(0.7, min(1.3, modifier))

        # 近期胜率：胜率高的队伍更可信
        home_wr = fundamentals.get('home_win_rate', 0)
        away_wr = fundamentals.get('away_win_rate', 0)
        if home_wr > 0.5:
            modifier += 0.05
        if away_wr > 0.5:
            modifier -= 0.05

        # 伤停：伤停多的队伍降低信心
        home_inj = fundamentals.get('home_injury_count', 0)
        away_inj = fundamentals.get('away_injury_count', 0)
        modifier -= home_inj * 0.02
        modifier += away_inj * 0.02  # 对手伤停多=利好

        # 净胜球
        home_ng = fundamentals.get('home_net_goal', 0)
        away_ng = fundamentals.get('away_net_goal', 0)
        modifier += (home_ng - away_ng) * 0.01

        return max(0.7, min(1.3, modifier))

    def _calculate_final_score(self, analysis: Dict[str, Any], fundamentals: Dict = None,
                                strategy: StrategyConfig = None) -> Dict[str, Any]:
        """计算综合评分

        final_score = EV_score × ev_weight + model_consistency × consistency_weight + risk_adjusted × risk_weight
        权重由策略动态决定，无策略时默认 0.4/0.3/0.3
        """
        combined_score = analysis.get("combined_score", 0)
        risk_level = analysis.get("risk_level", "中")

        # 1. EV 评分
        ev_score, ev_raw = self._calculate_ev_score(analysis)

        # 2. 模型一致性
        model_consistency = self._calculate_model_consistency(analysis)

        # 3. 风险调整评分
        risk_multiplier = self._get_risk_multiplier(risk_level)
        risk_adjusted = combined_score * risk_multiplier

        # 根据策略动态计算权重
        if strategy:
            ev_weight = strategy.model_weight * 0.5 + strategy.market_odds_weight * 0.5
            consistency_weight = strategy.fundamentals_weight
            risk_weight = strategy.jc_odds_weight
        else:
            ev_weight = 0.4
            consistency_weight = 0.3
            risk_weight = 0.3

        # 综合评分
        final_score = ev_score * ev_weight + model_consistency * consistency_weight + risk_adjusted * risk_weight

        # 基本面修正
        fundamentals_modifier = 1.0
        if fundamentals:
            fundamentals_modifier = self._calculate_fundamentals_modifier(fundamentals)
            final_score = final_score * fundamentals_modifier

        return {
            "final_score": round(final_score, 2),
            "ev_score": ev_score,
            "ev_raw": ev_raw,
            "model_consistency": model_consistency,
            "risk_adjusted": round(risk_adjusted, 2),
            "risk_multiplier": risk_multiplier,
            "combined_score": combined_score,
            "fundamentals_modifier": round(fundamentals_modifier, 3),
            "weights": {
                "ev_score": round(ev_weight, 3),
                "model_consistency": round(consistency_weight, 3),
                "risk_adjusted": round(risk_weight, 3),
            },
        }

    async def get_daily_recommendations(self, count: int = 50, strategy: str = "balanced",
                                  min_confidence: float = 30.0, 
                                  lottery_type: str = "竞彩足球") -> List[Dict[str, Any]]:
        """获取每日推荐

        使用 EV（期望值）加权 + 模型一致性校验的综合评分算法：
        final_score = EV_score × 0.4 + model_consistency × 0.3 + risk_adjusted × 0.3

        评分维度说明：
        - EV_score: 基于赔率隐含概率与模型概率的偏差，衡量投注价值
        - model_consistency: 多模型（泊松/Elo/xG）预测结果的一致性
        - risk_adjusted: 综合评分经风险等级调整后的得分

        每场比赛生成多种玩法推荐（胜平负、让球胜平负、比分、总进球、半全场），
        按综合评分排序后返回 top N。
        """
        matches = get_cached_matches()
        if not matches:
            # 缓存为空时，自动获取数据并设置缓存
            try:
                from lottery_mcp.data.fetcher import fetch_today_matches
                matches = fetch_today_matches()
                if matches:
                    set_cached_matches(matches)
                else:
                    raise ValueError("获取比赛数据为空")
            except Exception as e:
                raise ValueError(f"数据缓存为空且自动获取失败: {e}，请手动调用 lottery_fetch_today_matches 获取比赛数据")
        
        analysis_engine = get_analysis_engine()
        recommendations = []

        # 五大玩法
        PLAY_TYPES = ["胜平负", "让球胜平负", "比分", "总进球", "半全场"]
        
        for match in matches:
            match_id = match.get("match_id", "")
            analysis = await analysis_engine.analyze_match(match_id, lottery_type)
            
            # 获取基本面数据（排名/伤停/战绩）
            fundamentals = {}
            try:
                from lottery_mcp.data.sources import FreeDataSourceManager
                mgr = FreeDataSourceManager()

                tables_result = mgr.get_match_tables(match_id)
                tables_data = tables_result.get('data', {})
                home_tables = tables_data.get('homeTables', {}).get('total', {})
                away_tables = tables_data.get('awayTables', {}).get('total', {})
                
                form_result = mgr.get_match_recent_form(match_id)
                form_data = form_result.get('data', {})
                home_form = form_data.get('home', {}).get('statistics', {})
                away_form = form_data.get('away', {}).get('statistics', {})
                
                injury_result = mgr.get_injury_suspension(match_id)
                injury_data = injury_result.get('data', {})
                home_injury = injury_data.get('home', [])
                away_injury = injury_data.get('away', [])
                
                fundamentals = {
                    'home_rank': int(home_tables.get('ranking', 0) or 0),
                    'away_rank': int(away_tables.get('ranking', 0) or 0),
                    'home_points': int(home_tables.get('points', 0) or 0),
                    'away_points': int(away_tables.get('points', 0) or 0),
                    'home_win_rate': float(str(home_form.get('winProbability', '0%')).replace('%', '')) / 100.0,
                    'away_win_rate': float(str(away_form.get('winProbability', '0%')).replace('%', '')) / 100.0,
                    'home_injury_count': len(home_injury) if isinstance(home_injury, list) else 0,
                    'away_injury_count': len(away_injury) if isinstance(away_injury, list) else 0,
                    'home_net_goal': int(home_form.get('netGoal', 0) or 0),
                    'away_net_goal': int(away_form.get('netGoal', 0) or 0),
                }
            except Exception as e:
                fundamentals = {}
            
            # 策略引擎：根据比赛特征动态选择策略
            try:
                profile = MatchProfiler.profile(match)
                match_strategy = StrategySelector.select(profile)
            except Exception as e:
                profile = None
                match_strategy = None
            
            # AI分析
            ai_insight = None
            try:
                ai_insight = AIAnalyzer.analyze_match(match, profile)
            except Exception:
                pass
            
            # 从分析结果和缓存数据中提取公共字段
            rec = analysis.get("recommendation", {})
            match_data = analysis.get("match_data", {})
            # match_data 包含嵌套的 had/hhad/crs/ttg/hafu 和扁平的 odds
            # 将两者合并，确保玩法推荐方法能同时访问
            match_odds = dict(match_data.get("odds", {}))
            for nested_key in ("had", "hhad", "crs", "ttg", "hafu"):
                if nested_key in match_data and nested_key not in match_odds:
                    match_odds[nested_key] = match_data[nested_key]
            
            home_team = match_data.get("home_team", match.get("home_team", ""))
            away_team = match_data.get("away_team", match.get("away_team", ""))
            match_name = f"{home_team} vs {away_team}" if home_team and away_team else match_id
            league = match_data.get("league", match.get("league", ""))
            match_time = match_data.get("match_time", match.get("match_time", ""))
            
            # 泊松分析结果（用于比分、总进球、半全场推荐）
            poisson = analysis.get("statistical_models", {}).get("poisson", {})
            
            # 为每种玩法生成推荐（包含所有选项，支持双选/多选）
            for play_type in PLAY_TYPES:
                play_rec = self._calculate_play_recommendation(
                    play_type, rec, match_odds, poisson, analysis,
                    strategy=match_strategy, match_data=match
                )
                if play_rec is None:
                    continue
                
                # 获取所有选项（用于双选/多选）
                all_choices = play_rec.get("all_choices", [])
                
                # 为每个选项生成一条推荐
                for choice in all_choices:
                    choice_confidence = choice.get("score", 50)
                    if choice_confidence < min_confidence:
                        continue
                    
                    # 计算综合评分
                    scoring = self._calculate_final_score(analysis, fundamentals=fundamentals, strategy=match_strategy)
                    
                    # 玩法特定的评分调整
                    play_score_modifier = self._get_play_score_modifier(
                        play_type, play_rec, strategy
                    )
                    # 根据选项价值调整评分
                    value_modifier = choice.get("value_ratio", 1.0)
                    adjusted_final_score = round(
                        scoring["final_score"] * play_score_modifier * value_modifier, 2
                    )
                    
                    # 获取价值发现信息
                    choice_value_discovery = choice.get("value_discovery", {})
                    
                    recommendations.append({
                        "match_id": match_id,
                        "play_type": play_type,
                        "match": match_name,
                        "home_team": home_team,
                        "away_team": away_team,
                        "league": league,
                        "match_time": match_time,
                        "selection": choice["label"],
                        "odds": choice.get("odds", 0),
                        "confidence": "高" if choice_confidence >= 70 else "中" if choice_confidence >= 50 else "低",
                        "confidence_score": round(choice_confidence, 1),
                        "probability": choice.get("model_prob", 0),
                        "model_prob": choice.get("model_prob", 0),
                        "ev": choice.get("ev", 0),
                        "final_score": adjusted_final_score,
                        "combined_score": analysis.get("combined_score", 0),
                        "agreement_level": analysis.get("agreement_level", "未知"),
                        "recommendation": {
                            **play_rec,
                            "selection": choice["label"],
                            "odds": choice.get("odds", 0),
                            "probability": choice.get("model_prob", 0),
                            "confidence_score": round(choice_confidence, 1),
                            "ev": choice.get("ev", 0),
                            "value_ratio": choice.get("value_ratio", 1.0),
                        },
                        "risk_level": analysis.get("risk_level", "中"),
                        "fundamentals": fundamentals,
                        "scoring_breakdown": {
                            "ev_score": scoring["ev_score"],
                            "ev_raw": scoring["ev_raw"],
                            "model_consistency": scoring["model_consistency"],
                            "risk_adjusted": scoring["risk_adjusted"],
                            "risk_multiplier": scoring["risk_multiplier"],
                            "fundamentals_modifier": scoring.get("fundamentals_modifier", 1.0),
                            "play_modifier": play_score_modifier,
                            "value_modifier": value_modifier,
                            "weights": scoring.get("weights", {
                                "ev_score": 0.4,
                                "model_consistency": 0.3,
                                "risk_adjusted": 0.3,
                            }),
                        },
                        "match_profile": {
                            "tags": profile.tags if profile else [],
                            "league_tier": profile.league_tier.value if profile else "未知",
                            "odds_pattern": profile.odds_pattern.value if profile else "未知",
                            "data_quality": profile.data_quality.value if profile else "未知",
                        } if profile else {},
                        "strategy_name": match_strategy.strategy_name if match_strategy else "默认",
                        "value_rating": choice_value_discovery.get("value_rating", "N"),
                        "value_score": choice_value_discovery.get("overall_value_score", 0),
                        "ai_insight": {
                            "match_summary": ai_insight.match_summary if ai_insight else "",
                            "key_factors": ai_insight.key_factors if ai_insight else [],
                            "odds_analysis": ai_insight.odds_analysis if ai_insight else "",
                            "value_opportunities": ai_insight.value_opportunities if ai_insight else [],
                            "risk_assessment": ai_insight.risk_assessment if ai_insight else "",
                            "risk_factors": ai_insight.risk_factors if ai_insight else [],
                            "strategy_advice": ai_insight.strategy_advice if ai_insight else "",
                            "recommended_plays": ai_insight.recommended_plays if ai_insight else [],
                            "confidence_level": ai_insight.confidence_level if ai_insight else "中",
                            "betting_suggestion": ai_insight.betting_suggestion if ai_insight else "",
                            "suggested_stake": ai_insight.suggested_stake if ai_insight else "",
                            "reasoning": ai_insight.reasoning if ai_insight else "",
                        } if ai_insight else {},
                    })
        
        # 按综合评分排序
        recommendations.sort(key=lambda x: x["final_score"], reverse=True)
        
        # 如果count足够大，返回所有推荐（支持双选/多选）
        # 否则只返回前count个（用于精简展示）
        if count >= 500:
            return recommendations
        return recommendations[:count]

    def _calculate_play_recommendation(self, play_type: str, base_rec: Dict,
                                        match_odds: Dict, poisson: Dict,
                                        analysis: Dict,
                                        strategy: StrategyConfig = None,
                                        match_data: Dict = None) -> Optional[Dict[str, Any]]:
        """为指定玩法计算推荐

        Args:
            play_type: 玩法名称（胜平负/让球胜平负/比分/总进球/半全场）
            base_rec: analyze_match 返回的 recommendation
            match_odds: 赔率数据
            poisson: 泊松分析结果
            analysis: 完整分析结果
            strategy: 动态策略配置
            match_data: 完整比赛数据（用于价值发现引擎）

        Returns:
            推荐字典，如果该玩法无数据则返回 None
        """
        if play_type == "胜平负":
            return self._calc_spf_recommendation(base_rec, match_odds, strategy=strategy, match_data=match_data)
        elif play_type == "让球胜平负":
            return self._calc_rqspf_recommendation(match_odds, base_rec)
        elif play_type == "比分":
            return self._calc_bf_recommendation(poisson, match_odds)
        elif play_type == "总进球":
            return self._calc_zjq_recommendation(poisson, match_odds)
        elif play_type == "半全场":
            return self._calc_bqc_recommendation(poisson, match_odds)
        return None

    def _calc_spf_recommendation(self, base_rec: Dict,
                                   match_odds: Dict,
                                   strategy: StrategyConfig = None,
                                   match_data: Dict = None) -> Optional[Dict[str, Any]]:
        """胜平负玩法推荐 - 支持价值投注逻辑"""
        had = match_odds.get("had", {})
        if not had:
            # 尝试从扁平化键名构建
            w = match_odds.get("win") or match_odds.get("had_w")
            d = match_odds.get("draw") or match_odds.get("had_d")
            l = match_odds.get("lose") or match_odds.get("had_l")
            if w and d and l:
                had = {"win": w, "draw": d, "lose": l}
        if not had:
            return None
        try:
            w = float(had.get("win", 0))
            d = float(had.get("draw", 0))
            l = float(had.get("lose", 0))
            if w <= 0 or d <= 0 or l <= 0:
                return None
        except (ValueError, TypeError):
            return None

        # 获取概率数据
        implied_probs = base_rec.get("implied_probs", {})
        
        # 从base_rec反推模型概率（融合概率 = 0.6*模型 + 0.4*隐含）
        # base_rec["probability"]是融合后的概率，base_rec["pick"]是推荐选项
        model_probs = {}
        fused_prob = base_rec.get("probability", 0.33)
        pick = base_rec.get("pick", "主胜")
        
        if implied_probs and len(implied_probs) >= 3:
            # 对每个选项，用融合概率和隐含概率反推模型概率
            for label in ["主胜", "平局", "客胜"]:
                if label in implied_probs:
                    implied_p = implied_probs[label]
                    # 如果这是pick选项，用fused_prob；否则用implied_p作为近似
                    if label == pick:
                        # fused = 0.6 * model + 0.4 * implied
                        model_p = (fused_prob - 0.4 * implied_p) / 0.6
                        model_probs[label] = max(0.05, min(0.95, model_p))
                    else:
                        # 非pick选项，假设模型概率与隐含概率相近（保守估计）
                        # 或者使用隐含概率作为上界
                        model_probs[label] = implied_p * 0.9  # 保守估计
                else:
                    model_probs[label] = 0.33
        else:
            # 无隐含概率时，使用base_rec中的数据
            pick_label = base_rec.get("pick", "主胜")
            best_model_prob = base_rec.get("risk_assessment", {}).get("model_prob", 0.33)
            remaining = max(0, 1.0 - best_model_prob)
            other_prob = max(0.01, remaining / 2) if remaining > 0 else 0.33
            model_probs = {}
            for label in ["主胜", "平局", "客胜"]:
                if label == pick_label:
                    model_probs[label] = best_model_prob
                else:
                    model_probs[label] = other_prob
        
        # 计算每个选项的价值（EV = 模型概率 * 赔率 - 1）
        # 以及价值比率（模型概率 / 隐含概率）
        odds_map = {"主胜": w, "平局": d, "客胜": l}
        
        choices = []
        for label in ["主胜", "平局", "客胜"]:
            model_p = model_probs.get(label, 0.33)
            implied_p = implied_probs.get(label, 0.33)
            odds = odds_map[label]
            
            # 计算EV（期望值）
            ev = model_p * odds - 1.0
            
            # 计算价值比率（>1表示有价值）
            value_ratio = model_p / implied_p if implied_p > 0 else 1.0
            
            # 低赔率惩罚（基于策略动态调整）
            if strategy:
                low_odds_penalty = 1.0
                if odds > 0 and odds < strategy.low_odds_threshold:
                    if strategy.low_odds_handling == "penalize":
                        if odds < 1.3:
                            low_odds_penalty = 0.3
                        elif odds < 1.5:
                            low_odds_penalty = 0.5
                        elif odds < 1.8:
                            low_odds_penalty = 0.8
                    elif strategy.low_odds_handling == "look_for_handicap":
                        low_odds_penalty = 0.6
                    elif strategy.low_odds_handling == "avoid":
                        low_odds_penalty = 0.2
                    # "accept" 不做任何调整
            else:
                # 无策略时使用默认
                if odds < 1.5:
                    low_odds_penalty = 0.5
                elif odds < 1.8:
                    low_odds_penalty = 0.8
                else:
                    low_odds_penalty = 1.0
            
            # 综合得分 = 模型概率 * 价值比率 * 低赔率惩罚 * 100
            score = model_p * value_ratio * low_odds_penalty * 100
            
            choices.append({
                "label": label,
                "odds": odds,
                "model_prob": model_p,
                "implied_prob": implied_p,
                "ev": ev,
                "value_ratio": value_ratio,
                "score": score,
            })
        
        # 使用价值发现引擎分析每个选项
        for choice in choices:
            model_p = choice.get("model_prob", 0.33)
            odds = choice.get("odds", 0)
            label = choice.get("label", "")
            
            # 准备传递给价值发现引擎的完整比赛数据
            value_match_data = match_data if match_data else match_odds
            
            # 调用价值发现引擎
            value_result = ValueDiscoveryEngine.analyze(
                match_id=match_odds.get("match_id", ""),
                selection=label,
                model_prob=model_p,
                odds=odds,
                match_data=value_match_data,
                profile=None,
                strategy=strategy
            )
            
            # 将价值发现结果添加到 choice
            choice["value_discovery"] = {
                "value_ratio": value_result.value_ratio,
                "expected_value": value_result.expected_value,
                "overall_value_score": value_result.overall_value_score,
                "value_rating": value_result.value_rating,
                "signals": [
                    {
                        "type": s.signal_type.value,
                        "strength": s.strength,
                        "description": s.description
                    }
                    for s in value_result.signals
                ],
                "risk_factors": value_result.risk_factors,
                "confidence_level": value_result.confidence_level,
                "recommendation": value_result.recommendation,
            }
            
            # 使用价值发现评分替代简单评分
            choice["score"] = value_result.overall_value_score
            choice["ev"] = value_result.expected_value
            choice["value_ratio"] = value_result.value_ratio
        
        # 按综合得分排序，选择最有价值的
        choices.sort(key=lambda x: x["score"], reverse=True)
        best = choices[0]
        
        # 如果最佳选项是极低赔率，检查是否有更好的价值选项
        if best["odds"] < 1.3:
            better_value = [c for c in choices if c["odds"] >= 1.5 and c["ev"] > -0.2]
            if better_value:
                better_value.sort(key=lambda x: x["ev"], reverse=True)
                best = better_value[0]
        
        # 价值投注逻辑：如果有多个选项有价值（value_ratio > 1.05），优先推荐高赔率的
        valuable = [c for c in choices if c["value_ratio"] > 1.05 and c["ev"] > 0]
        if len(valuable) >= 2:
            # 在多个有价值选项中，优先推荐赔率更高的（避开低赔率陷阱）
            valuable.sort(key=lambda x: (x["ev"], x["odds"]), reverse=True)
            best = valuable[0]
        
        # 特别处理平局：如果平局有价值且赔率>3.0，即使不是最高分也推荐
        draw_choice = next((c for c in choices if c["label"] == "平局"), None)
        if draw_choice and draw_choice["value_ratio"] > 1.1 and draw_choice["odds"] >= 3.0:
            if best["label"] != "平局":
                # 平局有价值，但当前推荐不是平局，根据赔率决定
                if draw_choice["odds"] > best["odds"] * 1.5:  # 平局赔率显著更高
                    best = draw_choice
        
        # ========== 问题1修复：推荐同质化问题 ==========
        # 标记所有选项的推荐状态，不只是最高概率的
        # 1. 找出概率最高的选项
        prob_best = max(choices, key=lambda x: x.get("model_prob", 0))
        
        # 2. 找出所有有价值选项（VR > 1.1 或 EV > 0）
        value_options = [c for c in choices if c.get("value_ratio", 0) > 1.1 or c.get("ev", 0) > 0]
        ev_best = max(value_options, key=lambda x: x.get("ev", 0)) if value_options else None
        
        # 3. 为每个选项标记推荐状态
        recommended_labels = set()
        recommended_labels.add(best["label"])  # 当前最佳推荐
        
        # 将所有有显著价值的选项加入推荐列表（VR > 1.1 或 EV > 0）
        for choice in value_options:
            vr = choice.get("value_ratio", 0)
            ev = choice.get("ev", 0)
            # 显著价值条件：VR > 1.1 或 EV > 0
            if vr > 1.1 or ev > 0:
                recommended_labels.add(choice["label"])
        
        # 为每个选项添加推荐标记
        for choice in choices:
            is_recommended = choice["label"] in recommended_labels
            is_value = choice.get("value_ratio", 0) > 1.1 or choice.get("ev", 0) > 0
            choice["is_recommended"] = is_recommended
            choice["is_value"] = is_value
            choice["recommendation_type"] = []
            if is_recommended:
                if choice["label"] == best["label"]:
                    choice["recommendation_type"].append("最佳综合")
                if choice.get("value_ratio", 0) > 1.1:
                    choice["recommendation_type"].append("价值选项")
                if choice.get("ev", 0) > 0:
                    choice["recommendation_type"].append("正EV")
                if choice.get("model_prob", 0) == prob_best.get("model_prob", 0):
                    choice["recommendation_type"].append("概率最高")
        
        # ========== 问题2修复：欧指亚盘对比 ==========
        market_comparison = None
        try:
            # 尝试从 match_data 或 match_odds 中获取欧指/亚盘数据
            # 数据可能来自外部API或缓存
            source_data = match_data if match_data else match_odds
            
            # 获取欧指数据（可能在不同字段名下）
            euro_odds_data = source_data.get("european_odds") or source_data.get("euro_odds") or source_data.get("avg_odds") or {}
            asian_data = source_data.get("asian_handicap") or source_data.get("asian") or {}
            
            # 如果没有独立的欧指数据，尝试从 had 数据推断（假设竞彩赔率与欧指有差异）
            jc_had = had  # 竞彩赔率
            
            # 尝试获取欧指平均赔率
            euro_w = euro_odds_data.get("win") if isinstance(euro_odds_data, dict) else None
            euro_d = euro_odds_data.get("draw") if isinstance(euro_odds_data, dict) else None
            euro_l = euro_odds_data.get("lose") if isinstance(euro_odds_data, dict) else None
            
            # 获取亚盘盘口
            handicap = asian_data.get("handicap") or (hhad.get("handicap") if (hhad := match_odds.get("hhad")) else None) or "0"
            
            # 如果有欧指数据，计算对比
            if euro_w and euro_d and euro_l:
                # 计算竞彩与欧指的差异
                diff_w = w - euro_w
                diff_d = d - euro_d
                diff_l = l - euro_l
                
                # 计算百分比差异
                pct_w = (w - euro_w) / euro_w * 100 if euro_w > 0 else 0
                pct_d = (d - euro_d) / euro_d * 100 if euro_d > 0 else 0
                pct_l = (l - euro_l) / euro_l * 100 if euro_l > 0 else 0
                
                # 判断信号
                def get_signal(diff, pct):
                    if diff > 0.1:
                        return "竞彩赔率偏高"
                    elif diff < -0.1:
                        return "竞彩赔率偏低"
                    else:
                        return "正常"
                
                market_comparison = {
                    "jc_vs_euro": {
                        "主胜": {
                            "jc_odds": round(w, 3),
                            "euro_odds": round(euro_w, 3),
                            "diff": round(diff_w, 3),
                            "diff_pct": round(pct_w, 1),
                            "signal": get_signal(diff_w, pct_w)
                        },
                        "平局": {
                            "jc_odds": round(d, 3),
                            "euro_odds": round(euro_d, 3),
                            "diff": round(diff_d, 3),
                            "diff_pct": round(pct_d, 1),
                            "signal": get_signal(diff_d, pct_d)
                        },
                        "客胜": {
                            "jc_odds": round(l, 3),
                            "euro_odds": round(euro_l, 3),
                            "diff": round(diff_l, 3),
                            "diff_pct": round(pct_l, 1),
                            "signal": get_signal(diff_l, pct_l)
                        }
                    },
                    "asian_handicap_line": handicap,
                    "summary": self._generate_market_summary(w, d, l, euro_w, euro_d, euro_l)
                }
            else:
                # 没有欧指数据时，提供基础市场对比信息
                market_comparison = {
                    "jc_odds": {
                        "主胜": round(w, 3),
                        "平局": round(d, 3),
                        "客胜": round(l, 3)
                    },
                    "asian_handicap_line": handicap,
                    "note": "暂无欧指数据对比"
                }
        except Exception as e:
            market_comparison = {
                "error": str(e),
                "note": "市场对比数据获取失败"
            }
        
        # 计算置信度
        confidence_score = min(95, max(30, best["score"]))
        if best["ev"] < 0:
            confidence_score *= 0.5  # 负EV降低置信度
        
        # 确定置信等级
        if confidence_score >= 70:
            confidence = "高"
        elif confidence_score >= 50:
            confidence = "中"
        else:
            confidence = "低"
        
        # 风险评估
        risk_assessment = {
            "ev": round(best["ev"], 3),
            "value_ratio": round(best["value_ratio"], 2),
            "low_odds_warning": best["odds"] < 1.5,
        }

        # 收集所有信号摘要
        signals_summary = []
        for choice in choices:
            vd = choice.get("value_discovery", {})
            for signal in vd.get("signals", []):
                signals_summary.append({
                    "selection": choice.get("label"),
                    "type": signal.get("type"),
                    "strength": signal.get("strength"),
                    "description": signal.get("description"),
                })
        
        return {
            "selection": best["label"],
            "odds": best["odds"],
            "probability": best["model_prob"],
            "confidence": confidence,
            "confidence_score": round(confidence_score, 1),
            "risk_assessment": risk_assessment,
            "implied_probs": implied_probs,
            "all_choices": [{k: round(v, 3) if isinstance(v, float) else v 
                            for k, v in c.items()} for c in choices],
            "recommended_count": len(recommended_labels),
            "recommended_labels": list(recommended_labels),
            "strategy": {
                "name": strategy.strategy_name if strategy else "默认",
                "low_odds_handling": strategy.low_odds_handling if strategy else "penalize",
                "value_threshold": strategy.value_threshold if strategy else 1.05,
            } if strategy else {},
            "value_discovery": {
                "best_rating": best.get("value_discovery", {}).get("value_rating", "N"),
                "best_score": best.get("value_discovery", {}).get("overall_value_score", 0),
                "signals_summary": signals_summary[:5],  # 只保留前5个信号
            },
            "market_comparison": market_comparison,
        }

    def _calc_rqspf_recommendation(self, match_odds: Dict,
                                     base_rec: Dict) -> Optional[Dict[str, Any]]:
        """让球胜平负玩法推荐 - 支持双选/多选"""
        hhad = match_odds.get("hhad", {})
        if not hhad:
            return None
        try:
            w = float(hhad.get("win", 0))
            d = float(hhad.get("draw", 0))
            l = float(hhad.get("lose", 0))
            handicap = hhad.get("handicap", "0")
            if w <= 0 or d <= 0 or l <= 0:
                return None
        except (ValueError, TypeError):
            return None

        # 计算隐含概率
        total_implied = 1/w + 1/d + 1/l
        probs = {
            "让球主胜": (1/w) / total_implied,
            "让球平局": (1/d) / total_implied,
            "让球客胜": (1/l) / total_implied,
        }
        
        odds_map = {"让球主胜": w, "让球平局": d, "让球客胜": l}
        
        # 构建所有选项
        all_choices = []
        for label, prob in probs.items():
            odds = odds_map[label]
            ev = prob * odds - 1.0
            implied_prob = 1.0 / odds if odds > 1 else prob
            value_ratio = prob / implied_prob if implied_prob > 0 else 1.0
            low_odds_penalty = 0.7 if odds < 1.5 else 1.0
            score = prob * low_odds_penalty * 100
            
            all_choices.append({
                "label": f"{label}({handicap})",
                "odds": odds,
                "model_prob": round(prob, 3),
                "implied_prob": round(implied_prob, 3),
                "ev": round(ev, 3),
                "value_ratio": round(value_ratio, 2),
                "score": round(score, 1),
            })
        
        # 排序选最佳
        all_choices.sort(key=lambda x: x["score"], reverse=True)
        best = all_choices[0]
        
        # 置信度
        sorted_p = sorted(probs.values(), reverse=True)
        margin = sorted_p[0] - sorted_p[1]
        confidence_score = min(round((best["model_prob"] * 0.7 + margin * 0.3) * 100, 1), 99.0)
        confidence = "高" if confidence_score >= 65 else "中" if confidence_score >= 50 else "低"

        return {
            "selection": best["label"],
            "odds": best["odds"],
            "probability": best["model_prob"],
            "confidence": confidence,
            "confidence_score": confidence_score,
            "risk_assessment": {
                "level": "低" if best["model_prob"] > 0.45 else ("中" if best["model_prob"] > 0.30 else "高"),
                "detail": f"让球{handicap}，{best['label']}隐含概率最高",
                "handicap": handicap,
            },
            "implied_probs": {k: round(v, 4) for k, v in probs.items()},
            "all_choices": all_choices,
        }

    @staticmethod
    def _generate_market_summary(jc_w: float, jc_d: float, jc_l: float,
                                  euro_w: float, euro_d: float, euro_l: float) -> str:
        """生成市场对比摘要
        
        Args:
            jc_w, jc_d, jc_l: 竞彩主胜、平局、客胜赔率
            euro_w, euro_d, euro_l: 欧指主胜、平局、客胜赔率
            
        Returns:
            市场对比摘要字符串
        """
        if not all([jc_w, jc_d, jc_l, euro_w, euro_d, euro_l]):
            return "数据不完整"
        
        # 计算差异
        diff_w = jc_w - euro_w
        diff_d = jc_d - euro_d
        diff_l = jc_l - euro_l
        
        # 找出最大差异
        diffs = [("主胜", diff_w), ("平局", diff_d), ("客胜", diff_l)]
        max_diff_label, max_diff = max(diffs, key=lambda x: abs(x[1]))
        
        summary_parts = []
        
        # 分析主胜
        if diff_w > 0.1:
            summary_parts.append(f"竞彩主胜({jc_w:.2f})高于欧指({euro_w:.2f})，可能存在价值")
        elif diff_w < -0.1:
            summary_parts.append(f"竞彩主胜({jc_w:.2f})低于欧指({euro_w:.2f})，不建议投注")
        
        # 分析平局
        if diff_d > 0.1:
            summary_parts.append(f"竞彩平局({jc_d:.2f})高于欧指({euro_d:.2f})，平局有价值")
        elif diff_d < -0.1:
            summary_parts.append(f"竞彩平局({jc_d:.2f})低于欧指({euro_d:.2f})")
        
        # 分析客胜
        if diff_l > 0.1:
            summary_parts.append(f"竞彩客胜({jc_l:.2f})高于欧指({euro_l:.2f})，可能存在价值")
        elif diff_l < -0.1:
            summary_parts.append(f"竞彩客胜({jc_l:.2f})低于欧指({euro_l:.2f})，不建议投注")
        
        if not summary_parts:
            return "竞彩赔率与欧指基本一致，无明显价值差异"
        
        return "；".join(summary_parts)

    @staticmethod
    def _fuse_probs(model_probs: Dict[str, float],
                    implied_probs: Dict[str, float],
                    model_weight: float = 0.6) -> Dict[str, float]:
        """融合模型概率与赔率隐含概率

        Args:
            model_probs: 模型计算的概率 {选项: 概率}
            implied_probs: 赔率隐含概率 {选项: 概率}
            model_weight: 模型概率权重（默认0.6，隐含概率权重0.4）

        Returns:
            融合后的概率字典（已归一化）
        """
        implied_weight = 1.0 - model_weight
        fused = {}
        all_keys = set(model_probs.keys()) | set(implied_probs.keys())
        for key in all_keys:
            mp = model_probs.get(key, 0)
            ip = implied_probs.get(key, 0)
            fused[key] = mp * model_weight + ip * implied_weight
        # 归一化
        total = sum(fused.values())
        if total > 0:
            fused = {k: v / total for k, v in fused.items()}
        return fused

    def _calc_bf_recommendation(self, poisson: Dict,
                                  match_odds: Dict) -> Optional[Dict[str, Any]]:
        """比分玩法推荐（融合赔率隐含概率）"""
        # 比分推荐基于泊松模型的最可能比分
        most_likely = poisson.get("most_likely_score", "")
        most_likely_prob = poisson.get("most_likely_score_prob", 0)
        score_probs = poisson.get("score_probabilities", {})

        if not most_likely or most_likely_prob <= 0:
            return None

        # 尝试从赔率获取比分赔率，并计算隐含概率
        # 赔率可能以两种形式存在：
        # 1. 扁平化键: match_odds["crs_2:0"]
        # 2. 嵌套结构: match_odds["crs"]["options"][{"score": "2:0", "odds": 11.5}]
        bf_odds = 0
        implied_score_probs: Dict[str, float] = {}
        flat_key = f"crs_{most_likely}"
        if flat_key in match_odds:
            bf_odds = float(match_odds[flat_key])
        else:
            crs = match_odds.get("crs", {})
            if isinstance(crs, dict) and "options" in crs:
                for opt in crs["options"]:
                    score_val = opt.get("score", "")
                    opt_odds = float(opt.get("odds", 0))
                    if opt_odds > 0:
                        implied_score_probs[score_val] = 1.0 / opt_odds
                    if score_val == most_likely:
                        bf_odds = opt_odds
            elif isinstance(crs, dict):
                bf_odds = float(crs.get(most_likely, 0))
                # 尝试从嵌套字典中提取所有比分赔率的隐含概率
                for k, v in crs.items():
                    try:
                        v_float = float(v)
                        if v_float > 0:
                            implied_score_probs[k] = 1.0 / v_float
                    except (ValueError, TypeError):
                        pass

        # 融合泊松概率与赔率隐含概率
        fused_score_probs = score_probs
        if implied_score_probs:
            fused_score_probs = self._fuse_probs(score_probs, implied_score_probs)
            # 从融合概率中重新确定最可能比分
            most_likely = max(fused_score_probs, key=fused_score_probs.get)
            most_likely_prob = fused_score_probs[most_likely]

        # 置信度基于最可能比分相对于第二名的优势
        confidence_score = self._calc_relative_confidence(
            most_likely_prob, fused_score_probs, min_abs=8.0
        )
        confidence = "高" if confidence_score >= 30 else "中" if confidence_score >= 15 else "低"

        # 如果没有赔率数据，置信度适当降低
        if bf_odds <= 0:
            confidence_score = round(confidence_score * 0.8, 1)
        
        # 构建所有选项（用于双选/多选）
        all_choices = []
        for score, prob in fused_score_probs.items():
            # 获取赔率
            odds = 0
            flat_key = f"crs_{score}"
            if flat_key in match_odds:
                odds = float(match_odds[flat_key])
            else:
                crs = match_odds.get("crs", {})
                if isinstance(crs, dict):
                    # 格式A: {"2:0": 11.5}
                    direct_odds = crs.get(score, 0)
                    if direct_odds and float(direct_odds) > 0:
                        odds = float(direct_odds)
                    # 格式B: {"options": [{"score": "2:0", "odds": 11.5}]}
                    elif "options" in crs:
                        for opt in crs["options"]:
                            if opt.get("score") == score:
                                odds = float(opt.get("odds", 0) or 0)
                                break
            
            ev = prob * odds - 1.0 if odds > 0 else -1.0
            implied_p = 1.0 / odds if odds > 0 else prob
            value_ratio = prob / implied_p if implied_p > 0 else 1.0
            score_val = prob * 100
            
            all_choices.append({
                "label": score,
                "odds": odds,
                "model_prob": round(prob, 4),
                "implied_prob": round(implied_p, 4),
                "ev": round(ev, 3),
                "value_ratio": round(value_ratio, 2),
                "score": round(score_val, 1),
            })
        
        # 按概率排序，取前10个
        all_choices.sort(key=lambda x: x["score"], reverse=True)
        top_choices = all_choices[:10]

        return {
            "selection": most_likely,
            "odds": bf_odds if bf_odds > 0 else 0,
            "probability": round(most_likely_prob, 3),
            "confidence": confidence,
            "confidence_score": confidence_score,
            "risk_assessment": {
                "level": "高" if confidence_score < 15 else ("中" if confidence_score < 30 else "低"),
                "detail": f"融合模型预测最可能比分{most_likely}，概率{round(most_likely_prob*100, 1)}%",
            },
            "alternative_scores": self._get_top_scores(fused_score_probs, most_likely, n=3),
            "all_choices": top_choices,
        }

    def _calc_zjq_recommendation(self, poisson: Dict,
                                   match_odds: Dict) -> Optional[Dict[str, Any]]:
        """总进球玩法推荐

        竞彩总进球官方选项为 0/1/2/3/4/5/6/7+，
        基于泊松分布计算每个总进球数的概率，选择概率最高的选项。
        """
        score_probs = poisson.get("score_probabilities", {})
        if not score_probs:
            return None

        # 从比分概率矩阵计算每个总进球数的概率
        total_goals_probs: Dict[str, float] = {}
        for score_str, prob in score_probs.items():
            try:
                parts = score_str.split(":")
                total = int(parts[0]) + int(parts[1])
            except (ValueError, IndexError):
                continue
            # 官方选项: 0-6 各对应具体数字, 7+ 对应 7 及以上
            label = str(total) if total <= 6 else "7+"
            total_goals_probs[label] = total_goals_probs.get(label, 0) + prob

        if not total_goals_probs:
            return None

        # 选择概率最高的进球数选项
        best_goals = max(total_goals_probs, key=total_goals_probs.get)
        best_prob = total_goals_probs[best_goals]

        # 尝试获取总进球赔率，并计算隐含概率
        # 赔率可能以多种形式存在：
        # 1. 扁平化键: match_odds["ttg_2"] (总进球=2的赔率)
        # 2. 嵌套结构: match_odds["ttg"]["options"][{"goals": "2", "odds": 3.2}]
        # 3. goals_N 键格式: match_odds["ttg"]["goals_2"]
        ttg_odds = 0
        implied_goals_probs: Dict[str, float] = {}
        # 扁平化键
        flat_key = f"ttg_{best_goals}"
        if flat_key in match_odds:
            ttg_odds = float(match_odds[flat_key])
        else:
            ttg = match_odds.get("ttg", {})
            if isinstance(ttg, dict):
                if "options" in ttg:
                    for opt in ttg["options"]:
                        goals_val = str(opt.get("goals", opt.get("value", "")))
                        opt_odds = float(opt.get("odds", 0))
                        if opt_odds > 0:
                            implied_goals_probs[goals_val] = 1.0 / opt_odds
                        if goals_val == best_goals:
                            ttg_odds = opt_odds
                else:
                    ttg_odds = float(ttg.get(f"goals_{best_goals}", ttg.get(best_goals, 0)))
                    # 尝试从嵌套字典中提取所有进球数赔率的隐含概率
                    for k, v in ttg.items():
                        if k.startswith("goals_"):
                            try:
                                v_float = float(v)
                                if v_float > 0:
                                    goals_label = k.replace("goals_", "")
                                    implied_goals_probs[goals_label] = 1.0 / v_float
                            except (ValueError, TypeError):
                                pass

        # 融合泊松概率与赔率隐含概率
        fused_goals_probs = total_goals_probs
        if implied_goals_probs:
            fused_goals_probs = self._fuse_probs(total_goals_probs, implied_goals_probs)
            # 从融合概率中重新确定最可能进球数
            best_goals = max(fused_goals_probs, key=fused_goals_probs.get)
            best_prob = fused_goals_probs[best_goals]

        # 置信度基于相对优势
        confidence_score = self._calc_relative_confidence(
            best_prob, fused_goals_probs, min_abs=10.0
        )
        confidence = "高" if confidence_score >= 30 else "中" if confidence_score >= 15 else "低"

        # 构建所有选项（用于双选/多选）
        all_choices = []
        sorted_goals = sorted(fused_goals_probs.items(), key=lambda x: x[1], reverse=True)
        
        for goals, prob in sorted_goals:
            # 获取赔率
            odds = 0
            flat_key = f"ttg_{goals}"
            if flat_key in match_odds:
                odds = float(match_odds[flat_key])
            else:
                ttg = match_odds.get("ttg", {})
                if isinstance(ttg, dict):
                    odds = float(ttg.get(f"goals_{goals}", ttg.get(goals, 0)))
            
            ev = prob * odds - 1.0 if odds > 0 else -1.0
            implied_p = 1.0 / odds if odds > 0 else prob
            value_ratio = prob / implied_p if implied_p > 0 else 1.0
            score_val = prob * 100
            
            all_choices.append({
                "label": str(goals) if goals != "7+" else "7+",
                "odds": odds,
                "model_prob": round(prob, 4),
                "implied_prob": round(implied_p, 4),
                "ev": round(ev, 3),
                "value_ratio": round(value_ratio, 2),
                "score": round(score_val, 1),
            })
        
        # 确保按概率降序排序（概率高的排前面）
        all_choices.sort(key=lambda x: x["score"], reverse=True)
        
        # 构建备选进球数列表
        alternative_goals = [
            {"goals": g, "probability": round(p, 4)}
            for g, p in sorted_goals[:4] if g != best_goals
        ]

        return {
            "selection": f"{best_goals}" if best_goals != "7+" else "7+",
            "odds": ttg_odds if ttg_odds > 0 else 0,
            "probability": round(best_prob, 3),
            "confidence": confidence,
            "confidence_score": confidence_score,
            "risk_assessment": {
                "level": "高" if confidence_score < 15 else ("中" if confidence_score < 30 else "低"),
                "detail": f"融合模型预测总进球{best_goals}球概率最高({round(best_prob*100,1)}%)",
                "total_goals_probs": {k: round(v, 4) for k, v in sorted_goals},
            },
            "alternative_goals": alternative_goals,
            "all_choices": all_choices,
        }

    def _calc_bqc_recommendation(self, poisson: Dict,
                                   match_odds: Dict) -> Optional[Dict[str, Any]]:
        """半全场玩法推荐"""
        home_expected = poisson.get("home_expected_goals", 1.3)
        away_expected = poisson.get("away_expected_goals", 1.1)
        win_prob = poisson.get("win_prob", 0.33)
        draw_prob = poisson.get("draw_prob", 0.33)
        lose_prob = poisson.get("lose_prob", 0.33)

        if home_expected <= 0 and away_expected <= 0:
            return None

        # 半全场推荐逻辑：基于预期进球和胜平负概率
        # 半场最可能结果 + 全场最可能结果
        home_dominant = win_prob > 0.45
        away_dominant = lose_prob > 0.45
        draw_likely = draw_prob > 0.30

        # 半场预测：预期进球较低时半场更容易平局
        ht_draw_prob = 0.35  # 基础半场平局概率
        if home_expected + away_expected < 2.5:
            ht_draw_prob = 0.45
        elif home_expected + away_expected > 3.5:
            ht_draw_prob = 0.25
        
        # 半场胜负概率（基于全场概率调整）
        ht_home_win = win_prob * 0.6 + draw_prob * 0.2  # 全场主队胜，半场也倾向于主队
        ht_away_win = lose_prob * 0.6 + draw_prob * 0.2
        ht_draw = ht_draw_prob
        
        # 归一化半场概率
        ht_total = ht_home_win + ht_away_win + ht_draw
        ht_home_win /= ht_total
        ht_away_win /= ht_total
        ht_draw /= ht_total
        
        # 全场结果概率
        ft_home_win = win_prob
        ft_draw = draw_prob
        ft_away_win = lose_prob

        # 构建全部9个半全场概率（半场结果-全场结果）
        bqc_probs = {
            # 半场主队胜
            "胜-胜": ht_home_win * ft_home_win * 0.8,      # 半场主胜 -> 全场主胜
            "胜-平": ht_home_win * ft_draw * 0.3,        # 半场主胜 -> 全场平局（被逆转）
            "胜-负": ht_home_win * ft_away_win * 0.1,    # 半场主胜 -> 全场客胜（大逆转）
            # 半场平局
            "平-胜": ht_draw * ft_home_win * 0.5,        # 半场平 -> 全场主胜
            "平-平": ht_draw * ft_draw * 0.8,            # 半场平 -> 全场平
            "平-负": ht_draw * ft_away_win * 0.5,        # 半场平 -> 全场客胜
            # 半场客队胜
            "负-胜": ht_away_win * ft_home_win * 0.1,    # 半场客胜 -> 全场主胜（大逆转）
            "负-平": ht_away_win * ft_draw * 0.3,        # 半场客胜 -> 全场平局（被逆转）
            "负-负": ht_away_win * ft_away_win * 0.8,    # 半场客胜 -> 全场客胜
        }
        
        # 归一化概率
        total_prob = sum(bqc_probs.values())
        if total_prob > 0:
            bqc_probs = {k: v / total_prob for k, v in bqc_probs.items()}

        if not bqc_probs:
            return None

        best = max(bqc_probs, key=bqc_probs.get)
        best_prob = bqc_probs[best]

        # 尝试获取半全场赔率
        # 赔率可能以多种形式存在：
        # 1. 扁平化键: match_odds["hafu_胜-胜"] (中文横杠)
        # 2. 扁平化键: match_odds["hafu_胜胜"] (中文无横杠)
        # 3. 嵌套options: match_odds["hafu"]["options"][{"result": "胜-胜", "odds": 5.2}]
        # 4. 英文键: match_odds["hafu"]["win_win"]
        hafu_odds = 0
        # 中英文映射
        bqc_en_map = {"胜-胜": "win_win", "胜-平": "win_draw", "胜-负": "win_loss",
                       "平-胜": "draw_win", "平-平": "draw_draw", "平-负": "draw_loss",
                       "负-胜": "loss_win", "负-平": "loss_draw", "负-负": "loss_loss"}
        # 无横杠格式映射: "胜-胜" -> "胜胜"
        best_no_dash = best.replace("-", "")

        # 尝试多种扁平化键格式
        flat_key_with_dash = f"hafu_{best}"
        flat_key_no_dash = f"hafu_{best_no_dash}"
        flat_key_en = f"hafu_{bqc_en_map.get(best, '')}"
        if flat_key_with_dash in match_odds:
            hafu_odds = float(match_odds[flat_key_with_dash])
        elif flat_key_no_dash in match_odds:
            hafu_odds = float(match_odds[flat_key_no_dash])
        elif flat_key_en and flat_key_en in match_odds:
            hafu_odds = float(match_odds[flat_key_en])
        else:
            hafu = match_odds.get("hafu", {})
            if isinstance(hafu, dict) and "options" in hafu:
                for opt in hafu["options"]:
                    result_val = opt.get("result", opt.get("value", ""))
                    # 同时匹配 "胜-胜" 和 "胜胜" 格式
                    if result_val == best or result_val == best_no_dash:
                        hafu_odds = float(opt.get("odds", 0))
                        break
            elif isinstance(hafu, dict):
                en_key = bqc_en_map.get(best, best)
                hafu_odds = float(hafu.get(en_key, hafu.get(best, hafu.get(best_no_dash, 0))))

        # 置信度基于相对优势而非绝对概率
        confidence_score = self._calc_relative_confidence(
            best_prob, bqc_probs, min_abs=15.0
        )
        confidence = "高" if confidence_score >= 35 else "中" if confidence_score >= 20 else "低"
        
        # 构建所有选项（用于双选/多选）
        all_choices = []
        for bqc_result, prob in bqc_probs.items():
            # 获取赔率
            odds = 0
            bqc_no_dash = bqc_result.replace("-", "")
            flat_key_with_dash = f"hafu_{bqc_result}"
            flat_key_no_dash = f"hafu_{bqc_no_dash}"
            flat_key_en = f"hafu_{bqc_en_map.get(bqc_result, '')}"
            
            if flat_key_with_dash in match_odds:
                odds = float(match_odds[flat_key_with_dash])
            elif flat_key_no_dash in match_odds:
                odds = float(match_odds[flat_key_no_dash])
            elif flat_key_en and flat_key_en in match_odds:
                odds = float(match_odds[flat_key_en])
            else:
                hafu = match_odds.get("hafu", {})
                if isinstance(hafu, dict):
                    en_key = bqc_en_map.get(bqc_result, bqc_result)
                    odds = float(hafu.get(en_key, hafu.get(bqc_result, hafu.get(bqc_no_dash, 0))))
            
            ev = prob * odds - 1.0 if odds > 0 else -1.0
            implied_p = 1.0 / odds if odds > 0 else prob
            value_ratio = prob / implied_p if implied_p > 0 else 1.0
            score_val = prob * 100
            
            all_choices.append({
                "label": bqc_result,
                "odds": odds,
                "model_prob": round(prob, 4),
                "implied_prob": round(implied_p, 4),
                "ev": round(ev, 3),
                "value_ratio": round(value_ratio, 2),
                "score": round(score_val, 1),
            })
        
        # 按概率排序
        all_choices.sort(key=lambda x: x["score"], reverse=True)

        return {
            "selection": best,
            "odds": hafu_odds if hafu_odds > 0 else 0,
            "probability": round(best_prob, 3),
            "confidence": confidence,
            "confidence_score": confidence_score,
            "risk_assessment": {
                "level": "高" if confidence_score < 20 else ("中" if confidence_score < 35 else "低"),
                "detail": f"半全场{best}概率最高，预期进球{home_expected:.1f}-{away_expected:.1f}",
            },
            "bqc_probs": {k: round(v, 4) for k, v in bqc_probs.items()},
            "all_choices": all_choices,
        }

    def _get_play_score_modifier(self, play_type: str, play_rec: Dict,
                                  strategy: str) -> float:
        """根据策略和玩法类型计算评分修正系数

        不同策略对不同玩法有不同的偏好：
        - conservative: 偏好胜平负、让球胜平负（确定性高）
        - balanced: 所有玩法权重相近
        - aggressive: 偏好比分、半全场（赔率高但不确定性大）
        - value: 偏好有价值的玩法（基于赔率和概率偏差）
        """
        base_modifiers = {
            "胜平负": 1.0,
            "让球胜平负": 1.0,
            "比分": 0.85,
            "总进球": 0.90,
            "半全场": 0.80,
        }

        strategy_multipliers = {
            "conservative": {"胜平负": 1.1, "让球胜平负": 1.1, "比分": 0.7, "总进球": 0.8, "半全场": 0.7},
            "balanced": {"胜平负": 1.0, "让球胜平负": 1.0, "比分": 0.9, "总进球": 0.95, "半全场": 0.85},
            "aggressive": {"胜平负": 0.9, "让球胜平负": 0.9, "比分": 1.15, "总进球": 1.1, "半全场": 1.1},
            "value": {"胜平负": 1.0, "让球胜平负": 1.05, "比分": 1.0, "总进球": 1.0, "半全场": 1.0},
        }

        modifier = base_modifiers.get(play_type, 1.0)
        strategy_mult = strategy_multipliers.get(strategy, {})
        if strategy_mult:
            modifier *= strategy_mult.get(play_type, 1.0)

        # 价值策略额外调整：如果赔率和概率存在正偏差（EV > 1），提升评分
        if strategy == "value":
            odds = play_rec.get("odds", 0)
            prob = play_rec.get("probability", 0)
            if odds > 0 and prob > 0:
                ev = prob * odds
                if ev > 1.05:
                    modifier *= 1.1  # 正期望值加成
                elif ev < 0.9:
                    modifier *= 0.85  # 负期望值惩罚

        return round(modifier, 3)

    @staticmethod
    def _calc_relative_confidence(best_prob: float, all_probs: Dict,
                                   min_abs: float = 10.0) -> float:
        """计算基于相对优势的置信度分数

        对于比分/半全场等低概率高赔率玩法，绝对概率通常很低（5%-15%），
        但如果第一名相对第二名有明显优势，说明模型对该选项有较强信心。

        计算方式：
        1. 相对优势 = (best_prob - second_prob) / second_prob
        2. confidence = max(绝对概率 * 100, 相对优势 * 100 * 0.6, min_abs)
        3. 上限 99.0

        Args:
            best_prob: 最优选项的概率
            all_probs: 所有选项的概率字典
            min_abs: 绝对概率的最低保底分数

        Returns:
            置信度分数 (0-99)
        """
        if best_prob <= 0 or not all_probs:
            return 0.0

        # 找第二名概率
        sorted_probs = sorted(all_probs.values(), reverse=True)
        second_prob = sorted_probs[1] if len(sorted_probs) > 1 else 0

        # 绝对概率分数
        abs_score = best_prob * 100

        # 相对优势分数
        if second_prob > 0:
            relative_advantage = (best_prob - second_prob) / second_prob
            relative_score = relative_advantage * 100 * 0.6
        else:
            relative_score = abs_score  # 只有一个选项时用绝对概率

        # 取三者最大值，确保不低于 min_abs
        confidence = max(abs_score, relative_score, min_abs)
        return min(round(confidence, 1), 99.0)

    def _get_top_scores(self, score_probs: Dict, exclude: str = "", n: int = 3) -> List[Dict]:
        """获取概率最高的前N个比分"""
        if not score_probs:
            return []
        sorted_scores = sorted(
            ((k, v) for k, v in score_probs.items() if k != exclude),
            key=lambda x: x[1], reverse=True
        )
        return [{"score": k, "probability": round(v, 4)} for k, v in sorted_scores[:n]]
    
    async def generate_betting_slips(self, match_ids: List[str], strategy: str = "single",
                              bankroll: float = 1000.0, 
                              lottery_type: str = "竞彩足球") -> Dict[str, Any]:
        """生成标准投注单

        核心逻辑：
        1. 获取所有推荐（调用 get_daily_recommendations）
        2. 按玩法分组，确保多种玩法都有覆盖
        3. 为每种玩法选择最优的2-3场比赛
        4. 生成多个投注方案（保守/均衡/激进）
        5. 每个方案包含完整的推荐理由、串关理由
        6. 记录被淘汰的比赛及淘汰理由
        """
        return await self._build_standard_slips(
            match_ids=match_ids,
            strategy=strategy,
            bankroll=bankroll,
            lottery_type=lottery_type,
        )

    async def _build_standard_slips(self, match_ids: List[str], strategy: str = "single",
                               bankroll: float = 1000.0,
                               lottery_type: str = "竞彩足球") -> Dict[str, Any]:
        """构建标准投注单

        生成包含完整推荐理由、串关逻辑、淘汰理由的标准投注单。
        """
        # 1. 获取所有推荐
        # 将投注策略映射到推荐策略: single/parlay/mixed -> balanced
        # conservative/aggressive 直接透传
        strategy_map = {
            "single": "balanced",
            "parlay": "balanced",
            "mixed": "balanced",
        }
        rec_strategy = strategy_map.get(strategy, strategy)
        try:
            all_recommendations = await self.get_daily_recommendations(
                count=300,
                strategy=rec_strategy,
                min_confidence=0.0,
                lottery_type=lottery_type,
            )
        except ValueError:
            # 数据缓存为空且自动获取也失败时，回退到逐场分析
            all_recommendations = []
            analysis_engine = get_analysis_engine()
            for mid in match_ids:
                try:
                    analysis = await analysis_engine.analyze_match(mid, lottery_type)
                    rec = analysis.get("recommendation", {})
                    match_data = analysis.get("match_data", {})
                    home_team = match_data.get("home_team", "")
                    away_team = match_data.get("away_team", "")
                    # 从 match 数据中提取实际赔率，而不是设为 0
                    odds_data = match_data.get("odds", {})
                    had = odds_data.get("had", odds_data)
                    pick = rec.get("pick", "主胜")
                    if pick == "主胜":
                        actual_odds = float(had.get("win", had.get("had_w", 0)) or 0)
                    elif pick == "平局":
                        actual_odds = float(had.get("draw", had.get("had_d", 0)) or 0)
                    else:
                        actual_odds = float(had.get("lose", had.get("had_l", 0)) or 0)
                    all_recommendations.append({
                        "match_id": mid,
                        "play_type": "胜平负",
                        "match": f"{home_team} vs {away_team}" if home_team and away_team else mid,
                        "league": match_data.get("league", ""),
                        "match_time": match_data.get("match_time", ""),
                        "selection": pick,
                        "odds": actual_odds,
                        "confidence": rec.get("confidence", "中"),
                        "confidence_score": rec.get("confidence_score", 50.0),
                        "probability": rec.get("probability", 0.33),
                        "final_score": analysis.get("combined_score", 50),
                        "combined_score": analysis.get("combined_score", 50),
                        "risk_level": analysis.get("risk_level", "中"),
                        "recommendation": rec,
                    })
                except Exception as e:
                    logger.warning(f"分析比赛失败 {mid}: {e}")
                    continue

        # 2. 如果指定了 match_ids，过滤只保留这些比赛
        if match_ids:
            filtered = [r for r in all_recommendations if r["match_id"] in match_ids]
            if filtered:
                all_recommendations = filtered

        # 3. 按玩法分组
        play_type_groups: Dict[str, List[Dict]] = {}
        for rec in all_recommendations:
            pt = rec.get("play_type", "胜平负")
            if pt not in play_type_groups:
                play_type_groups[pt] = []
            play_type_groups[pt].append(rec)

        # 4. 为每种玩法选择最优比赛（按 confidence_score 排序）
        CONFIDENCE_THRESHOLD = 10.0
        selected_by_play: Dict[str, List[Dict]] = {}
        eliminated_matches: List[Dict] = []
        # 注意: seen_match_ids 按玩法独立，同一比赛可在不同玩法中各选一次
        seen_match_ids_by_play: Dict[str, set] = {}

        for play_type, recs in play_type_groups.items():
            seen_match_ids_by_play[play_type] = set()
            # 按 confidence_score 降序排序
            sorted_recs = sorted(recs, key=lambda x: x.get("confidence_score", 0), reverse=True)
            selected = []
            for rec in sorted_recs:
                mid = rec["match_id"]
                conf_score = rec.get("confidence_score", 0)
                if conf_score < CONFIDENCE_THRESHOLD:
                    eliminated_matches.append({
                        "match_id": mid,
                        "match": rec.get("match", mid),
                        "play_type": play_type,
                        "reason": f"置信度{conf_score}%低于阈值{CONFIDENCE_THRESHOLD}%，模型信心不足",
                    })
                    continue
                # 低赔率过滤：根据策略动态处理
                rec_odds = rec.get("odds", 0)
                if rec_odds > 0 and rec_odds < 1.5:
                    match_strategy_info = rec.get("recommendation", {}).get("strategy", {})
                    low_handling = match_strategy_info.get("low_odds_handling", "penalize")
                    if low_handling == "avoid":
                        eliminated_matches.append({
                            "match_id": mid,
                            "match": rec.get("match", mid),
                            "play_type": play_type,
                            "reason": f"策略建议避开低赔率({low_handling})，赔率{rec_odds}",
                        })
                        continue
                    elif low_handling == "look_for_handicap":
                        # 不淘汰，但降低优先级
                        conf_score *= 0.7
                    # "penalize" 和 "accept" 不淘汰
                
                # AI洞察参考：根据AI信心等级调整优先级
                ai_insight = rec.get("ai_insight", {})
                ai_confidence = ai_insight.get("confidence_level", "中")
                if ai_confidence == "高":
                    # AI信心高，提升优先级
                    conf_score *= 1.1
                elif ai_confidence == "低":
                    # AI信心低，降低优先级
                    conf_score *= 0.9
                
                if mid in seen_match_ids_by_play[play_type]:
                    continue
                selected.append(rec)
                seen_match_ids_by_play[play_type].add(mid)
                if len(selected) >= 3:
                    break

            # 记录因名额限制被淘汰的比赛
            for rec in sorted_recs[len(selected):]:
                mid = rec["match_id"]
                if mid not in seen_match_ids_by_play[play_type]:
                    conf_score = rec.get("confidence_score", 0)
                    eliminated_matches.append({
                        "match_id": mid,
                        "match": rec.get("match", mid),
                        "play_type": play_type,
                        "reason": f"该玩法名额已满（最多3场），置信度{conf_score}%排名靠后",
                    })

            if selected:
                selected_by_play[play_type] = selected

        # 5. 生成投注方案（保守/均衡/激进）
        betting_slips = []
        slip_counter = 1

        # 按玩法独立生成投注方案（每种玩法单独串关）
        # 官方规则:
        # - 胜平负/让球胜平负: 支持1串1(单关)到8串1
        # - 比分/半全场: 支持2串1到4串1（不支持单关）
        # - 总进球: 支持2串1到6串1（不支持单关）
        PLAY_PARLAY_CONFIG = {
            "胜平负": {
                "min_legs": 1, "max_legs": 8,
                "parlay_types": ["2x1", "3x1"],
                "max_bets": 3,
            },
            "让球胜平负": {
                "min_legs": 1, "max_legs": 8,
                "parlay_types": ["2x1", "3x1"],
                "max_bets": 3,
            },
            "比分": {
                "min_legs": 2, "max_legs": 4,
                "parlay_types": ["2x1", "3x1"],
                "max_bets": 3,
            },
            "总进球": {
                "min_legs": 2, "max_legs": 6,
                "parlay_types": ["2x1", "3x1"],
                "max_bets": 3,
            },
            "半全场": {
                "min_legs": 2, "max_legs": 4,
                "parlay_types": ["2x1", "3x1"],
                "max_bets": 3,
            },
        }

        # 策略配置（控制投入比例和风险偏好）
        strategy_configs = {
            "conservative": {"bankroll_pct": 0.05, "risk_level": "低", "name_prefix": "稳健"},
            "balanced": {"bankroll_pct": 0.08, "risk_level": "中", "name_prefix": "均衡"},
            "aggressive": {"bankroll_pct": 0.10, "risk_level": "中高", "name_prefix": "进取"},
        }

        # 根据 strategy 参数决定生成哪些方案
        if strategy == "single":
            strategies_to_generate = ["conservative"]
        elif strategy == "parlay":
            strategies_to_generate = ["balanced"]
        elif strategy == "mixed":
            strategies_to_generate = ["conservative", "balanced", "aggressive"]
        else:
            strategies_to_generate = ["conservative", "balanced", "aggressive"]

        for strat_key in strategies_to_generate:
            strat_config = strategy_configs[strat_key]
            bankroll_pct = strat_config["bankroll_pct"]
            risk_level = strat_config["risk_level"]
            name_prefix = strat_config["name_prefix"]

            # 为每种玩法独立生成方案
            for play_type, play_config in PLAY_PARLAY_CONFIG.items():
                if play_type not in selected_by_play:
                    continue

                play_recs = selected_by_play[play_type]
                if len(play_recs) < play_config["min_legs"]:
                    continue

                chosen = None
                for parlay_type in play_config["parlay_types"]:
                    # 解析串关数
                    try:
                        legs = int(parlay_type.split("x")[0])
                    except (ValueError, IndexError):
                        continue

                    if legs > len(play_recs):
                        continue
                    if legs > play_config["max_legs"]:
                        continue

                    # 取置信度最高的N场
                    chosen = sorted(play_recs, key=lambda x: x.get("confidence_score", 0), reverse=True)[:legs]

                    if len(chosen) < play_config["min_legs"]:
                        chosen = None
                        continue

                # 如果 chosen 未赋值或为 None，跳过该玩法
                if chosen is None:
                    continue

                # 计算总赔率
                total_odds = 1.0
                for c in chosen:
                    odds = c.get("odds", 0)
                    if odds > 0:
                        total_odds *= odds
                    else:
                        # 无赔率时使用概率反推
                        prob = c.get("probability", 0.33)
                        total_odds *= round(1.0 / prob, 2) if prob > 0 else 2.0
    
                stake = round(bankroll * bankroll_pct, 2)
                expected_return = round(stake * total_odds, 2)
    
                # 生成每场比赛的推荐理由
                bets = []
                play_types_in_slip = []
                for c in chosen:
                    c_play_type = c.get("play_type", "胜平负")
                    play_types_in_slip.append(c_play_type)
                    confidence_score = c.get("confidence_score", 0)
                    probability = c.get("probability", 0)
                    odds = c.get("odds", 0)
    
                    # 构建推荐理由
                    reasoning_parts = []
                    key_factors = []
    
                    # 基于概率的推理
                    if probability > 0:
                        reasoning_parts.append(f"模型预测概率{round(probability*100, 1)}%")
                        if probability > 0.6:
                            key_factors.append("模型预测概率较高")
    
                    # 基于赔率价值的推理
                    if odds > 0 and probability > 0:
                        implied_prob = round(1.0 / odds * 100, 1)
                        value_space = round(probability * 100 - implied_prob, 1)
                        if value_space > 5:
                            reasoning_parts.append(f"赔率隐含概率{implied_prob}%，存在{value_space}%价值空间")
                            key_factors.append("赔率有价值")
                        elif value_space > 0:
                            reasoning_parts.append(f"赔率隐含概率{implied_prob}%，概率匹配")
                        else:
                            reasoning_parts.append(f"赔率隐含概率{implied_prob}%，价值空间有限")
    
                    # 基于置信度的推理
                    if confidence_score >= 70:
                        key_factors.append("高置信度推荐")
                    elif confidence_score >= 50:
                        key_factors.append("中等置信度")
    
                    # 基于风险等级
                    risk = c.get("risk_level", "中")
                    if risk == "低":
                        key_factors.append("低风险")
    
                    # 基于联赛/主客场
                    league = c.get("league", "")
                    if league:
                        key_factors.append(f"{league}联赛")
    
                    reasoning = "，".join(reasoning_parts) if reasoning_parts else "综合分析推荐"
                    if not key_factors:
                        key_factors = ["综合分析推荐"]
    
                    bets.append({
                        "match_id": c.get("match_id", ""),
                        "match": c.get("match", ""),
                        "league": c.get("league", ""),
                        "match_time": c.get("match_time", ""),
                        "play_type": c_play_type,
                        "selection": c.get("selection", ""),
                        "odds": odds,
                        "confidence": confidence_score,
                        "reasoning": reasoning,
                        "key_factors": key_factors,
                    })
    
                # 生成串关理由
                parlay_reasoning_parts = []
                leagues = set(b.get("league", "") for b in bets if b.get("league"))
                if len(leagues) == 1:
                    parlay_reasoning_parts.append(f"均为{list(leagues)[0]}比赛")
                elif len(leagues) > 1:
                    parlay_reasoning_parts.append(f"跨{len(leagues)}个联赛分散风险")
    
                play_types_unique = list(dict.fromkeys(play_types_in_slip))
                parlay_reasoning_parts.append(f"玩法覆盖{'+'.join(play_types_unique)}")
    
                avg_confidence = sum(b["confidence"] for b in bets) / len(bets)
                if avg_confidence >= 65:
                    parlay_reasoning_parts.append(f"平均置信度{round(avg_confidence, 1)}%，信心充足")
                else:
                    parlay_reasoning_parts.append(f"平均置信度{round(avg_confidence, 1)}%")
    
                if risk_level == "低":
                    parlay_reasoning_parts.append("组合风险可控")
                elif risk_level == "中高":
                    parlay_reasoning_parts.append("赔率较高但风险偏高，注意仓位控制")
    
                parlay_reasoning = "，".join(parlay_reasoning_parts)
    
                # 方案推荐理由
                slip_reasoning = f"选择{play_type}玩法，"
                if strat_key == "conservative":
                    slip_reasoning += f"取置信度最高的{len(bets)}场比赛，低风险稳健组合"
                elif strat_key == "balanced":
                    slip_reasoning += f"{len(bets)}场均衡组合"
                else:
                    slip_reasoning += f"{len(bets)}场进取组合"
    
                slip_id = f"SLIP{slip_counter:03d}"
                slip_name = f"{name_prefix}{play_type}{parlay_type}"
    
                slip_data = {
                    "slip_id": slip_id,
                    "slip_name": slip_name,
                    "strategy": strat_key,
                    "parlay_type": parlay_type,
                    "total_odds": round(total_odds, 2),
                    "stake": stake,
                    "expected_return": expected_return,
                    "risk_level": risk_level,
                    "reasoning": slip_reasoning,
                    "bets": bets,
                    "parlay_reasoning": parlay_reasoning,
                }
    
                # P0-1: 调用 validate_parlay 验证投注方案
                try:
                    parlay_bets = []
                    for b in bets:
                        parlay_bets.append(ValidateBetInput(
                            match_id=b["match_id"],
                            play_type=b["play_type"],
                            selection=b["selection"],
                            odds=b["odds"] if b["odds"] > 0 else 2.0,
                            stake=round(stake / len(bets), 2),
                            lottery_type=lottery_type,
                        ))
                    parlay_input = ValidateParlayInput(
                        bets=parlay_bets,
                        parlay_type=parlay_type,
                        total_stake=stake,
                        lottery_type=lottery_type,
                    )
                    rules_engine = RulesEngine()
                    validation_result = rules_engine.validate_parlay(parlay_input)
                    if not validation_result.get("valid", False):
                        validation_errors = validation_result.get("errors", [])
                        for b in bets:
                            eliminated_matches.append({
                                "match_id": b["match_id"],
                                "match": b["match"],
                                "play_type": b["play_type"],
                                "reason": f"串关验证失败: {'; '.join(validation_errors)}",
                            })
                        logger.warning(f"投注方案 {slip_id} 验证失败: {validation_errors}")
                        continue
                except Exception as ve:
                    logger.warning(f"投注方案 {slip_id} 验证异常: {ve}")
                    continue
    
                betting_slips.append(slip_data)
                slip_counter += 1

        # 5b. 生成混合过关方案
        # 混合过关：一个方案包含2种以上不同玩法
        # 规则：如果包含比分/总进球/半全场，最多6串1
        # 混合过关的赔率计算：所有选项赔率相乘
        mixed_candidates = []
        for pt, recs in selected_by_play.items():
            if recs:
                # 每种玩法取置信度最高的1个
                sorted_recs = sorted(recs, key=lambda x: x.get("confidence_score", 0), reverse=True)
                mixed_candidates.append(sorted_recs[0])

        if len(mixed_candidates) >= 2:
            # 检查混合过关的木桶限制
            mixed_play_types = set(c.get("play_type", "") for c in mixed_candidates)
            from .rules_tools import MAX_LEGS_BY_PLAY_JINGCAI
            if lottery_type == "竞彩足球":
                max_legs_map = MAX_LEGS_BY_PLAY_JINGCAI
            else:
                from .rules_tools import MAX_LEGS_BY_PLAY_BEIDAN
                max_legs_map = MAX_LEGS_BY_PLAY_BEIDAN

            bucket_limit = 8  # 默认
            for pt in mixed_play_types:
                if pt in max_legs_map:
                    bucket_limit = min(bucket_limit, max_legs_map[pt])

            # 生成混合过关2串1
            mixed_slip_size = min(len(mixed_candidates), bucket_limit, 3)
            if mixed_slip_size >= 2:
                # 确保选中的候选来自不同比赛且不同玩法
                mixed_chosen = []
                used_match_ids = set()
                used_play_types = set()
                for c in mixed_candidates:
                    mid = c.get("match_id", "")
                    pt = c.get("play_type", "")
                    if mid not in used_match_ids and pt not in used_play_types:
                        mixed_chosen.append(c)
                        used_match_ids.add(mid)
                        used_play_types.add(pt)
                        if len(mixed_chosen) >= mixed_slip_size:
                            break

                if len(mixed_chosen) >= 2:
                    # 计算总赔率
                    mixed_total_odds = 1.0
                    for c in mixed_chosen:
                        odds = c.get("odds", 0)
                        if odds > 0:
                            mixed_total_odds *= odds
                        else:
                            prob = c.get("probability", 0.33)
                            mixed_total_odds *= round(1.0 / prob, 2) if prob > 0 else 2.0

                    mixed_stake = round(bankroll * 0.06, 2)
                    mixed_expected_return = round(mixed_stake * mixed_total_odds, 2)

                    # 构建投注明细
                    mixed_bets = []
                    mixed_play_types_in_slip = []
                    for c in mixed_chosen:
                        mpt = c.get("play_type", "胜平负")
                        mixed_play_types_in_slip.append(mpt)
                        confidence_score = c.get("confidence_score", 0)
                        probability = c.get("probability", 0)
                        odds = c.get("odds", 0)

                        reasoning_parts = []
                        if probability > 0:
                            reasoning_parts.append(f"模型预测概率{round(probability*100, 1)}%")
                        if odds > 0 and probability > 0:
                            implied_prob = round(1.0 / odds * 100, 1)
                            value_space = round(probability * 100 - implied_prob, 1)
                            if value_space > 5:
                                reasoning_parts.append(f"存在{value_space}%价值空间")

                        mixed_bets.append({
                            "match_id": c.get("match_id", ""),
                            "match": c.get("match", ""),
                            "league": c.get("league", ""),
                            "match_time": c.get("match_time", ""),
                            "play_type": mpt,
                            "selection": c.get("selection", ""),
                            "odds": odds,
                            "confidence": confidence_score,
                            "reasoning": "，".join(reasoning_parts) if reasoning_parts else "综合分析推荐",
                            "key_factors": ["混合过关组合"],
                        })

                    mixed_play_types_unique = list(dict.fromkeys(mixed_play_types_in_slip))
                    mixed_parlay_type = f"{len(mixed_chosen)}x1"

                    mixed_slip_data = {
                        "slip_id": f"SLIP{slip_counter:03d}",
                        "slip_name": f"混合过关{len(mixed_chosen)}串1",
                        "strategy": "mixed",
                        "parlay_type": mixed_parlay_type,
                        "total_odds": round(mixed_total_odds, 2),
                        "stake": mixed_stake,
                        "expected_return": mixed_expected_return,
                        "risk_level": "中",
                        "reasoning": (
                            f"混合过关方案，组合{'、'.join(mixed_play_types_unique)}玩法，"
                            f"{len(mixed_chosen)}场比赛跨玩法互补"
                        ),
                        "bets": mixed_bets,
                        "parlay_reasoning": (
                            f"混合过关：{'+'.join(mixed_play_types_unique)}，"
                            f"木桶限制{bucket_limit}关，当前{len(mixed_chosen)}场合规"
                        ),
                    }

                    # 验证混合过关方案
                    try:
                        mixed_parlay_bets = []
                        for b in mixed_bets:
                            mixed_parlay_bets.append(ValidateBetInput(
                                match_id=b["match_id"],
                                play_type=b["play_type"],
                                selection=b["selection"],
                                odds=b["odds"] if b["odds"] > 0 else 2.0,
                                stake=round(mixed_stake / len(mixed_bets), 2),
                                lottery_type=lottery_type,
                            ))
                        mixed_parlay_input = ValidateParlayInput(
                            bets=mixed_parlay_bets,
                            parlay_type=mixed_parlay_type,
                            total_stake=mixed_stake,
                            lottery_type=lottery_type,
                        )
                        mixed_rules_engine = RulesEngine()
                        mixed_validation = mixed_rules_engine.validate_parlay(mixed_parlay_input)
                        if mixed_validation.get("valid", False):
                            betting_slips.append(mixed_slip_data)
                            slip_counter += 1
                        else:
                            mixed_errors = mixed_validation.get("errors", [])
                            logger.info(f"混合过关方案验证未通过: {mixed_errors}")
                    except Exception as mixed_ve:
                        logger.info(f"混合过关方案验证异常: {mixed_ve}")

        # 6. 去重淘汰记录
        seen_eliminated = set()
        unique_eliminated = []
        for em in eliminated_matches:
            key = (em["match_id"], em["play_type"])
            if key not in seen_eliminated:
                seen_eliminated.add(key)
                unique_eliminated.append(em)

        # 7. 汇总
        play_types_covered = list(selected_by_play.keys())
        total_investment = sum(s["stake"] for s in betting_slips)
        risk_levels = [s["risk_level"] for s in betting_slips]
        if "中高" in risk_levels or "高" in risk_levels:
            risk_assessment = "中高风险，包含高赔率玩法"
        elif "中" in risk_levels:
            risk_assessment = "中等风险，均衡配置"
        else:
            risk_assessment = "中低风险，分散投注"

        summary = {
            "total_slips": len(betting_slips),
            "play_types_covered": play_types_covered,
            "total_investment": round(total_investment, 2),
            "risk_assessment": risk_assessment,
        }

        return {
            "betting_slips": betting_slips,
            "eliminated_matches": unique_eliminated,
            "summary": summary,
            "bets": betting_slips[0]["bets"] if betting_slips else [],
            "parlay_type": betting_slips[0]["parlay_type"] if betting_slips else "",
            "total_stake": round(total_investment, 2),
        }
    
    def generate_kelly_slips(self, match_id: str, edge: float, odds: float,
                            bankroll: float, fraction: float = 0.5) -> Dict[str, Any]:
        """生成凯利投注单"""
        kelly_result = _calculate_kelly_stake(bankroll, edge, odds, fraction)
        
        return {
            "match_id": match_id,
            "edge": edge,
            "odds": odds,
            "bankroll": bankroll,
            "kelly_fraction": kelly_result["kelly_fraction"],
            "adjusted_fraction": kelly_result["adjusted_fraction"],
            "stake": kelly_result["stake"],
            "stake_percentage": kelly_result["stake_percentage"],
            "recommendation": kelly_result["recommendation"],
        }
    
    async def cross_match_analysis(self, match_ids: List[str], analysis_type: str = "correlation",
                            lottery_type: str = "竞彩足球") -> Dict[str, Any]:
        """跨比赛分析"""
        analysis_engine = get_analysis_engine()
        match_analyses = []
        
        for match_id in match_ids:
            analysis = await analysis_engine.analyze_match(match_id, lottery_type)
            match_analyses.append({
                "match_id": match_id,
                "analysis": analysis,
            })
        
        if analysis_type == "correlation":
            return self._analyze_correlation(match_analyses)
        elif analysis_type == "value":
            return self._analyze_value(match_analyses)
        else:  # risk
            return self._analyze_risk(match_analyses)
    
    def _analyze_correlation(self, match_analyses: List[Dict]) -> Dict[str, Any]:
        """分析比赛关联性"""
        correlations = []
        
        for i, m1 in enumerate(match_analyses):
            for j, m2 in enumerate(match_analyses):
                if i >= j:
                    continue
                
                a1 = m1.get("analysis", {})
                a2 = m2.get("analysis", {})
                
                # 简单的关联性判断
                score1 = a1.get("combined_score", 50)
                score2 = a2.get("combined_score", 50)
                
                correlations.append({
                    "match_pair": f"{m1['match_id']} vs {m2['match_id']}",
                    "score_diff": abs(score1 - score2),
                    "correlation": "low" if abs(score1 - score2) > 20 else "medium" if abs(score1 - score2) > 10 else "high",
                })
        
        return {
            "analysis_type": "correlation",
            "correlations": correlations,
        }
    
    def _analyze_value(self, match_analyses: List[Dict]) -> Dict[str, Any]:
        """分析价值"""
        rankings = []
        
        for m in match_analyses:
            a = m.get("analysis", {})
            rankings.append({
                "match_id": m["match_id"],
                "combined_score": a.get("combined_score", 50),
                "agreement_level": a.get("agreement_level", "未知"),
            })
        
        rankings.sort(key=lambda x: x["combined_score"], reverse=True)
        
        return {
            "analysis_type": "value",
            "rankings": rankings,
        }
    
    def _analyze_risk(self, match_analyses: List[Dict]) -> Dict[str, Any]:
        """分析风险"""
        total_risk = 0
        high_risk_matches = []
        
        for m in match_analyses:
            a = m.get("analysis", {})
            risk = 100 - a.get("combined_score", 50)
            total_risk += risk
            
            if a.get("risk_level") == "高":
                high_risk_matches.append(m["match_id"])
        
        avg_risk = total_risk / len(match_analyses) if match_analyses else 50
        
        return {
            "analysis_type": "risk",
            "average_risk": round(avg_risk, 1),
            "high_risk_matches": high_risk_matches,
            "risk_level": "高" if avg_risk > 50 else "中" if avg_risk > 30 else "低",
        }
    
    async def auto_parlay_recommendation(self, match_ids: Optional[List[str]] = None,
                                   strategy: str = "balanced", parlay_type: str = "2x1",
                                   max_matches: int = 4, min_confidence: float = 60.0,
                                   bankroll: float = 1000.0,
                                   lottery_type: str = "竞彩足球") -> Dict[str, Any]:
        """自动串关推荐（支持多种玩法）"""
        # 从 get_daily_recommendations 获取多种玩法的推荐
        try:
            all_recs = await self.get_daily_recommendations(
                count=100,
                strategy=strategy,
                min_confidence=min_confidence,
                lottery_type=lottery_type,
            )
        except ValueError:
            all_recs = []

        # 如果指定了 match_ids，过滤推荐
        if match_ids:
            filtered = [r for r in all_recs if r.get("match_id") in match_ids]
            if filtered:
                all_recs = filtered

        # 按玩法分组，每种玩法选择置信度最高的推荐
        play_type_groups: Dict[str, List[Dict]] = {}
        for rec in all_recs:
            pt = rec.get("play_type", "胜平负")
            if pt not in play_type_groups:
                play_type_groups[pt] = []
            play_type_groups[pt].append(rec)

        # 从每种玩法中选出最佳推荐，合并后按 final_score 排序
        best_by_play = []
        for pt, recs in play_type_groups.items():
            sorted_recs = sorted(recs, key=lambda x: x.get("final_score", 0), reverse=True)
            best_by_play.append(sorted_recs[0])
        best_by_play.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        # 确定选择场次
        parlay_map = {"2x1": 2, "3x1": 3, "4x1": 4, "3x4": 3, "4x11": 4}
        select_count = parlay_map.get(parlay_type, 2)
        select_count = min(select_count, max_matches, len(best_by_play))

        selected = best_by_play[:select_count]

        # 生成串关方案
        selections = []
        total_odds = 1.0

        for rec in selected:
            odds = rec.get("odds", 0)
            if odds <= 0:
                odds = 2.0  # 兜底默认值

            selection = {
                "match_id": rec.get("match_id", ""),
                "match": rec.get("match", ""),
                "play_type": rec.get("play_type", "胜平负"),
                "selection": rec.get("selection", ""),
                "odds": odds,
                "confidence": rec.get("confidence_score", 50),
            }
            selections.append(selection)
            total_odds *= odds

        # 计算投注额
        stake = bankroll * 0.05  # 默认5%
        expected_return = stake * total_odds

        return {
            "strategy": strategy,
            "parlay_type": parlay_type,
            "selections": selections,
            "total_odds": round(total_odds, 2),
            "stake": round(stake, 2),
            "expected_return": round(expected_return, 2),
            "profit": round(expected_return - stake, 2),
        }


# 全局投注引擎实例
_betting_engine: Optional[BettingEngine] = None


def get_betting_engine() -> BettingEngine:
    """获取投注引擎实例（单例模式）"""
    global _betting_engine
    if _betting_engine is None:
        _betting_engine = BettingEngine()
    return _betting_engine


# ============================================================
# Tool Functions
# ============================================================

async def lottery_get_daily_recommendations(params: GetDailyRecommendationsInput, ctx: Context) -> str:
    """获取每日推荐"""
    try:
        await ctx.report_progress(0.3, "正在分析今日比赛...")
        await ctx.log_info(f"[推荐] 获取每日推荐: {params.count}场, 策略: {params.strategy}")
        
        engine = get_betting_engine()
        recommendations = await engine.get_daily_recommendations(
            count=params.count,
            strategy=params.strategy,
            min_confidence=params.min_confidence,
            lottery_type=params.lottery_type,
        )
        
        # 分页处理
        total_count = len(recommendations)
        paginated = recommendations[params.offset:params.offset + params.limit]
        has_more = total_count > params.offset + len(paginated)

        await ctx.report_progress(1.0, "推荐生成完成")
        
        methodology = (
            "综合评分算法: final_score = EV_score x 0.4 + model_consistency x 0.3 + risk_adjusted x 0.3\n"
            "- EV_score: 期望值评分，EV = (隐含概率 x 赔率 - 1) x 100，经 sigmoid 归一化到 0-100\n"
            "- model_consistency: 模型一致性评分，基于泊松/Elo/xG 多模型胜平负概率的标准差\n"
            "- risk_adjusted: 风险调整评分，combined_score x 风险系数（低1.0/中0.8/高0.5）"
        )
        
        return _to_json({
            "success": True,
            "data": {
                "recommendations": paginated,
                "count": len(paginated),
                "total_count": total_count,
                "has_more": has_more,
                "next_offset": params.offset + len(paginated) if has_more else None,
                "strategy": params.strategy,
                "methodology": methodology,
            },
            "timestamp": datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"获取每日推荐失败: {e}")
        raise_tool_error(f"获取每日推荐失败: {str(e)}")


async def lottery_generate_betting_slips(params: GenerateBettingSlipsInput, ctx: Context) -> str:
    """生成投注单
    
    支持策略（strategy参数）：
    - single: 单关投注
    - parlay: 串关投注
    - mixed: 混合投注
    - auto_parlay: 自动串关推荐（智能选择比赛并生成串关方案）
    """
    try:
        engine = get_betting_engine()
        
        # auto_parlay 模式
        if params.strategy == "auto_parlay":
            await ctx.report_progress(0.3, "正在生成自动串关推荐...")
            await ctx.log_info(f"[自动串关] 策略: {params.strategy}, 类型: {params.parlay_type}")
            
            result = await engine.auto_parlay_recommendation(
                match_ids=params.match_ids if params.match_ids else None,
                strategy=params.risk_level,
                parlay_type=params.parlay_type,
                max_matches=params.max_matches,
                min_confidence=params.min_confidence,
                bankroll=params.bankroll,
                lottery_type=params.lottery_type,
            )
            
            # 分页处理 selections
            selections = result.get("selections", [])
            total_count = len(selections)
            paginated = selections[params.offset:params.offset + params.limit]
            has_more = total_count > params.offset + len(paginated)
            result["selections"] = paginated
            result["total_count"] = total_count
            result["has_more"] = has_more
            result["next_offset"] = params.offset + len(paginated) if has_more else None

            await ctx.report_progress(1.0, "自动串关推荐生成完成")
            
            return _to_json({
                "success": True,
                "data": result,
                "timestamp": datetime.now().isoformat(),
            })
        
        # 其他模式（single/parlay/mixed）
        await ctx.report_progress(0.5, "正在生成投注单...")
        await ctx.log_info(f"[投注单] 生成投注单: {len(params.match_ids)}场, 策略: {params.strategy}")
        
        result = await engine.generate_betting_slips(
            match_ids=params.match_ids,
            strategy=params.strategy,
            bankroll=params.bankroll,
            lottery_type=params.lottery_type,
        )
        
        # 标准投注单格式：betting_slips / eliminated_matches / summary
        betting_slips = result.get("betting_slips", [])
        total_count = len(betting_slips)
        paginated = betting_slips[params.offset:params.offset + params.limit]
        has_more = total_count > params.offset + len(paginated)

        await ctx.report_progress(1.0, "投注单生成完成")
        
        return _to_json({
            "success": True,
            "data": {
                "betting_slips": paginated,
                "eliminated_matches": result.get("eliminated_matches", []),
                "summary": result.get("summary", {}),
                "total_count": total_count,
                "has_more": has_more,
                "next_offset": params.offset + len(paginated) if has_more else None,
            },
            "timestamp": datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"生成投注单失败: {e}")
        raise_tool_error(f"生成投注单失败: {str(e)}")


async def lottery_generate_kelly_slips(params: GenerateKellySlipsInput, ctx: Context) -> str:
    """生成凯利公式投注单
    
    基于凯利公式(Kelly Criterion)计算最优投注比例。
    公式: f* = (bp - q) / b
    其中: b=赔率-1, p=获胜概率, q=失败概率=1-p
    
    推荐使用保守系数(fraction)0.25-0.5，降低波动风险。
    """
    try:
        await ctx.report_progress(0.5, "正在计算凯利投注比例...")
        await ctx.log_info(f"[凯利公式] 比赛: {params.match_id}, 赔率: {params.odds}, 优势: {params.edge}")
        
        engine = get_betting_engine()
        result = engine.generate_kelly_slips(
            match_id=params.match_id,
            edge=params.edge,
            odds=params.odds,
            bankroll=params.bankroll,
            fraction=params.fraction,
        )
        
        await ctx.report_progress(1.0, "凯利投注单生成完成")
        
        return _to_json({
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"生成凯利投注单失败: {e}")
        raise_tool_error(f"生成凯利投注单失败: {str(e)}")


async def lottery_get_betting_stats(params: GetBettingStatsInput, ctx: Context) -> str:
    """获取投注统计（委托给 BetTracker，基于持久化数据）"""
    try:
        await ctx.report_progress(0.3, "正在统计投注数据...")
        await ctx.log_info(f"[投注统计] 统计周期: {params.period}")

        # 统一使用 BetTracker（JSON 持久化）
        from .enhanced_tools import get_bet_tracker
        tracker = get_bet_tracker()

        # 将 period 映射为日期范围
        from datetime import timedelta
        now = datetime.now()
        start_date = None
        if params.period == "today":
            start_date = now.strftime("%Y-%m-%d")
        elif params.period == "week":
            start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        stats = tracker.get_statistics(
            start_date=start_date,
            end_date=None,
            play_type=None,
        )

        await ctx.report_progress(1.0, "统计完成")

        return _to_json({
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"获取投注统计失败: {e}")
        raise_tool_error(f"获取投注统计失败: {str(e)}")


# ============================================================
# Tool Registration
# ============================================================

def register_betting_tools(mcp):
    """注册投注推荐工具"""
    from mcp.server.fastmcp import Context
    
    @mcp.tool(
        name="lottery_get_daily_recommendations",
        description="""获取每日投注推荐（基础版）

基于统计模型分析，推荐当日最有价值的比赛。
支持多种策略：conservative/balanced/aggressive/value

注意：如需专业版分析报告（含基本面、五大玩法概率、策略引擎、冷门预警），请使用 lottery_generate_prediction_report。

Use when: 需要快速获取当日简单投注建议时。

前置条件: 请先调用 lottery_fetch_today_matches 填充数据缓存。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_get_daily_recommendations(params: GetDailyRecommendationsInput, ctx: Context) -> str:
        return await lottery_get_daily_recommendations(params, ctx)
    
    @mcp.tool(
        name="lottery_generate_betting_slips",
        description="""生成投注单（基础版）

为指定比赛生成投注单，支持：
- single: 单关投注
- parlay: 串关投注
- mixed: 混合投注

注意：如需智能串关推荐（含规则验证、奖金计算、凯利资金管理、容错方案），请使用 lottery_smart_parlay。

Use when: 需要为特定比赛手动生成投注方案时。

Workflow: analyze_match(分析) → generate_betting_slips(生成) → validate_parlay(验证)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_generate_betting_slips(params: GenerateBettingSlipsInput, ctx: Context) -> str:
        return await lottery_generate_betting_slips(params, ctx)
    
    @mcp.tool(
        name="lottery_generate_kelly_slips",
        description="""生成凯利公式投注单

基于凯利公式(Kelly Criterion)计算最优投注比例，实现科学资金管理。

公式: f* = (bp - q) / b
- b = 赔率 - 1
- p = 获胜概率
- q = 失败概率 = 1 - p

推荐使用保守系数(fraction)0.25-0.5，降低波动风险。

参数说明:
- edge: 期望优势 = 获胜概率 - 1/赔率（范围-1到1）
- odds: 投注赔率
- bankroll: 可用资金
- fraction: 凯利分数（保守系数）

Use when: 需要科学计算最优投注金额，实现长期资金增长最大化时。

Workflow: predict_with_model(获取概率) → generate_kelly_slips(计算最优投注) → record_bet(记录)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_generate_kelly_slips(params: GenerateKellySlipsInput, ctx: Context) -> str:
        return await lottery_generate_kelly_slips(params, ctx)

    @mcp.tool(
        name="lottery_get_betting_stats",
        description="""获取投注统计（内存版，仅当前会话）

返回当前会话中通过 lottery_record_bet 记录的投注统计。
注意：如需完整的持久化投注统计（跨会话），请使用 lottery_get_bet_statistics。

Use when: 需要快速查看当前会话的投注统计时。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def _lottery_get_betting_stats(params: GetBettingStatsInput, ctx: Context) -> str:
        return await lottery_get_betting_stats(params, ctx)
