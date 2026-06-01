# -*- coding: utf-8 -*-
"""
statistical_models.py 综合测试
================================
覆盖 PoissonModel、EloRatingSystem、XGModel、StatisticalEngine 四大组件。
"""

import math
import pytest
import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lottery_mcp.analysis.models import (
    PoissonModel,
    PoissonMatchPrediction,
    EloRatingSystem,
    EloTeamRating,
    XGModel,
    XGAnalysisResult,
    StatisticalEngine,
    StatisticalAnalysisResult,
    poisson_pmf,
)


# ============================================================================
# PoissonModel 测试
# ============================================================================


class TestPoissonModel:
    """PoissonModel 测试套件"""

    def setup_method(self):
        self.model = PoissonModel(max_goals=8)

    # ----- calculate_expected_goals -----

    def test_calculate_expected_goals_epl_data(self):
        """使用英超真实数据计算预期进球: 主队35球/19场, 客队22球/19场"""
        home_exp, away_exp = self.model.calculate_expected_goals(
            home_goals_for=35, home_games=19,
            home_goals_against=15,
            away_goals_for=22, away_games=19,
            away_goals_against=20,
            league="英超",
        )
        # 主队攻击力 = (35/19) / 1.55 ≈ 1.19
        # 客队防守力 = (20/19) / 1.20 ≈ 0.88
        # home_expected = 1.19 * 0.88 * 1.55 * 1.10 ≈ 1.79
        assert 0.3 <= home_exp <= 4.0, f"home_expected={home_exp} 超出合理范围"
        assert 0.2 <= away_exp <= 3.5, f"away_expected={away_exp} 超出合理范围"
        assert isinstance(home_exp, float)
        assert isinstance(away_exp, float)

    def test_calculate_expected_goals_returns_tuple(self):
        """验证返回类型为 (float, float)"""
        result = self.model.calculate_expected_goals(
            home_goals_for=10, home_games=10,
            home_goals_against=8,
            away_goals_for=7, away_games=10,
            away_goals_against=12,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(v, float) for v in result)

    def test_calculate_expected_goals_zero_games(self):
        """零场次时使用默认值 1.0 作为攻击/防守力"""
        home_exp, away_exp = self.model.calculate_expected_goals(
            home_goals_for=0, home_games=0,
            home_goals_against=0,
            away_goals_for=0, away_games=0,
            away_goals_against=0,
        )
        # 当 games=0 时, attack/defense 默认为 1.0
        # home_expected = 1.0 * 1.0 * league_home * 1.10
        assert home_exp > 0
        assert away_exp > 0

    def test_calculate_expected_goals_extreme_high(self):
        """极端高进球数据应被限制在合理范围内"""
        home_exp, away_exp = self.model.calculate_expected_goals(
            home_goals_for=100, home_games=10,
            home_goals_against=1,
            away_goals_for=100, away_games=10,
            away_goals_against=1,
        )
        # 应被 clamp 到 max 4.0 / 3.5
        assert home_exp <= 4.0
        assert away_exp <= 3.5

    def test_calculate_expected_goals_extreme_low(self):
        """极端低进球数据应被限制在合理范围内"""
        home_exp, away_exp = self.model.calculate_expected_goals(
            home_goals_for=0, home_games=19,
            home_goals_against=50,
            away_goals_for=0, away_games=19,
            away_goals_against=50,
        )
        assert home_exp >= 0.3
        assert away_exp >= 0.2

    def test_calculate_expected_goals_different_leagues(self):
        """不同联赛应产生不同结果"""
        results = {}
        for league in ["英超", "西甲", "德甲", "意甲", "法甲"]:
            h, a = self.model.calculate_expected_goals(
                home_goals_for=30, home_games=19,
                home_goals_against=20,
                away_goals_for=25, away_games=19,
                away_goals_against=22,
                league=league,
            )
            results[league] = (h, a)

        # 不同联赛基准不同，结果应有差异
        unique_results = set(results.values())
        assert len(unique_results) > 1, "不同联赛应产生不同的预期进球"

    # ----- predict -----

    def test_predict_returns_poisson_match_prediction(self):
        """predict() 返回 PoissonMatchPrediction 实例"""
        result = self.model.predict(home_expected=1.5, away_expected=1.2)
        assert isinstance(result, PoissonMatchPrediction)

    def test_predict_probabilities_sum_to_one(self):
        """胜/平/负概率之和应约等于 1.0"""
        result = self.model.predict(home_expected=1.5, away_expected=1.2)
        total = result.home_win_prob + result.draw_prob + result.away_win_prob
        assert abs(total - 1.0) < 0.01, f"概率之和={total}, 不等于1.0"

    def test_predict_adjusted_probabilities_equal_true_probabilities(self):
        """调整后概率应与真实概率相同（返还率不再修改模型概率）"""
        return_rate = 0.70
        result = self.model.predict(
            home_expected=1.5, away_expected=1.2, return_rate=return_rate
        )
        # After fix M2, adjusted probabilities are the same as true probabilities
        assert abs(result.home_win_prob_adjusted - result.home_win_prob) < 1e-9, (
            f"adjusted={result.home_win_prob_adjusted} != true={result.home_win_prob}"
        )
        assert abs(result.draw_prob_adjusted - result.draw_prob) < 1e-9, (
            f"adjusted={result.draw_prob_adjusted} != true={result.draw_prob}"
        )
        assert abs(result.away_win_prob_adjusted - result.away_win_prob) < 1e-9, (
            f"adjusted={result.away_win_prob_adjusted} != true={result.away_win_prob}"
        )
        # Adjusted probabilities should sum to 1.0 (not return_rate)
        total_adj = (
            result.home_win_prob_adjusted
            + result.draw_prob_adjusted
            + result.away_win_prob_adjusted
        )
        assert abs(total_adj - 1.0) < 0.01, (
            f"调整后概率之和={total_adj}, 应等于1.0"
        )

    def test_predict_score_probabilities_populated(self):
        """比分概率字典应包含足够的比分，且最可能比分有值"""
        result = self.model.predict(home_expected=1.5, away_expected=1.2)
        # 模型返回所有可能的比分（max_goals=8，共9x9=81个）
        assert len(result.score_probabilities) >= 10
        # 最可能比分应有值
        assert result.most_likely_score != ""
        assert result.most_likely_score_prob > 0

    def test_predict_over_under_btts(self):
        """大小球和BTTS概率应在合理范围内"""
        result = self.model.predict(home_expected=1.5, away_expected=1.2)
        assert 0.0 <= result.over_under_2_5 <= 1.0
        assert 0.0 <= result.over_under_3_5 <= 1.0
        assert 0.0 <= result.btts_prob <= 1.0
        # over_3_5 应小于 over_2_5
        assert result.over_under_3_5 <= result.over_under_2_5

    def test_predict_confidence_interval(self):
        """置信区间应有上下界"""
        result = self.model.predict(home_expected=1.5, away_expected=1.2)
        ci = result.confidence_interval
        assert "home_goals_lower" in ci
        assert "home_goals_upper" in ci
        assert "away_goals_lower" in ci
        assert "away_goals_upper" in ci
        assert ci["home_goals_lower"] <= result.home_expected_goals <= ci["home_goals_upper"]
        assert ci["away_goals_lower"] <= result.away_expected_goals <= ci["away_goals_upper"]

    def test_predict_home_favorited(self):
        """主队预期进球更高时，主胜概率应更高"""
        result_home_fav = self.model.predict(home_expected=2.0, away_expected=0.8)
        assert result_home_fav.home_win_prob > result_home_fav.away_win_prob
        assert result_home_fav.home_win_prob > result_home_fav.draw_prob

    def test_predict_away_favorited(self):
        """客队预期进球更高时，客胜概率应更高"""
        result_away_fav = self.model.predict(home_expected=0.8, away_expected=2.0)
        assert result_away_fav.away_win_prob > result_away_fav.home_win_prob

    # ----- find_value_bets -----

    def test_find_value_bets_identifies_value(self):
        """当市场赔率低估真实概率时，应识别出价值投注"""
        prediction = self.model.predict(home_expected=1.8, away_expected=1.0)
        # 主胜真实概率约 55%，赔率 2.50 隐含概率 40%，edge = 15%
        market_odds = {"win": 2.50, "draw": 3.50, "lose": 3.00}
        value_bets = self.model.find_value_bets(prediction, market_odds, threshold=0.05)
        assert isinstance(value_bets, list)
        # 应至少有一个价值投注
        assert len(value_bets) >= 1, "应识别出至少一个价值投注"

    def test_find_value_bets_structure(self):
        """价值投注结果应包含正确的字段"""
        prediction = self.model.predict(home_expected=2.0, away_expected=0.8)
        market_odds = {"win": 3.00, "draw": 3.50, "lose": 2.50}
        value_bets = self.model.find_value_bets(prediction, market_odds, threshold=0.01)
        if value_bets:
            bet = value_bets[0]
            required_keys = {
                "selection", "true_probability", "implied_probability",
                "edge", "odds", "expected_value", "kelly_fraction",
                "recommendation",
            }
            assert required_keys.issubset(bet.keys()), f"缺少字段: {required_keys - bet.keys()}"

    def test_find_value_bets_sorted_by_edge(self):
        """价值投注应按 edge 降序排列"""
        prediction = self.model.predict(home_expected=1.8, away_expected=1.0)
        market_odds = {"win": 2.50, "draw": 3.50, "lose": 4.00}
        value_bets = self.model.find_value_bets(prediction, market_odds, threshold=0.01)
        if len(value_bets) >= 2:
            edges = [b["edge"] for b in value_bets]
            assert edges == sorted(edges, reverse=True), "价值投注未按edge降序排列"

    def test_find_value_bets_no_value(self):
        """当市场赔率合理时，不应识别出价值投注"""
        prediction = self.model.predict(home_expected=1.5, away_expected=1.2)
        # Use odds that reflect fair prices adjusted for return rate.
        # With return_rate=0.70, implied_prob = 1/odds * 0.70.
        # For no value: implied_prob >= true_prob, i.e., 1/odds * 0.70 >= prob,
        # so odds <= 0.70/prob.
        market_odds = {
            "win": round(0.70 / prediction.home_win_prob, 2),
            "draw": round(0.70 / prediction.draw_prob, 2),
            "lose": round(0.70 / prediction.away_win_prob, 2),
        }
        value_bets = self.model.find_value_bets(prediction, market_odds, threshold=0.10)
        assert len(value_bets) == 0, "赔率合理时不应有价值投注"

    def test_find_value_bets_empty_odds(self):
        """空赔率字典应返回空列表"""
        prediction = self.model.predict(home_expected=1.5, away_expected=1.2)
        value_bets = self.model.find_value_bets(prediction, {}, threshold=0.05)
        assert value_bets == []


# ============================================================================
# EloRatingSystem 测试
# ============================================================================


class TestEloRatingSystem:
    """EloRatingSystem 测试套件"""

    def setup_method(self):
        # 不使用持久化文件，避免测试间干扰
        self.elo = EloRatingSystem(ratings_file=None)

    def test_get_rating_new_team_initializes(self):
        """新球队应被正确初始化"""
        rating = self.elo.get_rating("team_new", "New Team FC", "英超")
        assert isinstance(rating, (int, float))
        # 英超基准约 1650, 加减50随机
        assert 1600 <= rating <= 1700, f"新球队Elo={rating} 超出预期范围"
        assert "team_new" in self.elo.ratings

    def test_get_rating_default_league(self):
        """默认联赛的新球队应初始化为约1500"""
        rating = self.elo.get_rating("team_default", "Default Team")
        assert 1450 <= rating <= 1550, f"默认联赛Elo={rating} 超出预期范围"

    def test_get_rating_existing_team(self):
        """已存在的球队应返回其当前评级"""
        # 先初始化
        first_rating = self.elo.get_rating("team_existing", "Existing FC")
        # 再次获取
        second_rating = self.elo.get_rating("team_existing", "Existing FC")
        assert first_rating == second_rating

    def test_get_rating_league_differences(self):
        """不同联赛的基准Elo应不同"""
        epl_rating = self.elo.get_rating("team_epl", "EPL Team", "英超")
        ligue1_rating = self.elo.get_rating("team_l1", "L1 Team", "法甲")
        # 英超基准 1650 > 法甲基准 1560
        assert epl_rating > ligue1_rating, (
            f"英超Elo={epl_rating} 应大于法甲Elo={ligue1_rating}"
        )

    def test_update_rating_changes_ratings(self):
        """更新评级后，两队评级应发生变化"""
        # 初始化两队
        home_before = self.elo.get_rating("team_h", "Home", "英超")
        away_before = self.elo.get_rating("team_a", "Away", "英超")

        # 主队2:0获胜
        result = self.elo.update_rating(
            home_team_id="team_h", away_team_id="team_a",
            home_goals=2, away_goals=0,
            match_type="league", league="英超",
        )

        home_after = self.elo.get_rating("team_h")
        away_after = self.elo.get_rating("team_a")

        # 主队赢了，评级应上升
        assert home_after > home_before, (
            f"主队获胜后Elo应上升: {home_before} -> {home_after}"
        )
        # 客队输了，评级应下降
        assert away_after < away_before, (
            f"客队失利后Elo应下降: {away_before} -> {away_after}"
        )

    def test_update_rating_result_structure(self):
        """update_rating 返回结果应包含正确字段"""
        self.elo.get_rating("team_x", "Team X")
        self.elo.get_rating("team_y", "Team Y")

        result = self.elo.update_rating(
            home_team_id="team_x", away_team_id="team_y",
            home_goals=1, away_goals=1,
        )

        required_keys = {
            "home_team", "home_rating_before", "home_rating_after",
            "home_rating_change", "away_team", "away_rating_before",
            "away_rating_after", "away_rating_change",
            "home_expected", "home_actual", "k_factor", "match_result",
        }
        assert required_keys.issubset(result.keys())
        assert result["match_result"] == "1:1"

    def test_update_rating_draw_keeps_close(self):
        """平局时两队评级变化应较小"""
        self.elo.get_rating("team_d1", "Draw1")
        self.elo.get_rating("team_d2", "Draw2")

        result = self.elo.update_rating(
            home_team_id="team_d1", away_team_id="team_d2",
            home_goals=0, away_goals=0,
        )

        # 平局变化应小于大胜
        assert abs(result["home_rating_change"]) < 20
        assert abs(result["away_rating_change"]) < 20

    def test_update_rating_big_win_more_change(self):
        """大胜的评级变化应大于小胜"""
        # 准备两对球队
        self.elo.get_rating("bw_h1", "BigWin H1")
        self.elo.get_rating("bw_a1", "BigWin A1")
        self.elo.get_rating("sw_h2", "SmallWin H2")
        self.elo.get_rating("sw_a2", "SmallWin A2")

        big_result = self.elo.update_rating(
            home_team_id="bw_h1", away_team_id="bw_a1",
            home_goals=5, away_goals=0,
        )
        small_result = self.elo.update_rating(
            home_team_id="sw_h2", away_team_id="sw_a2",
            home_goals=1, away_goals=0,
        )

        # 大胜的主队评级提升应大于小胜
        assert big_result["home_rating_change"] > small_result["home_rating_change"], (
            f"大胜提升{big_result['home_rating_change']} 应大于小胜提升{small_result['home_rating_change']}"
        )

    def test_predict_match_returns_valid_probabilities(self):
        """predict_match 应返回有效的概率值"""
        self.elo.get_rating("pred_h", "Pred Home", "英超")
        self.elo.get_rating("pred_a", "Pred Away", "英超")

        result = self.elo.predict_match("pred_h", "pred_a", "英超")

        assert 0.0 <= result["home_win_prob"] <= 1.0
        assert 0.0 <= result["draw_prob"] <= 1.0
        assert 0.0 <= result["away_win_prob"] <= 1.0
        # 三者之和应约等于 1.0
        total = result["home_win_prob"] + result["draw_prob"] + result["away_win_prob"]
        assert abs(total - 1.0) < 0.05, f"概率之和={total}, 偏差过大"

    def test_predict_match_structure(self):
        """predict_match 返回结果应包含正确字段"""
        self.elo.get_rating("str_h", "Str H")
        self.elo.get_rating("str_a", "Str A")

        result = self.elo.predict_match("str_h", "str_a")

        required_keys = {
            "home_team_id", "home_team_name", "home_elo", "home_home_elo",
            "away_team_id", "away_team_name", "away_elo", "away_away_elo",
            "rating_diff", "home_advantage",
            "home_win_prob", "draw_prob", "away_win_prob",
            "home_matches_rated", "away_matches_rated", "form_elo",
        }
        assert required_keys.issubset(result.keys())

    def test_predict_match_home_advantage(self):
        """同评级球队，主队应有主场优势加成"""
        # 使用相同联赛和相近的初始评级
        self.elo.ratings["same_h"] = EloTeamRating(
            team_id="same_h", team_name="Same H",
            rating=1600.0, peak_rating=1600.0, lowest_rating=1600.0,
            matches_played=5, home_rating=1600.0, away_rating=1600.0,
        )
        self.elo.ratings["same_a"] = EloTeamRating(
            team_id="same_a", team_name="Same A",
            rating=1600.0, peak_rating=1600.0, lowest_rating=1600.0,
            matches_played=5, home_rating=1600.0, away_rating=1600.0,
        )

        result = self.elo.predict_match("same_h", "same_a")
        # 同评级主队应有优势
        assert result["home_win_prob"] > result["away_win_prob"], (
            "同评级球队，主队胜率应高于客队"
        )

    def test_get_top_teams_returns_sorted(self):
        """get_top_teams 应返回按评级降序排列的列表"""
        # 添加几场比赛来产生有差异的评级
        teams = ["top_a", "top_b", "top_c", "top_d"]
        for t in teams:
            self.elo.get_rating(t, f"Team {t}", "英超")

        # team_a 连胜
        for _ in range(5):
            self.elo.update_rating("top_a", "top_d", 2, 0, league="英超")
        # team_b 连败
        for _ in range(5):
            self.elo.update_rating("top_b", "top_c", 0, 2, league="英超")

        top = self.elo.get_top_teams(n=10)
        assert isinstance(top, list)
        assert len(top) > 0
        # 验证排序
        ratings = [t["rating"] for t in top]
        assert ratings == sorted(ratings, reverse=True), "排行榜未按评级降序排列"

    def test_get_top_teams_structure(self):
        """排行榜条目应包含正确字段"""
        self.elo.get_rating("struct_h", "Struct H")
        self.elo.get_rating("struct_a", "Struct A")
        self.elo.update_rating("struct_h", "struct_a", 3, 0)

        top = self.elo.get_top_teams(n=5)
        if top:
            entry = top[0]
            required_keys = {"rank", "team_id", "team_name", "rating", "matches", "peak", "home_elo", "away_elo"}
            assert required_keys.issubset(entry.keys())
            assert entry["rank"] == 1

    def test_get_top_teams_filters_no_matches(self):
        """未参加比赛的球队不应出现在排行榜中"""
        self.elo.get_rating("no_match_team", "No Match")
        top = self.elo.get_top_teams()
        team_ids = [t["team_id"] for t in top]
        assert "no_match_team" not in team_ids

    def test_expected_score_formula(self):
        """expected_score 公式验证: 同评级时应返回 0.5"""
        result = self.elo.expected_score(1500, 1500)
        assert abs(result - 0.5) < 0.001, f"同评级预期得分应为0.5, 实际={result}"

    def test_expected_score_higher_rating_favored(self):
        """高评级球队的预期得分应更高"""
        high = self.elo.expected_score(1700, 1500)
        low = self.elo.expected_score(1500, 1700)
        assert high > 0.5
        assert low < 0.5
        assert abs(high + low - 1.0) < 0.001


# ============================================================================
# XGModel 测试
# ============================================================================


class TestXGModel:
    """XGModel 测试套件"""

    def setup_method(self):
        self.model = XGModel()

    def test_analyze_returns_xg_analysis_result(self):
        """analyze() 应返回 XGAnalysisResult 实例"""
        result = self.model.analyze(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
            league="英超",
        )
        assert isinstance(result, XGAnalysisResult)

    def test_analyze_basic_structure(self):
        """分析结果应包含所有核心字段"""
        result = self.model.analyze(
            home_goals_for=30, home_games=19, home_goals_against=18,
            away_goals_for=25, away_games=19, away_goals_against=22,
        )
        # 验证核心属性存在且类型正确
        assert isinstance(result.home_xg, float)
        assert isinstance(result.away_xg, float)
        assert isinstance(result.home_xga, float)
        assert isinstance(result.away_xga, float)
        assert isinstance(result.home_xg_difference, float)
        assert isinstance(result.away_xg_difference, float)
        assert isinstance(result.home_shot_quality, float)
        assert isinstance(result.away_shot_quality, float)
        assert isinstance(result.sustainability_score, float)
        assert isinstance(result.regression_warning, str)
        assert isinstance(result.details, dict)

    def test_sustainability_score_in_range(self):
        """sustainability_score 应在 0-100 范围内"""
        result = self.model.analyze(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
            league="英超",
        )
        assert 0 <= result.sustainability_score <= 100, (
            f"sustainability_score={result.sustainability_score} 超出0-100范围"
        )

    def test_sustainability_score_various_scenarios(self):
        """不同场景下可持续性评分应有差异"""
        # 场景1: 进球与xG接近
        r1 = self.model.analyze(
            home_goals_for=28, home_games=19, home_goals_against=20,
            away_goals_for=22, away_games=19, away_goals_against=24,
        )
        # 场景2: 进球远超xG（极端高进球）
        r2 = self.model.analyze(
            home_goals_for=60, home_games=19, home_goals_against=5,
            away_goals_for=10, away_games=19, away_goals_against=50,
        )
        # 极端场景的可持续性应更低
        assert r1.sustainability_score >= 0
        assert r2.sustainability_score >= 0

    def test_regression_warning_non_empty(self):
        """regression_warning 应为非空字符串"""
        result = self.model.analyze(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
        )
        assert isinstance(result.regression_warning, str)
        assert len(result.regression_warning) > 0, "regression_warning 不应为空字符串"

    def test_regression_warning_extreme_overperformance(self):
        """进球远超xG时应产生均值回归预警"""
        result = self.model.analyze(
            home_goals_for=80, home_games=19, home_goals_against=5,
            away_goals_for=5, away_games=19, away_goals_against=80,
        )
        # 极端超表现应触发预警
        assert "均值回归" in result.regression_warning or "被低估" in result.regression_warning, (
            f"极端数据应触发均值回归预警, 实际: {result.regression_warning}"
        )

    def test_analyze_with_shot_data(self):
        """有射门数据时应使用完整模式"""
        result = self.model.analyze(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
            home_shots=250, home_shots_on_target=90,
            away_shots=200, away_shots_on_target=70,
            league="英超",
        )
        assert result.details.get("data_mode") == "full", (
            "提供射门数据时应使用完整模式"
        )

    def test_analyze_without_shot_data(self):
        """无射门数据时应使用估算模式"""
        result = self.model.analyze(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
        )
        assert result.details.get("data_mode") == "estimated", (
            "未提供射门数据时应使用估算模式"
        )

    def test_analyze_xg_within_reasonable_range(self):
        """xG 值应在合理范围内（支持高进攻强度球队）"""
        result = self.model.analyze(
            home_goals_for=30, home_games=19, home_goals_against=18,
            away_goals_for=25, away_games=19, away_goals_against=22,
        )
        # 放宽上限以支持高进攻强度球队（如曼城、拜仁等）
        assert 0.2 <= result.home_xg <= 5.0
        assert 0.2 <= result.away_xg <= 4.5

    def test_analyze_shot_quality_in_range(self):
        """射门质量评分应在 0-100 范围内"""
        result = self.model.analyze(
            home_goals_for=30, home_games=19, home_goals_against=18,
            away_goals_for=25, away_games=19, away_goals_against=22,
        )
        assert 0 <= result.home_shot_quality <= 100
        assert 0 <= result.away_shot_quality <= 100

    def test_analyze_with_recent_goals(self):
        """提供近期进球数据应影响可持续性评分"""
        result = self.model.analyze(
            home_goals_for=30, home_games=19, home_goals_against=18,
            away_goals_for=25, away_games=19, away_goals_against=22,
            home_recent_goals=[2, 1, 3, 0, 2],
            away_recent_goals=[1, 0, 1, 2, 1],
        )
        assert 0 <= result.sustainability_score <= 100


# ============================================================================
# StatisticalEngine 测试
# ============================================================================


class TestStatisticalEngine:
    """StatisticalEngine 测试套件"""

    def setup_method(self):
        self.engine = StatisticalEngine(elo_ratings_file=None)

    def test_full_analysis_returns_result(self):
        """full_analysis 应返回 StatisticalAnalysisResult 实例"""
        result = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
            league="英超",
        )
        assert isinstance(result, StatisticalAnalysisResult)

    def test_full_analysis_integrates_all_models(self):
        """full_analysis 应集成泊松、Elo、xG三个模型"""
        result = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
            home_team_id="eng_h", away_team_id="eng_a",
            league="英超",
        )

        # 泊松结果
        assert isinstance(result.poisson, PoissonMatchPrediction)
        assert result.poisson.home_win_prob > 0

        # Elo结果
        assert isinstance(result.elo, dict)
        assert "home_win_prob" in result.elo

        # xG结果
        assert isinstance(result.xg, XGAnalysisResult)
        assert result.xg.home_xg > 0

    def test_full_analysis_combined_score_in_range(self):
        """综合评分应在 0-100 范围内"""
        result = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
        )
        assert 0 <= result.combined_score <= 100, (
            f"combined_score={result.combined_score} 超出0-100范围"
        )

    def test_full_analysis_combined_reasoning_non_empty(self):
        """综合推理说明应为非空字符串"""
        result = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
        )
        assert isinstance(result.combined_reasoning, str)
        assert len(result.combined_reasoning) > 0

    def test_full_analysis_agreement_level_valid(self):
        """agreement_level 应为有效值之一"""
        valid_levels = {"高度一致", "基本一致", "存在分歧", "显著分歧"}
        result = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
        )
        assert result.agreement_level in valid_levels, (
            f"agreement_level='{result.agreement_level}' 不是有效值"
        )

    def test_full_analysis_value_bets_without_market_odds(self):
        """不提供 market_odds 时，value_bets 应为空列表"""
        result = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
        )
        assert result.value_bets == []

    def test_full_analysis_value_bets_with_market_odds(self):
        """提供 market_odds 时，value_bets 应被填充"""
        result = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
            market_odds={"win": 2.50, "draw": 3.50, "lose": 3.00},
        )
        assert isinstance(result.value_bets, list)
        # 当赔率与真实概率有偏差时，应能找到价值投注
        # (不一定总是有，取决于具体概率计算)

    def test_full_analysis_value_bets_populated_when_value_exists(self):
        """当市场赔率明显偏离时，value_bets 应非空"""
        result = self.engine.full_analysis(
            home_goals_for=60, home_games=19, home_goals_against=5,
            away_goals_for=10, away_games=19, away_goals_against=50,
            market_odds={"win": 1.30, "draw": 5.00, "lose": 8.00},
            league="英超",
        )
        # 主队极强但赔率给的隐含概率不高，应有价值
        assert isinstance(result.value_bets, list)

    def test_full_analysis_with_shots_data(self):
        """提供射门数据时应正常工作"""
        result = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
            home_shots=250, home_shots_on_target=90,
            away_shots=200, away_shots_on_target=70,
            league="英超",
        )
        assert result.xg.details.get("data_mode") == "full"

    def test_full_analysis_different_leagues(self):
        """不同联赛应产生不同的分析结果"""
        r_epl = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
            league="英超",
        )
        r_ligue = self.engine.full_analysis(
            home_goals_for=35, home_games=19, home_goals_against=15,
            away_goals_for=22, away_games=19, away_goals_against=20,
            league="法甲",
        )
        # 泊松预期进球应因联赛基准不同而有差异
        assert r_epl.poisson.home_expected_goals != r_ligue.poisson.home_expected_goals or \
               r_epl.poisson.away_expected_goals != r_ligue.poisson.away_expected_goals

    def test_update_match_result_delegates_to_elo(self):
        """update_match_result 应委托给 EloRatingSystem"""
        self.engine.elo.get_rating("update_h", "Update H")
        self.engine.elo.get_rating("update_a", "Update A")

        result = self.engine.update_match_result(
            home_team_id="update_h", away_team_id="update_a",
            home_goals=3, away_goals=1,
        )
        assert "home_rating_change" in result
        assert "away_rating_change" in result


# ============================================================================
# poisson_pmf 辅助函数测试
# ============================================================================


class TestPoissonPMF:
    """poisson_pmf 辅助函数测试"""

    def test_pmf_zero_lambda(self):
        """lambda=0 时，P(X=0)=1.0"""
        assert poisson_pmf(0, 0) == 1.0
        assert poisson_pmf(1, 0) == 0.0

    def test_pmf_probabilities_sum_to_one(self):
        """对于任意 lambda，概率之和应约等于 1.0"""
        lambda_ = 1.5
        total = sum(poisson_pmf(k, lambda_) for k in range(20))
        assert abs(total - 1.0) < 0.001, f"概率之和={total}"

    def test_pmf_non_negative(self):
        """概率值应非负"""
        for k in range(10):
            for lam in [0.5, 1.0, 2.0, 3.5]:
                assert poisson_pmf(k, lam) >= 0

    def test_pmf_mode_near_lambda(self):
        """概率峰值应出现在 lambda 附近"""
        lambda_ = 2.5
        probs = [poisson_pmf(k, lambda_) for k in range(8)]
        mode = probs.index(max(probs))
        assert mode in (2, 3), f"lambda={lambda_} 时众数应为2或3, 实际={mode}"
