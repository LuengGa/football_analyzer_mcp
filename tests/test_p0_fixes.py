# -*- coding: utf-8 -*-
"""
P0 修复专项测试

测试竞彩足球 P0 级别问题的修复：
- P0-1: 比分(BF)分析包含"胜其他/平其他/负其他"
- P0-2: 总进球(ZJQ)使用官方8选项格式
- P0-3: 让球胜平负(RQSPF)让球数校验
- P0-4: 串关max_length放宽至15（运行时按彩种校验）
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lottery_mcp.models import ValidateBetInput, ValidateParlayInput, ValidateMixedParlayInput
from lottery_mcp.tools.rules_tools import RulesEngine


class TestP0_1_BF_Analysis:
    """P0-1: 比分分析包含胜其他/平其他/负其他"""

    def test_bf_has_other_options(self):
        """比分分析应包含胜其他/平其他/负其他选项"""
        from lottery_mcp.analysis.play_analysis import PlayAnalyzer

        analyzer = PlayAnalyzer()

        # 构造泊松结果（包含高比分以触发"其他"选项）
        poisson_result = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.2,
            "score_probabilities": {
                "1:0": 0.10, "0:1": 0.08, "1:1": 0.09,
                "2:1": 0.08, "2:0": 0.07, "0:2": 0.06,
                "2:2": 0.04, "3:1": 0.04, "3:0": 0.03,
                "1:2": 0.05, "0:0": 0.07, "3:2": 0.02,
                "4:0": 0.01, "4:1": 0.01, "0:3": 0.02,
                "8:0": 0.02, "0:8": 0.015,  # 超出范围，应归入"其他"
            },
            "win_prob": 0.45,
            "draw_prob": 0.25,
            "lose_prob": 0.30,
        }

        result = analyzer.analyze_bf(poisson_result, {})

        # 验证至少有一个"其他"选项出现在概率中
        has_other = any(
            key in result.probabilities
            for key in ["胜其他", "平其他", "负其他"]
        )
        assert has_other, f"比分分析应包含'其他'选项，当前概率键: {list(result.probabilities.keys())}"

    def test_bf_notes_contain_category_summary(self):
        """比分分析notes应包含主胜/平/客胜概率合计"""
        from lottery_mcp.analysis.play_analysis import PlayAnalyzer

        analyzer = PlayAnalyzer()
        poisson_result = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.2,
            "score_probabilities": {
                "1:0": 0.10, "0:1": 0.08, "1:1": 0.09,
                "2:1": 0.08, "2:0": 0.07, "0:2": 0.06,
                "2:2": 0.04, "3:1": 0.04, "3:0": 0.03,
                "1:2": 0.05, "0:0": 0.07, "3:2": 0.02,
            },
            "win_prob": 0.45,
            "draw_prob": 0.25,
            "lose_prob": 0.30,
        }

        result = analyzer.analyze_bf(poisson_result, {})

        # 验证notes包含分类统计
        notes_text = " ".join(result.analysis_notes)
        assert "主胜概率合计" in notes_text
        assert "平局概率合计" in notes_text
        assert "客胜概率合计" in notes_text


class TestP0_2_ZJQ_OfficialFormat:
    """P0-2: 总进球使用官方8选项格式"""

    OFFICIAL_OPTIONS = ["0", "1", "2", "3", "4", "5", "6", "7+"]

    def test_zjq_output_uses_official_options(self):
        """总进球分析应使用官方8选项格式"""
        from lottery_mcp.analysis.play_analysis import PlayAnalyzer

        analyzer = PlayAnalyzer()
        poisson_result = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.2,
            "win_prob": 0.45,
            "draw_prob": 0.25,
            "lose_prob": 0.30,
        }

        result = analyzer.analyze_zjq(poisson_result, {})

        # 验证所有概率键都是官方选项
        for key in result.probabilities:
            assert key in self.OFFICIAL_OPTIONS, (
                f"总进球选项 '{key}' 不是官方格式，官方选项: {self.OFFICIAL_OPTIONS}"
            )

    def test_zjq_has_all_8_options(self):
        """总进球分析应覆盖全部8个官方选项"""
        from lottery_mcp.analysis.play_analysis import PlayAnalyzer

        analyzer = PlayAnalyzer()
        poisson_result = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.2,
        }

        result = analyzer.analyze_zjq(poisson_result, {})

        for option in self.OFFICIAL_OPTIONS:
            assert option in result.probabilities, f"缺少官方选项: {option}"

    def test_zjq_probabilities_sum_to_one(self):
        """总进球8个选项概率之和应接近1.0"""
        from lottery_mcp.analysis.play_analysis import PlayAnalyzer

        analyzer = PlayAnalyzer()
        poisson_result = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.2,
        }

        result = analyzer.analyze_zjq(poisson_result, {})

        total = sum(result.probabilities.values())
        assert abs(total - 1.0) < 0.001, f"概率之和应为1.0，实际: {total}"

    def test_zjq_no_interval_format(self):
        """总进球分析不应包含旧的区间格式"""
        from lottery_mcp.analysis.play_analysis import PlayAnalyzer

        analyzer = PlayAnalyzer()
        poisson_result = {
            "home_expected_goals": 1.5,
            "away_expected_goals": 1.2,
        }

        result = analyzer.analyze_zjq(poisson_result, {})

        # 不应有旧的区间格式
        for key in result.probabilities:
            assert "球" not in key, f"不应包含旧格式'{key}'，应使用官方选项格式"
            assert "-" not in key, f"不应包含区间格式'{key}'，应使用官方选项格式"


class TestP0_3_RQSPF_Handicap_Validation:
    """P0-3: 让球胜平负让球数校验"""

    @pytest.fixture
    def engine(self):
        return RulesEngine()

    def test_rqspf_without_handicap_returns_error(self, engine):
        """RQSPF玩法不提供让球数应报错"""
        from lottery_mcp.models import ValidateBetInput

        bet = ValidateBetInput(
            match_id="test_001",
            play_type="RQSPF",
            selection="让球主胜",
            odds=2.10,
            stake=100,
            lottery_type="竞彩足球",
        )

        result = engine.validate_bet(bet)
        assert not result["valid"]
        assert any("handicap" in e or "让球数" in e for e in result["errors"])

    def test_rqspf_with_integer_handicap_passes(self, engine):
        """竞彩RQSPF提供整数让球数应通过"""
        from lottery_mcp.models import ValidateBetInput

        bet = ValidateBetInput(
            match_id="test_001",
            play_type="RQSPF",
            selection="让球主胜",
            odds=2.10,
            stake=100,
            lottery_type="竞彩足球",
            handicap=-1,
        )

        result = engine.validate_bet(bet)
        assert result["valid"], f"应通过验证，错误: {result['errors']}"

    def test_rqspf_with_decimal_handicap_fails_for_jingcai(self, engine):
        """竞彩RQSPF提供小数让球数应报错"""
        from lottery_mcp.models import ValidateBetInput

        bet = ValidateBetInput(
            match_id="test_001",
            play_type="RQSPF",
            selection="让球主胜",
            odds=2.10,
            stake=100,
            lottery_type="竞彩足球",
            handicap=-1.5,
        )

        result = engine.validate_bet(bet)
        assert not result["valid"]
        assert any("整数" in e for e in result["errors"])

    def test_rqspf_with_decimal_handicap_passes_for_beidan(self, engine):
        """北单RQSPF提供小数让球数应通过"""
        from lottery_mcp.models import ValidateBetInput

        bet = ValidateBetInput(
            match_id="test_001",
            play_type="RQSPF",
            selection="让球主胜",
            odds=2.10,
            stake=100,
            lottery_type="北京单场",
            handicap=-1.5,
        )

        result = engine.validate_bet(bet)
        assert result["valid"], f"应通过验证，错误: {result['errors']}"

    def test_rqspf_zero_handicap_warning(self, engine):
        """让球数为0应产生警告"""
        from lottery_mcp.models import ValidateBetInput

        bet = ValidateBetInput(
            match_id="test_001",
            play_type="RQSPF",
            selection="让球主胜",
            odds=2.10,
            stake=100,
            lottery_type="竞彩足球",
            handicap=0,
        )

        result = engine.validate_bet(bet)
        assert result["valid"]
        assert any("等同" in w for w in result["warnings"])


class TestP0_4_ParlayMaxLength:
    """P0-4: 串关max_length放宽至15"""

    def test_parlay_model_accepts_15_bets(self):
        """ValidateParlayInput应接受15场投注"""
        bets = [
            ValidateBetInput(
                match_id=f"match_{i}",
                play_type="SPF",
                selection="主胜",
                odds=2.0,
                stake=2,
                lottery_type="北京单场",
            )
            for i in range(15)
        ]

        parlay = ValidateParlayInput(
            bets=bets,
            parlay_type="15x1",
            total_stake=100,
            lottery_type="北京单场",
        )
        assert len(parlay.bets) == 15

    def test_parlay_model_rejects_16_bets(self):
        """ValidateParlayInput应拒绝超过15场"""
        with pytest.raises(Exception):
            bets = [
                ValidateBetInput(
                    match_id=f"match_{i}",
                    play_type="SPF",
                    selection="主胜",
                    odds=2.0,
                    stake=2,
                    lottery_type="北京单场",
                )
                for i in range(16)
            ]
            ValidateParlayInput(
                bets=bets,
                parlay_type="16x1",
                total_stake=100,
                lottery_type="北京单场",
            )

    def test_mixed_parlay_model_accepts_15_bets(self):
        """ValidateMixedParlayInput应接受15场投注"""
        bets = [
            ValidateBetInput(
                match_id=f"match_{i}",
                play_type="SPF",
                selection="主胜",
                odds=2.0,
                stake=2,
                lottery_type="北京单场",
            )
            for i in range(15)
        ]

        parlay = ValidateMixedParlayInput(
            bets=bets,
            parlay_type="15x1",
            total_stake=100,
            lottery_type="北京单场",
        )
        assert len(parlay.bets) == 15

    def test_jingcai_9_bets_runtime_validation(self):
        """竞彩足球9场应在运行时被拒绝（max_matches=8）"""
        engine = RulesEngine()
        bets = [
            ValidateBetInput(
                match_id=f"match_{i}",
                play_type="SPF",
                selection="主胜",
                odds=2.0,
                stake=2,
                lottery_type="竞彩足球",
            )
            for i in range(9)
        ]

        parlay = ValidateParlayInput(
            bets=bets,
            parlay_type="9x1",
            total_stake=100,
            lottery_type="竞彩足球",
        )

        result = engine.validate_parlay(parlay)
        assert not result["valid"]
        assert any("8" in e for e in result["errors"])

    def test_beidan_15_bets_runtime_validation(self):
        """北京单场15场应在运行时通过"""
        engine = RulesEngine()
        bets = [
            ValidateBetInput(
                match_id=f"match_{i}",
                play_type="SPF",
                selection="主胜",
                odds=2.0,
                stake=2,
                lottery_type="北京单场",
            )
            for i in range(15)
        ]

        parlay = ValidateParlayInput(
            bets=bets,
            parlay_type="15x1",
            total_stake=100,
            lottery_type="北京单场",
        )

        result = engine.validate_parlay(parlay)
        # 可能因为串关类型不在允许列表中而失败，但不应因为场次数量失败
        match_count_errors = [e for e in result["errors"] if "最多支持" in e or "至少需要" in e]
        assert len(match_count_errors) == 0, f"15场北单不应报场次数量错误: {match_count_errors}"
