"""
统一分析流水线 - 插件驱动的分析编排
=====================================
替代原有的 PlayAnalyzer.analyze_all_plays()，
使用插件架构实现"既解耦又耦合"的分析流程。

流水线阶段：
1. 数据准备 → 标准化输入
2. 并行分析 → 5个独立插件同时分析
3. 协同验证 → 跨玩法一致性检查
4. 组合发现 → 发现玩法间组合机会
5. 结果整合 → 生成统一报告

设计原则：
- 解耦：每个玩法独立分析，可单独替换/升级
- 耦合：通过验证规则和组合引擎实现协作
- 可扩展：新增玩法只需实现 PlayPlugin 接口
"""

import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from lottery_mcp.core.interfaces import PlayType, PlayAnalysisResult, PlayPlugin
from lottery_mcp.core.event_bus import EventBus, Event, EventNames
from lottery_mcp.core.plugin_registry import PluginRegistry
from lottery_mcp.analysis.synergy_validator import CrossPlaySynergyValidator
from lottery_mcp.analysis.combination_engine import SmartCombinationEngine

logger = logging.getLogger("lottery_mcp.pipeline")


class PipelineStage:
    """流水线阶段"""
    DATA_PREP = "data_preparation"
    PARALLEL_ANALYSIS = "parallel_analysis"
    SYNERGY_VALIDATION = "synergy_validation"
    COMBINATION_DISCOVERY = "combination_discovery"
    RESULT_INTEGRATION = "result_integration"


class UnifiedAnalysisPipeline:
    """
    统一分析流水线

    使用插件架构编排5大玩法的分析流程，
    替代原有的 PlayAnalyzer.analyze_all_plays()。
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        plugin_registry: Optional[PluginRegistry] = None,
    ):
        self._event_bus = event_bus or EventBus()
        self._registry = plugin_registry or PluginRegistry()
        self._synergy_validator = CrossPlaySynergyValidator(event_bus=self._event_bus)
        self._combination_engine = SmartCombinationEngine(event_bus=self._event_bus)
        self._plugins: Dict[PlayType, PlayPlugin] = {}

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def synergy_validator(self) -> CrossPlaySynergyValidator:
        return self._synergy_validator

    @property
    def combination_engine(self) -> SmartCombinationEngine:
        return self._combination_engine

    def register_plugin(self, plugin: PlayPlugin) -> bool:
        """注册玩法插件"""
        success = self._registry.register(plugin)
        if success:
            self._plugins[plugin.play_type] = plugin
            # 自动加载验证规则
            rules = plugin.get_validation_rules()
            for rule in rules:
                self._synergy_validator.add_rule(rule)
            logger.info(f"注册插件: {plugin.play_type.code} ({plugin.play_type.name_cn}), {len(rules)}条验证规则")

            # 发布事件
            self._event_bus.publish(Event(
                name=EventNames.PLUGIN_REGISTERED,
                data={"play_type": plugin.play_type.code, "version": plugin.version},
            ))
        return success

    def register_plugins(self, plugins: List[PlayPlugin]) -> int:
        """批量注册插件"""
        count = 0
        for plugin in plugins:
            if self.register_plugin(plugin):
                count += 1
        return count

    def analyze(
        self,
        match_context: Dict[str, Any],
        base_probabilities: Dict[str, float],
        odds: Dict[str, Any],
        enable_synergy: bool = True,
        enable_combination: bool = True,
    ) -> Dict[str, Any]:
        """
        执行完整的分析流水线

        Args:
            match_context: 比赛上下文
            base_probabilities: 基础概率（来自Poisson/Elo/xG模型）
            odds: 赔率数据
            enable_synergy: 是否启用协同验证
            enable_combination: 是否启用组合发现

        Returns:
            完整的分析报告
        """
        pipeline_start = time.time()
        report = {
            "pipeline_version": "2.0",
            "analyzed_at": datetime.now().isoformat(),
            "stages": {},
            "play_results": {},
            "synergy": None,
            "combinations": None,
            "summary": {},
        }

        # 阶段1: 数据准备
        stage_start = time.time()
        prepared = self._prepare_data(match_context, base_probabilities, odds)
        report["stages"][PipelineStage.DATA_PREP] = {
            "status": "completed",
            "duration_ms": round((time.time() - stage_start) * 1000, 1),
        }

        # 阶段2: 并行分析（5个独立插件）
        stage_start = time.time()
        play_results = self._parallel_analyze(prepared["match_context"], prepared["base_probabilities"], prepared["odds"])
        report["play_results"] = {
            pt.code: result.to_dict() for pt, result in play_results.items()
        }
        report["stages"][PipelineStage.PARALLEL_ANALYSIS] = {
            "status": "completed",
            "plays_analyzed": len(play_results),
            "duration_ms": round((time.time() - stage_start) * 1000, 1),
        }

        # 阶段3: 协同验证
        if enable_synergy and len(play_results) > 1:
            stage_start = time.time()
            validation_results = self._synergy_validator.validate_all(play_results)
            report["synergy"] = validation_results

            # 应用置信度调整
            self._apply_confidence_adjustments(play_results, validation_results)

            report["stages"][PipelineStage.SYNERGY_VALIDATION] = {
                "status": "completed",
                "is_consistent": validation_results["is_consistent"],
                "violations": len(validation_results["violations"]),
                "synergy_opportunities": len(validation_results["synergy_opportunities"]),
                "duration_ms": round((time.time() - stage_start) * 1000, 1),
            }

        # 阶段4: 组合发现
        if enable_combination and len(play_results) > 1 and report.get("synergy"):
            stage_start = time.time()
            combinations = self._combination_engine.find_combinations(
                play_results, report["synergy"]
            )
            report["combinations"] = combinations
            report["stages"][PipelineStage.COMBINATION_DISCOVERY] = {
                "status": "completed",
                "combinations_found": len(combinations),
                "duration_ms": round((time.time() - stage_start) * 1000, 1),
            }

        # 阶段5: 结果整合
        stage_start = time.time()
        report["summary"] = self._build_summary(play_results, report)
        report["stages"][PipelineStage.RESULT_INTEGRATION] = {
            "status": "completed",
            "duration_ms": round((time.time() - stage_start) * 1000, 1),
        }

        # 总耗时
        report["total_duration_ms"] = round((time.time() - pipeline_start) * 1000, 1)

        # 发布完成事件
        self._event_bus.publish(Event(
            name=EventNames.PLAY_ANALYSIS_COMPLETED,
            data={
                "plays_analyzed": len(play_results),
                "is_consistent": report["synergy"]["is_consistent"] if report.get("synergy") else True,
                "combinations": len(report.get("combinations") or []),
                "duration_ms": report["total_duration_ms"],
            },
        ))

        logger.info(
            f"分析流水线完成: {len(play_results)}个玩法, "
            f"{'一致' if (report.get('synergy') or {}).get('is_consistent', True) else '存在冲突'}, "
            f"{report['total_duration_ms']}ms"
        )

        return report

    def analyze_single(
        self,
        play_type: PlayType,
        match_context: Dict[str, Any],
        base_probabilities: Dict[str, float],
        odds: Dict[str, Any],
    ) -> Optional[PlayAnalysisResult]:
        """分析单个玩法（解耦的核心 - 可独立调用）"""
        plugin = self._plugins.get(play_type)
        if not plugin:
            logger.warning(f"未注册的玩法: {play_type.code}")
            return None

        return plugin.analyze(match_context, base_probabilities, odds)

    def _prepare_data(
        self,
        match_context: Dict[str, Any],
        base_probabilities: Dict[str, float],
        odds: Dict[str, Any],
    ) -> Dict[str, Any]:
        """数据准备阶段：标准化输入并验证数据完整性"""
        from lottery_mcp.analysis.plays.base import build_poisson_matrix
        from lottery_mcp.analysis.data_validator import validate_base_probabilities

        # 1. 验证基础概率数据完整性
        validation_result = validate_base_probabilities(
            base_probabilities,
            context=f"pipeline_{match_context.get('match_id', 'unknown')}"
        )
        
        if not validation_result.is_valid:
            # 记录验证错误但不中断流程（使用默认值）
            logger.warning(
                f"基础概率数据验证失败: {[e.message for e in validation_result.errors]}"
            )

        prepared_base = dict(base_probabilities)
        
        # 2. 设置默认值（如果验证失败或字段缺失）
        prepared_base.setdefault("home_expected_goals", 1.2)
        prepared_base.setdefault("away_expected_goals", 1.0)
        prepared_base.setdefault("win_prob", 0.33)
        prepared_base.setdefault("draw_prob", 0.33)
        prepared_base.setdefault("lose_prob", 0.33)

        # 3. 自动生成比分概率矩阵（供BF/ZJQ/BQC共享）
        if "score_probabilities" not in prepared_base or not prepared_base["score_probabilities"]:
            home_exp = prepared_base["home_expected_goals"]
            away_exp = prepared_base["away_expected_goals"]
            matrix = build_poisson_matrix(home_exp, away_exp, max_goals=8)
            prepared_base["score_probabilities"] = {
                f"{h}:{a}": p for (h, a), p in matrix.items()
            }

        # 4. 记录数据质量信息
        prepared_base["_data_quality"] = {
            "is_valid": validation_result.is_valid,
            "warnings": validation_result.warnings,
            "validation_errors": len(validation_result.errors),
        }

        return {
            "match_context": match_context or {},
            "base_probabilities": prepared_base,
            "odds": odds or {},
        }

    def _parallel_analyze(
        self,
        match_context: Dict[str, Any],
        base_probabilities: Dict[str, float],
        odds: Dict[str, Any],
    ) -> Dict[PlayType, PlayAnalysisResult]:
        """真并行分析阶段：使用 ThreadPoolExecutor 并发执行所有插件"""
        results = {}

        def _analyze_one(play_type: PlayType, plugin: PlayPlugin) -> tuple:
            try:
                start = time.time()
                result = plugin.analyze(match_context, base_probabilities, odds)
                duration = round((time.time() - start) * 1000, 1)
                logger.debug(f"{play_type.code} 分析完成: {duration}ms, conf={result.confidence}")
                return play_type, result
            except Exception as e:
                logger.error(f"{play_type.code} 分析失败: {e}")
                return play_type, PlayAnalysisResult(
                    play_type=play_type,
                    analysis_notes=[f"分析失败: {e}"],
                )

        with ThreadPoolExecutor(max_workers=min(len(self._plugins), 5)) as executor:
            futures = {
                executor.submit(_analyze_one, pt, plugin): pt
                for pt, plugin in self._plugins.items()
            }
            for future in as_completed(futures):
                play_type, result = future.result()
                results[play_type] = result

        return results

    @staticmethod
    def _apply_confidence_adjustments(
        results: Dict[PlayType, PlayAnalysisResult],
        validation_results: Dict[str, Any],
    ) -> None:
        """应用置信度调整"""
        adjustments = validation_results.get("confidence_adjustments", {})
        for play_type, result in results.items():
            adj = adjustments.get(play_type.code, 0.0)
            if adj != 0.0:
                result.confidence = max(0.0, min(1.0, result.confidence + adj))

    @staticmethod
    def _build_summary(
        play_results: Dict[PlayType, PlayAnalysisResult],
        report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """构建分析摘要"""
        best_picks = []
        for pt, result in play_results.items():
            best = result.get_best_selection()
            if best:
                best_picks.append({
                    "play": pt.code,
                    "play_name": pt.name_cn,
                    "selection": best.selection,
                    "probability": best.probability,
                    "odds": best.odds,
                    "expected_value": best.expected_value,
                    "confidence": result.confidence,
                })

        # 按置信度排序
        best_picks.sort(key=lambda x: x["confidence"], reverse=True)

        synergy = report.get("synergy") or {}
        combinations = report.get("combinations") or []

        return {
            "best_picks": best_picks,
            "top_recommendation": best_picks[0] if best_picks else None,
            "is_consistent": synergy.get("is_consistent", True),
            "synergy_count": len(synergy.get("synergy_opportunities", [])),
            "combination_count": len(combinations),
            "top_combination": combinations[0] if combinations else None,
        }

    def get_registered_plays(self) -> List[str]:
        """获取已注册的玩法列表"""
        return [pt.code for pt in self._plugins.keys()]

    def get_plugin_count(self) -> int:
        """获取已注册插件数量"""
        return len(self._plugins)


def create_default_pipeline() -> UnifiedAnalysisPipeline:
    """创建默认流水线（注册所有5大玩法插件）"""
    from lottery_mcp.analysis.plays import SPFPlugin, RQSPFPlugin, BFPlugin, ZJQPlugin, BQCPlugin

    pipeline = UnifiedAnalysisPipeline()
    pipeline.register_plugins([
        SPFPlugin(),
        RQSPFPlugin(),
        BFPlugin(),
        ZJQPlugin(),
        BQCPlugin(),
    ])
    return pipeline
