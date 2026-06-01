# -*- coding: utf-8 -*-
"""
分页功能测试 (P1-7)

测试 mcp_server.models 中各工具 Input 模型的分页参数：
- GetBettingStatsInput: 投注统计分页
- GetDailyRecommendationsInput: 每日推荐分页
- GenerateBettingSlipsInput: 投注单生成分页
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lottery_mcp.models import (
    GetBettingStatsInput,
    GetDailyRecommendationsInput,
    GenerateBettingSlipsInput,
)


class TestBettingStatsPagination:
    """测试投注统计分页参数"""

    def test_betting_stats_pagination(self):
        """验证分页参数存在于 GetBettingStatsInput 模型中"""
        # 验证模型可以接受 limit 和 offset 参数
        params = GetBettingStatsInput(
            period="all",
            limit=10,
            offset=0,
        )
        assert params.limit == 10
        assert params.offset == 0

    def test_betting_stats_pagination_defaults(self):
        """验证分页参数的默认值"""
        params = GetBettingStatsInput()
        assert params.limit == 20
        assert params.offset == 0

    def test_betting_stats_pagination_custom(self):
        """验证自定义分页参数"""
        params = GetBettingStatsInput(limit=50, offset=100)
        assert params.limit == 50
        assert params.offset == 100

    def test_betting_stats_pagination_validation(self):
        """验证分页参数的边界约束"""
        # limit 最小值
        params = GetBettingStatsInput(limit=1)
        assert params.limit == 1

        # offset 最小值
        params = GetBettingStatsInput(offset=0)
        assert params.offset == 0

    def test_betting_stats_period_options(self):
        """验证统计周期参数"""
        for period in ["all", "today", "week"]:
            params = GetBettingStatsInput(period=period)
            assert params.period == period


class TestDailyRecommendationsPagination:
    """测试每日推荐分页参数"""

    def test_daily_recommendations_pagination(self):
        """验证分页参数存在于 GetDailyRecommendationsInput 模型中"""
        params = GetDailyRecommendationsInput(
            count=5,
            strategy="balanced",
            limit=10,
            offset=0,
        )
        assert params.limit == 10
        assert params.offset == 0

    def test_daily_recommendations_pagination_defaults(self):
        """验证分页参数的默认值"""
        params = GetDailyRecommendationsInput()
        assert params.limit == 10
        assert params.offset == 0

    def test_daily_recommendations_pagination_custom(self):
        """验证自定义分页参数"""
        params = GetDailyRecommendationsInput(limit=20, offset=50)
        assert params.limit == 20
        assert params.offset == 50

    def test_daily_recommendations_pagination_with_all_params(self):
        """验证分页参数与其他参数共存"""
        params = GetDailyRecommendationsInput(
            count=3,
            strategy="conservative",
            min_confidence=70.0,
            lottery_type="竞彩足球",
            limit=5,
            offset=10,
        )
        assert params.count == 3
        assert params.strategy == "conservative"
        assert params.min_confidence == 70.0
        assert params.limit == 5
        assert params.offset == 10


class TestGenerateBettingSlipsPagination:
    """测试投注单生成分页参数"""

    def test_generate_betting_slips_pagination(self):
        """验证分页参数存在于 GenerateBettingSlipsInput 模型中"""
        params = GenerateBettingSlipsInput(
            match_ids=["match_001", "match_002"],
            strategy="single",
            limit=10,
            offset=0,
        )
        assert params.limit == 10
        assert params.offset == 0

    def test_generate_betting_slips_pagination_defaults(self):
        """验证分页参数的默认值"""
        params = GenerateBettingSlipsInput(
            match_ids=["match_001"],
        )
        assert params.limit == 10
        assert params.offset == 0

    def test_generate_betting_slips_pagination_custom(self):
        """验证自定义分页参数"""
        params = GenerateBettingSlipsInput(
            match_ids=["match_001", "match_002", "match_003"],
            limit=2,
            offset=1,
        )
        assert params.limit == 2
        assert params.offset == 1

    def test_generate_betting_slips_pagination_with_auto_parlay(self):
        """验证 auto_parlay 模式下分页参数可用"""
        params = GenerateBettingSlipsInput(
            match_ids=["match_001", "match_002", "match_003", "match_004"],
            strategy="auto_parlay",
            parlay_type="3x1",
            max_matches=4,
            min_confidence=60.0,
            risk_level="balanced",
            limit=5,
            offset=0,
        )
        assert params.strategy == "auto_parlay"
        assert params.limit == 5
        assert params.offset == 0
