"""
MCP Server Models - Pydantic input models for all tools.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================
# P0: 基础验证模型
# ============================================================

class ValidateBetInput(BaseModel):
    """单个投注验证输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛唯一标识符",
        examples=["match_001", "2024-01-15-home-away"],
        min_length=1,
        max_length=100
    )
    play_type: str = Field(
        ...,
        description="玩法类型: SPF(胜平负)/RQSPF(让球胜平负)/BF(比分)/JQS(进球数)/BQC(半全场)",
        examples=["SPF", "RQSPF", "BF"],
        min_length=2,
        max_length=10
    )
    selection: str = Field(
        ...,
        description="投注选项，如主胜/让球主胜/1:0/0/胜胜",
        examples=["主胜", "让球主胜", "1:0"],
        min_length=1,
        max_length=20
    )
    odds: float = Field(
        ...,
        description="投注赔率",
        examples=[2.15, 3.50],
        gt=1.0,
        le=1000.0
    )
    handicap: Optional[float] = Field(
        default=None,
        description="让球数（仅RQSPF玩法需要）。竞彩足球为整数（如-1, -2, +1），北京单场可为小数（如-1.5, -0.5）",
        examples=[-1, -2, 1, -1.5, -0.5],
        ge=-10,
        le=10
    )
    stake: float = Field(
        ...,
        description="投注金额（元）",
        examples=[100.0, 50.0],
        gt=0,
        le=1000000.0
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型: 竞彩足球/北京单场",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )


class ValidateParlayInput(BaseModel):
    """串关投注验证输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    bets: List[ValidateBetInput] = Field(
        ...,
        description="投注列表（2-15场，具体上限按彩种：竞彩足球8场，北京单场15场）",
        min_length=2,
        max_length=15
    )
    parlay_type: str = Field(
        default="2x1",
        description="串关类型: 2x1/3x1/4x1/3x4/4x11/MxN",
        examples=["2x1", "3x4", "4x11"],
        min_length=3,
        max_length=10
    )
    total_stake: float = Field(
        ...,
        description="总投注金额（元）",
        examples=[100.0, 200.0],
        gt=0,
        le=1000000.0
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )


# 混合过关验证输入（与 ValidateParlayInput 结构相同，语义别名）
ValidateMixedParlayInput = ValidateParlayInput




class CalculateBonusInput(BaseModel):
    """奖金计算输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    bets: List[ValidateBetInput] = Field(
        ...,
        description="投注列表",
        min_length=1,
        max_length=8
    )
    parlay_type: str = Field(
        default="1x1",
        description="串关类型",
        examples=["1x1", "2x1", "3x4"],
        min_length=3,
        max_length=10
    )
    results: Optional[Dict[str, str]] = Field(
        default=None,
        description="比赛结果映射 {match_id: result}，如 {'match_001': '主胜'}",
        examples=[{"match_001": "主胜", "match_002": "平局"}]
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )


class QueryRulesInput(BaseModel):
    """规则查询输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    rule_type: str = Field(
        ...,
        description="规则类型: limits(限额)/parlay(串关)/play(玩法)/bonus(奖金)",
        examples=["limits", "parlay", "play", "bonus"],
        min_length=2,
        max_length=20
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场", "北京单场"],
        min_length=2,
        max_length=20
    )
    play_type: Optional[str] = Field(
        default=None,
        description="玩法类型（可选）",
        examples=["SPF", "BF"],
        min_length=2,
        max_length=10
    )


# ============================================================
# P0: 强制规则验证模型
# ============================================================

class ValidateScenarioInput(BaseModel):
    """场景验证输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    scenario_type: str = Field(
        ...,
        description="场景类型: single_bet(单注)/parlay(串关)/daily_plan(日计划)/chase(追号)",
        examples=["single_bet", "parlay", "daily_plan"],
        min_length=5,
        max_length=20
    )
    bets: List[ValidateBetInput] = Field(
        default_factory=list,
        description="投注列表",
        max_length=50
    )
    total_stake: float = Field(
        default=0.0,
        description="总投注金额",
        ge=0,
        le=10000000.0
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="额外上下文信息"
    )


class ValidatePlanInput(BaseModel):
    """投注计划验证输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    plan_type: str = Field(
        ...,
        description="计划类型: daily(日计划)/weekly(周计划)/chase(追号计划)",
        examples=["daily", "weekly", "chase"],
        min_length=3,
        max_length=20
    )
    bets: List[ValidateBetInput] = Field(
        default_factory=list,
        description="计划中的投注列表",
        max_length=100
    )
    total_budget: float = Field(
        ...,
        description="计划总预算",
        gt=0,
        le=10000000.0
    )
    period_days: int = Field(
        default=1,
        description="计划周期（天）",
        ge=1,
        le=365
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )


class RejectInput(BaseModel):
    """强制拒绝输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    reason: str = Field(
        ...,
        description="拒绝原因",
        examples=["超出单日限额", "检测到异常投注模式"],
        min_length=1,
        max_length=500
    )
    scenario: Optional[str] = Field(
        default=None,
        description="触发场景",
        examples=["daily_limit", "risk_alert"],
        max_length=100
    )


class RuleGuardInput(BaseModel):
    """规则守卫输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    guard_type: str = Field(
        ...,
        description="守卫类型: pre_bet(投注前)/post_bet(投注后)/daily(日检查)/emergency(紧急)",
        examples=["pre_bet", "post_bet", "daily"],
        min_length=5,
        max_length=20
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="守卫检查数据"
    )


# ============================================================
# P1: 数据获取模型
# ============================================================

class FetchTodayMatchesInput(BaseModel):
    """获取今日比赛输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    sport_type: str = Field(
        default="football",
        description="运动类型: football",
        examples=["football"],
        min_length=3,
        max_length=20
    )
    league: Optional[str] = Field(
        default=None,
        description="联赛筛选（可选）",
        examples=["英超", "西甲"],
        max_length=50
    )
    include_odds: bool = Field(
        default=True,
        description="是否包含赔率数据"
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型: 竞彩足球/北京单场/传统足彩",
        examples=["竞彩足球", "北京单场", "传统足彩"],
        min_length=2,
        max_length=20
    )
    limit: int = Field(
        default=20,
        description="返回数量限制",
        ge=1,
        le=100
    )
    offset: int = Field(
        default=0,
        description="偏移量（分页）",
        ge=0
    )
    timeout: int = Field(
        default=30,
        description="请求超时时间（秒）",
        ge=5,
        le=120
    )
    response_format: str = Field(
        default="json",
        description="响应格式: json/markdown",
        examples=["json", "markdown"],
        max_length=10
    )
    force_refresh: bool = Field(
        default=False,
        description="强制刷新缓存，忽略缓存数据"
    )


class GetMatchDataInput(BaseModel):
    """获取比赛数据输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["match_001"],
        min_length=1,
        max_length=100
    )
    data_type: str = Field(
        default="full",
        description="数据类型: full/odds/stats/lineup/history",
        examples=["full", "odds", "stats"],
        min_length=3,
        max_length=20
    )
    league: Optional[str] = Field(
        default=None,
        description="联赛名称（用于积分榜查询，如 data_type 含 stats）",
        examples=["英超", "西甲", "中超"],
        max_length=50
    )
    home_team: Optional[str] = Field(
        default=None,
        description="主队名称（用于交锋记录查询，如 data_type 含 history）",
        examples=["曼联", "利物浦"],
        max_length=50
    )
    away_team: Optional[str] = Field(
        default=None,
        description="客队名称（用于交锋记录查询，如 data_type 含 history）",
        examples=["切尔西", "阿森纳"],
        max_length=50
    )


# ============================================================
# P1: 分析引擎模型
# ============================================================

class AnalyzeMatchPlaysInput(BaseModel):
    """比赛五大玩法分析输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["match_001"],
        min_length=1,
        max_length=100
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )
    handicap: float = Field(
        default=0.0,
        description="让球数（用于RQSPF分析），正数表示主队让球",
        examples=[0.0, -0.5, 1.0],
        ge=-3.0,
        le=3.0
    )


class AnalyzeAllMatchesInput(BaseModel):
    """分析所有比赛输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    filter: Optional[str] = Field(
        default=None,
        description="筛选条件: high_value(高价值)/low_risk(低风险)/all(全部)",
        examples=["high_value", "low_risk", "all"],
        max_length=20
    )
    max_matches: int = Field(
        default=20,
        description="最大分析场次",
        ge=1,
        le=50
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )


class AnalyzeWithPipelineInput(BaseModel):
    """使用统一流水线分析所有比赛输入参数
    
    这是 Phase 2 新增的工具，使用统一的分析流水线对比赛进行全面分析。
    与 lottery_analyze_all_matches 的区别：
    - 一次分析，产出完整数据包（基本面+模型+玩法+规则）
    - 包含比赛特征画像和策略配置
    - 包含完整的投注理由链
    """
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    max_matches: int = Field(
        default=10,
        description="最大分析场次",
        ge=1,
        le=30
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )
    include_reasoning: bool = Field(
        default=True,
        description="是否包含投注理由链"
    )


class DetectRiskSignalsInput(BaseModel):
    """风险信号检测输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID，建议格式: YYYYMMDD_Home_vs_Away",
        examples=["20250115_曼联_vs_利物浦"],
        min_length=1,
        max_length=100
    )
    signal_types: Optional[List[str]] = Field(
        default=None,
        description="信号类型列表: odds_drift(赔率异动)/lineup(阵容)/weather(天气)/market(市场)",
        examples=[["odds_drift", "lineup"]]
    )
    current_odds: Optional[Dict[str, float]] = Field(
        default=None,
        description="当前赔率，用于检测赔率异动，如 {'主胜': 2.15, '平局': 3.20, '客胜': 3.50}",
        examples=[{"主胜": 2.15, "平局": 3.20, "客胜": 3.50}]
    )
    previous_odds: Optional[Dict[str, float]] = Field(
        default=None,
        description="历史赔率（开盘赔率），用于检测赔率异动",
        examples=[{"主胜": 1.95, "平局": 3.40, "客胜": 3.80}]
    )


class ComprehensiveAnalysisInput(BaseModel):
    """综合分析输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_ids: List[str] = Field(
        ...,
        description="比赛ID列表",
        min_length=1,
        max_length=20
    )
    include_recommendations: bool = Field(
        default=True,
        description="是否包含投注建议"
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )


class GenerateAnalysisReportInput(BaseModel):
    """生成分析报告输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["match_001"],
        min_length=1,
        max_length=100
    )
    style: str = Field(
        default="professional",
        description="报告风格: professional(专业)/casual(轻松)/detailed(详细)",
        examples=["professional", "casual", "detailed"],
        min_length=3,
        max_length=20
    )
    include_reasoning: bool = Field(
        default=True,
        description="是否包含推理过程"
    )
    include_confidence: bool = Field(
        default=True,
        description="是否包含置信度说明"
    )
    analysis_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="预计算的分析数据（可选）"
    )


class BatchAnalyzeMatchesInput(BaseModel):
    """批量分析比赛输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_ids: List[str] = Field(
        ...,
        description="比赛ID列表",
        min_length=1,
        max_length=20
    )
    parallel: bool = Field(
        default=True,
        description="是否并行执行"
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )


# ============================================================
# P2: 投注推荐模型
# ============================================================

class GetDailyRecommendationsInput(BaseModel):
    """获取每日推荐输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    count: int = Field(
        default=5,
        description="推荐数量",
        ge=1,
        le=20
    )
    strategy: str = Field(
        default="balanced",
        description="策略: conservative(保守)/balanced(平衡)/aggressive(激进)/value(价值)",
        examples=["conservative", "balanced", "aggressive", "value"],
        min_length=3,
        max_length=20
    )
    min_confidence: float = Field(
        default=60.0,
        description="最低置信度",
        ge=0,
        le=100
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )
    limit: int = Field(
        default=10,
        description="返回记录数量限制",
        ge=1,
        le=100
    )
    offset: int = Field(
        default=0,
        description="分页偏移量",
        ge=0
    )


class GenerateBettingSlipsInput(BaseModel):
    """生成投注单输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_ids: List[str] = Field(
        ...,
        description="比赛ID列表",
        min_length=1,
        max_length=8
    )
    strategy: str = Field(
        default="single",
        description="策略: single(单关)/parlay(串关)/mixed(混合)/auto_parlay(自动串关)",
        examples=["single", "parlay", "mixed", "auto_parlay"],
        min_length=3,
        max_length=20
    )
    bankroll: float = Field(
        default=1000.0,
        description="可用资金",
        gt=0,
        le=10000000.0
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )
    # auto_parlay 模式参数
    parlay_type: str = Field(
        default="2x1",
        description="串关类型（仅在strategy=auto_parlay时使用）: 2x1/3x1/4x1/3x4/4x11/MxN",
        examples=["2x1", "3x1", "4x1", "3x4", "4x11"],
        min_length=3,
        max_length=10
    )
    max_matches: int = Field(
        default=4,
        description="最多选择场次（仅在strategy=auto_parlay时使用）",
        ge=2,
        le=8
    )
    min_confidence: float = Field(
        default=60.0,
        description="最低置信度（仅在strategy=auto_parlay时使用）",
        ge=0,
        le=100
    )
    kelly_fraction: float = Field(
        default=0.25,
        description="凯利系数分数（0.01-1.0），建议值0.1-0.3。0.25表示使用四分之一凯利公式，降低风险",
        ge=0.01,
        le=1.0
    )
    risk_level: str = Field(
        default="balanced",
        description="风险偏好（仅在strategy=auto_parlay时使用）: conservative(保守)/balanced(稳健)/aggressive(激进)/value(价值投注)",
        examples=["conservative", "balanced", "aggressive", "value"],
        min_length=3,
        max_length=20
    )
    limit: int = Field(
        default=10,
        description="返回记录数量限制",
        ge=1,
        le=100
    )
    offset: int = Field(
        default=0,
        description="分页偏移量",
        ge=0
    )


class GenerateKellySlipsInput(BaseModel):
    """生成凯利投注单输入参数
    
    基于凯利公式(Kelly Criterion)计算最优投注比例。
    公式: f* = (bp - q) / b
    其中: b=赔率-1, p=获胜概率, q=失败概率=1-p
    """
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛唯一标识符",
        examples=["match_001"],
        min_length=1,
        max_length=100
    )
    edge: float = Field(
        ...,
        description="期望优势（获胜概率 - 1/赔率），范围-1到1",
        examples=[0.1, 0.05, -0.02],
        ge=-1.0,
        le=1.0
    )
    odds: float = Field(
        ...,
        description="投注赔率",
        examples=[2.15, 3.50],
        gt=1.0,
        le=1000.0
    )
    bankroll: float = Field(
        default=1000.0,
        description="可用资金（元）",
        gt=0,
        le=10000000.0
    )
    fraction: float = Field(
        default=0.5,
        description="凯利分数（保守系数），建议0.25-0.5，降低波动风险",
        ge=0.01,
        le=1.0
    )


# ============================================================
# P2-1: 高级工作流模型
# ============================================================

class CrossMatchAnalysisInput(BaseModel):
    """跨比赛分析输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_ids: List[str] = Field(
        ...,
        description="比赛ID列表（2-5场）",
        min_length=2,
        max_length=5,
        examples=[["match_1", "match_2", "match_3"]]
    )
    analysis_type: str = Field(
        default="correlation",
        description="分析类型：correlation(关联性)/value(价值对比)/risk(风险聚合)",
        examples=["correlation", "value", "risk"]
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型"
    )


class AutoParlayRecommendationInput(BaseModel):
    """自动串关推荐输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_ids: Optional[List[str]] = Field(
        default=None,
        description="指定比赛ID列表（可选，如未提供则自动选择）",
        max_length=8
    )
    strategy: str = Field(
        default="balanced",
        description="策略：conservative(保守)/balanced(平衡)/aggressive(激进)/value(价值优先)",
        examples=["conservative", "balanced", "aggressive", "value"]
    )
    parlay_type: str = Field(
        default="2x1",
        description="串关类型：2x1/3x1/4x1/3x4/4x11/MxN",
        examples=["2x1", "3x1", "4x1", "3x4", "4x11"]
    )
    max_matches: int = Field(
        default=4,
        description="最多选择场次",
        ge=2,
        le=8
    )
    min_confidence: float = Field(
        default=60.0,
        description="最低置信度",
        ge=0,
        le=100
    )
    bankroll: float = Field(
        default=1000.0,
        description="可用资金（元）",
        gt=0
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型"
    )


# ============================================================
# P2-2: 数据获取扩展模型
# ============================================================

class TrackOddsChangesInput(BaseModel):
    """追踪竞彩赔率变化输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID（竞彩官网场次编号）",
        examples=["20260523001"],
        min_length=1,
        max_length=50
    )



# ============================================================
# P2-5: 开奖结果分析模型
# ============================================================

class AnalyzeResultsInput(BaseModel):
    """赛果统计分析输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型: 竞彩足球/北京单场/传统足彩",
        examples=["竞彩足球", "北京单场", "传统足彩"],
        min_length=2,
        max_length=20
    )
    start_date: Optional[str] = Field(
        default=None,
        description="起始日期（格式 YYYY-MM-DD，默认7天前）",
        examples=["2026-05-16"],
        max_length=10
    )
    end_date: Optional[str] = Field(
        default=None,
        description="结束日期（格式 YYYY-MM-DD，默认今天）",
        examples=["2026-05-23"],
        max_length=10
    )
    league: Optional[str] = Field(
        default=None,
        description="联赛筛选（如 英超、西甲）",
        examples=["英超", "西甲"],
        max_length=30
    )


class VerifyResultsInput(BaseModel):
    """多源开奖验证输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    date: Optional[str] = Field(
        default=None,
        description="查询日期（格式 YYYY-MM-DD，默认今天）",
        examples=["2026-05-23"],
        max_length=10
    )
    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型: 竞彩足球/北京单场/传统足彩",
        examples=["竞彩足球", "北京单场"],
        min_length=2,
        max_length=20
    )



class AnalyzeMatchInput(BaseModel):
    """单场比赛深度分析输入参数（工作流工具）

    整合多维度数据生成分析报告：
    - 官方赔率分析（返还率、凯利指数）
    - 市场赔率对比（欧赔、亚盘、大小球）
    - 比赛资讯综合分析
    - 投注建议生成
    """
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="竞彩比赛ID",
        examples=["20260523001"],
        min_length=1,
        max_length=50
    )
    analysis_depth: str = Field(
        default="standard",
        description="分析深度: basic(基础)/standard(标准)/deep(深度)",
        examples=["basic", "standard", "deep"],
        min_length=4,
        max_length=10
    )
    include_market_odds: bool = Field(
        default=True,
        description="是否获取市场赔率（欧赔/亚盘）进行对比分析"
    )


class QueryHistoryInput(BaseModel):
    """历史开奖查询输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    lottery_type: str = Field(
        default="竞彩足球",
        description="彩种类型: 竞彩足球/北京单场/传统足彩",
        examples=["竞彩足球", "北京单场", "传统足彩"],
        min_length=2,
        max_length=20
    )
    date: Optional[str] = Field(
        default=None,
        description="查询日期（格式 YYYY-MM-DD，默认今天）",
        examples=["2026-05-23"],
        max_length=10
    )
    expect: Optional[str] = Field(
        default=None,
        description="奖期编号（传统足彩必填）",
        examples=["24001"],
        max_length=10
    )
    play_type: Optional[str] = Field(
        default=None,
        description="玩法筛选: sfc(胜负彩)/rx9(任选9)/jqc(半全场)/bqc(进球彩)",
        examples=["sfc", "rx9"],
        max_length=10
    )
    limit: int = Field(
        default=50,
        description="返回数量限制",
        ge=1,
        le=200
    )
    offset: int = Field(
        default=0,
        description="偏移量（分页）",
        ge=0
    )
    response_format: str = Field(
        default="json",
        description="响应格式: json/markdown",
        examples=["json", "markdown"],
        max_length=10
    )


# ============================================================
# P2-5: 高级功能模型
# ============================================================

class GetLiveScoresInput(BaseModel):
    """获取实时比分输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    league: Optional[str] = Field(
        default=None,
        description="联赛名称（如 英超、西甲）",
        examples=["英超", "西甲"],
        max_length=30
    )
    include_finished: bool = Field(
        default=False,
        description="是否包含已结束的比赛"
    )
    limit: int = Field(
        default=20,
        description="返回数量限制",
        ge=1,
        le=100
    )
    offset: int = Field(
        default=0,
        description="偏移量（分页）",
        ge=0
    )
    response_format: str = Field(
        default="json",
        description="响应格式: json/markdown",
        examples=["json", "markdown"],
        max_length=10
    )


class GetMarketOddsInput(BaseModel):
    """获取市场赔率数据输入参数（统一入口）

    支持获取欧赔、亚盘、大小球等多种市场类型的赔率数据。
    数据源优先级：球探网 -> 捷报比分 -> The Odds API
    """
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    league: Optional[str] = Field(
        default=None,
        description="联赛名称（如 英超、西甲），支持中英文",
        examples=["英超", "西甲", "EPL"],
        max_length=30
    )
    home_team: Optional[str] = Field(
        default=None,
        description="主队名称（用于精确匹配特定比赛），支持中英文",
        examples=["曼联", "Manchester United"],
        max_length=50
    )
    away_team: Optional[str] = Field(
        default=None,
        description="客队名称（用于精确匹配特定比赛），支持中英文",
        examples=["利物浦", "Liverpool"],
        max_length=50
    )
    market_types: List[str] = Field(
        default=["european", "asian", "over_under"],
        description="要获取的市场类型列表: european(欧赔)/asian(亚盘)/over_under(大小球)",
        examples=[["european", "asian"], ["all"]]
    )


# ============================================================
# P3: 系统管理模型
# ============================================================

class ClearCacheInput(BaseModel):
    """清除缓存输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    cache_type: str = Field(
        default="all",
        description="缓存类型: all/matches/odds/analysis/results",
        examples=["all", "matches", "odds"],
        min_length=2,
        max_length=20
    )


class GetSystemStatusInput(BaseModel):
    """获取系统状态输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    include_details: bool = Field(
        default=True,
        description="是否包含详细信息"
    )
    action: str = Field(
        default="status",
        description="操作类型: status(获取状态)/health(健康检查)/clear_cache(清除缓存)",
        examples=["status", "health", "clear_cache"],
        min_length=5,
        max_length=20
    )
    cache_type: str = Field(
        default="all",
        description="缓存类型（仅在action=clear_cache时使用）: all/matches/odds/analysis/results",
        examples=["all", "matches", "odds"],
        min_length=2,
        max_length=20
    )



# ============================================================
# Phase 3: AI推理工具模型
# ============================================================

class GetMatchContextInput(BaseModel):
    """获取比赛上下文输入参数（AI推理工具）

    聚合所有相关数据供AI进行深度推理分析。
    """
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["20260523001"],
        min_length=1,
        max_length=100
    )
    include_market: bool = Field(
        default=True,
        description="是否包含市场赔率数据"
    )
    include_history: bool = Field(
        default=True,
        description="是否包含历史交锋数据"
    )
    include_form: bool = Field(
        default=True,
        description="是否包含近期状态数据"
    )


class AssessRiskInput(BaseModel):
    """风险评估输入参数（AI推理工具）

    多维度风险评估，包括投注风险、比赛不确定性等。
    """
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["20260523001"],
        min_length=1,
        max_length=100
    )
    proposed_bet: Optional[Dict] = Field(
        default=None,
        description="拟议投注选项，如 {'selection': '主胜', 'odds': 2.15, 'stake': 100}",
        examples=[{"selection": "主胜", "odds": 2.15, "stake": 100}]
    )


class SimulateScenariosInput(BaseModel):
    """情景模拟输入参数（AI推理工具）

    模拟不同比赛情景下的结果概率和影响。
    """
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["20260523001"],
        min_length=1,
        max_length=100
    )
    scenarios: List[str] = Field(
        default=["home_early_goal", "red_card", "away_lead_ht"],
        description="情景列表: home_early_goal(主队 early goal)/away_early_goal(客队 early goal)/red_card(红牌)/penalty(点球)/away_lead_ht(客队半场领先)/home_dominance(主队压制)/low_scoring(低比分)",
        examples=[["home_early_goal", "red_card"], ["away_lead_ht", "penalty"]]
    )


class GenerateRecommendationInput(BaseModel):
    """生成综合建议输入参数（AI推理工具）

    基于所有分析生成最终投注建议。
    """
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["20260523001"],
        min_length=1,
        max_length=100
    )
    risk_tolerance: str = Field(
        default="balanced",
        description="风险承受度: conservative(保守)/balanced(平衡)/aggressive(激进)",
        examples=["conservative", "balanced", "aggressive"],
        min_length=5,
        max_length=15
    )


# ============================================================
# Phase 2: 高级数据工具模型
# ============================================================

class PredictWithModelInput(BaseModel):
    """使用ML模型预测比赛结果输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["20260523001"],
        min_length=1,
        max_length=100
    )
    model_type: str = Field(
        default="ensemble",
        description="模型类型: poisson(泊松)/elo(Elo评级)/xg(预期进球)/ensemble(集成)",
        examples=["poisson", "elo", "xg", "ensemble"],
        min_length=3,
        max_length=10
    )
    include_features: bool = Field(
        default=True,
        description="是否包含特征重要性分析"
    )


class GetMarketSentimentInput(BaseModel):
    """获取市场情绪输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["20260523001"],
        min_length=1,
        max_length=100
    )
    include_betting_trends: bool = Field(
        default=True,
        description="是否包含投注趋势数据"
    )
    include_social_sentiment: bool = Field(
        default=False,
        description="是否包含社交媒体情绪（如可用）"
    )


class QuantifyInjuryImpactInput(BaseModel):
    """量化伤停影响输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_id: str = Field(
        ...,
        description="比赛ID",
        examples=["20260523001"],
        min_length=1,
        max_length=100
    )
    impact_weight: str = Field(
        default="balanced",
        description="影响权重: offense(进攻)/defense(防守)/balanced(均衡)",
        examples=["offense", "defense", "balanced"],
        min_length=5,
        max_length=10
    )


# ============================================================
# Phase 4: 新增高级工具模型
# ============================================================

class CompareMatchesInput(BaseModel):
    """多场比赛对比分析输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    match_ids: List[str] = Field(
        ...,
        description="比赛ID列表",
        min_length=2,
        max_length=8,
        examples=[["match_001", "match_002", "match_003"]]
    )
    comparison_dimensions: List[str] = Field(
        default=["odds", "form", "h2h", "injuries"],
        description="对比维度: odds(赔率)/form(近期状态)/h2h(历史交锋)/injuries(伤停)/standings(积分榜)"
    )
    response_format: str = Field(
        default="json",
        description="响应格式: json/markdown",
        examples=["json", "markdown"],
        max_length=10
    )


class OptimizeStakesInput(BaseModel):
    """资金分配优化输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    bankroll: float = Field(
        ...,
        description="总资金",
        gt=0,
        examples=[1000.0, 5000.0]
    )
    bets: List[Dict] = Field(
        ...,
        description="投注列表（含match_id, selection, odds, probability）",
        min_length=1,
        max_length=20
    )
    strategy: str = Field(
        default="kelly",
        description="策略: kelly(凯利公式)/risk_parity(风险平价)/equal(均等分配)",
        examples=["kelly", "risk_parity", "equal"],
        max_length=20
    )
    max_stake_percent: float = Field(
        default=0.05,
        description="单注最大比例",
        ge=0.01,
        le=0.5
    )


class TrackBettingRecordInput(BaseModel):
    """记录投注结果"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')
    match_id: str = Field(..., description="比赛ID", min_length=1, max_length=100)
    selection: str = Field(..., description="投注选项", min_length=1, max_length=20)
    odds: float = Field(..., description="赔率", gt=1.0, le=1000.0)
    stake: float = Field(..., description="投注金额", gt=0, le=1000000.0)
    won: bool = Field(..., description="是否中奖")
    profit: float = Field(..., description="盈亏金额（正=盈利，负=亏损）")


class GetBettingStatsInput(BaseModel):
    """获取投注统计"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')
    period: str = Field(default="all", description="统计周期: all(全部)/today(今日)/week(本周)", examples=["all", "today", "week"])
    limit: int = Field(default=20, description="返回记录数量限制", ge=1, le=100)
    offset: int = Field(default=0, description="分页偏移量", ge=0)


class CompareModelPredictionsInput(BaseModel):
    """多模型预测对比输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')
    match_id: str = Field(..., description="比赛ID", min_length=1, max_length=100)
    lottery_type: str = Field(default="竞彩足球", description="彩种类型", examples=["竞彩足球", "北京单场"])
    models: List[str] = Field(
        default=["poisson", "elo", "xg"],
        description="要对比的模型列表: poisson(泊松)/elo(Elo评级)/xg(期望进球)",
        examples=[["poisson", "elo", "xg"]],
        min_length=1,
        max_length=3
    )


class ExplainRuleInput(BaseModel):
    """规则解释输入"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')
    rule_topic: str = Field(
        ...,
        description="要解释的规则主题",
        examples=["混合过关", "单票限额", "串关类型", "奖金封顶", "税金", "让球规则", "倍数限制"],
        min_length=1,
        max_length=50
    )
    lottery_type: str = Field(default="竞彩足球", description="彩种类型", examples=["竞彩足球", "北京单场"])
    context: Optional[str] = Field(
        default=None,
        description="额外上下文（如具体的投注方案描述），用于生成更有针对性的解释",
        max_length=500
    )


class ManageConfigInput(BaseModel):
    """系统配置管理"""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')
    action: str = Field(
        ...,
        description="操作类型: get(获取配置)/set(修改配置)/reset(重置为默认)",
        examples=["get", "set", "reset"]
    )
    config_key: Optional[str] = Field(
        default=None,
        description="配置项: max_daily_stake(单日最大投注)/max_single_stake(单注最大投注)/risk_preference(风险偏好:conservative/balanced/aggressive)/warning_threshold(警告阈值)",
        examples=["max_daily_stake", "risk_preference"]
    )
    config_value: Optional[str] = Field(
        default=None,
        description="配置值（仅在action=set时需要）",
        max_length=100
    )


