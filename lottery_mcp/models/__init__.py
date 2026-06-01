"""
Pydantic 模型模块 (lottery_mcp.models)
====================================

定义所有 MCP 工具的输入输出模型。

模型分类:
    - P0 基础验证模型: ValidateBetInput, ValidateParlayInput, CalculateBonusInput
    - P0 强制规则模型: ValidateScenarioInput, ValidatePlanInput, RuleGuardInput
    - P1 数据获取模型: FetchTodayMatchesInput, GetMatchDataInput
    - P1 分析引擎模型: AnalyzeMatchInput, DetectRiskSignalsInput
    - P2 投注推荐模型: GetDailyRecommendationsInput, GenerateBettingSlipsInput
    - P3 系统管理模型: GetSystemStatusInput, ClearCacheInput
"""

from .schemas import (
    # P0: 基础验证模型
    ValidateBetInput,
    ValidateParlayInput,
    ValidateMixedParlayInput,
    CalculateBonusInput,
    QueryRulesInput,
    
    # P0: 强制规则验证模型
    ValidateScenarioInput,
    ValidatePlanInput,
    RejectInput,
    RuleGuardInput,
    
    # P1: 数据获取模型
    FetchTodayMatchesInput,
    GetMatchDataInput,
    TrackOddsChangesInput,
    VerifyResultsInput,
    QueryHistoryInput,
    GetLiveScoresInput,
    GetMarketOddsInput,
    
    # P1: 分析引擎模型
    AnalyzeMatchPlaysInput,
    AnalyzeAllMatchesInput,
    AnalyzeWithPipelineInput,
    DetectRiskSignalsInput,
    ComprehensiveAnalysisInput,
    GenerateAnalysisReportInput,
    BatchAnalyzeMatchesInput,
    AnalyzeMatchInput,
    AnalyzeResultsInput,
    
    # P2: 投注推荐模型
    GetDailyRecommendationsInput,
    GenerateBettingSlipsInput,
    GenerateKellySlipsInput,
    
    # P2-1: 高级工作流模型
    CrossMatchAnalysisInput,
    AutoParlayRecommendationInput,
    
    # Phase 3: AI推理工具模型
    GetMatchContextInput,
    AssessRiskInput,
    SimulateScenariosInput,
    GenerateRecommendationInput,
    
    # Phase 4: 新增高级工具模型
    CompareMatchesInput,
    OptimizeStakesInput,
    TrackBettingRecordInput,
    GetBettingStatsInput,
    CompareModelPredictionsInput,
    ExplainRuleInput,
    ManageConfigInput,
    GetSystemStatusInput,
    
    # Phase 2: 高级数据工具模型
    PredictWithModelInput,
    GetMarketSentimentInput,
    QuantifyInjuryImpactInput,
)

__all__ = [
    # P0: 基础验证模型
    "ValidateBetInput",
    "ValidateParlayInput",
    "ValidateMixedParlayInput",
    "CalculateBonusInput",
    "QueryRulesInput",
    
    # P0: 强制规则验证模型
    "ValidateScenarioInput",
    "ValidatePlanInput",
    "RejectInput",
    "RuleGuardInput",
    
    # P1: 数据获取模型
    "FetchTodayMatchesInput",
    "GetMatchDataInput",
    "TrackOddsChangesInput",
    "VerifyResultsInput",
    "QueryHistoryInput",
    "GetLiveScoresInput",
    "GetMarketOddsInput",
    
    # P1: 分析引擎模型
    "AnalyzeMatchPlaysInput",
    "AnalyzeAllMatchesInput",
    "AnalyzeWithPipelineInput",
    "DetectRiskSignalsInput",
    "ComprehensiveAnalysisInput",
    "GenerateAnalysisReportInput",
    "BatchAnalyzeMatchesInput",
    "AnalyzeMatchInput",
    "AnalyzeResultsInput",
    
    # P2: 投注推荐模型
    "GetDailyRecommendationsInput",
    "GenerateBettingSlipsInput",
    "GenerateKellySlipsInput",
    
    # P2-1: 高级工作流模型
    "CrossMatchAnalysisInput",
    "AutoParlayRecommendationInput",
    
    # Phase 3: AI推理工具模型
    "GetMatchContextInput",
    "AssessRiskInput",
    "SimulateScenariosInput",
    "GenerateRecommendationInput",
    
    # Phase 4: 新增高级工具模型
    "CompareMatchesInput",
    "OptimizeStakesInput",
    "TrackBettingRecordInput",
    "GetBettingStatsInput",
    "CompareModelPredictionsInput",
    "ExplainRuleInput",
    "ManageConfigInput",
    "GetSystemStatusInput",
    
    # Phase 2: 高级数据工具模型
    "PredictWithModelInput",
    "GetMarketSentimentInput",
    "QuantifyInjuryImpactInput",
]
