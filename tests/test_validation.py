# -*- coding: utf-8 -*-
"""
投注验证工具测试

测试投注验证和串关验证功能
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lottery_mcp.tools.rules_tools import RulesEngine, get_rules_engine


class TestBetValidation:
    """投注验证测试类"""

    @pytest.fixture
    def engine(self):
        """创建规则引擎实例"""
        return get_rules_engine()

    def test_valid_bet_jingcai(self, engine):
        """测试有效的竞彩投注"""
        result = engine.validate_bet({
            "match_id": "match_001",
            "play_type": "SPF",
            "selection": "胜",
            "odds": 2.0,
            "stake": 100.0,
            "lottery_type": "竞彩足球",
        })

        assert result["valid"] == True
        assert result["bet_summary"]["lottery_type"] == "竞彩足球"
        assert result["bet_summary"]["stake"] == 100.0

    def test_invalid_selection(self, engine):
        """测试无效的投注选项"""
        result = engine.validate_bet({
            "match_id": "match_001",
            "play_type": "SPF",
            "selection": "无效选项",
            "odds": 2.0,
            "stake": 100.0,
            "lottery_type": "竞彩足球",
        })

        assert result["valid"] == False
        assert len(result["errors"]) > 0

    def test_invalid_lottery_type(self, engine):
        """测试无效彩种"""
        result = engine.validate_bet({
            "match_id": "match_001",
            "play_type": "SPF",
            "selection": "胜",
            "odds": 2.0,
            "stake": 100.0,
            "lottery_type": "无效彩种",
        })

        assert result["valid"] == False
        assert len(result["errors"]) > 0

    def test_invalid_odds(self, engine):
        """测试无效赔率"""
        result = engine.validate_bet({
            "match_id": "match_001",
            "play_type": "SPF",
            "selection": "胜",
            "odds": 0.5,
            "stake": 100.0,
            "lottery_type": "竞彩足球",
        })

        assert result["valid"] == False
        assert len(result["errors"]) > 0


class TestParlayValidation:
    """串关验证测试类"""

    @pytest.fixture
    def engine(self):
        """创建规则引擎实例"""
        return get_rules_engine()

    def test_valid_parlay(self, engine):
        """测试有效的串关"""
        result = engine.validate_parlay({
            "bets": [
                {"match_id": "m1", "play_type": "SPF", "selection": "胜", "odds": 2.0, "stake": 2.0},
                {"match_id": "m2", "play_type": "SPF", "selection": "平", "odds": 3.0, "stake": 2.0},
                {"match_id": "m3", "play_type": "SPF", "selection": "负", "odds": 2.5, "stake": 2.0},
            ],
            "parlay_type": "3x1",
            "total_stake": 6.0,
            "lottery_type": "竞彩足球",
        })

        assert result["valid"] == True
        assert result["parlay_summary"]["match_count"] == 3

    def test_exceed_max_legs(self, engine):
        """测试超过最大过关数"""
        bets = [
            {"match_id": f"m{i}", "play_type": "SPF", "selection": "胜", "odds": 2.0, "stake": 2.0}
            for i in range(10)
        ]
        result = engine.validate_parlay({
            "bets": bets,
            "parlay_type": "10x1",
            "total_stake": 20.0,
            "lottery_type": "竞彩足球",
        })

        assert result["valid"] == False
        assert len(result["errors"]) > 0

    def test_exceed_single_ticket_limit(self, engine):
        """测试超过单票限额"""
        result = engine.validate_parlay({
            "bets": [
                {"match_id": "m1", "play_type": "SPF", "selection": "胜", "odds": 2.0, "stake": 2.0},
                {"match_id": "m2", "play_type": "SPF", "selection": "平", "odds": 3.0, "stake": 2.0},
            ],
            "parlay_type": "2x1",
            "total_stake": 10000.0,
            "lottery_type": "竞彩足球",
        })

        assert result["valid"] == False
        assert any("单票" in e for e in result["errors"])
