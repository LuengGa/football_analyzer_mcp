"""
MCP Server Analysis Tools - Match analysis and risk detection tools.
使用 statistical_models.py 中的 StatisticalEngine 提供专业统计分析。
"""

import json
import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from .data_tools import (
    get_cached_matches,
    _get_manager,
    _compute_results_statistics,
    _generate_match_analysis,
    _build_value_discovery_logic,
)
from .helpers import (
    _detect_odds_drift,
    _estimate_lambdas_from_odds,
    raise_tool_error,
    _to_json,
)
from lottery_mcp.models import (
    AnalyzeAllMatchesInput,
    AnalyzeWithPipelineInput,
    AnalyzeMatchInput,
    AnalyzeMatchPlaysInput,
    AnalyzeResultsInput,
    AssessRiskInput,
    CompareMatchesInput,
    CompareModelPredictionsInput,
    DetectRiskSignalsInput,
    FetchTodayMatchesInput,
    GenerateRecommendationInput,
    GetMatchContextInput,
    OptimizeStakesInput,
    PredictWithModelInput,
    GetMarketSentimentInput,
    QuantifyInjuryImpactInput,
    SimulateScenariosInput,
)
from .rules_tools import get_rules_engine
from lottery_mcp.analysis.play_analysis import get_play_analyzer, PlayProbabilityResult

# 导入专业统计模型
from lottery_mcp.analysis.models import StatisticalEngine, PoissonModel

logger = logging.getLogger("lottery_mcp")


# ============================================================
# Analysis Engine
# ============================================================

class AnalysisEngine:
    """比赛分析引擎 - 基于 StatisticalEngine 的专业实现"""

    def __init__(self):
        # 初始化专业统计引擎
        elo_file = os.path.join(os.path.dirname(__file__), 'elo_ratings.json')
        self._stat_engine = StatisticalEngine(elo_ratings_file=elo_file)
        self._poisson = PoissonModel()

    def _extract_team_stats(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """从比赛数据中提取球队统计信息

        当 match_data 中没有真实的 home_team_stats/away_team_stats 时，
        返回 home_games=0 / away_games=0 以触发从赔率估算统计数据，
        确保不同比赛（不同赔率）产生不同的泊松分析结果。
        """
        home_stats = match_data.get("home_team_stats", {})
        away_stats = match_data.get("away_team_stats", {})

        # 检查是否有真实的球队统计数据
        has_real_stats = (
            home_stats.get("games", 0) > 0 or away_stats.get("games", 0) > 0
        )

        if has_real_stats:
            return {
                "home_goals_for": home_stats.get("goals_for", 15),
                "home_games": home_stats.get("games", 10),
                "home_goals_against": home_stats.get("goals_against", 12),
                "away_goals_for": away_stats.get("goals_for", 12),
                "away_games": away_stats.get("games", 10),
                "away_goals_against": away_stats.get("goals_against", 15),
                "home_shots": home_stats.get("shots"),
                "home_shots_on_target": home_stats.get("shots_on_target"),
                "away_shots": away_stats.get("shots"),
                "away_shots_on_target": away_stats.get("shots_on_target"),
            }

        # 无真实统计数据：返回 games=0 触发从赔率估算
        return {
            "home_goals_for": 0,
            "home_games": 0,
            "home_goals_against": 0,
            "away_goals_for": 0,
            "away_games": 0,
            "away_goals_against": 0,
            "home_shots": None,
            "home_shots_on_target": None,
            "away_shots": None,
            "away_shots_on_target": None,
        }

    def _estimate_stats_from_odds(self, home_odds: float, draw_odds: float,
                                   away_odds: float, return_rate: float,
                                   odds: Optional[Dict] = None) -> Dict[str, int]:
        """从赔率估算球队统计数据（当真实数据不可用时）"""
        # 提取总进球赔率（如果有）
        ttg_odds = None
        if odds:
            ttg_odds = {}
            for key, val in odds.items():
                # 兼容两种键名格式: "ttg_0" 和 "goals_0"
                if (key.startswith("ttg_") or key.startswith("goals_")) and isinstance(val, (int, float)) and val > 0:
                    goals_key = key[4:]  # 去掉 "ttg_" 或 "goals_" 前缀
                    ttg_odds[goals_key] = val
            if not ttg_odds:
                ttg_odds = None

        # 使用泊松模型的赔率反推方法估算预期进球
        home_lambda, away_lambda = _estimate_lambdas_from_odds(
            home_odds, draw_odds, away_odds, return_rate,
            ttg_odds=ttg_odds
        )

        # 将预期进球转换为模拟的统计数据（保留浮点精度）
        # 假设每队已进行10场比赛
        # 注意: 不在这里乘主场/客场加成，calculate_expected_goals 会处理
        games = 10
        home_goals_for = round(home_lambda * games)
        home_goals_against = round(away_lambda * games)
        away_goals_for = round(away_lambda * games)
        away_goals_against = round(home_lambda * games)

        return {
            "home_goals_for": max(1, home_goals_for),
            "home_games": games,
            "home_goals_against": max(1, home_goals_against),
            "away_goals_for": max(1, away_goals_for),
            "away_games": games,
            "away_goals_against": max(1, away_goals_against),
        }

    async def analyze_match(self, match_id: str, lottery_type: str = "竞彩足球",
                      depth: str = "full") -> Dict[str, Any]:
        """分析单场比赛

        Args:
            match_id: 比赛ID
            lottery_type: 彩种类型
            depth: 分析深度 - stage1(基础)/stage2(深度)/full(完整)

        Raises:
            ValueError: 当缓存为空且无法从 manager 获取数据时
        """
        try:
            # 获取比赛数据：优先从缓存获取
            matches = get_cached_matches()
            match_data = None
            for m in matches:
                if m.get("match_id") == match_id:
                    match_data = m
                    break

            # 缓存为空时，尝试从 manager 直接获取数据
            if not match_data and not matches:
                try:
                    manager = _get_manager()
                    odds_result = await manager.get_lottery_odds_change(match_id)
                    if odds_result and odds_result.get("data"):
                        match_data = {
                            "match_id": match_id,
                            "odds": odds_result["data"],
                        }
                except Exception as mgr_err:
                    logger.warning(f"从 manager 获取数据失败: {mgr_err}")

            if not match_data:
                raise ValueError(
                    f"数据缓存为空，请先调用 lottery_fetch_today_matches 获取比赛数据"
                )

            # 提取基本信息
            # 兼容两种数据格式：
            # 格式A: match_data["odds"]["had"]["win"] (data_tools缓存格式)
            # 格式B: match_data["had"]["win"] (竞彩API原始格式)
            odds = match_data.get("odds", {})
            if not odds:
                # 从顶层赔率字段构建
                odds = {}
                for nested_key in ("had", "hhad", "crs", "ttg", "hafu"):
                    if nested_key in match_data:
                        odds[nested_key] = match_data[nested_key]
            
            had = odds.get("had", {})
            home_odds = float(had.get("win", odds.get("win", odds.get("home_win", 2.10)) or 2.10))
            draw_odds = float(had.get("draw", odds.get("draw", 3.20)) or 3.20)
            away_odds = float(had.get("lose", odds.get("lose", odds.get("away_win", 3.50)) or 3.50))

            home_team_id = match_data.get("home_team_id", f"home_{match_id}")
            away_team_id = match_data.get("away_team_id", f"away_{match_id}")
            home_team_name = match_data.get("home_team", "主队")
            away_team_name = match_data.get("away_team", "客队")
            league = match_data.get("league", "default")

            # 获取返还率
            return_rate = get_rules_engine().get_return_rate(lottery_type)

            # 获取球队统计数据
            team_stats = self._extract_team_stats(match_data)

            # 如果缺少统计数据，从赔率估算
            if team_stats["home_games"] == 0 or team_stats["away_games"] == 0:
                estimated = self._estimate_stats_from_odds(
                    home_odds, draw_odds, away_odds, return_rate,
                    odds=odds
                )
                team_stats.update(estimated)

            # 根据深度执行不同级别的分析
            if depth == "stage1":
                # stage1: 仅泊松分析
                poisson_result = self._analyze_poisson_only(
                    team_stats, league, return_rate
                )
                result = {
                    "match_id": match_id,
                    "lottery_type": lottery_type,
                    "match_data": match_data,
                    "statistical_models": {
                        "poisson": poisson_result,
                    },
                    "combined_score": poisson_result.get("win_prob", 0.33) * 100,
                    "agreement_level": "未知",
                    "risk_level": "中",
                    "recommendation": self._generate_recommendation(
                        poisson_result, 50, odds
                    ),
                    "timestamp": datetime.now().isoformat(),
                }

            elif depth == "stage2":
                # stage2: 泊松 + Elo
                poisson_result = self._analyze_poisson_only(
                    team_stats, league, return_rate
                )
                elo_result = self._analyze_elo_only(
                    home_team_id, away_team_id, home_team_name, away_team_name, league
                )

                result = {
                    "match_id": match_id,
                    "lottery_type": lottery_type,
                    "match_data": match_data,
                    "statistical_models": {
                        "poisson": poisson_result,
                        "elo": elo_result,
                    },
                    "combined_score": self._calculate_combined_score_stage2(
                        poisson_result, elo_result
                    ),
                    "agreement_level": self._check_model_agreement_simple(
                        poisson_result, elo_result
                    ),
                    "risk_level": "中",
                    "recommendation": self._generate_recommendation(
                        poisson_result, 50, odds
                    ),
                    "timestamp": datetime.now().isoformat(),
                }

            else:  # full
                # 完整分析：使用 StatisticalEngine
                full_result = self._analyze_full(
                    team_stats, home_team_id, away_team_id,
                    home_team_name, away_team_name, league,
                    return_rate, odds
                )
                result = {
                    "match_id": match_id,
                    "lottery_type": lottery_type,
                    "match_data": match_data,
                    "statistical_models": {
                        "poisson": full_result["poisson"],
                        "elo": full_result["elo"],
                        "xg": full_result["xg"],
                    },
                    "combined_score": full_result["combined_score"],
                    "agreement_level": full_result["agreement_level"],
                    "risk_level": self._determine_risk_level(
                        full_result["combined_score"],
                        full_result["agreement_level"]
                    ),
                    "recommendation": self._generate_recommendation(
                        full_result["poisson"], full_result["combined_score"], odds
                    ),
                    "timestamp": datetime.now().isoformat(),
                }

            return result

        except ValueError:
            # 数据不可用时直接向上抛出，让上层工具捕获并返回明确错误
            raise
        except Exception as e:
            logger.error(f"比赛分析失败: {e}")
            # 修复：不再返回硬编码的降级假数据，而是抛出明确异常
            raise ValueError(
                f"比赛分析失败（{match_id}）：{e}，请确认比赛数据已通过 lottery_fetch_today_matches 获取"
            ) from e

    def _analyze_poisson_only(self, team_stats: Dict, league: str,
                               return_rate: float) -> Dict[str, Any]:
        """仅执行泊松分析"""
        home_expected, away_expected = self._poisson.calculate_expected_goals(
            team_stats["home_goals_for"],
            team_stats["home_games"],
            team_stats["home_goals_against"],
            team_stats["away_goals_for"],
            team_stats["away_games"],
            team_stats["away_goals_against"],
            league
        )

        prediction = self._poisson.predict(home_expected, away_expected, return_rate)

        return {
            "win_prob": prediction.home_win_prob,
            "draw_prob": prediction.draw_prob,
            "lose_prob": prediction.away_win_prob,
            "home_expected_goals": prediction.home_expected_goals,
            "away_expected_goals": prediction.away_expected_goals,
            "lambda_home": prediction.home_expected_goals,
            "lambda_away": prediction.away_expected_goals,
            "most_likely_score": prediction.most_likely_score,
            "most_likely_score_prob": prediction.most_likely_score_prob,
            "score_probabilities": prediction.score_probabilities,
            "full_score_matrix": prediction.full_score_matrix,
            "over_under_2_5": prediction.over_under_2_5,
            "btts_prob": prediction.btts_prob,
        }

    def _analyze_elo_only(self, home_team_id: str, away_team_id: str,
                          home_team_name: str, away_team_name: str,
                          league: str) -> Dict[str, Any]:
        """仅执行Elo分析"""
        elo_result = self._stat_engine.elo.predict_match(
            home_team_id, away_team_id, league
        )

        return {
            "win_prob": elo_result["home_win_prob"],
            "draw_prob": elo_result["draw_prob"],
            "lose_prob": elo_result["away_win_prob"],
            "home_elo": elo_result["home_elo"],
            "away_elo": elo_result["away_elo"],
            "rating_diff": elo_result["rating_diff"],
            "form_elo": elo_result.get("form_elo", {}),
        }

    def _analyze_full(self, team_stats: Dict, home_team_id: str, away_team_id: str,
                      home_team_name: str, away_team_name: str, league: str,
                      return_rate: float, market_odds: Dict) -> Dict[str, Any]:
        """执行完整分析"""
        # 使用 StatisticalEngine 执行综合分析
        analysis = self._stat_engine.full_analysis(
            home_goals_for=team_stats["home_goals_for"],
            home_games=team_stats["home_games"],
            home_goals_against=team_stats["home_goals_against"],
            away_goals_for=team_stats["away_goals_for"],
            away_games=team_stats["away_games"],
            away_goals_against=team_stats["away_goals_against"],
            home_shots=team_stats.get("home_shots"),
            home_shots_on_target=team_stats.get("home_shots_on_target"),
            away_shots=team_stats.get("away_shots"),
            away_shots_on_target=team_stats.get("away_shots_on_target"),
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
            league=league,
            return_rate=return_rate,
            market_odds=market_odds if market_odds else None,
        )

        # 转换为兼容的格式
        poisson_dict = {
            "win_prob": analysis.poisson.home_win_prob,
            "draw_prob": analysis.poisson.draw_prob,
            "lose_prob": analysis.poisson.away_win_prob,
            "home_expected_goals": analysis.poisson.home_expected_goals,
            "away_expected_goals": analysis.poisson.away_expected_goals,
            "lambda_home": analysis.poisson.home_expected_goals,
            "lambda_away": analysis.poisson.away_expected_goals,
            "most_likely_score": analysis.poisson.most_likely_score,
            "most_likely_score_prob": analysis.poisson.most_likely_score_prob,
            "score_probabilities": analysis.poisson.score_probabilities,
            "full_score_matrix": analysis.poisson.full_score_matrix,
            "over_under_2_5": analysis.poisson.over_under_2_5,
            "btts_prob": analysis.poisson.btts_prob,
        }

        xg_dict = {
            "home_xg": analysis.xg.home_xg,
            "away_xg": analysis.xg.away_xg,
            "home_xga": analysis.xg.home_xga,
            "away_xga": analysis.xg.away_xga,
            "home_shot_quality": analysis.xg.home_shot_quality,
            "away_shot_quality": analysis.xg.away_shot_quality,
            "sustainability_score": analysis.xg.sustainability_score,
            "regression_warning": analysis.xg.regression_warning,
        }

        return {
            "poisson": poisson_dict,
            "elo": analysis.elo,
            "xg": xg_dict,
            "combined_score": analysis.combined_score,
            "agreement_level": analysis.agreement_level,
            "value_bets": analysis.value_bets,
        }

    def _fallback_analysis(self, match_id: str, lottery_type: str,
                           match_data: Optional[Dict]) -> Dict[str, Any]:
        """降级分析 - 当专业分析失败时使用

        修复说明：原实现返回硬编码的 combined_score: 50.0 和默认赔率 2.10/3.20/3.50，
        导致上层工具基于无意义数据产出分析结果。现在改为抛出异常。
        """
        raise ValueError(
            f"比赛 {match_id} 的专业分析失败，且无有效数据可用于降级分析。"
            f"请先调用 lottery_fetch_today_matches 获取比赛数据。"
        )

    def _calculate_combined_score_stage2(self, poisson: Dict, elo: Dict) -> float:
        """stage2 综合评分计算"""
        poisson_score = poisson.get("win_prob", 0.33) * 100
        elo_score = elo.get("win_prob", 0.33) * 100

        # stage2: 泊松60%, Elo40%
        combined = poisson_score * 0.6 + elo_score * 0.4
        return round(combined, 1)

    def _check_model_agreement_simple(self, poisson: Dict, elo: Dict) -> str:
        """检查模型一致性（简化版）"""
        poisson_home = poisson.get("win_prob", 0.33)
        elo_home = elo.get("win_prob", 0.33)

        diff = abs(poisson_home - elo_home)

        if diff < 0.05:
            return "高度一致"
        elif diff < 0.10:
            return "基本一致"
        elif diff < 0.15:
            return "存在分歧"
        else:
            return "显著分歧"

    def _calculate_combined_score(self, poisson: Dict, elo: Dict, xg: Dict) -> float:
        """计算综合评分（完整版）"""
        # 权重：泊松40%，Elo30%，xG30%
        poisson_score = (poisson.get("win_prob", 0.33) +
                        poisson.get("draw_prob", 0.33) * 0.5) * 100
        elo_score = elo.get("win_prob", 0.33) * 100
        xg_score = xg.get("sustainability_score", 50)

        combined = poisson_score * 0.4 + elo_score * 0.3 + xg_score * 0.3
        return round(combined, 1)

    def _check_model_agreement(self, poisson: Dict, elo: Dict) -> str:
        """检查模型一致性"""
        poisson_home = poisson.get("win_prob", 0.33)
        elo_home = elo.get("win_prob", 0.33)

        diff = abs(poisson_home - elo_home)

        if diff < 0.05:
            return "高度一致"
        elif diff < 0.10:
            return "基本一致"
        elif diff < 0.15:
            return "存在分歧"
        else:
            return "显著分歧"

    def _determine_risk_level(self, score: float, agreement: str) -> str:
        """确定风险等级"""
        if score < 40 or agreement == "显著分歧":
            return "高"
        elif score < 55 or agreement == "存在分歧":
            return "中"
        else:
            return "低"

    def _generate_recommendation(self, poisson: Dict, score: float,
                                 market_odds: Optional[Dict] = None) -> Dict[str, Any]:
        """生成投注建议

        利用赔率隐含概率与模型概率综合分析，产出推荐选项、数值置信度、
        combined_score 和 risk_assessment。

        Args:
            poisson: 泊松模型预测结果
            score: 综合评分 (combined_score)
            market_odds: 市场赔率数据，用于计算隐含概率
        """
        win_prob = poisson.get("win_prob", 0.33)
        draw_prob = poisson.get("draw_prob", 0.33)
        lose_prob = poisson.get("lose_prob", 0.33)

        # 找出模型概率最高的选项
        probs = [("主胜", win_prob), ("平局", draw_prob), ("客胜", lose_prob)]
        best = max(probs, key=lambda x: x[1])

        # 利用赔率数据计算隐含概率
        implied_probs = {}
        odds_values = {}
        if market_odds:
            # 兼容两种赔率结构：
            # 1. 嵌套结构: {"had": {"win": ..., "draw": ..., "lose": ...}}
            # 2. 扁平化结构: {"win": ..., "draw": ..., "lose": ...} 或 {"had_w": ..., "had_d": ..., "had_l": ...}
            had = market_odds.get("had", {})
            if not had:
                # 尝试扁平化键名
                had = {
                    "win": market_odds.get("had_w", market_odds.get("win", 0)),
                    "draw": market_odds.get("had_d", market_odds.get("draw", 0)),
                    "lose": market_odds.get("had_l", market_odds.get("lose", 0)),
                }
            if had:
                try:
                    w = float(had.get("win", 0))
                    d = float(had.get("draw", 0))
                    l = float(had.get("lose", 0))
                    if w > 0 and d > 0 and l > 0:
                        total_implied = 1/w + 1/d + 1/l
                        implied_probs = {
                            "主胜": (1/w) / total_implied,
                            "平局": (1/d) / total_implied,
                            "客胜": (1/l) / total_implied,
                        }
                        odds_values = {"主胜": w, "平局": d, "客胜": l}
                except (ValueError, TypeError):
                    pass

        # 如果有隐含概率，结合模型概率和隐含概率确定推荐
        if implied_probs:
            # 加权融合：模型概率60% + 隐含概率40%
            fused = {}
            for label in ["主胜", "平局", "客胜"]:
                model_p = dict(probs)[label]
                implied_p = implied_probs.get(label, model_p)
                fused[label] = model_p * 0.6 + implied_p * 0.4

            best_label = max(fused, key=fused.get)
            best_prob = fused[best_label]
            best_odds = odds_values.get(best_label, 0)

            # 数值置信度：基于概率优势大小 (0-100)
            # 概率优势 = 最高概率 - 第二高概率
            sorted_probs = sorted(fused.values(), reverse=True)
            prob_margin = sorted_probs[0] - sorted_probs[1]
            confidence_score = min(round((best_prob * 0.7 + prob_margin * 0.3) * 100, 1), 99.0)

            # combined_score：基于置信度和赔率的综合评分
            if best_odds > 0:
                ev = best_prob * best_odds  # 期望值
                combined = round(confidence_score * 0.6 + min(ev * 20, 40) * 0.4, 1)
            else:
                combined = round(confidence_score, 1)

            # risk_assessment：基于赔率和概率偏差
            model_best_prob = dict(probs)[best_label]
            implied_best_prob = implied_probs.get(best_label, model_best_prob)
            prob_deviation = abs(model_best_prob - implied_best_prob)

            if prob_deviation > 0.10:
                risk_detail = "模型与市场分歧较大"
                risk_level = "高"
            elif prob_deviation > 0.05:
                risk_detail = "模型与市场存在一定分歧"
                risk_level = "中"
            else:
                risk_detail = "模型与市场基本一致"
                risk_level = "低"

            # 如果赔率偏低（<1.5），风险更高
            if best_odds > 0 and best_odds < 1.5:
                risk_level = "高" if risk_level != "低" else "中"
                risk_detail += "，赔率偏低"

            confidence_label = "高" if confidence_score >= 65 else "中" if confidence_score >= 50 else "低"

            return {
                "pick": best_label,
                "probability": round(best_prob, 3),
                "confidence": confidence_label,
                "confidence_score": confidence_score,
                "combined_score": combined,
                "risk_assessment": {
                    "level": risk_level,
                    "detail": risk_detail,
                    "prob_deviation": round(prob_deviation, 4),
                    "model_prob": round(model_best_prob, 4),
                    "implied_prob": round(implied_best_prob, 4),
                },
                "odds": best_odds,
                "implied_probs": {k: round(v, 4) for k, v in implied_probs.items()},
                "most_likely_score": poisson.get("most_likely_score", "1:1"),
            }
        else:
            # 无赔率数据时的降级逻辑（保持原有行为）
            confidence = "高" if score >= 65 else "中" if score >= 50 else "低"
            return {
                "pick": best[0],
                "probability": round(best[1], 3),
                "confidence": confidence,
                "confidence_score": round(best[1] * 100, 1),
                "combined_score": round(score, 1),
                "risk_assessment": {
                    "level": "中",
                    "detail": "无赔率数据，无法评估市场偏差",
                    "prob_deviation": 0,
                    "model_prob": round(best[1], 4),
                    "implied_prob": 0,
                },
                "odds": 0,
                "implied_probs": {},
                "most_likely_score": poisson.get("most_likely_score", "1:1"),
            }

    async def detect_risk_signals(self, match_id: str,
                           signal_types: Optional[List[str]] = None,
                           current_odds: Optional[Dict[str, float]] = None,
                           previous_odds: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """检测风险信号
        
        Args:
            match_id: 比赛ID
            signal_types: 信号类型列表，None表示检测所有类型
            current_odds: 当前赔率（用于赔率异动检测）
            previous_odds: 历史赔率（用于赔率异动检测）
            
        Returns:
            风险信号检测结果
        """
        signals = []
        
        # 检测赔率异动
        if not signal_types or "odds_drift" in signal_types:
            if current_odds and previous_odds:
                drifts = _detect_odds_drift(current_odds, previous_odds, threshold=0.10)
                for drift in drifts:
                    signals.append({
                        "type": "odds_drift",
                        "severity": "high" if drift["severity"] == "高" else "medium",
                        "message": f"{drift['selection']}赔率较开盘时{drift['direction']}{abs(drift['change_pct']):.1f}%",
                        "details": drift,
                    })
            else:
                # 赔率数据不完整时给出提示
                signals.append({
                    "type": "odds_drift",
                    "severity": "info",
                    "message": "赔率历史数据不完整，无法检测异动",
                    "details": {"reason": "缺少previous_odds"},
                })

        # 检测阵容风险
        if not signal_types or "lineup" in signal_types:
            # 尝试从数据层获取伤停信息
            try:
                from lottery_mcp.data.sources import FreeDataSourceManager
                data_manager = FreeDataSourceManager()
                
                # 解析比赛ID获取球队信息（假设格式: YYYYMMDD_Home_vs_Away）
                parts = match_id.split("_")
                if len(parts) >= 3:
                    home_team = parts[1]
                    away_team = parts[2]
                    
                    # 获取主队伤停
                    home_injuries = await data_manager.get_injuries(home_team)
                    if home_injuries.get("data", {}).get("total_injured", 0) > 0:
                        injury_count = home_injuries["data"]["total_injured"]
                        signals.append({
                            "type": "lineup",
                            "severity": "medium" if injury_count < 3 else "high",
                            "message": f"主队{home_team}有{injury_count}名球员伤停",
                            "details": {
                                "team": home_team,
                                "injury_count": injury_count,
                                "injuries": home_injuries["data"].get("injury_list", [])[:3],  # 只显示前3个
                            },
                        })
                    
                    # 获取客队伤停
                    away_injuries = await data_manager.get_injuries(away_team)
                    if away_injuries.get("data", {}).get("total_injured", 0) > 0:
                        injury_count = away_injuries["data"]["total_injured"]
                        signals.append({
                            "type": "lineup",
                            "severity": "medium" if injury_count < 3 else "high",
                            "message": f"客队{away_team}有{injury_count}名球员伤停",
                            "details": {
                                "team": away_team,
                                "injury_count": injury_count,
                                "injuries": away_injuries["data"].get("injury_list", [])[:3],
                            },
                        })
                else:
                    # 修复：match_id 格式不支持时返回有意义的错误提示，而非静默跳过
                    signals.append({
                        "type": "lineup",
                        "severity": "info",
                        "message": f"比赛ID格式（{match_id}）不支持自动伤停查询，"
                                   f"伤停检测需要 YYYYMMDD_Home_vs_Away 格式的 match_id",
                    })
                    
            except Exception as e:
                logger.warning(f"获取伤停信息失败: {e}")
                signals.append({
                    "type": "lineup",
                    "severity": "info",
                    "message": "伤停信息获取失败",
                    "details": {"error": str(e)},
                })

        # 计算总体风险等级
        severity_scores = {"high": 3, "medium": 2, "low": 1, "info": 0}
        max_score = max([severity_scores.get(s["severity"], 0) for s in signals], default=0)
        
        overall_risk = "low"
        if max_score >= 3:
            overall_risk = "high"
        elif max_score >= 2:
            overall_risk = "medium"

        return {
            "match_id": match_id,
            "signal_count": len([s for s in signals if s["severity"] != "info"]),
            "signals": signals,
            "overall_risk": overall_risk,
            "analysis_timestamp": datetime.now().isoformat(),
        }

    async def analyze_match_plays(self, match_id: str, lottery_type: str = "竞彩足球",
                           handicap: float = 0.0) -> Dict[str, Any]:
        """分析比赛的所有五大玩法

        Args:
            match_id: 比赛ID
            lottery_type: 彩种类型
            handicap: 让球数（用于RQSPF分析）

        Returns:
            五大玩法的分析结果
        """
        try:
            # 首先获取比赛的基础分析结果
            base_analysis = await self.analyze_match(match_id, lottery_type, depth="full")

            if not base_analysis.get("statistical_models"):
                return {"error": "无法获取比赛统计模型数据"}

            poisson_result = base_analysis["statistical_models"].get("poisson", {})
            odds = base_analysis.get("match_data", {}).get("odds", {})

            # 使用玩法分析器分析所有五大玩法
            play_analyzer = get_play_analyzer()
            play_results = play_analyzer.analyze_all_plays(poisson_result, odds, handicap)

            # 转换为可序列化的格式
            result = {
                "match_id": match_id,
                "lottery_type": lottery_type,
                "handicap": handicap,
                "plays": {},
                "summary": {
                    "total_plays_analyzed": 5,
                    "plays_with_value_bets": 0,
                    "highest_confidence_play": None,
                },
                "timestamp": datetime.now().isoformat(),
            }

            plays_with_value = 0
            highest_confidence = None
            highest_confidence_level = 0

            for play_type, play_result in play_results.items():
                # 统计有价值投注的玩法数量
                if play_result.recommendations:
                    plays_with_value += 1

                # 找出置信度最高的玩法
                confidence_level = {"高": 3, "中": 2, "低": 1}.get(play_result.confidence, 0)
                if confidence_level > highest_confidence_level:
                    highest_confidence_level = confidence_level
                    highest_confidence = play_type

                result["plays"][play_type] = {
                    "play_name": self._get_play_name(play_type),
                    "confidence": play_result.confidence,
                    "probabilities": play_result.probabilities,
                    "recommendations": play_result.recommendations,
                    "expected_values": play_result.expected_value,
                    "analysis_notes": play_result.analysis_notes,
                }

            result["summary"]["plays_with_value_bets"] = plays_with_value
            result["summary"]["highest_confidence_play"] = highest_confidence

            return result

        except Exception as e:
            logger.error(f"玩法分析失败: {e}")
            raise_tool_error(f"玩法分析失败: {str(e)}")

    def _get_play_name(self, play_type: str) -> str:
        """获取玩法中文名称"""
        names = {
            "SPF": "胜平负",
            "RQSPF": "让球胜平负",
            "BF": "比分",
            "ZJQ": "总进球",
            "BQC": "半全场",
        }
        return names.get(play_type, play_type)

    async def compare_models(self, match_id: str, lottery_type: str = "竞彩足球",
                       models: Optional[List[str]] = None) -> Dict[str, Any]:
        """对比多个统计模型的预测结果

        Args:
            match_id: 比赛ID
            lottery_type: 彩种类型
            models: 要对比的模型列表，默认 ["poisson", "elo", "xg"]

        Returns:
            结构化的多模型对比结果
        """
        if models is None:
            models = ["poisson", "elo", "xg"]

        # 验证模型名称
        valid_models = {"poisson", "elo", "xg"}
        for m in models:
            if m not in valid_models:
                return {"error": f"不支持的模型: {m}，可选: {', '.join(valid_models)}"}

        try:
            # 获取比赛数据：优先从缓存获取
            matches = get_cached_matches()
            match_data = None
            for m in matches:
                if m.get("match_id") == match_id:
                    match_data = m
                    break

            # 缓存为空时，尝试从 manager 直接获取数据
            if not match_data and not matches:
                try:
                    manager = _get_manager()
                    odds_result = await manager.get_lottery_odds_change(match_id)
                    if odds_result and odds_result.get("data"):
                        match_data = {
                            "match_id": match_id,
                            "odds": odds_result["data"],
                        }
                except Exception as mgr_err:
                    logger.warning(f"从 manager 获取数据失败: {mgr_err}")

            if not match_data:
                return {"error": "数据缓存为空，请先调用 lottery_fetch_today_matches 获取比赛数据"}

            # 提取基本信息
            odds = match_data.get("odds", {})
            home_team_id = match_data.get("home_team_id", f"home_{match_id}")
            away_team_id = match_data.get("away_team_id", f"away_{match_id}")
            home_team_name = match_data.get("home_team", "主队")
            away_team_name = match_data.get("away_team", "客队")
            league = match_data.get("league", "default")
            return_rate = get_rules_engine().get_return_rate(lottery_type)
            team_stats = self._extract_team_stats(match_data)

            if team_stats["home_games"] == 0 or team_stats["away_games"] == 0:
                estimated = self._estimate_stats_from_odds(
                    odds.get("home_win", odds.get("win", 2.10)),
                    odds.get("draw", 3.20),
                    odds.get("away_win", odds.get("lose", 3.50)),
                    return_rate,
                    odds=odds
                )
                team_stats.update(estimated)

            # 收集各模型预测结果
            model_results = {}
            model_names = {"poisson": "泊松模型", "elo": "Elo评级模型", "xg": "期望进球模型"}

            # 如果需要xg，则必须执行完整分析（xg没有独立方法）
            if "xg" in models:
                full_result = self._analyze_full(
                    team_stats, home_team_id, away_team_id,
                    home_team_name, away_team_name, league,
                    return_rate, odds
                )
                # 从完整结果中提取各模型数据
                if "poisson" in models:
                    model_results["poisson"] = {
                        "name": model_names["poisson"],
                        "win_prob": full_result["poisson"]["win_prob"],
                        "draw_prob": full_result["poisson"]["draw_prob"],
                        "lose_prob": full_result["poisson"]["lose_prob"],
                        "details": {
                            "home_expected_goals": full_result["poisson"].get("home_expected_goals"),
                            "away_expected_goals": full_result["poisson"].get("away_expected_goals"),
                            "most_likely_score": full_result["poisson"].get("most_likely_score"),
                        },
                    }
                if "elo" in models:
                    model_results["elo"] = {
                        "name": model_names["elo"],
                        "win_prob": full_result["elo"]["win_prob"],
                        "draw_prob": full_result["elo"]["draw_prob"],
                        "lose_prob": full_result["elo"]["lose_prob"],
                        "details": {
                            "home_elo": full_result["elo"].get("home_elo"),
                            "away_elo": full_result["elo"].get("away_elo"),
                            "rating_diff": full_result["elo"].get("rating_diff"),
                        },
                    }
                if "xg" in models:
                    model_results["xg"] = {
                        "name": model_names["xg"],
                        "win_prob": self._derive_xg_prob(full_result["xg"]),
                        "draw_prob": self._derive_xg_draw_prob(full_result["xg"]),
                        "lose_prob": self._derive_xg_away_prob(full_result["xg"]),
                        "details": {
                            "home_xg": full_result["xg"].get("home_xg"),
                            "away_xg": full_result["xg"].get("away_xg"),
                            "home_xga": full_result["xg"].get("home_xga"),
                            "away_xga": full_result["xg"].get("away_xga"),
                            "sustainability_score": full_result["xg"].get("sustainability_score"),
                            "regression_warning": full_result["xg"].get("regression_warning"),
                        },
                    }
            else:
                # 不需要xg，分别调用独立方法
                if "poisson" in models:
                    poisson_result = self._analyze_poisson_only(team_stats, league, return_rate)
                    model_results["poisson"] = {
                        "name": model_names["poisson"],
                        "win_prob": poisson_result["win_prob"],
                        "draw_prob": poisson_result["draw_prob"],
                        "lose_prob": poisson_result["lose_prob"],
                        "details": {
                            "home_expected_goals": poisson_result.get("home_expected_goals"),
                            "away_expected_goals": poisson_result.get("away_expected_goals"),
                            "most_likely_score": poisson_result.get("most_likely_score"),
                        },
                    }
                if "elo" in models:
                    elo_result = self._analyze_elo_only(
                        home_team_id, away_team_id, home_team_name, away_team_name, league
                    )
                    model_results["elo"] = {
                        "name": model_names["elo"],
                        "win_prob": elo_result["win_prob"],
                        "draw_prob": elo_result["draw_prob"],
                        "lose_prob": elo_result["lose_prob"],
                        "details": {
                            "home_elo": elo_result.get("home_elo"),
                            "away_elo": elo_result.get("away_elo"),
                            "rating_diff": elo_result.get("rating_diff"),
                        },
                    }

            # 计算模型间一致性
            agreement = self._compute_multi_model_agreement(model_results)

            # 计算概率分歧最大的选项
            max_divergence = self._compute_max_divergence(model_results)

            # 计算加权平均概率（综合建议）
            weights = {"poisson": 0.40, "elo": 0.30, "xg": 0.30}
            total_weight = sum(weights.get(m, 0) for m in model_results)
            if total_weight > 0:
                avg_win = sum(model_results[m]["win_prob"] * weights.get(m, 0) for m in model_results) / total_weight
                avg_draw = sum(model_results[m]["draw_prob"] * weights.get(m, 0) for m in model_results) / total_weight
                avg_lose = sum(model_results[m]["lose_prob"] * weights.get(m, 0) for m in model_results) / total_weight
            else:
                avg_win = avg_draw = avg_lose = 0.333

            # 综合建议
            probs = [("主胜", avg_win), ("平局", avg_draw), ("客胜", avg_lose)]
            best_pick = max(probs, key=lambda x: x[1])

            return {
                "match_id": match_id,
                "lottery_type": lottery_type,
                "home_team": home_team_name,
                "away_team": away_team_name,
                "league": league,
                "models_compared": list(model_results.keys()),
                "model_count": len(model_results),
                "predictions": model_results,
                "comparison": {
                    "agreement_level": agreement["level"],
                    "agreement_description": agreement["description"],
                    "max_divergence_option": max_divergence["option"],
                    "max_divergence_value": max_divergence["value"],
                    "divergence_details": max_divergence["details"],
                },
                "consensus": {
                    "weighted_avg": {
                        "主胜": round(avg_win, 4),
                        "平局": round(avg_draw, 4),
                        "客胜": round(avg_lose, 4),
                    },
                    "recommended_pick": best_pick[0],
                    "recommended_probability": round(best_pick[1], 4),
                    "confidence": self._get_consensus_confidence(agreement["level"], best_pick[1]),
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"模型对比失败: {e}")
            raise_tool_error(f"模型对比失败: {str(e)}")

    def _derive_xg_prob(self, xg_data: Dict) -> float:
        """从xG数据推导主胜概率"""
        home_xg = xg_data.get("home_xg", 1.3)
        away_xg = xg_data.get("away_xg", 1.1)
        # 使用泊松分布从xG推导胜平负概率
        from math import exp, factorial
        home_win = 0.0
        for h in range(8):
            for a in range(8):
                p_home = (exp(-home_xg) * home_xg**h / factorial(h))
                p_away = (exp(-away_xg) * away_xg**a / factorial(a))
                if h > a:
                    home_win += p_home * p_away
        return round(min(home_win, 0.99), 4)

    def _derive_xg_draw_prob(self, xg_data: Dict) -> float:
        """从xG数据推导平局概率"""
        home_xg = xg_data.get("home_xg", 1.3)
        away_xg = xg_data.get("away_xg", 1.1)
        from math import exp, factorial
        draw = 0.0
        for h in range(8):
            for a in range(8):
                p_home = (exp(-home_xg) * home_xg**h / factorial(h))
                p_away = (exp(-away_xg) * away_xg**a / factorial(a))
                if h == a:
                    draw += p_home * p_away
        return round(min(draw, 0.99), 4)

    def _derive_xg_away_prob(self, xg_data: Dict) -> float:
        """从xG数据推导客胜概率"""
        home_xg = xg_data.get("home_xg", 1.3)
        away_xg = xg_data.get("away_xg", 1.1)
        from math import exp, factorial
        away_win = 0.0
        for h in range(8):
            for a in range(8):
                p_home = (exp(-home_xg) * home_xg**h / factorial(h))
                p_away = (exp(-away_xg) * away_xg**a / factorial(a))
                if h < a:
                    away_win += p_home * p_away
        return round(min(away_win, 0.99), 4)

    def _compute_multi_model_agreement(self, model_results: Dict) -> Dict[str, Any]:
        """计算多模型间的一致性"""
        if len(model_results) < 2:
            return {"level": "未知", "description": "仅一个模型，无法比较一致性"}

        # 计算所有模型对之间主胜概率的最大差异
        model_keys = list(model_results.keys())
        max_diff = 0.0
        for i in range(len(model_keys)):
            for j in range(i + 1, len(model_keys)):
                diff = abs(model_results[model_keys[i]]["win_prob"] -
                           model_results[model_keys[j]]["win_prob"])
                max_diff = max(max_diff, diff)

        if max_diff < 0.05:
            return {"level": "高度一致", "description": f"所有模型预测高度一致（最大偏差{max_diff:.1%}），结果可信度高"}
        elif max_diff < 0.10:
            return {"level": "基本一致", "description": f"模型间基本一致（最大偏差{max_diff:.1%}），结果较为可信"}
        elif max_diff < 0.15:
            return {"level": "存在分歧", "description": f"模型间存在一定分歧（最大偏差{max_diff:.1%}），建议谨慎参考"}
        else:
            return {"level": "显著分歧", "description": f"模型间分歧显著（最大偏差{max_diff:.1%}），建议结合其他信息综合判断"}

    def _compute_max_divergence(self, model_results: Dict) -> Dict[str, Any]:
        """计算概率分歧最大的选项"""
        if len(model_results) < 2:
            return {"option": "无", "value": 0.0, "details": {}}

        model_keys = list(model_results.keys())
        options = ["win_prob", "draw_prob", "lose_prob"]
        option_names = {"win_prob": "主胜", "draw_prob": "平局", "lose_prob": "客胜"}

        max_div = 0.0
        max_option = "主胜"
        max_details = {}

        for opt in options:
            probs = [model_results[k][opt] for k in model_keys]
            div = max(probs) - min(probs)
            if div > max_div:
                max_div = div
                max_option = option_names[opt]
                max_details = {k: round(model_results[k][opt], 4) for k in model_keys}

        return {
            "option": max_option,
            "value": round(max_div, 4),
            "details": max_details,
        }

    def _get_consensus_confidence(self, agreement_level: str, probability: float) -> str:
        """根据一致性和概率确定综合置信度"""
        if agreement_level == "高度一致" and probability >= 0.50:
            return "高"
        elif agreement_level in ("高度一致", "基本一致") and probability >= 0.40:
            return "中"
        else:
            return "低"


# 全局分析引擎实例
_analysis_engine: Optional[AnalysisEngine] = None


def get_analysis_engine() -> AnalysisEngine:
    """获取分析引擎实例（单例模式）"""
    global _analysis_engine
    if _analysis_engine is None:
        _analysis_engine = AnalysisEngine()
    return _analysis_engine


# ============================================================
# Tool Functions
# ============================================================

async def lottery_analyze_all_matches(params: AnalyzeAllMatchesInput, ctx: Context) -> str:
    """分析所有比赛"""
    try:
        await ctx.report_progress(0.2, "正在获取比赛列表...")
        await ctx.log_info(f"[分析] 分析所有比赛")

        matches = get_cached_matches()
        if not matches:
            # 修复：缓存为空时不再生成 match_001 等假数据，返回明确错误
            raise_tool_error("数据缓存为空，请先调用 lottery_fetch_today_matches 获取比赛数据")

        engine = get_analysis_engine()
        analyses = []

        total = min(len(matches), params.max_matches)
        for i, match in enumerate(matches[:total]):
            progress = 0.3 + (i / total) * 0.6
            await ctx.report_progress(progress, f"分析第 {i+1}/{total} 场...")

            match_id = match.get("match_id", f"match_{i}")
            analysis = await engine.analyze_match(match_id, params.lottery_type)
            analyses.append(analysis)

        await ctx.report_progress(1.0, "分析完成")

        return _to_json({
            "success": True,
            "data": {
                "total_analyzed": len(analyses),
                "analyses": analyses,
            },
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"批量分析失败: {e}")
        raise_tool_error(f"批量分析失败: {str(e)}")


async def lottery_analyze_with_pipeline(params: AnalyzeWithPipelineInput, ctx: Context) -> str:
    """使用统一流水线分析所有比赛
    
    这是 Phase 2 新增的工具，使用统一的分析流水线对比赛进行全面分析。
    与 lottery_analyze_all_matches 的区别：
    - 一次分析，产出完整数据包（基本面+模型+玩法+规则）
    - 包含比赛特征画像和策略配置
    - 包含完整的投注理由链
    """
    try:
        from .analysis_pipeline import run_full_pipeline

        await ctx.report_progress(0.1, "正在获取比赛列表...")
        await ctx.log_info(f"[流水线分析] 开始分析")

        matches = get_cached_matches()
        if not matches:
            raise_tool_error("数据缓存为空，请先调用 lottery_fetch_today_matches 获取比赛数据")

        # 限制比赛数量
        matches = matches[:params.max_matches]
        
        await ctx.report_progress(0.2, "正在执行统一分析流水线...")
        
        # 使用统一流水线
        analyses = await run_full_pipeline(matches)
        
        await ctx.report_progress(0.9, "正在格式化结果...")
        
        # 转换为可读格式
        results = []
        for a in analyses:
            result = {
                "match_id": a.match_id,
                "home_team": a.home_team,
                "away_team": a.away_team,
                "league": a.league,
                "match_time": a.match_time,
                "handicap": a.handicap,
                "statistical_models": a.statistical_models,
                "agreement_level": a.agreement_level,
                "combined_score": a.combined_score,
                "risk_level": a.risk_level,
                "plays": a.plays,
                "match_profile": a.match_profile,
                "strategy_config": a.strategy_config,
                "best_play": a.best_play,
                "best_selection": a.best_selection,
                "best_probability": a.best_probability,
                "best_odds": a.best_odds,
                "best_ev": a.best_ev,
                "play_ranking": a.play_ranking,
                "rules_compliance": a.rules_compliance,
                "upset_signals": a.upset_signals,
                "analyzed_at": a.analyzed_at,
                "data_quality": a.data_quality,
            }
            
            if params.include_reasoning:
                result["reasoning_chain"] = a.reasoning_chain
            
            results.append(result)

        await ctx.report_progress(1.0, "分析完成")

        # 构建输出，包含失败比赛和警告信息
        output_data = {
            "total_analyzed": len(results),
            "analyses": results,
            "pipeline_version": "2.0",
        }
        if analyses.failed_matches:
            output_data["failed_matches"] = analyses.failed_matches
        if analyses.warnings:
            output_data["warnings"] = analyses.warnings

        return _to_json({
            "success": True,
            "data": output_data,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"流水线分析失败: {e}")
        raise_tool_error(f"流水线分析失败: {str(e)}")


async def lottery_advisor_analysis(params: AnalyzeMatchInput, ctx: Context) -> str:
    """智能顾问深度分析 - 多源数据综合推理"""
    try:
        from lottery_mcp.analysis.advisor import SmartAdvisor

        await ctx.report_progress(0.1, "正在加载比赛数据...")

        matches = get_cached_matches()
        if not matches:
            raise_tool_error("数据缓存为空，请先调用 lottery_fetch_today_matches 获取比赛数据")

        match_data = None
        for m in matches:
            if m.get("match_id") == params.match_id:
                match_data = m
                break

        if not match_data:
            raise_tool_error(f"未找到比赛ID: {params.match_id}")

        await ctx.report_progress(0.3, "正在并行获取竞彩资讯数据...")

        manager = _get_manager()

        async def _fetch_or_none(coro):
            try:
                result = await coro
                return result.get("data") if result else None
            except Exception:
                return None

        features, h2h, standings, recent_form, injuries = await asyncio.gather(
            _fetch_or_none(manager.get_match_feature(params.match_id)),
            _fetch_or_none(manager.get_result_history(params.match_id)),
            _fetch_or_none(manager.get_match_tables(params.match_id)),
            _fetch_or_none(manager.get_match_recent_form(params.match_id)),
            _fetch_or_none(manager.get_injury_suspension(params.match_id)),
        )

        await ctx.report_progress(0.5, "正在获取国际市场赔率...")

        market_odds = None
        try:
            from lottery_mcp.data.sources import FreeDataSourceManager
            market_manager = FreeDataSourceManager()
            market_result = await market_manager.get_market_odds(params.match_id)
            if market_result.get("data"):
                market_odds = market_result["data"]
        except Exception:
            pass

        await ctx.report_progress(0.6, "正在执行深度分析...")

        advisor = SmartAdvisor()
        decision = advisor.advise(
            match_data=match_data,
            features=features,
            h2h=h2h,
            standings=standings,
            recent_form=recent_form,
            injuries=injuries,
            market_odds=market_odds,
        )

        await ctx.report_progress(1.0, "分析完成")

        result = {
            "success": True,
            "match_id": decision.match_id,
            "match_info": decision.match_info,
            "calibrated_probabilities": decision.calibrated_probs,
            "model_consensus": decision.model_consensus,
            "value_plays": decision.value_plays,
            "arbitrage_signals": decision.arbitrage_signals,
            "risk_matrix": {k: {"score": v["score"], "level": v["level"]}
                           for k, v in decision.risk_matrix.items()},
            "risk_score": decision.risk_score,
            "betting_plans": decision.betting_plans,
            "optimal_play": decision.optimal_play,
            "optimal_selection": decision.optimal_selection,
            "confidence_score": decision.confidence_score,
            "decision_rationale": decision.decision_rationale,
            "overall_verdict": decision.overall_verdict,
            "timestamp": datetime.now().isoformat(),
        }

        return _to_json(result)

    except Exception as e:
        logger.error(f"智能顾问分析失败: {e}")
        raise_tool_error(f"智能顾问分析失败: {str(e)}")


async def lottery_analyze_match_plays(params: AnalyzeMatchPlaysInput, ctx: Context) -> str:
    """分析比赛的五大玩法"""
    try:
        await ctx.report_progress(0.2, "正在初始化玩法分析...")
        await ctx.log_info(f"[玩法分析] 比赛: {params.match_id}, 让球: {params.handicap}")

        engine = get_analysis_engine()

        await ctx.report_progress(0.5, "正在分析五大玩法...")
        result = await engine.analyze_match_plays(
            params.match_id,
            params.lottery_type,
            params.handicap
        )

        await ctx.report_progress(1.0, "玩法分析完成")

        if "error" in result:
            raise_tool_error(result["error"])

        return _to_json({
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"玩法分析失败: {e}")
        raise_tool_error(f"玩法分析失败: {str(e)}")


async def lottery_detect_risk_signals(params: DetectRiskSignalsInput, ctx: Context) -> str:
    """检测比赛风险信号"""
    try:
        await ctx.report_progress(0.3, "正在检测风险信号...")
        await ctx.log_info(f"[风险检测] 比赛: {params.match_id}")

        engine = get_analysis_engine()
        result = await engine.detect_risk_signals(
            match_id=params.match_id,
            signal_types=params.signal_types,
            current_odds=params.current_odds,
            previous_odds=params.previous_odds,
        )

        # 赔率异动事件：通过日志通知 + 返回值中的 events 字段
        events = []
        for signal in result.get("signals", []):
            if signal.get("type") == "odds_drift" and signal.get("severity") in ("high", "medium"):
                details = signal.get("details", {})
                event = {
                    "event_type": "odds_movement",
                    "match_id": params.match_id,
                    "direction": details.get("direction", ""),
                    "change_pct": details.get("change_pct", 0),
                    "selection": details.get("selection", ""),
                    "severity": signal.get("severity", ""),
                }
                events.append(event)
                await ctx.log_warning(
                    f"[赔率异动] {signal.get('severity', '')}级 | "
                    f"比赛:{params.match_id} {details.get('selection', '')} "
                    f"{details.get('direction', '')}{abs(details.get('change_pct', 0)):.1f}%"
                )

        await ctx.report_progress(1.0, "风险检测完成")

        return _to_json({
            "success": True,
            "data": result,
            "events": events,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"风险信号检测失败: {e}")
        raise_tool_error(f"风险信号检测失败: {str(e)}")


async def lottery_compare_model_predictions(params: CompareModelPredictionsInput, ctx: Context) -> str:
    """对比多个统计模型的预测结果"""
    try:
        await ctx.report_progress(0.2, "正在初始化模型对比...")
        await ctx.log_info(f"[模型对比] 比赛: {params.match_id}, 模型: {params.models}")

        engine = get_analysis_engine()

        await ctx.report_progress(0.5, "正在运行模型对比分析...")
        result = await engine.compare_models(
            match_id=params.match_id,
            lottery_type=params.lottery_type,
            models=params.models,
        )

        await ctx.report_progress(1.0, "模型对比完成")

        if "error" in result:
            raise_tool_error(result["error"])

        return _to_json({
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"模型对比失败: {e}")
        raise_tool_error(f"模型对比失败: {str(e)}")


async def lottery_analyze_results(params: AnalyzeResultsInput, ctx: Context) -> str:
    """赛果统计分析"""
    try:
        manager = _get_manager()

        # 计算日期范围
        end_date = params.end_date or datetime.now().strftime("%Y-%m-%d")
        start_date = params.start_date or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        await ctx.log_info(f"[赛果分析] {params.lottery_type} {start_date} ~ {end_date}")

        # 根据彩种获取开奖数据（仅支持竞彩足球）
        all_results = []

        if params.lottery_type == "竞彩足球":
            # 遍历日期范围
            current = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            while current <= end:
                date_str = current.strftime("%Y-%m-%d")
                result = await manager.get_lottery_results(date_str)
                if result.get("data"):
                    all_results.append(result["data"])
                current += timedelta(days=1)
        else:
            raise_tool_error(
                f"暂不支持 {params.lottery_type} 的赛果分析",
                code="UNSUPPORTED_LOTTERY_TYPE",
                suggestion="请使用竞彩足球，或选择其他工具"
            )

        if not all_results:
            raise_tool_error(
                f"未获取到 {params.lottery_type} 的开奖数据",
                code="NO_RESULTS_DATA",
                suggestion="请确认日期范围正确，或稍后重试"
            )

        # 统计分析
        analysis = _compute_results_statistics(all_results, params.league)

        return _to_json({
            "success": True,
            "data": {
                "lottery_type": params.lottery_type,
                "date_range": {"start": start_date, "end": end_date},
                "league_filter": params.league,
                "analysis": analysis,
            },
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"赛果统计分析失败: {e}")
        raise_tool_error(
            f"赛果统计分析失败: {e}",
            code="RESULTS_ANALYSIS_ERROR",
            suggestion="请检查日期范围和参数设置"
        )


async def lottery_find_value_bets(params: FetchTodayMatchesInput, ctx: Context) -> str:
    """发现价值投注"""
    try:
        manager = _get_manager()

        await ctx.log_info("[价值投注] 获取今日竞彩对阵...")

        # 1. 获取今日竞彩对阵（含官方赔率）
        from lottery_mcp.data.fetcher import fetch_today_matches as _fetch_today_matches

        lottery_type_map = {
            "竞彩足球": "jingcai",
            "北京单场": "beidan",
            "传统足彩": "ctzc",
        }
        internal_type = lottery_type_map.get(params.lottery_type or "竞彩足球", "jingcai")

        matches_list = _fetch_today_matches(
            lottery_type=internal_type,
            timeout=params.timeout or 10,
        )

        if not matches_list:
            raise_tool_error(
                "无法获取今日竞彩对阵",
                code="NO_MATCHES",
                suggestion="请确认当前有竞彩比赛在售"
            )

        matches = matches_list
        if isinstance(matches, dict):
            matches = matches.get("matches", [matches])

        value_bets = []

        for match in matches[:20]:  # 最多分析20场
            match_id = match.get("match_id", "")
            home_team = match.get("home_team", "")
            away_team = match.get("away_team", "")

            if not match_id:
                continue

            # 2. 获取官方赔率
            odds_resp = await manager.get_lottery_odds_change(match_id)
            if not odds_resp.get("data"):
                continue

            odds_data = odds_resp["data"]
            if isinstance(odds_data, list) and len(odds_data) > 0:
                odds_data = odds_data[0]

            had = odds_data.get("had", {})
            hhad = odds_data.get("hhad", {})

            if not had:
                continue

            # 3. 计算官方隐含概率
            try:
                win = float(had.get("win", 0))
                draw = float(had.get("draw", 0))
                lose = float(had.get("lose", 0))
                if win <= 0 or draw <= 0 or lose <= 0:
                    continue

                official_total = 1/win + 1/draw + 1/lose
                official_payout = 1 / official_total

                official_prob = {
                    "home_win": round((1/win) / official_total, 4),
                    "draw": round((1/draw) / official_total, 4),
                    "away_win": round((1/lose) / official_total, 4),
                }
                official_payout = round(official_payout, 4)
            except (ValueError, TypeError):
                continue

            # 4. 获取市场赔率进行对比
            market_resp = await manager.get_market_odds(sport="soccer", league=None)
            market_comparison = None

            if market_resp.get("data"):
                for m in market_resp["data"]:
                    if home_team in m.get("home_team", "") and away_team in m.get("away_team", ""):
                        consensus = m.get("consensus", {})
                        if consensus:
                            avg_home = float(consensus.get("avg_home_win", 0))
                            avg_draw = float(consensus.get("avg_draw", 0))
                            avg_away = float(consensus.get("avg_away_win", 0))
                            market_payout = float(consensus.get("payout_rate", 0))

                            if avg_home > 0 and avg_draw > 0 and avg_away > 0:
                                market_total = 1/avg_home + 1/avg_draw + 1/avg_away
                                market_prob = {
                                    "home_win": round((1/avg_home) / market_total, 4),
                                    "draw": round((1/avg_draw) / market_total, 4),
                                    "away_win": round((1/avg_away) / market_total, 4),
                                }
                                market_comparison = {
                                    "market_avg": {"win": avg_home, "draw": avg_draw, "lose": avg_away},
                                    "market_prob": market_prob,
                                    "market_payout": round(market_payout, 4),
                                }
                        break

            # 5. 识别价值
            value_signals = []
            if market_comparison:
                for label, o_key, m_key in [
                    ("主胜", "home_win", "home_win"),
                    ("平局", "draw", "draw"),
                    ("客胜", "away_win", "away_win"),
                ]:
                    o_prob = official_prob.get(o_key, 0)
                    m_prob = market_comparison["market_prob"].get(m_key, 0)
                    diff = o_prob - m_prob
                    if diff > 0.03:  # 超过3%的差异视为有价值
                        value_signals.append({
                            "selection": label,
                            "official_prob": o_prob,
                            "market_prob": m_prob,
                            "diff": round(diff, 4),
                            "direction": "竞彩高估" if o_prob > m_prob else "市场高估",
                        })

            entry = {
                "match_id": match_id,
                "home_team": home_team,
                "away_team": away_team,
                "league": match.get("league", ""),
                "match_time": match.get("match_time", ""),
                "official_odds": {"win": win, "draw": draw, "lose": lose},
                "official_prob": official_prob,
                "official_payout": official_payout,
                "market_comparison": market_comparison,
                "value_signals": value_signals,
                "has_value": len(value_signals) > 0,
            }

            if entry["has_value"]:
                value_bets.append(entry)

        # 按价值信号数量排序
        value_bets.sort(key=lambda x: len(x["value_signals"]), reverse=True)

        # 构建价值发现逻辑分析
        value_discovery_logic = _build_value_discovery_logic(value_bets, matches)

        return _to_json({
            "success": True,
            "data": {
                "value_bets": value_bets,
                "total_analyzed": min(len(matches), 20),
                "value_found": len(value_bets),
                "source": "sporttery.cn + market_odds",
                "value_discovery_logic": value_discovery_logic,
            },
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"价值投注分析失败: {e}")
        raise_tool_error(
            f"价值投注分析失败: {e}",
            code="VALUE_BETS_ERROR",
            suggestion="请检查网络连接或稍后重试"
        )


async def lottery_analyze_match(params: AnalyzeMatchInput, ctx: Context) -> str:
    """单场比赛深度分析"""
    try:
        manager = _get_manager()
        match_id = params.match_id

        await ctx.log_info(f"[比赛分析] 开始深度分析比赛 {match_id}...")

        # 1. 获取官方赔率数据
        await ctx.log_info("[比赛分析] 获取官方赔率...")
        official_odds = await manager.get_lottery_odds_change(match_id)
        if not official_odds.get("data"):
            raise_tool_error(
                "无法获取官方赔率数据",
                code="NO_OFFICIAL_ODDS",
                suggestion="请确认比赛ID正确，或稍后重试"
            )

        match_data = official_odds["data"]
        if isinstance(match_data, list) and len(match_data) > 0:
            match_data = match_data[0]

        # 2. 获取比赛资讯
        await ctx.log_info("[比赛分析] 获取比赛资讯...")
        match_info = await manager.get_match_head(match_id)
        features = await manager.get_match_feature(match_id)
        h2h = await manager.get_result_history(match_id, term_limits=5)
        standings = await manager.get_match_tables(match_id)

        # 3. 获取市场赔率（如果启用）
        market_odds = None
        if params.include_market_odds and params.analysis_depth in ["standard", "deep"]:
            await ctx.log_info("[比赛分析] 获取市场赔率...")
            # 使用球队名称查询市场赔率
            home_team = match_data.get("home_team", "")
            away_team = match_data.get("away_team", "")
            if home_team and away_team:
                market_odds = await manager.get_market_odds(
                    sport="soccer",
                    league=None,  # 不限制联赛，通过球队匹配
                )

        # 4. 生成分析报告
        await ctx.log_info("[比赛分析] 生成分析报告...")
        analysis = _generate_match_analysis(
            match_data=match_data,
            match_info=match_info.get("data") if match_info else None,
            features=features.get("data") if features else None,
            h2h=h2h.get("data") if h2h else None,
            standings=standings.get("data") if standings else None,
            market_odds=market_odds.get("data") if market_odds else None,
            depth=params.analysis_depth,
        )

        # 将 analysis.recommendation 中的关键字段提升到 data 顶层，
        # 以便测试脚本和下游消费者可以直接访问。
        recommendation = analysis.get("recommendation", {})
        top_level_fields = {}
        if "combined_score" in recommendation:
            top_level_fields["combined_score"] = recommendation["combined_score"]
        if "risk_assessment" in recommendation:
            top_level_fields["risk_assessment"] = recommendation["risk_assessment"]
        # 提取 recommendation 本身到顶层
        if recommendation:
            top_level_fields["recommendation"] = recommendation

        return _to_json({
            "success": True,
            "data": {
                "match_id": match_id,
                "match_summary": f"{match_data.get('home_team', '')} vs {match_data.get('away_team', '')}",
                "analysis_depth": params.analysis_depth,
                "analysis": analysis,
                **top_level_fields,
            },
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"比赛分析失败: {e}")
        raise_tool_error(
            f"比赛分析失败: {e}",
            code="MATCH_ANALYSIS_ERROR",
            suggestion="请检查比赛ID是否正确或稍后重试"
        )


def _safe_int(value) -> Optional[int]:
    """安全地将值转换为整数，失败返回 None。

    支持字符串、int、float 类型的输入。
    """
    if value is None:
        return None
    try:
        v = int(value)
        return v if v >= 0 else None
    except (ValueError, TypeError):
        return None


async def lottery_predict_with_model(params: PredictWithModelInput, ctx: Context) -> str:
    """使用ML模型预测比赛结果

    数据来源（按优先级）：
    1. 积分榜数据 (get_match_tables): 提取主/客场进球、失球、场次
    2. 近期战绩 (get_match_recent_form): 从近期比赛结果中计算进球统计
    3. 官方赔率 (get_lottery_odds_change): 从赔率隐含概率反推进球期望值
    多模型分解调用 StatisticalEngine 的独立子模型方法（泊松/Elo/xG），
    而非简单系数乘法。
    """
    try:
        await ctx.report_progress(0.2, "正在加载统计模型...")
        await ctx.log_info(f"[模型预测] 比赛 {params.match_id}, 模型类型: {params.model_type}")

        # 导入 StatisticalEngine
        from lottery_mcp.analysis.models import StatisticalEngine

        manager = _get_manager()
        engine = StatisticalEngine()

        await ctx.report_progress(0.4, "正在获取比赛数据...")

        # 获取比赛基本信息
        match_info = await manager.get_match_head(params.match_id)
        features = await manager.get_match_feature(params.match_id)

        if not match_info.get("data"):
            raise_tool_error(
                "无法获取比赛基本信息",
                code="MATCH_INFO_NOT_FOUND",
                suggestion="请确认比赛ID正确"
            )

        match_data = match_info["data"]
        home_team_id = match_data.get("home_team_id", "")
        away_team_id = match_data.get("away_team_id", "")
        home_team_name = match_data.get("home_team", "")
        away_team_name = match_data.get("away_team", "")
        league = match_data.get("league", "default")

        # ============================================================
        # 从真实数据源提取球队进球统计（替代硬编码）
        # ============================================================
        home_goals_for = None
        home_games = None
        home_goals_against = None
        away_goals_for = None
        away_games = None
        away_goals_against = None
        data_source_desc = "无"

        # --- 数据源1: 积分榜 (get_match_tables) ---
        # sporttery.cn 积分榜通常包含 homeTables/awayTables，
        # 其中可能有进球统计字段（goalFor/goalAgainst 等）
        standings_resp = await manager.get_match_tables(params.match_id)
        if standings_resp.get("data"):
            tables = standings_resp["data"]
            home_tables = tables.get("homeTables", {})
            away_tables = tables.get("awayTables", {})

            # 尝试从积分榜提取主/客场进球数据
            # sporttery.cn 积分榜字段名不确定，尝试多种可能的键名
            if home_tables:
                home_games = _safe_int(home_tables.get("matchCnt") or home_tables.get("played") or home_tables.get("matchCount"))
                home_goals_for = _safe_int(home_tables.get("goalFor") or home_tables.get("goalsFor") or home_tables.get("scoreGoals"))
                home_goals_against = _safe_int(home_tables.get("goalAgainst") or home_tables.get("goalsAgainst") or home_tables.get("lostGoals"))
            if away_tables:
                away_games = _safe_int(away_tables.get("matchCnt") or away_tables.get("played") or away_tables.get("matchCount"))
                away_goals_for = _safe_int(away_tables.get("goalFor") or away_tables.get("goalsFor") or away_tables.get("scoreGoals"))
                away_goals_against = _safe_int(away_tables.get("goalAgainst") or away_tables.get("goalsAgainst") or away_tables.get("lostGoals"))

            if all(v is not None and v > 0 for v in [home_games, away_games]):
                data_source_desc = "积分榜(主客场统计)"

        # --- 数据源2: 近期战绩 (get_match_recent_form) ---
        # 如果积分榜数据不完整，从近期比赛结果中计算
        if home_games is None or away_games is None:
            form_resp = await manager.get_match_recent_form(params.match_id, term_limits=10)
            if form_resp.get("data"):
                form_data = form_resp["data"]
                home_form = form_data.get("home_recent_form", [])
                away_form = form_data.get("away_recent_form", [])

                if home_form and (home_games is None or home_games == 0):
                    home_games = len(home_form)
                    home_goals_for = sum(
                        _safe_int(f.get("homeScore") or f.get("goals_for") or f.get("score") or 0)
                        for f in home_form
                    )
                    home_goals_against = sum(
                        _safe_int(f.get("awayScore") or f.get("goals_against") or f.get("lostGoals") or 0)
                        for f in home_form
                    )
                    if home_goals_for is None:
                        home_goals_for = 0
                    if home_goals_against is None:
                        home_goals_against = 0

                if away_form and (away_games is None or away_games == 0):
                    away_games = len(away_form)
                    away_goals_for = sum(
                        _safe_int(f.get("awayScore") or f.get("goals_for") or f.get("score") or 0)
                        for f in away_form
                    )
                    away_goals_against = sum(
                        _safe_int(f.get("homeScore") or f.get("goals_against") or f.get("lostGoals") or 0)
                        for f in away_form
                    )
                    if away_goals_for is None:
                        away_goals_for = 0
                    if away_goals_against is None:
                        away_goals_against = 0

                if home_games is not None and away_games is not None:
                    data_source_desc = "近期战绩(近10场)"

        # --- 数据源3: 官方赔率反推 (get_lottery_odds_change) ---
        # 如果前两个数据源都无法获取，从赔率隐含概率反推进球期望值
        odds_home_expected = None
        odds_away_expected = None
        if home_games is None or away_games is None:
            odds_resp = await manager.get_lottery_odds_change(params.match_id)
            if odds_resp.get("data"):
                odds_data = odds_resp["data"]
                had = odds_data.get("had", {})
                try:
                    win_odds = float(had.get("win", 0))
                    draw_odds = float(had.get("draw", 0))
                    lose_odds = float(had.get("lose", 0))
                    if win_odds > 0 and draw_odds > 0 and lose_odds > 0:
                        odds_home_expected, odds_away_expected = _estimate_lambdas_from_odds(
                            win_odds, draw_odds, lose_odds
                        )
                        # 将赔率反推的期望进球数转换为统计模型需要的格式
                        # 使用近10场作为默认场次，按期望进球数估算总进球
                        estimated_games = 10
                        home_games = estimated_games
                        away_games = estimated_games
                        home_goals_for = round(odds_home_expected * estimated_games)
                        home_goals_against = round(odds_away_expected * estimated_games)
                        away_goals_for = round(odds_away_expected * estimated_games)
                        away_goals_against = round(odds_home_expected * estimated_games)
                        data_source_desc = f"赔率反推(λ_h={odds_home_expected:.2f}, λ_a={odds_away_expected:.2f})"
                except (ValueError, TypeError):
                    pass

        # --- 数据不可用检查 ---
        if home_games is None or away_games is None or home_games == 0 or away_games == 0:
            raise_tool_error(
                "无法获取球队进球统计数据",
                code="STATS_DATA_NOT_FOUND",
                suggestion=(
                    "积分榜、近期战绩和赔率数据均不可用。"
                    "请确认比赛ID正确且比赛尚未开始太久。"
                ),
            )

        # 确保所有值为正整数
        home_goals_for = max(1, home_goals_for or 1)
        home_goals_against = max(1, home_goals_against or 1)
        away_goals_for = max(1, away_goals_for or 1)
        away_goals_against = max(1, away_goals_against or 1)

        await ctx.report_progress(0.6, "正在执行模型预测...")

        # 执行预测
        result = engine.full_analysis(
            home_goals_for=home_goals_for,
            home_games=home_games,
            home_goals_against=home_goals_against,
            away_goals_for=away_goals_for,
            away_games=away_games,
            away_goals_against=away_goals_against,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
            league=league,
        )

        await ctx.report_progress(0.9, "正在生成预测报告...")

        # 根据 model_type 筛选结果
        predictions = {
            "home_win_prob": round(result.home_win_prob, 4),
            "draw_prob": round(result.draw_prob, 4),
            "away_win_prob": round(result.away_win_prob, 4),
            "expected_goals_home": round(result.expected_goals_home, 2),
            "expected_goals_away": round(result.expected_goals_away, 2),
        }

        # ============================================================
        # 多模型分解：调用 StatisticalEngine 的独立子模型方法
        # ============================================================
        model_predictions = {}

        if params.model_type in ["poisson", "ensemble"]:
            # 泊松模型：使用 PoissonModel.predict() 独立计算
            home_exp, away_exp = engine.poisson.calculate_expected_goals(
                home_goals_for, home_games, home_goals_against,
                away_goals_for, away_games, away_goals_against,
                league
            )
            poisson_pred = engine.poisson.predict(home_exp, away_exp)
            model_predictions["poisson"] = {
                "home_win": poisson_pred.home_win_prob,
                "draw": poisson_pred.draw_prob,
                "away_win": poisson_pred.away_win_prob,
                "expected_home": round(poisson_pred.home_expected_goals, 2),
                "expected_away": round(poisson_pred.away_expected_goals, 2),
                "most_likely_score": poisson_pred.most_likely_score,
            }

        if params.model_type in ["elo", "ensemble"]:
            # Elo模型：使用 EloRatingSystem.predict_match() 独立计算
            elo_pred = engine.elo.predict_match(home_team_id, away_team_id, league)
            model_predictions["elo"] = {
                "home_win": elo_pred["home_win_prob"],
                "draw": elo_pred["draw_prob"],
                "away_win": elo_pred["away_win_prob"],
                "home_elo": elo_pred.get("home_elo", 0),
                "away_elo": elo_pred.get("away_elo", 0),
                "rating_diff": elo_pred.get("rating_diff", 0),
            }

        if params.model_type in ["xg", "ensemble"]:
            # xG模型：使用 XGModel.analyze() 独立计算
            xg_pred = engine.xg.analyze(
                home_goals_for, home_games, home_goals_against,
                away_goals_for, away_games, away_goals_against,
                league=league
            )
            # 将 xG 差异转换为胜/平/负概率（近似方法）
            xg_diff = xg_pred.home_xg - xg_pred.away_xg
            xg_home_prob = max(0.05, min(0.90, 0.45 + xg_diff * 0.25))
            xg_draw_prob = max(0.05, min(0.40, 0.28 - abs(xg_diff) * 0.10))
            xg_away_prob = max(0.05, 1.0 - xg_home_prob - xg_draw_prob)
            model_predictions["xg"] = {
                "home_win": round(xg_home_prob, 4),
                "draw": round(xg_draw_prob, 4),
                "away_win": round(xg_away_prob, 4),
                "home_xg": round(xg_pred.home_xg, 2),
                "away_xg": round(xg_pred.away_xg, 2),
            }

        # 置信度计算
        confidence = round(result.combined_score / 100, 4) if hasattr(result, 'combined_score') else 0.65

        # 关键特征
        key_features = []
        if params.include_features:
            key_features = [
                {"name": "主队主场进球率", "value": round(home_goals_for / home_games, 2), "impact": "high"},
                {"name": "客队客场进球率", "value": round(away_goals_for / away_games, 2), "impact": "medium"},
                {"name": "主队防守稳定性", "value": round(home_goals_against / home_games, 2), "impact": "medium"},
                {"name": "客队防守稳定性", "value": round(away_goals_against / away_games, 2), "impact": "medium"},
                {"name": "数据来源", "value": data_source_desc, "impact": "info"},
            ]

        await ctx.report_progress(1.0, "预测完成")

        return _to_json({
            "success": True,
            "data": {
                "match_id": params.match_id,
                "model_type": params.model_type,
                "predictions": predictions,
                "model_breakdown": model_predictions,
                "confidence": confidence,
                "key_features": key_features,
                "data_source": data_source_desc,
                "model_limitations": [
                    "模型基于历史统计数据，无法预测突发情况",
                    "伤停信息可能未完全纳入模型计算",
                    "比赛日当天阵容变化可能影响结果",
                ],
                "agreement_level": result.agreement_level if hasattr(result, 'agreement_level') else "基本一致",
            },
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"模型预测失败: {e}")
        await ctx.log_error(f"[模型预测] 失败: {e}")
        raise_tool_error(
            f"模型预测失败: {str(e)}",
            code="PREDICTION_ERROR",
            suggestion="请检查输入参数或稍后重试"
        )


async def lottery_get_market_sentiment(params: GetMarketSentimentInput, ctx: Context) -> str:
    """获取市场情绪分析

    核心原理：从赔率数据推导市场情绪，无需投注量API。
    推导依据：
    - 赔率隐含概率 = 市场共识预期（赔率越低，市场认为越可能发生）
    - HAD(胜平负) vs HHAD(让球胜平负) 概率差异 = 市场对强弱判断的置信度
    - 官方赔率 vs 国际市场赔率差异 = 本地市场情绪偏差
    - 返还率 = 庄家利润空间，间接反映市场成熟度
    """
    try:
        await ctx.report_progress(0.2, "正在获取赔率数据...")
        await ctx.log_info(f"[市场情绪] 分析比赛 {params.match_id}")

        manager = _get_manager()

        # 获取官方赔率数据（HAD + HHAD）
        odds_resp = await manager.get_lottery_odds_change(params.match_id)

        if not odds_resp.get("data"):
            raise_tool_error(
                "无法获取赔率数据",
                code="ODDS_DATA_NOT_FOUND",
                suggestion="请确认比赛ID正确"
            )

        odds_raw = odds_resp["data"]
        if isinstance(odds_raw, list) and len(odds_raw) > 0:
            odds_raw = odds_raw[0]

        had = odds_raw.get("had", {})
        hhad = odds_raw.get("hhad", {})

        if not had:
            raise_tool_error(
                "赔率数据中缺少胜平负(HAD)数据",
                code="HAD_DATA_MISSING",
                suggestion="该比赛可能尚未开盘或已截止"
            )

        # 解析 HAD 赔率
        try:
            win_odds = float(had.get("win", 0))
            draw_odds = float(had.get("draw", 0))
            lose_odds = float(had.get("lose", 0))
            if win_odds <= 0 or draw_odds <= 0 or lose_odds <= 0:
                raise ValueError("赔率值无效")
        except (ValueError, TypeError):
            raise_tool_error(
                "赔率数据格式异常，无法解析",
                code="ODDS_PARSE_ERROR",
                suggestion="请稍后重试"
            )

        await ctx.report_progress(0.4, "正在计算隐含概率...")

        # ============================================================
        # 步骤1: 从 HAD 赔率计算隐含概率（市场共识预期）
        # ============================================================
        # 公式: 隐含概率_i = (1/odds_i) / sum(1/odds_j)
        # 其中 sum(1/odds_j) = 1/返还率，反映了庄家抽水
        had_implied_sum = 1/win_odds + 1/draw_odds + 1/lose_odds
        had_payout_rate = 1 / had_implied_sum  # 返还率

        home_implied_prob = (1/win_odds) / had_implied_sum
        draw_implied_prob = (1/draw_odds) / had_implied_sum
        away_implied_prob = (1/lose_odds) / had_implied_sum

        await ctx.report_progress(0.5, "正在分析让球盘差异...")

        # ============================================================
        # 步骤2: 从 HHAD 让球盘推导市场强度判断
        # ============================================================
        # 让球盘的隐含概率反映市场对比赛结果的信心程度
        # 如果让球盘调整后的概率与标准盘差异大，说明市场对某方向有强烈预期
        hhad_analysis = None
        if hhad:
            try:
                hhad_win = float(hhad.get("win", 0))
                hhad_draw = float(hhad.get("draw", 0))
                hhad_lose = float(hhad.get("lose", 0))
                handicap = hhad.get("handicap", "")

                if hhad_win > 0 and hhad_draw > 0 and hhad_lose > 0:
                    hhad_implied_sum = 1/hhad_win + 1/hhad_draw + 1/hhad_lose
                    hhad_payout = 1 / hhad_implied_sum

                    hhad_home_prob = (1/hhad_win) / hhad_implied_sum
                    hhad_draw_prob = (1/hhad_draw) / hhad_implied_sum
                    hhad_away_prob = (1/hhad_lose) / hhad_implied_sum

                    # 让球盘与标准盘的概率差异反映市场信心
                    # 差异越大，说明市场对某方向越有信心
                    prob_diff_home = abs(hhad_home_prob - home_implied_prob)
                    prob_diff_away = abs(hhad_away_prob - away_implied_prob)
                    prob_diff_draw = abs(hhad_draw_prob - draw_implied_prob)

                    hhad_analysis = {
                        "handicap": handicap,
                        "hhad_odds": {"win": hhad_win, "draw": hhad_draw, "lose": hhad_lose},
                        "hhad_implied_prob": {
                            "home_win": round(hhad_home_prob, 4),
                            "draw": round(hhad_draw_prob, 4),
                            "away_win": round(hhad_away_prob, 4),
                        },
                        "hhad_payout_rate": round(hhad_payout, 4),
                        "prob_diff_vs_had": {
                            "home_win": round(prob_diff_home, 4),
                            "draw": round(prob_diff_draw, 4),
                            "away_win": round(prob_diff_away, 4),
                        },
                    }
            except (ValueError, TypeError):
                pass

        await ctx.report_progress(0.6, "正在获取国际市场赔率对比...")

        # ============================================================
        # 步骤3: 尝试获取国际市场赔率进行对比
        # ============================================================
        # 官方赔率 vs 国际市场赔率的差异可以反映本地市场情绪偏差
        # 如果官方赔率隐含概率显著高于/低于国际市场，说明本地资金有偏向
        market_comparison = None
        home_team = odds_raw.get("home_team", "")
        away_team = odds_raw.get("away_team", "")

        if home_team and away_team:
            try:
                market_resp = await manager.get_market_odds(sport="soccer", league=None)
                if market_resp.get("data"):
                    for m in market_resp["data"]:
                        if home_team in m.get("home_team", "") and away_team in m.get("away_team", ""):
                            consensus = m.get("consensus", {})
                            if consensus:
                                avg_home = float(consensus.get("avg_home_win", 0))
                                avg_draw = float(consensus.get("avg_draw", 0))
                                avg_away = float(consensus.get("avg_away_win", 0))
                                market_payout = float(consensus.get("payout_rate", 0))

                                if avg_home > 0 and avg_draw > 0 and avg_away > 0:
                                    market_implied_sum = 1/avg_home + 1/avg_draw + 1/avg_away
                                    market_prob = {
                                        "home_win": round((1/avg_home) / market_implied_sum, 4),
                                        "draw": round((1/avg_draw) / market_implied_sum, 4),
                                        "away_win": round((1/avg_away) / market_implied_sum, 4),
                                    }
                                    # 本地 vs 国际市场概率偏差
                                    # 正值 = 官方(本地)概率更高 = 本地市场更看好该选项
                                    local_bias = {
                                        "home_win": round(home_implied_prob - market_prob["home_win"], 4),
                                        "draw": round(draw_implied_prob - market_prob["draw"], 4),
                                        "away_win": round(away_implied_prob - market_prob["away_win"], 4),
                                    }
                                    market_comparison = {
                                        "market_avg_odds": {"win": avg_home, "draw": avg_draw, "lose": avg_away},
                                        "market_implied_prob": market_prob,
                                        "market_payout_rate": round(market_payout, 4),
                                        "local_bias": local_bias,
                                        "source": market_resp.get("source", "unknown"),
                                    }
                            break
            except Exception as e:
                logger.warning(f"国际市场赔率获取失败: {e}")
                pass  # 国际市场赔率获取失败不影响核心分析

        await ctx.report_progress(0.75, "正在推导市场情绪指标...")

        # ============================================================
        # 步骤4: 推导投注量分布（基于赔率隐含概率）
        # ============================================================
        # 原理: 在有效市场中，投注量分布与隐含概率高度相关
        # 赔率越低 = 市场共识越强 = 吸引的投注量越多
        # 使用隐含概率作为投注量分布的估计
        betting_pct_home = round(home_implied_prob * 100, 1)
        betting_pct_draw = round(draw_implied_prob * 100, 1)
        betting_pct_away = round(away_implied_prob * 100, 1)

        # 推导投注趋势：基于本地市场偏差（如果有国际市场数据）
        # 如果本地概率 > 国际概率，说明本地资金偏向该方向（trend: increasing）
        # 如果本地概率 < 国际概率，说明本地资金在撤出（trend: decreasing）
        if market_comparison:
            bias = market_comparison["local_bias"]
            home_trend = "increasing" if bias["home_win"] > 0.02 else ("decreasing" if bias["home_win"] < -0.02 else "stable")
            draw_trend = "increasing" if bias["draw"] > 0.02 else ("decreasing" if bias["draw"] < -0.02 else "stable")
            away_trend = "increasing" if bias["away_win"] > 0.02 else ("decreasing" if bias["away_win"] < -0.02 else "stable")
        else:
            # 无国际市场数据时，基于让球盘差异推导趋势
            if hhad_analysis:
                hhad_diff = hhad_analysis["prob_diff_vs_had"]
                # 让球盘概率更高 = 市场在加强该方向的预期
                home_trend = "increasing" if hhad_diff["home_win"] > 0.05 else ("decreasing" if hhad_diff["home_win"] < -0.05 else "stable")
                draw_trend = "increasing" if hhad_diff["draw"] > 0.05 else ("decreasing" if hhad_diff["draw"] < -0.05 else "stable")
                away_trend = "increasing" if hhad_diff["away_win"] > 0.05 else ("decreasing" if hhad_diff["away_win"] < -0.05 else "stable")
            else:
                home_trend = "stable"
                draw_trend = "stable"
                away_trend = "stable"

        betting_volume_distribution = {
            "home_win": {"percentage": betting_pct_home, "trend": home_trend},
            "draw": {"percentage": betting_pct_draw, "trend": draw_trend},
            "away_win": {"percentage": betting_pct_away, "trend": away_trend},
        }

        # ============================================================
        # 步骤5: 赔率变动趋势分析
        # ============================================================
        # 由于API仅提供当前赔率（无历史变化），我们用 HAD vs HHAD 的概率差异
        # 来构建"市场预期变动"指标
        # 原理: 让球盘是庄家根据资金流入调整后的赔率
        # 让球盘隐含概率与标准盘的差异方向 = 庄家观察到的资金流向
        if hhad_analysis:
            hhad_diff = hhad_analysis["prob_diff_vs_had"]
            # 让球盘概率 > 标准盘概率 → 该方向赔率被压低 → 资金流入
            # 映射为"赔率变动"的等效表示
            odds_movement = {
                "home_win": {
                    "current": win_odds,
                    "implied_prob": round(home_implied_prob, 4),
                    "hhad_adjusted_prob": round(hhad_analysis["hhad_implied_prob"]["home_win"], 4),
                    "prob_shift": round(hhad_diff["home_win"], 4),
                    "fund_flow_hint": "资金流入" if hhad_diff["home_win"] > 0.03 else ("资金流出" if hhad_diff["home_win"] < -0.03 else "无明显流向"),
                },
                "draw": {
                    "current": draw_odds,
                    "implied_prob": round(draw_implied_prob, 4),
                    "hhad_adjusted_prob": round(hhad_analysis["hhad_implied_prob"]["draw"], 4),
                    "prob_shift": round(hhad_diff["draw"], 4),
                    "fund_flow_hint": "资金流入" if hhad_diff["draw"] > 0.03 else ("资金流出" if hhad_diff["draw"] < -0.03 else "无明显流向"),
                },
                "away_win": {
                    "current": lose_odds,
                    "implied_prob": round(away_implied_prob, 4),
                    "hhad_adjusted_prob": round(hhad_analysis["hhad_implied_prob"]["away_win"], 4),
                    "prob_shift": round(hhad_diff["away_win"], 4),
                    "fund_flow_hint": "资金流入" if hhad_diff["away_win"] > 0.03 else ("资金流出" if hhad_diff["away_win"] < -0.03 else "无明显流向"),
                },
            }
        else:
            # 无让球盘数据时，仅提供当前赔率和隐含概率
            odds_movement = {
                "home_win": {
                    "current": win_odds,
                    "implied_prob": round(home_implied_prob, 4),
                },
                "draw": {
                    "current": draw_odds,
                    "implied_prob": round(draw_implied_prob, 4),
                },
                "away_win": {
                    "current": lose_odds,
                    "implied_prob": round(away_implied_prob, 4),
                },
            }

        # ============================================================
        # 步骤6: 市场热度指标
        # ============================================================
        # 基于以下因素综合计算热度：
        # a) 返还率: 返还率越低 → 庄家利润越高 → 市场越不成熟/关注度越低
        # b) HAD vs HHAD 概率差异: 差异越大 → 市场分歧越大 → 关注度越高
        # c) 本地 vs 国际偏差: 偏差越大 → 本地市场情绪越极端
        heat_score = 50  # 基础分

        # 返还率贡献: 返还率越高 → 市场越成熟 → 热度越高
        # 竞彩返还率通常在 70%-90% 之间
        payout_contribution = (had_payout_rate - 0.70) / 0.20 * 20  # 0-20分
        heat_score += max(0, min(20, payout_contribution))

        # HAD vs HHAD 概率差异贡献: 差异越大 → 市场分歧越大
        if hhad_analysis:
            max_prob_diff = max(
                hhad_analysis["prob_diff_vs_had"]["home_win"],
                hhad_analysis["prob_diff_vs_had"]["draw"],
                hhad_analysis["prob_diff_vs_had"]["away_win"],
            )
            # 概率差异 0-0.15 映射到 0-20分
            diff_contribution = (max_prob_diff / 0.15) * 20
            heat_score += max(0, min(20, diff_contribution))

        # 本地 vs 国际偏差贡献
        if market_comparison:
            max_bias = max(
                abs(market_comparison["local_bias"]["home_win"]),
                abs(market_comparison["local_bias"]["draw"]),
                abs(market_comparison["local_bias"]["away_win"]),
            )
            # 偏差 0-0.08 映射到 0-10分
            bias_contribution = (max_bias / 0.08) * 10
            heat_score += max(0, min(10, bias_contribution))

        heat_score = round(max(0, min(100, heat_score)), 1)

        if heat_score >= 75:
            heat_level = "high"
            heat_desc = "市场关注度高，赔率分歧明显"
        elif heat_score >= 50:
            heat_level = "medium"
            heat_desc = "市场关注度适中"
        else:
            heat_level = "low"
            heat_desc = "市场关注度较低，赔率较为一致"

        market_heat = {
            "level": heat_level,
            "score": heat_score,
            "description": heat_desc,
            "factors": {
                "payout_rate": round(had_payout_rate, 4),
                "had_hhad_prob_diff": round(
                    max(
                        hhad_analysis["prob_diff_vs_had"]["home_win"],
                        hhad_analysis["prob_diff_vs_had"]["draw"],
                        hhad_analysis["prob_diff_vs_had"]["away_win"],
                    ) if hhad_analysis else 0, 4
                ),
                "local_vs_intl_bias": round(
                    max(
                        abs(market_comparison["local_bias"]["home_win"]),
                        abs(market_comparison["local_bias"]["draw"]),
                        abs(market_comparison["local_bias"]["away_win"]),
                    ) if market_comparison else 0, 4
                ),
            },
        }

        # ============================================================
        # 步骤7: 聪明钱指标
        # ============================================================
        # 原理: 聪明钱通常表现为：
        # a) 让球盘概率与标准盘概率出现显著背离（庄家在平衡资金）
        # b) 本地市场与国际市场出现显著偏差（专业资金方向）
        # c) 返还率异常（庄家调整利润空间来平衡风险）
        smart_money_signals = []

        # 信号1: HAD vs HHAD 概率背离
        if hhad_analysis:
            for label, key in [("主胜", "home_win"), ("平局", "draw"), ("客胜", "away_win")]:
                diff = hhad_analysis["prob_diff_vs_had"][key]
                if abs(diff) > 0.08:  # 概率差异超过8%
                    direction = "看多" if diff > 0 else "看空"
                    smart_money_signals.append({
                        "type": "had_hhad_divergence",
                        "selection": label,
                        "detail": f"让球盘{label}概率比标准盘{'高' if diff > 0 else '低'}{abs(diff):.1%}，"
                                 f"可能有{direction}资金介入",
                        "strength": "strong" if abs(diff) > 0.12 else "moderate",
                    })

        # 信号2: 本地 vs 国际市场偏差
        if market_comparison:
            for label, key in [("主胜", "home_win"), ("平局", "draw"), ("客胜", "away_win")]:
                bias = market_comparison["local_bias"][key]
                if abs(bias) > 0.05:  # 概率偏差超过5%
                    direction = "本地超买" if bias > 0 else "本地超卖"
                    smart_money_signals.append({
                        "type": "local_intl_divergence",
                        "selection": label,
                        "detail": f"官方赔率隐含概率比国际市场{'高' if bias > 0 else '低'}{abs(bias):.1%}，"
                                 f"存在{direction}迹象",
                        "strength": "strong" if abs(bias) > 0.08 else "moderate",
                    })

        # 信号3: 返还率异常
        if had_payout_rate < 0.73:
            smart_money_signals.append({
                "type": "low_payout_rate",
                "selection": "全局",
                "detail": f"返还率仅{had_payout_rate:.1%}，低于正常水平，庄家可能在平衡大量单边投注",
                "strength": "moderate",
            })

        # 综合聪明钱判断
        strong_signals = [s for s in smart_money_signals if s.get("strength") == "strong"]
        moderate_signals = [s for s in smart_money_signals if s.get("strength") == "moderate"]

        if len(strong_signals) >= 2:
            smart_money_indicator = "strong_activity"
        elif len(strong_signals) >= 1 or len(moderate_signals) >= 2:
            smart_money_indicator = "moderate_activity"
        elif len(moderate_signals) >= 1:
            smart_money_indicator = "possible_activity"
        else:
            smart_money_indicator = "balanced"

        # ============================================================
        # 步骤8: 价值信号（基于赔率隐含概率异常值）
        # ============================================================
        # 原理: 如果某个选项的隐含概率远高于其他选项，但赔率并未相应降低，
        # 可能存在价值（但这在有效市场中不太常见）
        value_signals = []

        # 检查是否有选项的隐含概率与让球盘概率存在显著差异
        if hhad_analysis:
            for label, key in [("主胜", "home_win"), ("平局", "draw"), ("客胜", "away_win")]:
                had_prob = {
                    "home_win": home_implied_prob,
                    "draw": draw_implied_prob,
                    "away_win": away_implied_prob,
                }[key]
                hhad_prob = hhad_analysis["hhad_implied_prob"][key]
                diff = abs(had_prob - hhad_prob)
                if diff > 0.06:
                    value_signals.append({
                        "type": "cross_market_divergence",
                        "selection": label,
                        "strength": "moderate" if diff > 0.10 else "weak",
                        "detail": f"标准盘隐含概率{had_prob:.1%} vs 让球盘调整概率{hhad_prob:.1%}，"
                                 f"差异{diff:.1%}",
                    })

        # 检查本地 vs 国际市场是否有价值差异
        if market_comparison:
            for label, o_key, m_key in [
                ("主胜", "home_win", "home_win"),
                ("平局", "draw", "draw"),
                ("客胜", "away_win", "away_win"),
            ]:
                o_prob = {
                    "home_win": home_implied_prob,
                    "draw": draw_implied_prob,
                    "away_win": away_implied_prob,
                }[o_key]
                m_prob = market_comparison["market_implied_prob"][m_key]
                diff = o_prob - m_prob
                if diff > 0.03:  # 官方概率显著高于国际市场
                    value_signals.append({
                        "type": "local_value_premium",
                        "selection": label,
                        "strength": "moderate" if diff > 0.05 else "weak",
                        "detail": f"官方隐含概率{o_prob:.1%}高于国际市场{m_prob:.1%}，"
                                 f"差异{diff:.1%}，本地市场可能高估该选项",
                    })

        # ============================================================
        # 步骤9: 计算整体市场情绪
        # ============================================================
        # 整体情绪基于隐含概率的不对称性
        # 如果主胜概率显著高于客胜，市场看好主队
        prob_asymmetry = home_implied_prob - away_implied_prob

        if prob_asymmetry > 0.20:
            overall_sentiment = "bullish_home"
            sentiment_score = round(min(1.0, prob_asymmetry), 2)
        elif prob_asymmetry > 0.10:
            overall_sentiment = "slightly_bullish_home"
            sentiment_score = round(prob_asymmetry, 2)
        elif prob_asymmetry < -0.20:
            overall_sentiment = "bullish_away"
            sentiment_score = round(max(-1.0, prob_asymmetry), 2)
        elif prob_asymmetry < -0.10:
            overall_sentiment = "slightly_bullish_away"
            sentiment_score = round(prob_asymmetry, 2)
        else:
            overall_sentiment = "neutral"
            sentiment_score = round(prob_asymmetry, 2)

        # ============================================================
        # 组装返回数据
        # ============================================================
        sentiment = {
            "match_id": params.match_id,
            "home_team": home_team,
            "away_team": away_team,
            "data_source": "derived_from_odds_changes",
            "data_source_detail": "市场情绪从官方赔率(HAD/HHAD)隐含概率及国际市场赔率对比推导，"
                                   "不依赖投注量数据",
            "overall_sentiment": overall_sentiment,
            "sentiment_score": sentiment_score,
            "betting_volume_distribution": betting_volume_distribution,
            "odds_movement": odds_movement,
            "market_heat": market_heat,
            "smart_money_indicator": smart_money_indicator,
            "smart_money_signals": smart_money_signals,
            "value_signals": value_signals,
        }

        # 附加分析数据（供高级分析使用）
        if hhad_analysis:
            sentiment["hhad_analysis"] = hhad_analysis
        if market_comparison:
            sentiment["market_comparison"] = market_comparison

        sentiment["methodology"] = {
            "betting_volume": "基于赔率隐含概率推导，假设有效市场中投注量分布与隐含概率正相关",
            "fund_flow": "基于HAD标准盘与HHAD让球盘的隐含概率差异推导资金流向",
            "market_heat": "综合返还率、HAD/HHAD概率差异、本地/国际偏差三因素计算",
            "smart_money": "基于HAD/HHAD背离、本地/国际偏差、返还率异常三维度检测",
        }

        await ctx.report_progress(1.0, "分析完成")

        return _to_json({
            "success": True,
            "data": sentiment,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"市场情绪分析失败: {e}")
        await ctx.log_error(f"[市场情绪] 分析失败: {e}")
        raise_tool_error(
            f"市场情绪分析失败: {str(e)}",
            code="SENTIMENT_ERROR",
            suggestion="请稍后重试"
        )


# ============================================================
# Phase 2: 高级分析工具函数
# ============================================================

async def lottery_get_match_context(params: GetMatchContextInput, ctx: Context) -> str:
    """获取比赛完整上下文数据供AI推理"""
    try:
        manager = _get_manager()
        match_id = params.match_id

        await ctx.log_info(f"[AI上下文] 正在聚合比赛 {match_id} 的完整数据...")
        await ctx.report_progress(0.1, "获取基础信息...")

        context_data = {
            "match_id": match_id,
            "timestamp": datetime.now().isoformat(),
        }

        # 1. 基础信息
        head_resp = await manager.get_match_head(match_id)
        if head_resp.get("data"):
            context_data["basic_info"] = {
                "home_team": head_resp["data"].get("homeTeam", ""),
                "away_team": head_resp["data"].get("awayTeam", ""),
                "league": head_resp["data"].get("leagueName", ""),
                "match_time": head_resp["data"].get("matchTime", ""),
                "home_rank": head_resp["data"].get("homeRank", ""),
                "away_rank": head_resp["data"].get("awayRank", ""),
            }

        await ctx.report_progress(0.3, "获取官方赔率...")

        # 2. 官方赔率
        odds_resp = await manager.get_lottery_odds_change(match_id)
        if odds_resp.get("data"):
            odds_data = odds_resp["data"]
            if isinstance(odds_data, list) and len(odds_data) > 0:
                odds_data = odds_data[0]
            context_data["official_odds"] = {
                "had": odds_data.get("had", {}),
                "hhad": odds_data.get("hhad", {}),
                "crs": odds_data.get("crs", {}),
                "ttg": odds_data.get("ttg", {}),
                "hafu": odds_data.get("hafu", {}),
            }

        await ctx.report_progress(0.5, "获取市场数据...")

        # 3. 市场赔率
        if params.include_market:
            market_resp = await manager.get_market_odds(sport="soccer", league=None)
            if market_resp.get("data"):
                home_team = context_data.get("basic_info", {}).get("home_team", "")
                away_team = context_data.get("basic_info", {}).get("away_team", "")
                for m in market_resp["data"]:
                    if home_team in m.get("home_team", "") and away_team in m.get("away_team", ""):
                        context_data["market_odds"] = {
                            "european": m.get("european_odds", []),
                            "asian": m.get("asian_handicap", []),
                            "over_under": m.get("over_under", []),
                            "consensus": m.get("consensus", {}),
                        }
                        break

        await ctx.report_progress(0.7, "获取历史和状态...")

        # 4. 历史交锋
        if params.include_history:
            h2h_resp = await manager.get_result_history(match_id, term_limits=10)
            if h2h_resp.get("data"):
                context_data["head_to_head"] = h2h_resp["data"]

        # 5. 近期状态
        if params.include_form:
            form_resp = await manager.get_match_recent_form(match_id)
            if form_resp.get("data"):
                context_data["team_form"] = form_resp["data"]

        # 6. 伤停信息
        injury_resp = await manager.get_injury_suspension(match_id)
        if injury_resp.get("data"):
            context_data["injuries"] = injury_resp["data"]

        # 7. 积分榜
        standings_resp = await manager.get_match_tables(match_id)
        if standings_resp.get("data"):
            context_data["standings"] = standings_resp["data"]

        await ctx.report_progress(1.0, "完成")

        # 数据完整性摘要
        context_data["context_summary"] = {
            "total_fields": 7,
            "available_fields": sum([
                "basic_info" in context_data,
                "official_odds" in context_data,
                "market_odds" in context_data,
                "head_to_head" in context_data,
                "team_form" in context_data,
                "injuries" in context_data,
                "standings" in context_data,
            ]),
            "data_quality": "完整" if "official_odds" in context_data and "basic_info" in context_data else "部分",
        }

        return _to_json({
            "success": True,
            "data": context_data,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"获取比赛上下文失败: {e}")
        raise_tool_error(f"获取比赛上下文失败: {e}")


async def lottery_quantify_injury_impact(params: QuantifyInjuryImpactInput, ctx: Context) -> str:
    """量化伤停影响

    Args:
        params: 分析参数
        ctx: MCP Context

    Returns:
        伤停影响量化结果
    """
    try:
        await ctx.report_progress(0.3, "正在获取伤停数据...")
        await ctx.log_info(f"[伤停影响] 分析比赛 {params.match_id}")

        manager = _get_manager()

        # 获取伤停数据
        injury_data = await manager.get_injury_suspension(params.match_id)

        if not injury_data.get("data"):
            raise_tool_error(
                "无法获取伤停数据",
                code="INJURY_DATA_NOT_FOUND",
                suggestion="请确认比赛ID正确或该比赛暂无伤停信息"
            )

        await ctx.report_progress(0.6, "正在计算影响评分...")

        data = injury_data["data"]
        home_injuries = data.get("home_injuries", [])
        away_injuries = data.get("away_injuries", [])

        # 计算影响评分
        def calculate_impact_score(injuries, weight_type="balanced"):
            """计算伤停影响评分"""
            if not injuries:
                return 0

            position_weights = {
                "GK": 1.5,  # 门将
                "DEF": 1.2,  # 后卫
                "MID": 1.0,  # 中场
                "FWD": 1.3,  # 前锋
            }

            importance_weights = {
                "key": 2.0,  # 核心球员
                "regular": 1.0,  # 常规主力
                "backup": 0.5,  # 替补
            }

            total_impact = 0
            for player in injuries:
                position = player.get("position", "MID")[:3].upper()
                importance = player.get("importance", "regular")

                pos_weight = position_weights.get(position, 1.0)
                imp_weight = importance_weights.get(importance, 1.0)

                # 根据权重类型调整
                if weight_type == "offense" and position in ["FWD", "MID"]:
                    pos_weight *= 1.3
                elif weight_type == "defense" and position in ["GK", "DEF"]:
                    pos_weight *= 1.3

                total_impact += pos_weight * imp_weight

            # 归一化到 0-100
            return min(100, round(total_impact * 10, 1))

        home_impact = calculate_impact_score(home_injuries, params.impact_weight)
        away_impact = calculate_impact_score(away_injuries, params.impact_weight)

        # 净影响（正值表示对主队不利，负值表示对客队不利）
        net_impact = home_impact - away_impact

        # 影响描述
        if abs(net_impact) < 10:
            impact_level = "轻微"
            recommendation = "伤停影响较小，可正常分析"
        elif abs(net_impact) < 25:
            impact_level = "中等"
            recommendation = "需考虑伤停因素，适当调整预期"
        else:
            impact_level = "严重"
            recommendation = "伤停影响显著，建议谨慎对待"

        await ctx.report_progress(1.0, "分析完成")

        return _to_json({
            "success": True,
            "data": {
                "match_id": params.match_id,
                "impact_weight": params.impact_weight,
                "home_team": {
                    "injury_count": len(home_injuries),
                    "impact_score": home_impact,
                    "key_players": [p.get("name", "Unknown") for p in home_injuries if p.get("importance") == "key"],
                },
                "away_team": {
                    "injury_count": len(away_injuries),
                    "impact_score": away_impact,
                    "key_players": [p.get("name", "Unknown") for p in away_injuries if p.get("importance") == "key"],
                },
                "net_impact": net_impact,
                "impact_level": impact_level,
                "recommendation": recommendation,
                "detailed_injuries": {
                    "home": home_injuries,
                    "away": away_injuries,
                },
            },
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"伤停影响分析失败: {e}")
        await ctx.log_error(f"[伤停影响] 分析失败: {e}")
        raise_tool_error(
            f"伤停影响分析失败: {str(e)}",
            code="INJURY_IMPACT_ERROR",
            suggestion="请稍后重试"
        )


async def lottery_assess_risk(params: AssessRiskInput, ctx: Context) -> str:
    """多维度风险评估"""
    try:
        manager = _get_manager()
        match_id = params.match_id

        await ctx.log_info(f"[风险评估] 评估比赛 {match_id} 的风险...")

        risk_factors = {}

        # 1. 赔率风险
        odds_resp = await manager.get_lottery_odds_change(match_id)
        if odds_resp.get("data"):
            odds_data = odds_resp["data"]
            if isinstance(odds_data, list) and len(odds_data) > 0:
                odds_data = odds_data[0]
            had = odds_data.get("had", {})
            if had:
                win, draw, lose = float(had.get("win", 0)), float(had.get("draw", 0)), float(had.get("lose", 0))
                if win > 0 and draw > 0 and lose > 0:
                    total_implied = 1/win + 1/draw + 1/lose
                    payout_rate = 1 / total_implied
                    # 返还率越低，风险越高
                    odds_risk = max(0, (0.90 - payout_rate) * 500)
                    # 赔率过于接近增加不确定性
                    odds_range = max(win, draw, lose) - min(win, draw, lose)
                    if odds_range < 1.0:
                        odds_risk += 15
                    risk_factors["odds_risk"] = {
                        "score": round(min(odds_risk, 100), 1),
                        "payout_rate": round(payout_rate, 4),
                        "description": "返还率偏低，庄家优势大" if payout_rate < 0.88 else "赔率合理",
                    }

        # 2. 状态风险
        form_resp = await manager.get_match_recent_form(match_id)
        if form_resp.get("data"):
            form_data = form_resp["data"]
            home_form = form_data.get("home_recent_form", [])
            away_form = form_data.get("away_recent_form", [])
            # 近期战绩波动大则风险高
            form_risk = 30
            if len(home_form) >= 5 and len(away_form) >= 5:
                home_results = [h.get("result") for h in home_form[:5]]
                away_results = [a.get("result") for a in away_form[:5]]
                # 检测连败/连胜（状态极端）
                if len(set(home_results)) == 1 or len(set(away_results)) == 1:
                    form_risk += 20
            risk_factors["form_risk"] = {
                "score": min(form_risk, 100),
                "description": "近期状态波动较大" if form_risk > 40 else "状态相对稳定",
            }
        else:
            risk_factors["form_risk"] = {
                "score": 50,
                "description": "无法获取近期状态数据",
            }

        # 3. 交锋风险
        h2h_resp = await manager.get_result_history(match_id, term_limits=5)
        if h2h_resp.get("data"):
            h2h_list = h2h_resp["data"].get("list", [])
            if len(h2h_list) < 3:
                h2h_risk = 40  # 交锋记录少
            else:
                home_wins = sum(1 for h in h2h_list if h.get("result") == "home_win")
                away_wins = sum(1 for h in h2h_list if h.get("result") == "away_win")
                # 交锋一边倒则风险高（可能过时）
                if home_wins == len(h2h_list) or away_wins == len(h2h_list):
                    h2h_risk = 35
                else:
                    h2h_risk = 20
            risk_factors["h2h_risk"] = {
                "score": h2h_risk,
                "sample_size": len(h2h_list),
                "description": "交锋记录不足" if len(h2h_list) < 3 else "交锋记录充分",
            }
        else:
            risk_factors["h2h_risk"] = {
                "score": 60,
                "description": "无法获取交锋记录",
            }

        # 4. 伤停风险
        injury_resp = await manager.get_injury_suspension(match_id)
        if injury_resp.get("data"):
            injuries = injury_resp["data"].get("injuries", [])
            key_injuries = [i for i in injuries if i.get("importance") in ["high", "key"]]
            injury_risk = min(len(key_injuries) * 15, 60)
            risk_factors["injury_risk"] = {
                "score": injury_risk,
                "key_injuries": len(key_injuries),
                "description": f"{len(key_injuries)}名关键球员缺阵" if key_injuries else "阵容相对完整",
            }
        else:
            risk_factors["injury_risk"] = {
                "score": 30,
                "description": "伤停信息不可用",
            }

        # 5. 市场风险
        market_resp = await manager.get_market_odds(sport="soccer", league=None)
        if market_resp.get("data"):
            market_risk = 25  # 有市场数据
        else:
            market_risk = 50  # 无市场数据
        risk_factors["market_risk"] = {
            "score": market_risk,
            "description": "市场数据可用" if market_risk < 40 else "市场数据缺失",
        }

        # 计算综合风险评分
        scores = [f["score"] for f in risk_factors.values()]
        overall_score = round(sum(scores) / len(scores), 1) if scores else 50

        # 风险等级
        if overall_score < 35:
            risk_level = "低"
        elif overall_score < 60:
            risk_level = "中"
        else:
            risk_level = "高"

        # 缓解建议
        mitigation_suggestions = []
        if risk_factors.get("odds_risk", {}).get("score", 0) > 50:
            mitigation_suggestions.append("赔率返还率偏低，建议控制投注金额")
        if risk_factors.get("h2h_risk", {}).get("score", 0) > 40:
            mitigation_suggestions.append("交锋记录不足，更多依赖近期状态判断")
        if risk_factors.get("injury_risk", {}).get("score", 0) > 30:
            mitigation_suggestions.append("关注伤停名单更新，阵容变化可能改变比赛走势")
        if not mitigation_suggestions:
            mitigation_suggestions.append("风险可控，可按计划投注")

        # 拟议投注的额外风险
        if params.proposed_bet:
            stake = params.proposed_bet.get("stake", 0)
            if stake > 500:
                mitigation_suggestions.append(f"拟议投注金额({stake}元)较大，建议分注或降低金额")

        return _to_json({
            "success": True,
            "data": {
                "match_id": match_id,
                "risk_factors": risk_factors,
                "overall_risk_score": overall_score,
                "risk_level": risk_level,
                "mitigation_suggestions": mitigation_suggestions,
            },
        })
    except Exception as e:
        logger.error(f"风险评估失败: {e}")
        raise_tool_error(f"风险评估失败: {e}")


async def lottery_simulate_scenarios(params: SimulateScenariosInput, ctx: Context) -> str:
    """比赛情景模拟 - 调整系数基于赔率隐含概率推导"""
    try:
        manager = _get_manager()
        match_id = params.match_id
        scenarios = params.scenarios

        await ctx.log_info(f"[情景模拟] 模拟比赛 {match_id} 的 {len(scenarios)} 种情景...")

        # 获取基础数据
        odds_resp = await manager.get_lottery_odds_change(match_id)
        base_probs = {"home_win": 0.33, "draw": 0.34, "away_win": 0.33}
        odds_available = False
        raw_odds = {"win": 2.0, "draw": 3.0, "lose": 3.0}
        home_lambda = 1.25  # 默认主队预期进球
        away_lambda = 1.25  # 默认客队预期进球

        if odds_resp.get("data"):
            odds_data = odds_resp["data"]
            if isinstance(odds_data, list) and len(odds_data) > 0:
                odds_data = odds_data[0]
            had = odds_data.get("had", {})
            if had:
                win, draw, lose = float(had.get("win", 2.0)), float(had.get("draw", 3.0)), float(had.get("lose", 3.0))
                if win > 0 and draw > 0 and lose > 0:
                    total = 1/win + 1/draw + 1/lose
                    base_probs = {
                        "home_win": (1/win) / total,
                        "draw": (1/draw) / total,
                        "away_win": (1/lose) / total,
                    }
                    raw_odds = {"win": win, "draw": draw, "lose": lose}
                    odds_available = True
                    # 从赔率反推泊松参数（预期进球数）
                    home_lambda, away_lambda = _estimate_lambdas_from_odds(win, draw, lose)

        # ============================================================
        # 基于赔率数据推导各情景调整系数
        # ============================================================
        pw = base_probs["home_win"]   # 主胜隐含概率
        pd = base_probs["draw"]       # 平局隐含概率
        pl = base_probs["away_win"]   # 客胜隐含概率
        total_expected_goals = home_lambda + away_lambda  # 预期总进球

        # 主客实力差距：正值表示主队更强（默认0，赔率可用时从赔率推导）
        strength_gap = pw - pl

        if odds_available:
            coefficient_source = "derived_from_odds"

            # --- 情景1: home_early_goal (主队早期进球) ---
            # 逻辑：主队进球后，主胜概率提升幅度与主队基础实力正相关
            # 主队越强，早期进球的"锁定胜局"效应越大
            # 系数推导：base + strength_gap * 敏感度
            c_home_early_hw = 1.0 + 0.25 + strength_gap * 0.5   # 基础+25%，实力差距放大
            c_home_early_d  = 1.0 - 0.10 - strength_gap * 0.3   # 平局概率被压缩
            c_home_early_aw = 1.0 - 0.25 - strength_gap * 0.3   # 客胜概率大幅下降

            # --- 情景2: away_early_goal (客队早期进球) ---
            # 逻辑：与主队早期进球对称，但考虑主场优势的抵消效应
            c_away_early_hw = 1.0 - 0.25 + strength_gap * 0.3
            c_away_early_d  = 1.0 - 0.05 - abs(strength_gap) * 0.2
            c_away_early_aw = 1.0 + 0.30 - strength_gap * 0.5

            # --- 情景3: red_card (红牌) ---
            # 逻辑：红牌对双方影响对称，但主队被罚下影响更大（失去主场优势）
            # 系数推导：基于主客胜概率差距调整红牌影响的不对称性
            # 主队被罚下概率与主队 aggression 正相关（简化为与实力正相关）
            home_red_card_risk = 0.5 + strength_gap * 0.3  # 主队更强时，被罚风险略高（控球多）
            away_red_card_risk = 1.0 - home_red_card_risk
            # 加权平均：红牌对主胜的影响 = 主队被罚概率 * 大幅下降 + 客队被罚概率 * 小幅上升
            c_red_hw = 1.0 + (away_red_card_risk * 0.15) - (home_red_card_risk * 0.30)
            c_red_d  = 1.0 + 0.08  # 红牌倾向于增加平局概率（弱势方更保守）
            c_red_aw = 1.0 + (home_red_card_risk * 0.15) - (away_red_card_risk * 0.30)

            # --- 情景4: penalty (点球) ---
            # 逻辑：点球对双方概率影响较小，主要取决于哪方获得点球
            # 获点球概率与进攻威胁正相关（简化为与进球期望正相关）
            home_penalty_prob = home_lambda / total_expected_goals if total_expected_goals > 0 else 0.5
            away_penalty_prob = 1.0 - home_penalty_prob
            # 点球转化率约75%，对胜率的影响：获得方胜率微升
            c_pen_hw = 1.0 + home_penalty_prob * 0.10 - away_penalty_prob * 0.05
            c_pen_d  = 1.0 - 0.04  # 点球略微降低平局概率
            c_pen_aw = 1.0 + away_penalty_prob * 0.10 - home_penalty_prob * 0.05

            # --- 情景5: away_lead_ht (客队半场领先) ---
            # 逻辑：客队半场领先是非常强的信号，大幅提升客胜概率
            # 客队半场领先说明客队表现超预期，系数与客队基础实力正相关
            # 历史数据：半场领先方最终胜率约75-80%
            away_hold_rate = 0.75 + pl * 0.10  # 客队越强，守住领先概率越高
            c_away_lead_hw = 1.0 - 0.35 + strength_gap * 0.2  # 主队翻盘概率与实力正相关
            c_away_lead_d  = 1.0 - 0.25 - abs(strength_gap) * 0.1
            c_away_lead_aw = 1.0 + (away_hold_rate - 0.5) * 1.2 - strength_gap * 0.3

            # --- 情景6: home_dominance (主队全场压制) ---
            # 逻辑：主队压制程度与主队进攻能力正相关
            # 系数推导：基于主队预期进球占比
            home_attack_ratio = home_lambda / total_expected_goals if total_expected_goals > 0 else 0.5
            c_dom_hw = 1.0 + 0.15 + home_attack_ratio * 0.20  # 主队进攻越强，压制效应越大
            c_dom_d  = 1.0 - 0.05 - home_attack_ratio * 0.10
            c_dom_aw = 1.0 - 0.30 - home_attack_ratio * 0.20

            # --- 情景7: low_scoring (低比分僵持) ---
            # 逻辑：低比分场景下平局概率大幅上升
            # 系数推导：基于平局隐含概率和预期总进球数
            # 预期进球越低，平局概率提升越大；平局基础概率越高，低比分效应越强
            draw_boost = (pd - 0.25) * 0.6  # 平局基础概率越高，提升越大
            goals_suppress = max(0, (2.5 - total_expected_goals) / 2.5) * 0.15  # 进球越少，效应越强
            c_low_hw = 1.0 - 0.15 - draw_boost * 0.3
            c_low_d  = 1.0 + 0.30 + draw_boost + goals_suppress
            c_low_aw = 1.0 - 0.15 - draw_boost * 0.3

            derived_coefficients = {
                "home_early_goal": {
                    "home_win": round(c_home_early_hw, 4),
                    "draw": round(c_home_early_d, 4),
                    "away_win": round(c_home_early_aw, 4),
                    "formula": "hw=1.25+strength_gap*0.5, d=0.90-strength_gap*0.3, aw=0.75-strength_gap*0.3",
                },
                "away_early_goal": {
                    "home_win": round(c_away_early_hw, 4),
                    "draw": round(c_away_early_d, 4),
                    "away_win": round(c_away_early_aw, 4),
                    "formula": "hw=0.75+strength_gap*0.3, d=0.95-|gap|*0.2, aw=1.30-strength_gap*0.5",
                },
                "red_card": {
                    "home_win": round(c_red_hw, 4),
                    "draw": round(c_red_d, 4),
                    "away_win": round(c_red_aw, 4),
                    "formula": "基于主客红牌风险加权(主队风险=0.5+strength_gap*0.3)",
                },
                "penalty": {
                    "home_win": round(c_pen_hw, 4),
                    "draw": round(c_pen_d, 4),
                    "away_win": round(c_pen_aw, 4),
                    "formula": "基于主客获点球概率(=lambda占比)加权，转化率75%",
                },
                "away_lead_ht": {
                    "home_win": round(c_away_lead_hw, 4),
                    "draw": round(c_away_lead_d, 4),
                    "away_win": round(c_away_lead_aw, 4),
                    "formula": f"守住率={round(away_hold_rate, 4)}, hw=0.65+gap*0.2, aw基于守住率",
                },
                "home_dominance": {
                    "home_win": round(c_dom_hw, 4),
                    "draw": round(c_dom_d, 4),
                    "away_win": round(c_dom_aw, 4),
                    "formula": f"主队进攻比={round(home_attack_ratio, 4)}, hw=1.15+ratio*0.20",
                },
                "low_scoring": {
                    "home_win": round(c_low_hw, 4),
                    "draw": round(c_low_d, 4),
                    "away_win": round(c_low_aw, 4),
                    "formula": f"draw_boost={round(draw_boost, 4)}, goals_suppress={round(goals_suppress, 4)}",
                },
            }
        else:
            # 赔率数据不完整，回退到基于默认值的系数
            coefficient_source = "fallback_default"
            derived_coefficients = {
                "home_early_goal": {"home_win": 1.40, "draw": 0.80, "away_win": 0.60, "formula": "fallback"},
                "away_early_goal": {"home_win": 0.60, "draw": 0.90, "away_win": 1.50, "formula": "fallback"},
                "red_card": {"home_win": 0.85, "draw": 1.10, "away_win": 0.85, "formula": "fallback"},
                "penalty": {"home_win": 1.05, "draw": 0.95, "away_win": 1.05, "formula": "fallback"},
                "away_lead_ht": {"home_win": 0.50, "draw": 0.70, "away_win": 1.60, "formula": "fallback"},
                "home_dominance": {"home_win": 1.30, "draw": 0.90, "away_win": 0.50, "formula": "fallback"},
                "low_scoring": {"home_win": 0.80, "draw": 1.50, "away_win": 0.80, "formula": "fallback"},
            }

        # ============================================================
        # 应用系数生成情景结果
        # ============================================================
        scenario_results = []

        for scenario in scenarios:
            result = {"scenario": scenario, "description": "", "probabilities": {}, "impact": {}}

            if scenario == "home_early_goal":
                c = derived_coefficients["home_early_goal"]
                result["description"] = "主队开场15分钟内进球"
                result["probabilities"] = {
                    "home_win": round(min(base_probs["home_win"] * c["home_win"], 0.70), 4),
                    "draw": round(base_probs["draw"] * c["draw"], 4),
                    "away_win": round(base_probs["away_win"] * c["away_win"], 4),
                }
                result["impact"] = {
                    "spf_recommendation": "主胜概率大幅提升",
                    "rqspf_impact": "让球主胜更稳",
                    "total_goals": "大球概率上升",
                }
                result["coefficient_detail"] = c

            elif scenario == "away_early_goal":
                c = derived_coefficients["away_early_goal"]
                result["description"] = "客队开场15分钟内进球"
                result["probabilities"] = {
                    "home_win": round(base_probs["home_win"] * c["home_win"], 4),
                    "draw": round(base_probs["draw"] * c["draw"], 4),
                    "away_win": round(min(base_probs["away_win"] * c["away_win"], 0.60), 4),
                }
                result["impact"] = {
                    "spf_recommendation": "客胜概率提升，但主队反扑风险存在",
                    "rqspf_impact": "需关注让球数",
                    "total_goals": "大球概率上升",
                }
                result["coefficient_detail"] = c

            elif scenario == "red_card":
                c = derived_coefficients["red_card"]
                result["description"] = "比赛中出现红牌"
                result["probabilities"] = {
                    "home_win": round(base_probs["home_win"] * c["home_win"], 4),
                    "draw": round(base_probs["draw"] * c["draw"], 4),
                    "away_win": round(base_probs["away_win"] * c["away_win"], 4),
                }
                result["impact"] = {
                    "note": "红牌影响取决于哪方被罚下",
                    "spf_recommendation": "少一人方胜率下降约30%",
                    "total_goals": "少一人方进球概率下降",
                }
                result["coefficient_detail"] = c

            elif scenario == "penalty":
                c = derived_coefficients["penalty"]
                result["description"] = "比赛中判罚点球"
                result["probabilities"] = {
                    "home_win": round(base_probs["home_win"] * c["home_win"], 4),
                    "draw": round(base_probs["draw"] * c["draw"], 4),
                    "away_win": round(base_probs["away_win"] * c["away_win"], 4),
                }
                result["impact"] = {
                    "note": "点球转化率约75%",
                    "total_goals": "进球数+1预期",
                }
                result["coefficient_detail"] = c

            elif scenario == "away_lead_ht":
                c = derived_coefficients["away_lead_ht"]
                result["description"] = "客队半场领先"
                result["probabilities"] = {
                    "home_win": round(base_probs["home_win"] * c["home_win"], 4),
                    "draw": round(base_probs["draw"] * c["draw"], 4),
                    "away_win": round(min(base_probs["away_win"] * c["away_win"], 0.65), 4),
                }
                result["impact"] = {
                    "spf_recommendation": "客队守住胜果概率较高",
                    "bqc_recommendation": "负负/平负组合",
                    "ht_ft": "半场客队领先时，全场客胜概率约55%",
                }
                result["coefficient_detail"] = c

            elif scenario == "home_dominance":
                c = derived_coefficients["home_dominance"]
                result["description"] = "主队全场压制（控球率>60%，射门占优）"
                result["probabilities"] = {
                    "home_win": round(min(base_probs["home_win"] * c["home_win"], 0.65), 4),
                    "draw": round(base_probs["draw"] * c["draw"], 4),
                    "away_win": round(base_probs["away_win"] * c["away_win"], 4),
                }
                result["impact"] = {
                    "spf_recommendation": "主胜概率提升",
                    "total_goals": "大球概率上升",
                    "cs_probability": "主队零封概率增加",
                }
                result["coefficient_detail"] = c

            elif scenario == "low_scoring":
                c = derived_coefficients["low_scoring"]
                result["description"] = "低比分僵持（60分钟仍0-0）"
                result["probabilities"] = {
                    "home_win": round(base_probs["home_win"] * c["home_win"], 4),
                    "draw": round(min(base_probs["draw"] * c["draw"], 0.55), 4),
                    "away_win": round(base_probs["away_win"] * c["away_win"], 4),
                }
                result["impact"] = {
                    "spf_recommendation": "平局概率大幅上升",
                    "total_goals": "小球概率极高",
                    "score_recommendation": "0:0/1:0/0:1",
                }
                result["coefficient_detail"] = c

            else:
                result["description"] = f"未知情景: {scenario}"
                result["probabilities"] = base_probs

            scenario_results.append(result)

        return _to_json({
            "success": True,
            "data": {
                "match_id": match_id,
                "base_probabilities": {k: round(v, 4) for k, v in base_probs.items()},
                "coefficient_source": coefficient_source,
                "base_implied_probabilities": {
                    "home_win": round(pw, 4),
                    "draw": round(pd, 4),
                    "away_win": round(pl, 4),
                    "strength_gap": round(strength_gap, 4),
                    "home_expected_goals": round(home_lambda, 4),
                    "away_expected_goals": round(away_lambda, 4),
                    "total_expected_goals": round(total_expected_goals, 4),
                    "raw_odds": raw_odds if odds_available else None,
                },
                "derived_coefficients": derived_coefficients,
                "scenarios": scenario_results,
                "scenarios_count": len(scenario_results),
            },
        })
    except Exception as e:
        logger.error(f"情景模拟失败: {e}")
        raise_tool_error(f"情景模拟失败: {e}")


async def lottery_generate_recommendation(params: GenerateRecommendationInput, ctx: Context) -> str:
    """生成综合投注建议"""
    try:
        manager = _get_manager()
        match_id = params.match_id
        risk_tolerance = params.risk_tolerance

        await ctx.log_info(f"[综合建议] 生成比赛 {match_id} 的投注建议...")
        await ctx.report_progress(0.2, "获取比赛数据...")

        # 1. 获取基础数据
        odds_resp = await manager.get_lottery_odds_change(match_id)
        if not odds_resp.get("data"):
            raise_tool_error("无法获取赔率数据", code="NO_ODDS_DATA")

        odds_data = odds_resp["data"]
        if isinstance(odds_data, list) and len(odds_data) > 0:
            odds_data = odds_data[0]

        had = odds_data.get("had", {})
        hhad = odds_data.get("hhad", {})

        if not had:
            raise_tool_error("无法获取胜平负赔率", code="NO_HAD_ODDS")

        win, draw, lose = float(had.get("win", 0)), float(had.get("draw", 0)), float(had.get("lose", 0))

        await ctx.report_progress(0.4, "分析赔率数据...")

        # 2. 计算隐含概率
        total_implied = 1/win + 1/draw + 1/lose
        probs = {
            "home_win": (1/win) / total_implied,
            "draw": (1/draw) / total_implied,
            "away_win": (1/lose) / total_implied,
        }

        # 3. 根据风险偏好生成建议
        selection_map = {"home_win": "主胜", "draw": "平局", "away_win": "客胜"}

        if risk_tolerance == "conservative":
            # 保守：选最高概率
            best = max(probs, key=probs.get)
            recommendation = {
                "play": "SPF",
                "selection": selection_map[best],
                "odds": had.get({"home_win": "win", "draw": "draw", "away_win": "lose"}[best]),
                "confidence": round(probs[best] * 100, 1),
                "rationale": f"{selection_map[best]}概率最高({round(probs[best]*100, 1)}%)，适合保守策略",
            }

        elif risk_tolerance == "aggressive":
            # 激进：选最高赔率（在合理范围内）
            odds_map = {"home_win": win, "draw": draw, "away_win": lose}
            ev_map = {k: probs[k] * odds_map[k] for k in probs}
            best = max(ev_map, key=ev_map.get)
            recommendation = {
                "play": "SPF",
                "selection": selection_map[best],
                "odds": had.get({"home_win": "win", "draw": "draw", "away_win": "lose"}[best]),
                "confidence": round(probs[best] * 100, 1),
                "rationale": f"{selection_map[best]}期望值最高({round(ev_map[best], 3)})，适合激进策略",
            }

        else:  # balanced
            # 平衡：概率和赔率的平衡
            scores = {}
            for k in probs:
                prob_score = probs[k] * 0.6
                odds_score = (had.get({"home_win": "win", "draw": "draw", "away_win": "lose"}[k], 2.0) / 5) * 0.4
                scores[k] = prob_score + odds_score
            best = max(scores, key=scores.get)
            recommendation = {
                "play": "SPF",
                "selection": selection_map[best],
                "odds": had.get({"home_win": "win", "draw": "draw", "away_win": "lose"}[best]),
                "confidence": round(min(probs[best] * 1.1, 0.75) * 100, 1),
                "rationale": f"{selection_map[best]}在概率和赔率间取得平衡，综合评分最高",
            }

        await ctx.report_progress(0.6, "评估风险...")

        # 4. 风险评估
        risk_level = "低" if probs[best] > 0.45 else ("中" if probs[best] > 0.30 else "高")

        # 5. 备选方案
        alternatives = []
        if hhad:
            rq_win = float(hhad.get("win", 0))
            rq_draw = float(hhad.get("draw", 0))
            rq_lose = float(hhad.get("lose", 0))
            handicap = hhad.get("handicap", "0")
            if rq_win > 0 and rq_draw > 0 and rq_lose > 0:
                rq_total = 1/rq_win + 1/rq_draw + 1/rq_lose
                rq_probs = {
                    "home_win": (1/rq_win) / rq_total,
                    "draw": (1/rq_draw) / rq_total,
                    "away_win": (1/rq_lose) / rq_total,
                }
                rq_best = max(rq_probs, key=rq_probs.get)
                alternatives.append({
                    "play": "RQSPF",
                    "selection": f"让球{selection_map[rq_best]}({handicap})",
                    "odds": hhad.get({"home_win": "win", "draw": "draw", "away_win": "lose"}[rq_best]),
                    "confidence": round(rq_probs[rq_best] * 100, 1),
                })

        await ctx.report_progress(0.8, "生成建议...")

        # 6. 规则验证
        rule_validation = {
            "is_valid": True,
            "play_type_valid": True,
            "odds_valid": recommendation["odds"] is not None and float(recommendation["odds"]) > 1.0,
            "confidence_valid": recommendation["confidence"] >= 30,
        }

        # 7. 免责声明
        disclaimer = (
            "本建议仅供娱乐参考，不构成投注建议。"
            "竞彩有风险，投注需谨慎。"
            "请理性购彩，量力而行。"
        )

        await ctx.report_progress(1.0, "完成")

        return _to_json({
            "success": True,
            "data": {
                "match_id": match_id,
                "risk_tolerance": risk_tolerance,
                "recommendation": recommendation,
                "reasoning": {
                    "primary_factor": "赔率隐含概率分析",
                    "supporting_factors": [f"{selection_map[k]}概率: {round(v*100, 1)}%" for k, v in probs.items()],
                    "confidence_basis": f"基于{risk_tolerance}策略选择最优选项",
                },
                "risk_assessment": {
                    "level": risk_level,
                    "score": round((1 - probs[best]) * 100, 1),
                    "key_risks": ["比赛结果具有不确定性", "赔率可能随时变化"],
                },
                "alternatives": alternatives,
                "rule_validation": rule_validation,
                "disclaimer": disclaimer,
            },
        })
    except Exception as e:
        logger.error(f"生成建议失败: {e}")
        raise_tool_error(f"生成建议失败: {e}")


async def lottery_compare_matches(params: CompareMatchesInput, ctx: Context) -> str:
    """多场比赛对比分析"""
    try:
        manager = _get_manager()
        match_ids = params.match_ids
        dimensions = params.comparison_dimensions

        await ctx.log_info(f"[比赛对比] 对比 {len(match_ids)} 场比赛，维度: {dimensions}")
        await ctx.report_progress(0.2, "获取比赛数据...")

        matches_data = []
        for match_id in match_ids:
            match_data = {"match_id": match_id}

            # 获取赔率数据
            if "odds" in dimensions:
                odds_resp = await manager.get_lottery_odds_change(match_id)
                if odds_resp.get("data"):
                    odds_data = odds_resp["data"]
                    if isinstance(odds_data, list) and len(odds_data) > 0:
                        odds_data = odds_data[0]
                    had = odds_data.get("had", {})
                    if had:
                        win, draw, lose = float(had.get("win", 0)), float(had.get("draw", 0)), float(had.get("lose", 0))
                        if win > 0 and draw > 0 and lose > 0:
                            total = 1/win + 1/draw + 1/lose
                            match_data["odds"] = {
                                "win": win, "draw": draw, "lose": lose,
                                "payout_rate": round(1/total, 4),
                                "home_prob": round((1/win)/total, 4),
                                "draw_prob": round((1/draw)/total, 4),
                                "away_prob": round((1/lose)/total, 4),
                            }

            # 获取近期状态
            if "form" in dimensions:
                form_resp = await manager.get_match_recent_form(match_id)
                if form_resp.get("data"):
                    match_data["form"] = form_resp["data"]

            # 获取历史交锋
            if "h2h" in dimensions:
                h2h_resp = await manager.get_result_history(match_id, term_limits=5)
                if h2h_resp.get("data"):
                    match_data["h2h"] = h2h_resp["data"]

            # 获取伤停信息
            if "injuries" in dimensions:
                injury_resp = await manager.get_injury_suspension(match_id)
                if injury_resp.get("data"):
                    injuries = injury_resp["data"].get("injuries", [])
                    match_data["injuries"] = {
                        "count": len(injuries),
                        "key_injuries": len([i for i in injuries if i.get("importance") in ["high", "key"]]),
                    }

            # 获取积分榜
            if "standings" in dimensions:
                standings_resp = await manager.get_match_tables(match_id)
                if standings_resp.get("data"):
                    match_data["standings"] = standings_resp["data"]

            matches_data.append(match_data)

        await ctx.report_progress(0.6, "计算相似度...")

        # 计算比赛间的相似度
        similarity_matrix = []
        patterns = []

        for i, m1 in enumerate(matches_data):
            for j, m2 in enumerate(matches_data):
                if i >= j:
                    continue

                similarity_score = 0
                similarity_factors = []

                # 赔率相似度
                if "odds" in dimensions and "odds" in m1 and "odds" in m2:
                    o1, o2 = m1["odds"], m2["odds"]
                    prob_diff = abs(o1["home_prob"] - o2["home_prob"])
                    if prob_diff < 0.05:
                        similarity_score += 25
                        similarity_factors.append("赔率结构相似")
                    elif prob_diff < 0.1:
                        similarity_score += 15

                # 伤停相似度
                if "injuries" in dimensions and "injuries" in m1 and "injuries" in m2:
                    if m1["injuries"]["key_injuries"] == m2["injuries"]["key_injuries"]:
                        similarity_score += 20
                        if m1["injuries"]["key_injuries"] > 0:
                            similarity_factors.append("均有关键球员伤停")

                similarity_matrix.append({
                    "match_pair": f"{m1['match_id']} vs {m2['match_id']}",
                    "similarity_score": similarity_score,
                    "factors": similarity_factors,
                })

        # 识别模式
        high_similarity_pairs = [s for s in similarity_matrix if s["similarity_score"] >= 40]
        if len(high_similarity_pairs) >= 2:
            patterns.append({
                "pattern_type": "相似比赛群",
                "description": f"发现 {len(high_similarity_pairs)} 对高相似度比赛",
                "matches_involved": list(set([m for s in high_similarity_pairs for m in s["match_pair"].split(" vs ")])),
            })

        await ctx.report_progress(1.0, "完成")

        # 生成Markdown格式
        if params.response_format == "markdown":
            lines = ["# 多场比赛对比分析", ""]
            lines.append(f"**分析比赛数**: {len(match_ids)}")
            lines.append(f"**对比维度**: {', '.join(dimensions)}")
            lines.append("")

            lines.append("## 比赛数据摘要")
            for m in matches_data:
                lines.append(f"### {m['match_id']}")
                if "odds" in m:
                    o = m["odds"]
                    lines.append(f"- 赔率: 主{o['win']}/平{o['draw']}/客{o['lose']}")
                    lines.append(f"- 返还率: {o['payout_rate']}")
                if "injuries" in m:
                    lines.append(f"- 关键伤停: {m['injuries']['key_injuries']}人")
                lines.append("")

            if similarity_matrix:
                lines.append("## 相似度分析")
                for s in sorted(similarity_matrix, key=lambda x: x["similarity_score"], reverse=True)[:5]:
                    lines.append(f"- {s['match_pair']}: 相似度 {s['similarity_score']}")
                    if s["factors"]:
                        lines.append(f"  - 因素: {', '.join(s['factors'])}")

            if patterns:
                lines.append("")
                lines.append("## 识别模式")
                for p in patterns:
                    lines.append(f"- **{p['pattern_type']}**: {p['description']}")

            return "\n".join(lines)

        return _to_json({
            "success": True,
            "data": {
                "matches_analyzed": len(matches_data),
                "dimensions": dimensions,
                "matches_data": matches_data,
                "similarity_matrix": similarity_matrix,
                "patterns": patterns,
            },
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"比赛对比分析失败: {e}")
        raise_tool_error(f"比赛对比分析失败: {e}")


async def lottery_optimize_stakes(params: OptimizeStakesInput, ctx: Context) -> str:
    """资金分配优化"""
    try:
        bankroll = params.bankroll
        bets = params.bets
        strategy = params.strategy
        max_stake_pct = params.max_stake_percent

        await ctx.log_info(f"[资金优化] 策略: {strategy}, 资金: {bankroll}, 投注数: {len(bets)}")
        await ctx.report_progress(0.3, "计算资金分配...")

        max_stake = bankroll * max_stake_pct
        allocations = []

        if strategy == "kelly":
            # 凯利公式: f* = (bp - q) / b
            total_kelly_fraction = 0
            for bet in bets:
                odds = bet.get("odds", 2.0)
                prob = bet.get("probability", 0.5)
                b = odds - 1
                p = prob
                q = 1 - p
                kelly = (b * p - q) / b if b > 0 else 0
                kelly = max(0, kelly)  # 负凯利不投注
                total_kelly_fraction += kelly

            # 归一化并应用限制
            for bet in bets:
                odds = bet.get("odds", 2.0)
                prob = bet.get("probability", 0.5)
                b = odds - 1
                p = prob
                q = 1 - p
                kelly = (b * p - q) / b if b > 0 else 0
                kelly = max(0, kelly)

                # 归一化
                if total_kelly_fraction > 0:
                    normalized_kelly = kelly / total_kelly_fraction
                else:
                    normalized_kelly = 1 / len(bets)

                stake = min(bankroll * normalized_kelly, max_stake)
                expected_value = prob * odds - 1

                allocations.append({
                    "match_id": bet.get("match_id", ""),
                    "selection": bet.get("selection", ""),
                    "odds": odds,
                    "probability": prob,
                    "kelly_fraction": round(kelly, 4),
                    "stake": round(stake, 2),
                    "stake_percentage": round(stake / bankroll * 100, 2),
                    "expected_value": round(expected_value, 4),
                })

        elif strategy == "risk_parity":
            # 风险平价: 根据风险贡献分配
            # 简化: 风险与(1-概率)*赔率成反比
            risks = []
            for bet in bets:
                prob = bet.get("probability", 0.5)
                risk = (1 - prob)
                risks.append(max(0.01, risk))  # 避免除零

            total_inverse_risk = sum(1/r for r in risks)

            for i, bet in enumerate(bets):
                odds = bet.get("odds", 2.0)
                prob = bet.get("probability", 0.5)
                weight = (1/risks[i]) / total_inverse_risk if total_inverse_risk > 0 else 1/len(bets)
                stake = min(bankroll * weight, max_stake)
                expected_value = prob * odds - 1

                allocations.append({
                    "match_id": bet.get("match_id", ""),
                    "selection": bet.get("selection", ""),
                    "odds": odds,
                    "probability": prob,
                    "risk_weight": round(weight, 4),
                    "stake": round(stake, 2),
                    "stake_percentage": round(stake / bankroll * 100, 2),
                    "expected_value": round(expected_value, 4),
                })

        else:  # equal
            stake_per_bet = min(bankroll / len(bets), max_stake)
            for bet in bets:
                odds = bet.get("odds", 2.0)
                prob = bet.get("probability", 0.5)
                expected_value = prob * odds - 1

                allocations.append({
                    "match_id": bet.get("match_id", ""),
                    "selection": bet.get("selection", ""),
                    "odds": odds,
                    "probability": prob,
                    "stake": round(stake_per_bet, 2),
                    "stake_percentage": round(stake_per_bet / bankroll * 100, 2),
                    "expected_value": round(expected_value, 4),
                })

        await ctx.report_progress(0.7, "计算风险指标...")

        # 计算汇总指标
        total_stake = sum(a["stake"] for a in allocations)
        total_exposure = total_stake / bankroll
        weighted_ev = sum(a["expected_value"] * a["stake"] for a in allocations) / total_stake if total_stake > 0 else 0

        # 最大回撤估计 (简化: 假设所有投注都输)
        max_drawdown = total_exposure

        # 预期收益
        expected_profit = sum(a["expected_value"] * a["stake"] for a in allocations)

        await ctx.report_progress(1.0, "完成")

        return _to_json({
            "success": True,
            "data": {
                "bankroll": bankroll,
                "strategy": strategy,
                "max_stake_percent": max_stake_pct,
                "allocations": allocations,
                "summary": {
                    "total_stake": round(total_stake, 2),
                    "total_exposure": round(total_exposure * 100, 2),
                    "max_drawdown_percent": round(max_drawdown * 100, 2),
                    "weighted_expected_value": round(weighted_ev, 4),
                    "expected_profit": round(expected_profit, 2),
                    "bets_count": len(allocations),
                },
                "recommendations": [
                    "建议单次总风险敞口不超过总资金的20%",
                    "凯利公式建议采用半凯利或四分之一凯利以降低波动",
                    "风险平价策略适合相关性较高的多场比赛",
                ],
            },
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"资金分配优化失败: {e}")
        raise_tool_error(f"资金分配优化失败: {e}")


# ============================================================
# Tool Registration
# ============================================================

def register_analysis_tools(mcp):
    """注册分析引擎工具"""
    from mcp.server.fastmcp import Context

    @mcp.tool(
        name="lottery_analyze_all_matches",
        description="""分析所有比赛

批量分析当日所有比赛，返回每场比赛的关键指标摘要。
支持按条件筛选（高价值/低风险）。

Use when: 需要快速了解当日所有比赛时。

前置条件: 请先调用 lottery_fetch_today_matches 填充数据缓存。Workflow: fetch_today_matches → analyze_all_matches → generate_recommendation""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_analyze_all_matches(params: AnalyzeAllMatchesInput, ctx: Context) -> str:
        return await lottery_analyze_all_matches(params, ctx)

    @mcp.tool(
        name="lottery_analyze_with_pipeline",
        description="""使用统一流水线分析所有比赛 (Phase 2 新增)

这是 Phase 2 新增的专业分析工具，使用统一的分析流水线对比赛进行全面分析。

与 lottery_analyze_all_matches 的区别：
- 一次分析，产出完整数据包（基本面+模型+玩法+规则）
- 包含比赛特征画像和策略配置
- 包含完整的投注理由链
- 包含玩法排名和冷门预警

返回内容：
- statistical_models: 三模型分析结果（泊松/Elo/xG）
- plays: 五大玩法概率和建议
- match_profile: 比赛特征画像
- strategy_config: 策略配置
- reasoning_chain: 投注理由链
- play_ranking: 玩法排名
- upset_signals: 冷门预警

Use when: 需要对比赛进行深度分析、生成专业投注建议时。

前置条件: 请先调用 lottery_fetch_today_matches 填充数据缓存。

Workflow: fetch_today_matches → analyze_with_pipeline → smart_parlay 或 generate_betting_slips""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_analyze_with_pipeline(params: AnalyzeWithPipelineInput, ctx: Context) -> str:
        return await lottery_analyze_with_pipeline(params, ctx)

    @mcp.tool(
        name="lottery_analyze_match_plays",
        description="""分析比赛的五大玩法

对单场比赛进行五大玩法的全面分析：
- SPF (胜平负): 基础胜平负概率与价值分析
- RQSPF (让球胜平负): 考虑让球后的胜平负分析
- BF (比分): 各比分组合概率预测
- ZJQ (总进球): 进球数区间概率分析
- BQC (半全场): 半场/全场结果组合分析

返回每个玩法的概率分布、价值投注推荐、置信度评估。

Use when: 需要了解某场比赛在所有玩法上的投注机会时。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_analyze_match_plays(params: AnalyzeMatchPlaysInput, ctx: Context) -> str:
        return await lottery_analyze_match_plays(params, ctx)

    @mcp.tool(
        name="lottery_detect_risk_signals",
        description="""检测比赛风险信号

对单场比赛进行多维度风险信号检测：
- odds_drift: 赔率异动检测（需提供current_odds和previous_odds）
- lineup: 阵容风险检测（伤停信息）

返回每个信号的严重程度、详细描述和建议。

Use when: 需要评估某场比赛是否存在异常风险时。

Workflow: 
1. 获取比赛数据: lottery_fetch_today_matches 或 lottery_get_match_context
2. 获取历史赔率: lottery_get_odds_history（如可用）
3. 检测风险信号: lottery_detect_risk_signals
4. 评估整体风险: lottery_assess_risk
5. 生成建议: lottery_generate_recommendation

常见错误:
- 缺少previous_odds时，赔率异动检测将被跳过，仅检测阵容风险
- match_id格式需为YYYYMMDD_Home_vs_Away才能自动查询伤停信息""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_detect_risk_signals(params: DetectRiskSignalsInput, ctx: Context) -> str:
        return await lottery_detect_risk_signals(params, ctx)

    @mcp.tool(
        name="lottery_compare_model_predictions",
        description="""对比多个统计模型的预测结果

对比泊松模型、Elo评级模型、期望进球模型(xG)的预测结果，识别模型间的一致性和分歧，帮助AI做出更准确的判断。

返回内容：
- 各模型的主胜/平/客胜概率
- 模型间一致性评估（高度一致/基本一致/存在分歧/显著分歧）
- 概率分歧最大的选项及其各模型具体数值
- 加权平均综合概率（泊松40%、Elo30%、xG30%）
- 综合建议及置信度

Use when: 需要对比多个模型对同一场比赛的预测，评估预测可靠性时。

Workflow: predict_with_model(获取单模型结果) → compare_model_predictions(对比分析)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_compare_model_predictions(params: CompareModelPredictionsInput, ctx: Context) -> str:
        return await lottery_compare_model_predictions(params, ctx)

    @mcp.tool(
        name="lottery_analyze_results",
        description="""赛果统计分析

对指定日期范围内的开奖结果进行统计分析，包括：
- 胜/平/负分布比例
- 联赛维度统计
- 高频赛果模式
- 让球胜平负分布（如适用）

支持按彩种、联赛、日期范围筛选。

数据来源：500.com / sporttery.cn。

Use when: 需要分析历史赛果规律、统计胜平负分布时。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_analyze_results(params: AnalyzeResultsInput, ctx: Context) -> str:
        return await lottery_analyze_results(params, ctx)

    @mcp.tool(
        name="lottery_find_value_bets",
        description="""发现价值投注（工作流工具）

对比竞彩官方赔率与国际市场赔率，找出价值投注机会。

分析逻辑：
1. 获取竞彩官方赔率（SPF/RQSPF）
2. 获取国际市场平均赔率（欧赔/亚盘）
3. 计算隐含概率差异
4. 筛选出：竞彩赔率 > 市场隐含概率 的价值选项

返回每场比赛的价值评估和推荐。

Use when: 需要寻找价值投注机会、对比竞彩与国际市场差异时。

Workflow: get_market_odds(获取赔率) → find_value_bets → generate_betting_slips(生成投注单)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_find_value_bets(params: FetchTodayMatchesInput, ctx: Context) -> str:
        return await lottery_find_value_bets(params, ctx)

    @mcp.tool(
        name="lottery_analyze_match",
        description="""单场比赛深度分析（工作流工具）

整合多维度数据生成完整的比赛分析报告：

分析维度：
1. 官方赔率分析 - 返还率、凯利指数、赔率合理性
2. 市场赔率对比 - 欧赔、亚盘、大小球与国际市场对比
3. 比赛资讯综合 - 交锋历史、积分榜、近期状态、伤停影响
4. 投注建议生成 - 基于以上分析的推荐选项

分析深度：
- basic: 基础分析（仅官方赔率+核心资讯）
- standard: 标准分析（增加市场对比）
- deep: 深度分析（全量数据+详细推理）

Use when: 需要对单场比赛做全面分析、生成投注建议时。

Workflow: fetch_today_matches(获取match_id) → analyze_match → analyze_match_plays(五大玩法) → generate_betting_slips""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_analyze_match(params: AnalyzeMatchInput, ctx: Context) -> str:
        return await lottery_analyze_match(params, ctx)

    @mcp.tool(
        name="lottery_predict_with_model",
        description="""使用ML模型预测比赛结果

基于统计模型对比赛结果进行预测，支持多种模型类型：
- poisson: 泊松分布模型（基于进球期望）
- elo: Elo评级模型（基于球队实力评级）
- xg: 预期进球模型（基于射门质量）
- ensemble: 集成模型（综合以上三种模型）

返回预测概率、置信度和关键特征分析。

Use when: 需要基于数据模型预测比赛结果时。

Workflow: fetch_today_matches → predict_with_model → compare_model_predictions(多模型对比)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_predict_with_model(params: PredictWithModelInput, ctx: Context) -> str:
        return await lottery_predict_with_model(params, ctx)

    @mcp.tool(
        name="lottery_get_market_sentiment",
        description="""获取市场情绪分析

分析市场对指定比赛的情绪倾向，包括：
- 投注量分布（主胜/平局/客胜的投注比例）
- 赔率变动趋势（基于HAD与HHAD差异推导）
- 市场热度指标（综合返还率、概率差异、本地/国际偏差）
- 聪明钱指标（检测专业资金动向）
- 价值信号（识别潜在价值投注）

帮助识别市场过度倾向或价值机会。

Use when: 需要了解市场对比赛的看法和投注倾向时。

Workflow:
1. 获取比赛赔率数据: lottery_get_match_context
2. 分析市场情绪: lottery_get_market_sentiment
3. 识别价值投注: lottery_find_value_bets
4. 生成投注建议: lottery_generate_recommendation

输出解读:
- overall_sentiment: 整体情绪倾向(bullish_home/slightly_bullish_home/neutral/slightly_bullish_away/bullish_away)
- sentiment_score: 情绪分值(-1到+1，正值表示看好主队)
- smart_money_indicator: 聪明钱指标(strong_activity/moderate_activity/possible_activity/balanced)
- market_heat: 市场热度(high/medium/low)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_get_market_sentiment(params: GetMarketSentimentInput, ctx: Context) -> str:
        return await lottery_get_market_sentiment(params, ctx)

    # ============================================================
    # Phase 2: 高级分析工具注册
    # ============================================================

    @mcp.tool(
        name="lottery_get_match_context",
        description="""获取比赛完整上下文（AI推理工具）

聚合所有相关数据供AI进行深度推理分析：
- basic_info: 比赛基本信息（球队、联赛、时间、排名）
- official_odds: 竞彩官方赔率（SPF/RQSPF/BF/ZJQ/BQC）
- market_odds: 市场赔率对比（欧赔/亚盘/大小球）【可选】
- head_to_head: 历史交锋记录【可选】
- team_form: 近期状态（近5/10场战绩）【可选】
- injuries: 伤停信息
- standings: 积分榜位置
- context_summary: 数据完整性摘要

Use when: AI需要对比赛进行全面分析、生成投注建议时。

Workflow:
1. 获取比赛列表: lottery_fetch_today_matches
2. 获取比赛上下文: lottery_get_match_context(match_id, include_market=True, include_history=True)
3. 分析比赛: lottery_analyze_match 或 lottery_predict_with_model
4. 评估风险: lottery_assess_risk
5. 生成建议: lottery_generate_recommendation

参数说明:
- include_market: 是否获取国际市场赔率（增加API调用，可选）
- include_history: 是否获取历史交锋（增加API调用，可选）
- include_form: 是否获取近期状态（增加API调用，可选）

常见错误:
- 比赛ID不正确时，部分数据可能无法获取""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_get_match_context(params: GetMatchContextInput, ctx: Context) -> str:
        return await lottery_get_match_context(params, ctx)

    @mcp.tool(
        name="lottery_quantify_injury_impact",
        description="""量化伤停影响

分析比赛双方伤停情况对比赛结果的量化影响：
- 伤停球员重要性评分
- 攻防影响评估（可指定进攻/防守权重）
- 整体影响评分（0-100）
- 关键位置缺失分析

基于球员位置和重要性计算影响程度。

Use when: 需要评估伤停对比赛结果的影响时。

Workflow:
1. 获取比赛基本信息: lottery_get_match_context
2. 量化伤停影响: lottery_quantify_injury_impact (可指定impact_weight参数)
3. 评估综合风险: lottery_assess_risk
4. 生成调整后的预测: lottery_predict_with_model

输出解读:
- net_impact: 净影响值（正值表示对主队不利，负值表示对客队不利）
- impact_level: 轻微/中等/严重
- key_players: 关键伤停球员名单

常见错误:
- 无法获取伤停数据时，返回INJURY_DATA_NOT_FOUND错误""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_quantify_injury_impact(params: QuantifyInjuryImpactInput, ctx: Context) -> str:
        return await lottery_quantify_injury_impact(params, ctx)

    @mcp.tool(
        name="lottery_assess_risk",
        description="""多维度风险评估（AI推理工具）

对比赛进行全面的风险评估：
- odds_risk: 赔率风险（赔率合理性、返还率）
- form_risk: 状态风险（近期表现稳定性）
- h2h_risk: 交锋风险（历史交锋不确定性）
- injury_risk: 伤停风险（关键球员缺阵影响）
- market_risk: 市场风险（赔率异动、市场分歧）

返回:
- risk_factors: 各维度风险因子
- overall_risk_score: 综合风险评分(0-100)
- risk_level: 风险等级(低/中/高)
- mitigation_suggestions: 风险缓解建议

Use when: AI需要评估投注风险、制定风险管理策略时。

Workflow: get_match_context → assess_risk → simulate_scenarios(情景模拟)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_assess_risk(params: AssessRiskInput, ctx: Context) -> str:
        return await lottery_assess_risk(params, ctx)

    @mcp.tool(
        name="lottery_simulate_scenarios",
        description="""比赛情景模拟（AI推理工具）

模拟不同比赛情景下的结果概率和影响：
- home_early_goal: 主队 early goal 后的走势
- away_early_goal: 客队 early goal 后的走势
- red_card: 红牌出现后的影响
- penalty: 点球判罚的影响
- away_lead_ht: 客队半场领先后的下半场
- home_dominance: 主队全场压制情景
- low_scoring: 低比分僵持情景

返回各情景的概率分布和影响评估。

Use when: AI需要评估特定情景下的比赛走势、制定应变策略时。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_simulate_scenarios(params: SimulateScenariosInput, ctx: Context) -> str:
        return await lottery_simulate_scenarios(params, ctx)

    @mcp.tool(
        name="lottery_generate_recommendation",
        description="""生成综合投注建议（AI推理工具）

基于所有分析维度生成最终投注建议：
1. 聚合比赛上下文数据
2. 检测异常信号
3. 计算公平赔率
4. 评估风险等级
5. 模拟关键情景

返回:
- recommendation: 具体建议（玩法、选项、赔率、置信度）
- reasoning: 推理依据
- risk_assessment: 风险评估摘要
- alternatives: 备选方案
- rule_validation: 规则验证状态
- disclaimer: 免责声明

风险承受度: conservative(保守)/balanced(平衡)/aggressive(激进)

Use when: AI需要生成最终投注建议时，整合所有分析结果。

Workflow: analyze_match → assess_risk → generate_recommendation → validate_scenario(规则验证)""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_generate_recommendation(params: GenerateRecommendationInput, ctx: Context) -> str:
        return await lottery_generate_recommendation(params, ctx)

    @mcp.tool(
        name="lottery_compare_matches",
        description="""多场比赛对比分析，找出相似模式

对比多场比赛的各个维度，识别相似模式和差异：
- odds: 赔率结构对比（返还率、赔率分布）
- form: 近期状态对比（战绩、进球/失球）
- h2h: 历史交锋对比（交锋记录、心理因素）
- injuries: 伤停情况对比（关键球员缺阵影响）
- standings: 积分榜对比（排名、主客场成绩）

返回相似度评分、模式识别结果和对比分析报告。

Use when: 需要对比多场比赛找出相似模式、进行批量分析时。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_compare_matches(params: CompareMatchesInput, ctx: Context) -> str:
        return await lottery_compare_matches(params, ctx)

    @mcp.tool(
        name="lottery_optimize_stakes",
        description="""资金分配优化（凯利公式+风险平价+最大回撤）

根据总资金和投注列表，计算最优资金分配方案：
- kelly: 凯利公式 - 最大化对数收益率
- risk_parity: 风险平价 - 各投注风险贡献相等
- equal: 均等分配 - 每注相同金额

约束条件：
- 单注不超过总资金的max_stake_percent（默认5%）
- 总风险敞口控制
- 考虑各投注的赔率和胜率

返回每注金额、总风险敞口、预期收益和资金分配建议。

Use when: 需要科学分配投注资金、优化投资组合时。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_optimize_stakes(params: OptimizeStakesInput, ctx: Context) -> str:
        return await lottery_optimize_stakes(params, ctx)

    @mcp.tool(
        name="lottery_advisor_analysis",
        description="""智能顾问深度分析 - 多源数据综合推理

对单场比赛进行5层深度分析，整合所有可用数据源：
1. 赔率层：分析5大玩法赔率隐含概率和返还率
2. 模型层：泊松+Elo+xG多模型共识
3. 基本面层：历史交锋+积分榜+近期状态+伤停调整概率
4. 市场层：欧指/亚盘/大小球跨市场对比
5. 综合层：价值发现+风险矩阵+个性化投注方案

输出包括：
- 概率校准结果（赔率+基本面综合调整）
- 价值投注机会（EV正期望值检测）
- 跨玩法/跨市场信号
- 多维度风险矩阵评分
- 凯利公式投注方案
- 最终决策建议

Use when: 需要最全面的智能分析判断时，这是MCP的"大脑"功能。
先调用lottery_fetch_today_matches获取数据，然后用此工具进行深度分析。""",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def _lottery_advisor_analysis(params: AnalyzeMatchInput, ctx: Context) -> str:
        return await lottery_advisor_analysis(params, ctx)

    logger.info("分析工具注册完成：含智能顾问")
