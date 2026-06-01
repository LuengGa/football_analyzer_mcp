"""
分析引擎模块 (lottery_mcp.analysis)
=================================

提供比赛分析、统计模型、玩法分析等功能。

模块结构:
    - engine: 分析引擎核心（统计分析、模型预测）
    - models: 统计模型（泊松分布、Elo评级、xG模型）
    - strategy: 比赛策略分析
    - play_analysis: 五大玩法分析（SPF/RQSPF/BF/ZJQ/BQC）
    - play_strategies: 玩法专属策略（各玩法独立的分析和排名逻辑）
    - mixed_parlay: 混合过关优化（生成混合过关投注方案）
    - play_advanced: 高级玩法分析（比分范围、大小球、半全场一致性）
    - play_clustering: 聚类分析与深度评估
    - historical_features: 历史数据特征与交锋分析
    - advanced_enhancements: 高级深化功能（平局优化、逆转识别、凯利公式）
    - backtest_framework: 回测框架与ML集成
    - advanced_ml_integration: 完整ML集成与剩余功能
"""

from .engine import (
    StatisticalEngine,
    DeepAnalysisEngine,
    MultiSourceAnalysis,
    analyze_match,
    analyze_all_matches,
    detect_risk_signals,
    comprehensive_analysis,
    generate_analysis_report,
    batch_analyze_matches,
)

from .advisor import (
    SmartAdvisor,
    AdvisorDecision,
    get_advisor_analysis,
)

from .models import (
    # 泊松模型
    PoissonModel,
    PoissonMatchPrediction,
    poisson_pmf,
    
    # Elo评级
    EloRatingSystem,
    EloTeamRating,
    
    # xG模型
    XGModel,
    XGAnalysisResult,
    
    # 统计分析结果
    StatisticalAnalysisResult,
)

from .strategy import (
    MatchProfile,
    StrategyConfig,
    MatchProfiler,
    StrategySelector,
    LeagueTier,
    OddsPattern,
    DataQuality,
)

from .play_analysis import (
    PlayAnalyzer,
    PlayProbabilityResult,
    get_play_analyzer,
)

from .play_strategies import (
    PlayType,
    PlayRiskLevel,
    PlayStrategyConfig,
    BasePlayStrategy,
    SPFStrategy,
    RQSPFStrategy,
    BFStrategy,
    ZJQStrategy,
    BQCStrategy,
    PlayStrategyFactory,
)

from .mixed_parlay import (
    ParlayStrategy,
    ParlayCandidate,
    MixedParlayOptimizer,
)
from .play_advanced import (
    PlayAdvancedAnalyzer,
    ScoreRange,
    OverUnderAnalysis,
    BQCConsistencyAnalysis,
)
from .play_clustering import (
    PlayClusterAnalyzer,
    ScoreCluster,
    ScorePattern,
    HandicapDepthAnalysis,
    PlayCorrelation,
)
from .historical_features import (
    HistoricalFeatureExtractor,
    EnhancedHistoricalAnalyzer,
    HistoricalFeatures,
    OddsDynamics,
    HeadToHeadPattern,
    RecentFormTrend,
    OddsMovement,
)
from .advanced_enhancements import (
    DrawOptimizer,
    DrawPattern,
    ComebackPatternRecognizer,
    RiskDiversifier,
    KellyCriterionOptimizer,
    ParlayPlanGenerator,
    ParlayType,
    PreciseExpectedGoals,
    OddsDeviationAnalyzer,
    UnderdogResilienceAnalyzer,
)
from .backtest_framework import (
    HistoricalBacktestEngine,
    ValueBetDetector,
    SimpleMLModel,
    BacktestPerformance,
    BacktestMatch,
    BacktestBet,
)
from .advanced_ml_integration import (
    FullMLModel,
    MLModelType,
    MatchFeatures,
    MLModelPrediction,
    PeriodGoalAnalyzer,
    EnvironmentAnalyzer,
    HalfTimeAnalyzer,
    FullBacktestEngine,
    WeatherType,
    PitchCondition,
)
from .play_enhancement_plan import (
    generate_enhancement_report,
    PLAY_CHARACTERISTICS,
)

__all__ = [
    "StatisticalEngine",
    "DeepAnalysisEngine",
    "analyze_match",
    "analyze_all_matches",
    "SmartAdvisor",
    "get_advisor_analysis",
    "PoissonModel",
    "poisson_pmf",
    "EloRatingSystem",
    "StrategyConfig",
    "MatchProfiler",
    "StrategySelector",
    "PlayAnalyzer",
    "PlayProbabilityResult",
    "get_play_analyzer",
    "PlayType",
    "PlayStrategyFactory",
    "MixedParlayOptimizer",
    "ParlayStrategy",
    "PlayAdvancedAnalyzer",
    "PlayClusterAnalyzer",
    "EnhancedHistoricalAnalyzer",
    "DrawOptimizer",
    "ComebackPatternRecognizer",
    "RiskDiversifier",
    "KellyCriterionOptimizer",
    "ParlayPlanGenerator",
    "PreciseExpectedGoals",
    "OddsDeviationAnalyzer",
    "UnderdogResilienceAnalyzer",
    "HistoricalBacktestEngine",
    "ValueBetDetector",
    "SimpleMLModel",
    "BacktestPerformance",
    "BacktestMatch",
    "BacktestBet",
    "FullMLModel",
    "MLModelType",
    "MatchFeatures",
    "PeriodGoalAnalyzer",
    "EnvironmentAnalyzer",
    "HalfTimeAnalyzer",
    "FullBacktestEngine",
    "WeatherType",
    "PitchCondition",
]
