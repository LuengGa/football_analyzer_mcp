"""
MCP Server Output Schemas - 工具输出结构定义

定义各工具的结构化输出格式，供 LLM 理解返回数据结构。
这些模型用于生成 outputSchema，不影响实际返回格式。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


# ============================================================
# 通用响应结构
# ============================================================

class BaseResponse(BaseModel):
    """基础响应结构"""
    success: bool = Field(description="操作是否成功")
    timestamp: str = Field(description="响应时间戳")


class ErrorResponse(BaseModel):
    """错误响应结构"""
    success: bool = Field(default=False, description="操作失败")
    error: str = Field(description="错误信息")
    error_code: Optional[str] = Field(default=None, description="错误码")


class AnalysisOutput(BaseModel):
    """统一分析输出结构
    
    所有工具应使用此统一格式返回数据，确保输出格式一致性。
    """
    success: bool = Field(description="操作是否成功")
    data: Dict[str, Any] = Field(description="分析数据")
    message: str = Field(default="", description="提示信息或说明")
    timestamp: str = Field(description="响应时间戳")
    risk_level: Optional[str] = Field(default=None, description="风险等级: 低/中/高")
    confidence: Optional[str] = Field(default=None, description="置信度: 低/中/高/极高")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "data": {"match_id": "20240101_teamA_vs_teamB", "probability": {"win": 0.45}},
                    "message": "分析完成",
                    "timestamp": "2024-01-01T12:00:00",
                    "risk_level": "低",
                    "confidence": "高"
                }
            ]
        }
    }


# ============================================================
# 投注验证输出
# ============================================================

class BetSummary(BaseModel):
    """投注摘要"""
    match_id: str = Field(description="比赛ID")
    play_type: str = Field(description="玩法类型")
    play_type_cn: str = Field(description="玩法中文名")
    selection: str = Field(description="投注选项")
    odds: float = Field(description="赔率")
    stake: float = Field(description="投注金额")
    expected_bonus: float = Field(description="预期奖金")
    lottery_type: str = Field(description="彩种类型")


class ValidateBetOutput(BaseModel):
    """单注验证输出"""
    valid: bool = Field(description="是否通过验证")
    errors: List[str] = Field(default_factory=list, description="错误列表")
    warnings: List[str] = Field(default_factory=list, description="警告列表")
    bet_summary: BetSummary = Field(description="投注摘要")


class ValidateParlayOutput(BaseModel):
    """串关验证输出"""
    valid: bool = Field(description="是否通过验证")
    errors: List[str] = Field(default_factory=list, description="错误列表")
    warnings: List[str] = Field(default_factory=list, description="警告列表")
    is_mixed_parlay: bool = Field(description="是否为混合过关")
    parlay_summary: Dict[str, Any] = Field(description="串关摘要")
    bet_details: List[Dict[str, Any]] = Field(default_factory=list, description="各场详情")
    mixed_parlay_detail: Optional[Dict[str, Any]] = Field(default=None, description="混合过关详情")


class MixedParlayDetail(BaseModel):
    """混合过关详情"""
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    play_types_used: List[str] = Field(description="使用的玩法列表")
    match_count: int = Field(description="场次数")
    bucket_limit: int = Field(description="木桶限制（最大关数）")
    limiting_plays: List[str] = Field(description="限制性玩法")
    max_legs_by_play: Dict[str, int] = Field(description="各玩法最大关数")


# ============================================================
# 奖金计算输出
# ============================================================

class BonusCalculationOutput(BaseModel):
    """奖金计算输出

    覆盖 calculate_bonus 引擎的所有返回状态：
    - simulation: 模拟模式（无比赛结果）
    - won: 中奖
    - lost: 未中奖
    - error: 错误（倍数超限/单票超限等）
    """
    status: str = Field(description="状态: simulation/won/lost/error")
    lottery_type: str = Field(default="", description="彩种类型")
    match_count: int = Field(default=0, description="场次数")
    parlay_type: str = Field(default="", description="串关类型")
    multiplier: int = Field(default=1, description="倍数")
    total_stake: float = Field(default=0.0, description="总投注额")
    total_bets: int = Field(default=0, description="总注数")
    total_odds: float = Field(default=0.0, description="总赔率(SP连乘)")
    single_bonus: float = Field(default=0.0, description="单注奖金")
    gross_bonus: float = Field(default=0.0, description="税前总奖金")
    per_bet_bonus: float = Field(default=0.0, description="单注奖金（用于税金计算）")
    tax: float = Field(default=0.0, description="税金")
    net_bonus: float = Field(default=0.0, description="税后奖金")
    profit: float = Field(default=0.0, description="盈亏")
    capped: bool = Field(default=False, description="是否封顶")
    cap_amount: Optional[float] = Field(default=None, description="封顶金额")
    bonus_formula: str = Field(default="", description="奖金公式")
    return_rate: float = Field(default=0.0, description="返还率")
    message: Optional[str] = Field(default=None, description="附加信息")
    won_matches: Optional[List[str]] = Field(default=None, description="中奖场次")
    lost_matches: Optional[List[str]] = Field(default=None, description="未中奖场次")
    bonus: Optional[float] = Field(default=None, description="奖金（lost状态为0）")


# ============================================================
# 规则查询输出
# ============================================================

class LimitsRuleOutput(BaseModel):
    """限额规则输出"""
    rule_type: str = Field(default="limits")
    lottery_type: str
    play_limits: Dict[str, Dict[str, float]] = Field(description="各玩法限额")
    parlay_limits: Dict[str, Any] = Field(description="串关限制")
    single_ticket_limit: int = Field(default=0, description="单票限额")
    multiplier_range: List[int] = Field(default_factory=list, description="倍数范围")


class ParlayRuleOutput(BaseModel):
    """串关规则输出"""
    rule_type: str = Field(default="parlay")
    lottery_type: str = Field(default="")
    max_matches: int = Field(description="最大场次数")
    min_matches: int = Field(description="最小场次数")
    single_ticket_limit: int = Field(description="单票限额")
    min_multiplier: int = Field(description="最小倍数")
    max_multiplier: int = Field(description="最大倍数")
    allowed_types: List[str] = Field(default_factory=list, description="支持的串关类型")
    mixed_parlay: Dict[str, Any] = Field(default_factory=dict, description="混合过关规则")
    limits: Optional[Dict[str, Any]] = Field(default=None, description="完整串关限制配置")
    supported_types: Optional[List[str]] = Field(default=None, description="支持的串关类型（别名）")
    multiplier_range: Optional[List[int]] = Field(default=None, description="倍数范围")


class BonusRuleOutput(BaseModel):
    """奖金规则输出"""
    rule_type: str = Field(default="bonus")
    lottery_type: str
    return_rate: float = Field(description="返还率")
    tax_rate: float = Field(description="税率")
    tax_threshold: float = Field(description="税金起征点")
    bonus_cap_by_legs: Dict[int, int] = Field(description="各级封顶金额")
    bonus_formula: Optional[Dict[str, str]] = Field(default=None, description="各彩种奖金公式")


class MixedParlayRuleOutput(BaseModel):
    """混合过关规则输出"""
    rule_type: str = Field(default="mixed_parlay")
    lottery_type: str
    mixable_plays: List[str] = Field(description="可混合玩法")
    max_legs_by_play: Dict[str, int] = Field(description="各玩法最大关数")
    restrictions: List[str] = Field(description="限制条件")


class PlayRuleOutput(BaseModel):
    """玩法规则输出"""
    rule_type: str = Field(default="play")
    lottery_type: str
    available_plays: List[str] = Field(description="可用玩法列表")
    play_details: Dict[str, Dict[str, float]] = Field(description="各玩法详细限额")
    max_legs_by_play: Dict[str, int] = Field(description="各玩法最大串关数")


class QueryRulesOutput(BaseModel):
    """规则查询统一输出

    lottery_query_rules 工具的结构化输出模型。
    根据查询的 rule_type 不同，返回不同规则详情。
    所有字段均为 Optional，实际填充取决于 rule_type。
    """
    rule_type: str = Field(description="规则类型: limits/parlay/play/bonus/mixed_parlay")
    lottery_type: str = Field(default="", description="彩种类型")
    # limits 规则字段
    play_limits: Optional[Dict[str, Dict[str, float]]] = Field(default=None, description="各玩法限额")
    parlay_limits: Optional[Dict[str, Any]] = Field(default=None, description="串关限制")
    single_ticket_limit: Optional[int] = Field(default=None, description="单票限额")
    multiplier_range: Optional[List[int]] = Field(default=None, description="倍数范围")
    # parlay 规则字段
    max_matches: Optional[int] = Field(default=None, description="最大场次数")
    min_matches: Optional[int] = Field(default=None, description="最小场次数")
    allowed_types: Optional[List[str]] = Field(default=None, description="支持的串关类型")
    supported_types: Optional[List[str]] = Field(default=None, description="支持的串关类型")
    mixed_parlay: Optional[Dict[str, Any]] = Field(default=None, description="混合过关规则")
    limits: Optional[Dict[str, Any]] = Field(default=None, description="完整串关限制配置")
    # play 规则字段
    available_plays: Optional[List[str]] = Field(default=None, description="可用玩法列表")
    play_details: Optional[Dict[str, Dict[str, float]]] = Field(default=None, description="各玩法详细限额")
    max_legs_by_play: Optional[Dict[str, int]] = Field(default=None, description="各玩法最大串关数")
    # bonus 规则字段
    return_rate: Optional[float] = Field(default=None, description="返还率")
    tax_rate: Optional[float] = Field(default=None, description="税率")
    tax_threshold: Optional[float] = Field(default=None, description="税金起征点")
    bonus_cap_by_legs: Optional[Dict[int, int]] = Field(default=None, description="各级封顶金额")
    bonus_formula: Optional[Dict[str, str]] = Field(default=None, description="各彩种奖金公式")
    # mixed_parlay 规则字段
    mixable_plays: Optional[List[str]] = Field(default=None, description="可混合玩法")
    restrictions: Optional[List[str]] = Field(default=None, description="限制条件")
    # 错误字段
    error: Optional[str] = Field(default=None, description="错误信息")


# ============================================================
# 混合过关规则查询输出
# ============================================================

class QueryMixedParlayRulesOutput(BaseModel):
    """查询混合过关规则输出"""
    lottery_type: str
    play_types_requested: List[str] = Field(description="请求的玩法列表")
    play_types_resolved: List[str] = Field(description="解析后的玩法中文名")
    all_mixable: bool = Field(description="是否全部可混合")
    mixable_status: Dict[str, bool] = Field(description="各玩法可混合状态")
    max_legs_by_play: List[Dict[str, Any]] = Field(description="各玩法最大关数")
    bucket_limit: int = Field(description="木桶限制（最大关数）")
    limiting_plays: List[str] = Field(description="限制性玩法")
    bonus_cap: int = Field(description="奖金封顶")
    return_rate: float = Field(description="返还率")
    tax_threshold: float = Field(description="税金起征点")
    tax_rate: float = Field(description="税率")
    single_ticket_limit: int = Field(description="单票限额")
    multiplier_range: List[int] = Field(description="倍数范围")
    max_matches: int = Field(description="最大场次数")
    restrictions: List[str] = Field(description="限制条件说明")


# ============================================================
# 比赛分析输出
# ============================================================

class PlayRecommendation(BaseModel):
    """玩法推荐"""
    selection: str = Field(description="推荐选项")
    probability: float = Field(description="概率")
    odds: Optional[float] = Field(default=None, description="赔率")
    expected_value: float = Field(description="期望值")
    value_rating: str = Field(description="价值评级")


class PlayAnalysisOutput(BaseModel):
    """玩法分析输出"""
    play_type: str = Field(description="玩法类型")
    play_name: str = Field(description="玩法名称")
    confidence: str = Field(description="置信度: 高/中/低")
    probabilities: Dict[str, float] = Field(description="各选项概率")
    recommendations: List[PlayRecommendation] = Field(description="推荐列表")
    expected_values: Dict[str, float] = Field(default_factory=dict, description="期望值")
    analysis_notes: List[str] = Field(description="分析说明")


class MatchPlaysAnalysisOutput(BaseModel):
    """比赛五大玩法分析输出"""
    match_id: str
    lottery_type: str
    handicap: float = Field(description="让球数")
    plays: Dict[str, PlayAnalysisOutput] = Field(description="各玩法分析")
    summary: Dict[str, Any] = Field(description="汇总信息")
    timestamp: str = Field(description="时间戳")


# ============================================================
# 导出所有输出模型
# ============================================================

OUTPUT_SCHEMAS = {
    "lottery_validate_bet": ValidateBetOutput,
    "lottery_validate_parlay": ValidateParlayOutput,
    "lottery_validate_mixed_parlay": ValidateParlayOutput,
    "lottery_calculate_bonus": BonusCalculationOutput,
    "lottery_query_rules": QueryRulesOutput,
    "lottery_query_rules_limits": LimitsRuleOutput,
    "lottery_query_rules_parlay": ParlayRuleOutput,
    "lottery_query_rules_bonus": BonusRuleOutput,
    "lottery_query_rules_mixed_parlay": MixedParlayRuleOutput,
    "lottery_query_rules_play": PlayRuleOutput,
    "lottery_query_mixed_parlay_rules": QueryMixedParlayRulesOutput,
    "lottery_analyze_match_plays": MatchPlaysAnalysisOutput,
}
