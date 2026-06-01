# -*- coding: utf-8 -*-
"""
规则引擎单元测试

测试RulesEngine的核心功能
"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from lottery_mcp.tools.rules_tools import RulesEngine, get_rules_engine


class TestRulesEngine:
    """规则引擎测试类"""

    @pytest.fixture
    def engine(self):
        """创建规则引擎实例"""
        return get_rules_engine()

    def test_get_max_matches_jingcai(self, engine):
        """测试竞彩最大串关场次"""
        limits = engine._get_parlay_limits("竞彩足球")
        assert limits["max_matches"] == 8

    def test_get_max_matches_beidan(self, engine):
        """测试北单最大串关场次"""
        limits = engine._get_parlay_limits("北京单场")
        assert limits["max_matches"] == 15

    def test_get_multiplier_range(self, engine):
        """测试倍数范围"""
        jingcai_limits = engine._get_parlay_limits("竞彩足球")
        assert jingcai_limits["min_multiplier"] == 2
        assert jingcai_limits["max_multiplier"] == 50

        beidan_limits = engine._get_parlay_limits("北京单场")
        assert beidan_limits["min_multiplier"] == 2
        assert beidan_limits["max_multiplier"] == 99

    def test_get_return_rate(self, engine):
        """测试返奖率"""
        assert engine.get_return_rate("竞彩足球") == 0.70
        assert engine.get_return_rate("北京单场") == 0.65
        assert engine.get_return_rate("传统足彩") == 0.65

    def test_calculate_bonus_jingcai(self, engine):
        """测试竞彩奖金计算"""
        result = engine.calculate_bonus(
            bets=[{"match_id": "m1", "play_type": "SPF", "selection": "胜", "odds": 2.0, "stake": 2.0},
                   {"match_id": "m2", "play_type": "SPF", "selection": "胜", "odds": 1.5, "stake": 2.0}],
            parlay_type="2x1",
            lottery_type="竞彩足球",
            multiplier=2,
        )
        # 竞彩过关: 2元 x SP连乘 x 倍数 = 2 * 2.0 * 1.5 * 2 = 12.0
        assert result["status"] == "simulation"
        assert result["gross_bonus"] == 12.0

    def test_calculate_bonus_beidan(self, engine):
        """测试北单奖金计算"""
        result = engine.calculate_bonus(
            bets=[{"match_id": "m1", "play_type": "SPF", "selection": "胜", "odds": 2.0, "stake": 2.0},
                   {"match_id": "m2", "play_type": "SPF", "selection": "胜", "odds": 1.5, "stake": 2.0}],
            parlay_type="2x1",
            lottery_type="北京单场",
            multiplier=1,
        )
        # 北单: 2元 x SP连乘 x 65% x 倍数 = 2 * 2.0 * 1.5 * 0.65 * 1 = 3.9
        assert result["status"] == "simulation"
        assert abs(result["gross_bonus"] - 3.9) < 0.01

    def test_get_single_ticket_limit(self, engine):
        """测试单票限额"""
        jingcai_limits = engine._get_parlay_limits("竞彩足球")
        assert jingcai_limits["single_ticket_limit"] == 6000

        beidan_limits = engine._get_parlay_limits("北京单场")
        assert beidan_limits["single_ticket_limit"] == 20000


class TestPlayValidation:
    """玩法选项验证测试类"""

    def test_validate_play_selection_spf_valid(self):
        """测试胜平负合法选项"""
        from lottery_mcp.rules.engine import validate_play_selection

        result = validate_play_selection("SPF", "胜")
        assert result["valid"] is True

        result = validate_play_selection("SPF", "平")
        assert result["valid"] is True

        result = validate_play_selection("SPF", "负")
        assert result["valid"] is True

    def test_validate_play_selection_spf_invalid(self):
        """测试胜平负非法选项"""
        from lottery_mcp.rules.engine import validate_play_selection

        result = validate_play_selection("SPF", "无效")
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_validate_play_selection_rqspf_no_handicap(self):
        """测试让球胜平负未提供让球数"""
        from lottery_mcp.rules.engine import validate_play_selection

        result = validate_play_selection("RQSPF", "胜")
        assert result["valid"] is False
        assert any("让球数" in e for e in result["errors"])

    def test_validate_play_selection_rqspf_with_handicap(self):
        """测试让球胜平负提供让球数"""
        from lottery_mcp.rules.engine import validate_play_selection

        result = validate_play_selection("RQSPF", "胜", handicap=-1)
        assert result["valid"] is True

    def test_validate_play_selection_bf_valid(self):
        """测试比分合法选项"""
        from lottery_mcp.rules.engine import validate_play_selection

        result = validate_play_selection("BF", "2:1")
        assert result["valid"] is True

        result = validate_play_selection("BF", "胜其他")
        assert result["valid"] is True

    def test_validate_play_selection_bf_invalid(self):
        """测试比分非法选项"""
        from lottery_mcp.rules.engine import validate_play_selection

        result = validate_play_selection("BF", "10:0")
        assert result["valid"] is False

    def test_validate_play_selection_zjq_valid(self):
        """测试总进球合法选项"""
        from lottery_mcp.rules.engine import validate_play_selection

        result = validate_play_selection("ZJQ", "3")
        assert result["valid"] is True

        result = validate_play_selection("ZJQ", "7+")
        assert result["valid"] is True

    def test_validate_play_selection_bqc_valid(self):
        """测试半全场合法选项"""
        from lottery_mcp.rules.engine import validate_play_selection

        result = validate_play_selection("BQC", "胜-胜")
        assert result["valid"] is True

    def test_validate_play_selection_unknown_type(self):
        """测试未知玩法类型"""
        from lottery_mcp.rules.engine import validate_play_selection

        result = validate_play_selection("UNKNOWN", "胜")
        assert result["valid"] is False
        assert any("未知" in e for e in result["errors"])


class TestMixedParlayCompatibility:
    """混合过关兼容性验证测试"""

    def test_valid_mixed_parlay(self):
        """测试合法的混合过关"""
        from lottery_mcp.rules.engine import validate_mixed_parlay_compatibility

        result = validate_mixed_parlay_compatibility([
            {"match_id": "m1", "play_type": "SPF", "selection": "胜"},
            {"match_id": "m2", "play_type": "BF", "selection": "2:1"},
        ])
        assert result["valid"] is True

    def test_duplicate_match_in_parlay(self):
        """测试同场比赛重复出现"""
        from lottery_mcp.rules.engine import validate_mixed_parlay_compatibility

        result = validate_mixed_parlay_compatibility([
            {"match_id": "m1", "play_type": "SPF", "selection": "胜"},
            {"match_id": "m1", "play_type": "BF", "selection": "2:1"},
        ])
        assert result["valid"] is False
        assert any("多次" in e for e in result["errors"])

    def test_bucket_principle_violation(self):
        """测试木桶原则违规"""
        from lottery_mcp.rules.engine import validate_mixed_parlay_compatibility

        # 比分最多4关，所以混合过关包含比分时最多4场
        bets = [
            {"match_id": f"m{i}", "play_type": "BF", "selection": "2:1"}
            for i in range(5)
        ]
        result = validate_mixed_parlay_compatibility(bets)
        assert result["valid"] is False
        assert any("木桶" in e for e in result["errors"])


class TestRulesQuery:
    """规则查询测试"""

    @pytest.fixture
    def engine(self):
        """创建规则引擎实例"""
        return get_rules_engine()

    def test_query_limits(self, engine):
        """测试限额查询"""
        result = engine.query_rules("limits", "竞彩足球")
        assert result["rule_type"] == "limits"
        assert "single_ticket_limit" in result
        assert "multiplier_range" in result

    def test_query_parlay(self, engine):
        """测试串关规则查询"""
        result = engine.query_rules("parlay", "竞彩足球")
        assert result["rule_type"] == "parlay"
        assert "max_matches" in result
        assert "supported_types" in result

    def test_query_bonus(self, engine):
        """测试奖金规则查询"""
        result = engine.query_rules("bonus", "竞彩足球")
        assert result["rule_type"] == "bonus"
        assert result["return_rate"] == 0.70
        assert "tax_rate" in result
