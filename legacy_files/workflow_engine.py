"""
工作流编排引擎 - 复杂任务的自动化执行
========================================

核心功能:
1. 定义可复用的工作流模板
2. 任务依赖管理
3. 并行/串行执行控制
4. 错误处理和重试机制
5. 执行状态追踪

工作流类型:
- 单场比赛深度分析
- 多场比赛批量分析
- 投资组合构建
- 串关组合优化
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable, Union
from enum import Enum
from datetime import datetime
from functools import wraps
import traceback

logger = logging.getLogger("lottery_mcp")


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class WorkflowStatus(Enum):
    """工作流状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # 部分成功


@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    status: TaskStatus
    data: Any = None
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    retry_count: int = 0
    
    @property
    def duration_ms(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    workflow_id: str
    status: WorkflowStatus
    task_results: Dict[str, TaskResult]
    data: Dict[str, Any] = field(default_factory=dict)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    errors: List[str] = field(default_factory=list)
    
    @property
    def duration_ms(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None
    
    @property
    def success_rate(self) -> float:
        if not self.task_results:
            return 0.0
        success_count = sum(
            1 for r in self.task_results.values()
            if r.status == TaskStatus.SUCCESS
        )
        return success_count / len(self.task_results)


@dataclass
class TaskConfig:
    """任务配置"""
    task_id: str
    name: str
    func: Callable[..., Awaitable[Any]]
    dependencies: List[str] = field(default_factory=list)
    retries: int = 3
    retry_delay: float = 1.0
    timeout: Optional[float] = None
    parallel: bool = True  # 是否可并行执行


class WorkflowEngine:
    """工作流引擎"""
    
    def __init__(self):
        self.workflows: Dict[str, WorkflowResult] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def execute_workflow(
        self,
        workflow_id: str,
        tasks: List[TaskConfig],
        context: Optional[Dict] = None,
    ) -> WorkflowResult:
        """
        执行工作流
        
        Args:
            workflow_id: 工作流ID
            tasks: 任务列表
            context: 共享上下文数据
            
        Returns:
            工作流执行结果
        """
        context = context or {}
        result = WorkflowResult(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            task_results={},
            start_time=time.time(),
        )
        self.workflows[workflow_id] = result
        
        # 构建依赖图
        dependency_graph = self._build_dependency_graph(tasks)
        completed_tasks: set = set()
        failed_tasks: set = set()
        
        try:
            while len(completed_tasks) + len(failed_tasks) < len(tasks):
                # 找出可执行的任务（依赖已满足）
                executable = self._get_executable_tasks(
                    tasks, dependency_graph, completed_tasks, failed_tasks
                )
                
                if not executable:
                    if failed_tasks:
                        # 有任务失败导致其他任务无法执行
                        break
                    await asyncio.sleep(0.1)
                    continue
                
                # 并行执行可执行任务
                task_futures = [
                    self._execute_task_with_retry(task, context, result)
                    for task in executable
                ]
                
                # 等待所有任务完成
                task_results = await asyncio.gather(*task_futures, return_exceptions=True)
                
                # 处理结果
                for task, task_result in zip(executable, task_results):
                    if isinstance(task_result, Exception):
                        failed_tasks.add(task.task_id)
                        result.task_results[task.task_id] = TaskResult(
                            task_id=task.task_id,
                            status=TaskStatus.FAILED,
                            error=str(task_result),
                        )
                        result.errors.append(
                            f"Task {task.name} failed: {task_result}"
                        )
                    else:
                        completed_tasks.add(task.task_id)
                        result.task_results[task.task_id] = task_result
                        # 将任务结果存入上下文
                        context[f"task_{task.task_id}_result"] = task_result.data
            
            # 确定最终状态
            if len(failed_tasks) == 0:
                result.status = WorkflowStatus.COMPLETED
            elif len(completed_tasks) == 0:
                result.status = WorkflowStatus.FAILED
            else:
                result.status = WorkflowStatus.PARTIAL
                
        except Exception as e:
            result.status = WorkflowStatus.FAILED
            result.errors.append(f"Workflow execution error: {e}")
            logger.error(f"Workflow {workflow_id} failed: {e}", exc_info=True)
        
        finally:
            result.end_time = time.time()
        
        return result
    
    def _build_dependency_graph(
        self, tasks: List[TaskConfig]
    ) -> Dict[str, List[str]]:
        """构建依赖图"""
        graph = {}
        task_ids = {t.task_id for t in tasks}
        
        for task in tasks:
            # 验证依赖存在
            for dep in task.dependencies:
                if dep not in task_ids:
                    raise ValueError(
                        f"Task {task.task_id} depends on unknown task {dep}"
                    )
            graph[task.task_id] = task.dependencies
        
        return graph
    
    def _get_executable_tasks(
        self,
        tasks: List[TaskConfig],
        dependency_graph: Dict[str, List[str]],
        completed: set,
        failed: set,
    ) -> List[TaskConfig]:
        """获取可执行的任务"""
        executable = []
        task_map = {t.task_id: t for t in tasks}
        
        for task_id, deps in dependency_graph.items():
            if task_id in completed or task_id in failed:
                continue
            
            # 检查依赖是否满足
            deps_satisfied = all(
                dep in completed for dep in deps
            )
            
            # 如果有依赖失败，标记为失败
            deps_failed = any(
                dep in failed for dep in deps
            )
            
            if deps_failed:
                failed.add(task_id)
                continue
            
            if deps_satisfied:
                executable.append(task_map[task_id])
        
        return executable
    
    async def _execute_task_with_retry(
        self,
        task: TaskConfig,
        context: Dict,
        workflow_result: WorkflowResult,
    ) -> TaskResult:
        """执行任务（带重试）"""
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.PENDING,
        )
        
        for attempt in range(task.retries + 1):
            result.start_time = time.time()
            result.status = TaskStatus.RUNNING
            
            try:
                # 准备参数
                kwargs = {"context": context, "workflow_id": workflow_result.workflow_id}
                
                # 执行
                if task.timeout:
                    data = await asyncio.wait_for(
                        task.func(**kwargs),
                        timeout=task.timeout,
                    )
                else:
                    data = await task.func(**kwargs)
                
                result.data = data
                result.status = TaskStatus.SUCCESS
                result.end_time = time.time()
                return result
                
            except Exception as e:
                result.retry_count = attempt
                result.error = str(e)
                
                if attempt < task.retries:
                    result.status = TaskStatus.RETRYING
                    await asyncio.sleep(task.retry_delay * (attempt + 1))
                else:
                    result.status = TaskStatus.FAILED
                    result.end_time = time.time()
                    logger.warning(
                        f"Task {task.name} failed after {task.retries} retries: {e}"
                    )
        
        return result
    
    def get_workflow_status(self, workflow_id: str) -> Optional[WorkflowStatus]:
        """获取工作流状态"""
        if workflow_id in self.workflows:
            return self.workflows[workflow_id].status
        return None
    
    def cancel_workflow(self, workflow_id: str):
        """取消工作流"""
        if workflow_id in self._running_tasks:
            self._running_tasks[workflow_id].cancel()
            logger.info(f"Workflow {workflow_id} cancelled")


# 预定义工作流模板
class WorkflowTemplates:
    """工作流模板"""
    
    @staticmethod
    def create_single_match_analysis_workflow(
        match_id: str,
        include_plays: List[str] = None,
    ) -> List[TaskConfig]:
        """
        创建单场比赛深度分析工作流
        
        任务顺序:
        1. 获取比赛数据
        2. 获取赔率数据
        3. 执行统计分析
        4. 分析5大玩法
        5. 协同验证
        6. 生成推荐
        """
        include_plays = include_plays or ["SPF", "RQSPF", "BF", "ZJQ", "BQC"]
        
        async def fetch_match_data(context, workflow_id):
            from .data_tools import get_cached_matches
            matches = get_cached_matches()
            for m in matches or []:
                if m.get("match_id") == match_id:
                    return {"match": m}
            raise ValueError(f"Match {match_id} not found")
        
        async def fetch_odds_data(context, workflow_id):
            match = context.get("task_fetch_match_result", {}).get("match", {})
            # 赔率数据已在match中
            return {"odds": match.get("odds", {})}
        
        async def run_statistical_analysis(context, workflow_id):
            from .analysis_tools import get_analysis_engine
            engine = get_analysis_engine()
            match = context.get("task_fetch_match_result", {}).get("match", {})
            result = await engine.analyze_match(match_id, depth="full")
            return {"analysis": result}
        
        async def analyze_plays(context, workflow_id):
            from lottery_mcp.analysis.play_analysis import get_play_analyzer
            analyzer = get_play_analyzer()
            analysis = context.get("task_statistical_analysis_result", {}).get("analysis", {})
            poisson = analysis.get("statistical_models", {}).get("poisson", {})
            odds = context.get("task_fetch_odds_result", {}).get("odds", {})
            match = context.get("task_fetch_match_result", {}).get("match", {})
            
            plays = analyzer.analyze_all_plays(poisson, odds, match.get("handicap", 0))
            return {
                "plays": {
                    k: {
                        "probabilities": v.probabilities,
                        "confidence": v.confidence,
                        "recommendations": v.recommendations,
                    }
                    for k, v in plays.items()
                    if k in include_plays
                }
            }
        
        async def run_synergy_validation(context, workflow_id):
            from lottery_mcp.analysis.play_synergy_plan import get_synergy_analyzer
            analyzer = get_synergy_analyzer()
            plays = context.get("task_analyze_plays_result", {}).get("plays", {})
            
            validation_data = {
                k: v.get("probabilities", {})
                for k, v in plays.items()
            }
            result = analyzer.validate_all_plays_consistency(validation_data)
            return {"validation": result}
        
        async def generate_recommendation(context, workflow_id):
            plays = context.get("task_analyze_plays_result", {}).get("plays", {})
            validation = context.get("task_synergy_validation_result", {}).get("validation", {})
            
            # 找出最佳推荐
            best_play = None
            best_score = 0
            
            for play_type, play_data in plays.items():
                recs = play_data.get("recommendations", [])
                if recs:
                    top_rec = max(recs, key=lambda x: x.get("expected_value", 0))
                    score = top_rec.get("expected_value", 0) * play_data.get("confidence", 0)
                    if score > best_score:
                        best_score = score
                        best_play = {
                            "play_type": play_type,
                            "selection": top_rec.get("selection"),
                            "probability": top_rec.get("probability"),
                            "odds": top_rec.get("odds"),
                            "expected_value": top_rec.get("expected_value"),
                        }
            
            return {
                "best_recommendation": best_play,
                "validation_passed": validation.get("overall_consistent", False),
            }
        
        return [
            TaskConfig("fetch_match", "获取比赛数据", fetch_match_data, retries=2),
            TaskConfig("fetch_odds", "获取赔率数据", fetch_odds_data, dependencies=["fetch_match"]),
            TaskConfig("statistical_analysis", "统计分析", run_statistical_analysis, dependencies=["fetch_match"]),
            TaskConfig("analyze_plays", "玩法分析", analyze_plays, dependencies=["statistical_analysis", "fetch_odds"]),
            TaskConfig("synergy_validation", "协同验证", run_synergy_validation, dependencies=["analyze_plays"]),
            TaskConfig("generate_recommendation", "生成推荐", generate_recommendation, dependencies=["analyze_plays", "synergy_validation"]),
        ]
    
    @staticmethod
    def create_portfolio_building_workflow(
        match_ids: List[str],
        bankroll: float = 1000.0,
        risk_profile: str = "moderate",
    ) -> List[TaskConfig]:
        """
        创建投资组合构建工作流
        
        任务顺序:
        1. 并行分析所有比赛
        2. 收集价值投注机会
        3. 优化投资组合分配
        4. 生成最终推荐
        """
        async def analyze_all_matches(context, workflow_id):
            """并行分析所有指定比赛"""
            from lottery_mcp.analysis.engine import analyze_match
            
            results = []
            for match_id in match_ids:
                try:
                    match_data = context.get("match_data", {}).get(match_id, {})
                    if not match_data:
                        logger.warning(f"工作流: 比赛数据缺失 {match_id}")
                        continue
                    
                    analysis = analyze_match(match_data)
                    results.append({
                        "match_id": match_id,
                        "analysis": analysis,
                        "success": True,
                    })
                except Exception as e:
                    logger.error(f"工作流: 比赛分析失败 {match_id}: {e}")
                    results.append({
                        "match_id": match_id,
                        "error": str(e),
                        "success": False,
                    })
            
            return {"analyzed_matches": results}
        
        async def collect_value_bets(context, workflow_id):
            """从分析结果中筛选价值投注（EV > 1.0 或 value_rating 为 S/A/B）"""
            analysis_results = context.get("task_analyze_matches_result", {}).get("analyzed_matches", [])
            value_bets = []

            for match_entry in analysis_results:
                if not match_entry.get("success", False):
                    continue

                match_id = match_entry.get("match_id", "")
                analysis = match_entry.get("analysis", {})

                # 遍历各玩法的 selections
                for play_type, play_data in analysis.items():
                    if not isinstance(play_data, dict):
                        continue

                    selections = play_data.get("selections", [])
                    if not selections:
                        # 兼容 recommendations 格式
                        recommendations = play_data.get("recommendations", [])
                        if recommendations:
                            selections = recommendations

                    for sel in selections:
                        ev = sel.get("expected_value", 0) or sel.get("ev", 0)
                        value_rating = sel.get("value_rating", "")

                        # 筛选条件: EV > 1.0 或 value_rating 为 S/A/B
                        is_value = ev > 1.0 or value_rating.upper() in ("S", "A", "B")
                        if is_value:
                            value_bets.append({
                                "match_id": match_id,
                                "play_type": play_type,
                                "selection": sel.get("selection", ""),
                                "probability": sel.get("probability", 0),
                                "odds": sel.get("odds", 0),
                                "expected_value": ev,
                                "value_rating": value_rating,
                                "confidence": play_data.get("confidence", 0),
                            })

            # 按 expected_value 降序排列
            value_bets.sort(key=lambda x: x.get("expected_value", 0), reverse=True)

            logger.info(f"收集到 {len(value_bets)} 个价值投注机会")
            return {"value_bets": value_bets}
        
        async def optimize_portfolio(context, workflow_id):
            from lottery_mcp.betting.portfolio import optimize_bet_portfolio
            
            value_bets = context.get("task_collect_value_bets_result", {}).get("value_bets", [])
            result = optimize_bet_portfolio(value_bets, bankroll, risk_profile)
            return {"portfolio": result}
        
        return [
            TaskConfig("analyze_matches", "分析比赛", analyze_all_matches),
            TaskConfig("collect_value_bets", "收集价值投注", collect_value_bets, dependencies=["analyze_matches"]),
            TaskConfig("optimize_portfolio", "优化组合", optimize_portfolio, dependencies=["collect_value_bets"]),
        ]

    @staticmethod
    def create_batch_analysis_workflow(match_ids: List[str]) -> List[TaskConfig]:
        """批量比赛分析工作流

        步骤:
        1. fetch_all_data: 并行获取所有比赛数据
        2. analyze_all_matches: 并行分析所有比赛（5大玩法）
        3. collect_value_bets: 收集所有比赛的价值投注
        4. generate_daily_report: 生成每日分析报告
        """
        async def fetch_all_data(context, workflow_id):
            """并行获取所有比赛数据"""
            from .data_tools import get_cached_matches

            async def fetch_single(mid):
                matches = get_cached_matches()
                for m in matches or []:
                    if m.get("match_id") == mid:
                        return {"match_id": mid, "match": m}
                raise ValueError(f"Match {mid} not found")

            # 并行获取所有比赛数据
            tasks = [fetch_single(mid) for mid in match_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_matches = {}
            errors = []
            for mid, result in zip(match_ids, results):
                if isinstance(result, Exception):
                    errors.append(f"获取比赛 {mid} 数据失败: {result}")
                    logger.warning(f"批量分析: 获取比赛 {mid} 数据失败: {result}")
                else:
                    all_matches[mid] = result.get("match", {})

            return {
                "matches": all_matches,
                "errors": errors,
                "total": len(match_ids),
                "fetched": len(all_matches),
            }

        async def analyze_all_matches(context, workflow_id):
            """并行分析所有比赛（5大玩法）"""
            from .analysis_tools import get_analysis_engine
            from lottery_mcp.analysis.play_analysis import get_play_analyzer

            matches_data = context.get("task_fetch_all_data_result", {}).get("matches", {})
            engine = get_analysis_engine()
            analyzer = get_play_analyzer()

            async def analyze_single(mid, match):
                try:
                    # 执行统计分析
                    analysis = await engine.analyze_match(mid, depth="full")

                    # 分析5大玩法
                    poisson = analysis.get("statistical_models", {}).get("poisson", {})
                    odds = match.get("odds", {})
                    handicap = match.get("handicap", 0)
                    plays = analyzer.analyze_all_plays(poisson, odds, handicap)

                    return {
                        "match_id": mid,
                        "success": True,
                        "analysis": analysis,
                        "plays": {
                            k: {
                                "probabilities": v.probabilities,
                                "confidence": v.confidence,
                                "recommendations": v.recommendations,
                            }
                            for k, v in plays.items()
                        },
                    }
                except Exception as e:
                    logger.error(f"批量分析: 比赛分析失败 {mid}: {e}")
                    return {"match_id": mid, "success": False, "error": str(e)}

            # 并行分析所有比赛
            tasks = [analyze_single(mid, m) for mid, m in matches_data.items()]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            analyzed = []
            for r in results:
                if isinstance(r, Exception):
                    analyzed.append({"match_id": "unknown", "success": False, "error": str(r)})
                else:
                    analyzed.append(r)

            success_count = sum(1 for a in analyzed if a.get("success", False))
            logger.info(f"批量分析: 完成 {success_count}/{len(analyzed)} 场比赛分析")

            return {"analyzed_matches": analyzed, "success_count": success_count}

        async def collect_value_bets(context, workflow_id):
            """收集所有比赛的价值投注"""
            analyzed_matches = context.get(
                "task_analyze_all_matches_result", {}
            ).get("analyzed_matches", [])
            value_bets = []

            for match_entry in analyzed_matches:
                if not match_entry.get("success", False):
                    continue

                match_id = match_entry.get("match_id", "")
                plays = match_entry.get("plays", {})

                for play_type, play_data in plays.items():
                    if not isinstance(play_data, dict):
                        continue

                    recommendations = play_data.get("recommendations", [])
                    for rec in recommendations:
                        ev = rec.get("expected_value", 0)
                        value_rating = rec.get("value_rating", "")

                        if ev > 1.0 or value_rating.upper() in ("S", "A", "B"):
                            value_bets.append({
                                "match_id": match_id,
                                "play_type": play_type,
                                "selection": rec.get("selection", ""),
                                "probability": rec.get("probability", 0),
                                "odds": rec.get("odds", 0),
                                "expected_value": ev,
                                "value_rating": value_rating,
                                "confidence": play_data.get("confidence", 0),
                            })

            value_bets.sort(key=lambda x: x.get("expected_value", 0), reverse=True)
            logger.info(f"批量分析: 收集到 {len(value_bets)} 个价值投注机会")

            return {"value_bets": value_bets}

        async def generate_daily_report(context, workflow_id):
            """生成每日分析报告"""
            analyzed_matches = context.get(
                "task_analyze_all_matches_result", {}
            ).get("analyzed_matches", [])
            value_bets = context.get(
                "task_collect_value_bets_result", {}
            ).get("value_bets", [])

            success_count = sum(1 for a in analyzed_matches if a.get("success", False))
            total_count = len(analyzed_matches)

            # 按玩法统计价值投注
            play_type_stats = {}
            for vb in value_bets:
                pt = vb.get("play_type", "unknown")
                if pt not in play_type_stats:
                    play_type_stats[pt] = {"count": 0, "avg_ev": 0, "total_ev": 0}
                play_type_stats[pt]["count"] += 1
                play_type_stats[pt]["total_ev"] += vb.get("expected_value", 0)

            for pt, stats in play_type_stats.items():
                if stats["count"] > 0:
                    stats["avg_ev"] = round(stats["total_ev"] / stats["count"], 3)

            report = {
                "generated_at": datetime.now().isoformat(),
                "summary": {
                    "total_matches": total_count,
                    "analyzed_success": success_count,
                    "value_bets_count": len(value_bets),
                    "success_rate": round(success_count / total_count, 2) if total_count > 0 else 0,
                },
                "play_type_distribution": play_type_stats,
                "top_value_bets": value_bets[:10],
                "match_details": [
                    {
                        "match_id": a.get("match_id"),
                        "success": a.get("success"),
                        "play_count": len(a.get("plays", {})),
                    }
                    for a in analyzed_matches
                ],
            }

            logger.info(f"批量分析: 生成每日报告完成，共 {len(value_bets)} 个价值投注")
            return {"report": report}

        return [
            TaskConfig("fetch_all_data", "并行获取比赛数据", fetch_all_data, parallel=True, retries=2),
            TaskConfig("analyze_all_matches", "并行分析比赛", analyze_all_matches, dependencies=["fetch_all_data"], parallel=True, retries=2),
            TaskConfig("collect_value_bets", "收集价值投注", collect_value_bets, dependencies=["analyze_all_matches"]),
            TaskConfig("generate_daily_report", "生成每日报告", generate_daily_report, dependencies=["collect_value_bets"]),
        ]


# 全局工作流引擎实例
_workflow_engine: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    """获取全局工作流引擎"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine


# 便捷函数
async def run_single_match_analysis(match_id: str) -> Dict[str, Any]:
    """运行单场比赛分析工作流"""
    engine = get_workflow_engine()
    tasks = WorkflowTemplates.create_single_match_analysis_workflow(match_id)
    result = await engine.execute_workflow(f"match_analysis_{match_id}", tasks)

    # 从 task_results 中提取各步骤的结果数据
    def _get_task_data(task_id: str) -> Any:
        task_result = result.task_results.get(task_id)
        if task_result and task_result.status == TaskStatus.SUCCESS:
            return task_result.data or {}
        return {}

    recommendation_data = _get_task_data("generate_recommendation")
    plays_data = _get_task_data("analyze_plays")
    validation_data = _get_task_data("synergy_validation")

    return {
        "workflow_id": result.workflow_id,
        "status": result.status.value,
        "success_rate": result.success_rate,
        "duration_ms": result.duration_ms,
        "recommendation": recommendation_data.get("best_recommendation", {}),
        "plays": plays_data.get("plays", {}),
        "validation": validation_data.get("validation", {}),
    }


async def run_portfolio_building(
    match_ids: List[str],
    bankroll: float = 1000.0,
    risk_profile: str = "moderate",
) -> Dict[str, Any]:
    """运行投资组合构建工作流"""
    engine = get_workflow_engine()
    tasks = WorkflowTemplates.create_portfolio_building_workflow(
        match_ids, bankroll, risk_profile
    )
    result = await engine.execute_workflow(
        f"portfolio_building_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        tasks,
    )

    # 从 task_results 中提取各步骤的结果数据
    def _get_task_data(task_id: str) -> Any:
        task_result = result.task_results.get(task_id)
        if task_result and task_result.status == TaskStatus.SUCCESS:
            return task_result.data or {}
        return {}

    portfolio_data = _get_task_data("optimize_portfolio")

    return {
        "workflow_id": result.workflow_id,
        "status": result.status.value,
        "success_rate": result.success_rate,
        "duration_ms": result.duration_ms,
        "portfolio": portfolio_data.get("portfolio", {}),
    }


async def run_batch_analysis(match_ids: List[str]) -> Dict[str, Any]:
    """运行批量比赛分析工作流"""
    engine = get_workflow_engine()
    tasks = WorkflowTemplates.create_batch_analysis_workflow(match_ids)
    result = await engine.execute_workflow(
        f"batch_analysis_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        tasks,
    )

    # 从 task_results 中提取各步骤的结果数据
    def _get_task_data(task_id: str) -> Any:
        task_result = result.task_results.get(task_id)
        if task_result and task_result.status == TaskStatus.SUCCESS:
            return task_result.data or {}
        return {}

    fetch_data = _get_task_data("fetch_all_data")
    analyzed_data = _get_task_data("analyze_all_matches")
    value_bets_data = _get_task_data("collect_value_bets")
    report_data = _get_task_data("generate_daily_report")

    return {
        "workflow_id": result.workflow_id,
        "status": result.status.value,
        "success_rate": result.success_rate,
        "duration_ms": result.duration_ms,
        "data_summary": {
            "total_matches": fetch_data.get("total", 0),
            "fetched_matches": fetch_data.get("fetched", 0),
            "fetch_errors": fetch_data.get("errors", []),
            "analyzed_success": analyzed_data.get("success_count", 0),
            "value_bets_count": len(value_bets_data.get("value_bets", [])),
        },
        "value_bets": value_bets_data.get("value_bets", []),
        "report": report_data.get("report", {}),
    }


__all__ = [
    "TaskStatus",
    "WorkflowStatus",
    "TaskResult",
    "WorkflowResult",
    "TaskConfig",
    "WorkflowEngine",
    "WorkflowTemplates",
    "get_workflow_engine",
    "run_single_match_analysis",
    "run_portfolio_building",
    "run_batch_analysis",
]
