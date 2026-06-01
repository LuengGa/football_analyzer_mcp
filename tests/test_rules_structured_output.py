# -*- coding: utf-8 -*-
"""
结构化输出测试 (P1-4)

测试 mcp_server.output_schemas 中的结构化输出模型：
- ValidateBetOutput: 单注验证输出
- BonusCalculationOutput: 奖金计算输出
- QueryRulesOutput: 规则查询输出
- OUTPUT_SCHEMAS: 工具到输出模型的映射字典
"""

import pytest
import sys
import importlib
from pathlib import Path

# 直接导入子模块，避免触发 mcp_server/__init__.py 的完整导入链
sys.path.insert(0, str(Path(__file__).parent.parent))

output_schemas = importlib.import_module("mcp_server.output_schemas")

ValidateBetOutput = output_schemas.ValidateBetOutput
BonusCalculationOutput = output_schemas.BonusCalculationOutput
QueryRulesOutput = output_schemas.QueryRulesOutput
OUTPUT_SCHEMAS = output_schemas.OUTPUT_SCHEMAS
BetSummary = output_schemas.BetSummary
ValidateParlayOutput = output_schemas.ValidateParlayOutput
MixedParlayDetail = output_schemas.MixedParlayDetail
LimitsRuleOutput = output_schemas.LimitsRuleOutput
ParlayRuleOutput = output_schemas.ParlayRuleOutput
BonusRuleOutput = output_schemas.BonusRuleOutput
MixedParlayRuleOutput = output_schemas.MixedParlayRuleOutput
PlayRuleOutput = output_schemas.PlayRuleOutput
QueryMixedParlayRulesOutput = output_schemas.QueryMixedParlayRulesOutput
PlayRecommendation = output_schemas.PlayRecommendation
PlayAnalysisOutput = output_schemas.PlayAnalysisOutput
MatchPlaysAnalysisOutput = output_schemas.MatchPlaysAnalysisOutput
BaseResponse = output_schemas.BaseResponse
ErrorResponse = output_schemas.ErrorResponse


class TestValidateBetOutputModel:
    """测试 ValidateBetOutput 模型"""

    def test_validate_bet_output_model(self):
        """验证 ValidateBetOutput 模型可以正确实例化"""
        output = ValidateBetOutput(
            valid=True,
            errors=[],
            warnings=[],
            bet_summary=BetSummary(
                match_id="match_001",
                play_type="SPF",
                play_type_cn="胜平负",
                selection="主胜",
                odds=2.15,
                stake=100.0,
                expected_bonus=215.0,
                lottery_type="竞彩足球",
            ),
        )
        assert output.valid is True
        assert output.errors == []
        assert output.bet_summary.match_id == "match_001"
        assert output.bet_summary.odds == 2.15

    def test_validate_bet_output_with_errors(self):
        """验证 ValidateBetOutput 可以包含错误信息"""
        output = ValidateBetOutput(
            valid=False,
            errors=["投注金额超过限额"],
            warnings=["赔率偏高"],
            bet_summary=BetSummary(
                match_id="match_002",
                play_type="RQSPF",
                play_type_cn="让球胜平负",
                selection="让球主胜",
                odds=1.85,
                stake=20000.0,
                expected_bonus=37000.0,
                lottery_type="竞彩足球",
            ),
        )
        assert output.valid is False
        assert len(output.errors) == 1
        assert len(output.warnings) == 1

    def test_validate_bet_output_defaults(self):
        """验证 ValidateBetOutput 的默认值"""
        output = ValidateBetOutput(
            valid=True,
            bet_summary=BetSummary(
                match_id="m1",
                play_type="SPF",
                play_type_cn="胜平负",
                selection="主胜",
                odds=2.0,
                stake=100.0,
                expected_bonus=200.0,
                lottery_type="竞彩足球",
            ),
        )
        assert output.errors == []
        assert output.warnings == []


class TestBonusCalculationOutputModel:
    """测试 BonusCalculationOutput 模型"""

    def test_calculate_bonus_output_model(self):
        """验证 BonusCalculationOutput 模型可以正确实例化"""
        output = BonusCalculationOutput(
            status="won",
            lottery_type="竞彩足球",
            match_count=3,
            parlay_type="3x1",
            multiplier=1,
            total_stake=6.0,
            total_bets=1,
            total_odds=10.5,
            single_bonus=63.0,
            gross_bonus=63.0,
            per_bet_bonus=63.0,
            tax=0.0,
            net_bonus=63.0,
            profit=57.0,
            capped=False,
            bonus_formula="单注奖金 = SP连乘 x 倍数",
            return_rate=0.70,
        )
        assert output.status == "won"
        assert output.lottery_type == "竞彩足球"
        assert output.match_count == 3
        assert output.net_bonus == 63.0

    def test_calculate_bonus_output_simulation(self):
        """验证 BonusCalculationOutput 模拟模式"""
        output = BonusCalculationOutput(
            status="simulation",
            message="无比赛结果，仅计算理论奖金",
        )
        assert output.status == "simulation"
        assert output.message == "无比赛结果，仅计算理论奖金"

    def test_calculate_bonus_output_lost(self):
        """验证 BonusCalculationOutput 未中奖模式"""
        output = BonusCalculationOutput(
            status="lost",
            bonus=0.0,
            profit=-6.0,
        )
        assert output.status == "lost"
        assert output.bonus == 0.0
        assert output.profit == -6.0

    def test_calculate_bonus_output_error(self):
        """验证 BonusCalculationOutput 错误模式"""
        output = BonusCalculationOutput(
            status="error",
            message="倍数超限",
        )
        assert output.status == "error"

    def test_calculate_bonus_output_defaults(self):
        """验证 BonusCalculationOutput 的默认值"""
        output = BonusCalculationOutput(status="simulation")
        assert output.status == "simulation"
        assert output.lottery_type == ""
        assert output.match_count == 0
        assert output.multiplier == 1
        assert output.total_stake == 0.0
        assert output.capped is False
        assert output.cap_amount is None


class TestQueryRulesOutputModel:
    """测试 QueryRulesOutput 模型"""

    def test_query_rules_output_model(self):
        """验证 QueryRulesOutput 模型可以正确实例化"""
        output = QueryRulesOutput(
            rule_type="limits",
            lottery_type="竞彩足球",
            play_limits={"SPF": {"min_stake": 2.0, "max_stake": 10000.0}},
            parlay_limits={"max_matches": 8},
            single_ticket_limit=100000,
            multiplier_range=[1, 99],
        )
        assert output.rule_type == "limits"
        assert output.lottery_type == "竞彩足球"
        assert "SPF" in output.play_limits

    def test_query_rules_output_parlay(self):
        """验证 QueryRulesOutput 串关规则类型"""
        output = QueryRulesOutput(
            rule_type="parlay",
            lottery_type="竞彩足球",
            max_matches=8,
            min_matches=2,
            allowed_types=["2x1", "3x1", "4x1"],
        )
        assert output.rule_type == "parlay"
        assert output.max_matches == 8
        assert output.min_matches == 2

    def test_query_rules_output_bonus(self):
        """验证 QueryRulesOutput 奖金规则类型"""
        output = QueryRulesOutput(
            rule_type="bonus",
            lottery_type="竞彩足球",
            return_rate=0.70,
            tax_rate=0.20,
            tax_threshold=10000.0,
            bonus_cap_by_legs={2: 500000, 3: 1000000},
        )
        assert output.rule_type == "bonus"
        assert output.return_rate == 0.70
        assert output.tax_threshold == 10000.0

    def test_query_rules_output_defaults(self):
        """验证 QueryRulesOutput 的默认值"""
        output = QueryRulesOutput(rule_type="play", lottery_type="竞彩足球")
        assert output.play_limits is None
        assert output.parlay_limits is None
        assert output.error is None

    def test_query_rules_output_with_error(self):
        """验证 QueryRulesOutput 错误状态"""
        output = QueryRulesOutput(
            rule_type="unknown",
            error="不支持的规则类型",
        )
        assert output.error == "不支持的规则类型"


class TestOutputSchemasComplete:
    """测试 OUTPUT_SCHEMAS 字典完整性"""

    def test_output_schemas_complete(self):
        """验证 OUTPUT_SCHEMAS 字典包含所有预期的工具映射"""
        expected_keys = [
            "lottery_validate_bet",
            "lottery_validate_parlay",
            "lottery_validate_mixed_parlay",
            "lottery_calculate_bonus",
            "lottery_query_rules",
            "lottery_query_rules_limits",
            "lottery_query_rules_parlay",
            "lottery_query_rules_bonus",
            "lottery_query_rules_mixed_parlay",
            "lottery_query_rules_play",
            "lottery_query_mixed_parlay_rules",
            "lottery_analyze_match_plays",
        ]
        for key in expected_keys:
            assert key in OUTPUT_SCHEMAS, f"OUTPUT_SCHEMAS 缺少工具映射: {key}"

    def test_output_schemas_values_are_models(self):
        """验证 OUTPUT_SCHEMAS 中的值都是 Pydantic BaseModel 子类"""
        from pydantic import BaseModel

        for key, model_cls in OUTPUT_SCHEMAS.items():
            assert issubclass(model_cls, BaseModel), (
                f"OUTPUT_SCHEMAS['{key}'] 不是 BaseModel 子类"
            )

    def test_output_schemas_specific_mappings(self):
        """验证特定工具到模型的映射正确"""
        assert OUTPUT_SCHEMAS["lottery_validate_bet"] is ValidateBetOutput
        assert OUTPUT_SCHEMAS["lottery_calculate_bonus"] is BonusCalculationOutput
        assert OUTPUT_SCHEMAS["lottery_query_rules"] is QueryRulesOutput
        assert OUTPUT_SCHEMAS["lottery_validate_parlay"] is ValidateParlayOutput
