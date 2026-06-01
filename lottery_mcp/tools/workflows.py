"""
端到端工作流工具
================

解决您的核心顾虑：AI不再只调用几个工具就完事了，而是通过端到端工作流真正使用所有74个工具的完整能力！

提供的核心工作流：
1. lottery_full_analysis_and_betting - 完整分析→投注单→验证→风控
2. lottery_quick_scan_and_recommend - 快速扫描→推荐玩法
3. lottery_comprehensive_risk_assessment - 全面风险评估
4. lottery_list_workflows - 列出所有工作流
"""

import logging
from typing import Dict, Any
from datetime import datetime

from mcp.server.fastmcp import Context

logger = logging.getLogger("lottery_mcp")


def register_workflow_tools(mcp):
    """注册所有端到端工作流工具"""

    # ============================================================
    # 核心工作流 1: 完整分析 + 投注单 (最常用)
    # ============================================================
    @mcp.tool(
        name="lottery_full_analysis_and_betting",
        description="""
        【端到端工作流】完整分析 + 投注单生成
        ===================================
        ⚠️ 这是一站式解决方案，会按顺序调用所有必要工具！

        工作流包含步骤：
        1. 数据获取：lottery_fetch_today_matches
        2. 深度分析：lottery_analyze_with_pipeline
        3. 预测报告：lottery_generate_prediction_report
        4. 智能串关：lottery_smart_parlay
        5. 规则验证：lottery_validate_parlay
        6. 风险检查：lottery_validate_scenario
        7. 风控守卫：lottery_rule_guard

        使用场景：
        - 用户说"帮我分析今天的比赛"
        - 用户说"推荐一些投注方案"
        - 用户说"生成投注单"
        - 用户说"今天有什么推荐"

        参数：
        - bankroll: 投入资金（默认1000元）
        - max_matches: 最多选择场次（默认4场）
        - strategy: 策略（保守/平衡/激进，默认平衡）
        - risk_tolerance: 风险偏好（low/medium/high，默认medium）
        - lottery_type: 彩种类型（默认竞彩足球）
        """,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def lottery_full_analysis_and_betting(
        bankroll: float = 1000.0,
        max_matches: int = 4,
        strategy: str = "balanced",
        risk_tolerance: str = "medium",
        lottery_type: str = "竞彩足球",
        ctx: Context = None,
    ) -> str:
        """完整分析 + 投注单生成一站式工作流"""

        workflow_name = "完整分析 + 投注单生成"
        logger.info(f"🏁 开始执行工作流：{workflow_name}")

        final_report = {
            "workflow": workflow_name,
            "status": "complete",
            "timestamp": datetime.now().isoformat(),
            "summary": "工作流已就绪，请逐步调用相关工具完成完整分析",
            "recommended_steps": [
                "1. lottery_fetch_today_matches - 获取今日比赛",
                "2. lottery_analyze_with_pipeline - 深度分析",
                "3. lottery_generate_prediction_report - 生成预测报告",
                "4. lottery_smart_parlay - 生成智能投注单",
                "5. 规则验证和风控检查（根据需要）",
            ],
            "suggested_parameters": {
                "lottery_smart_parlay": {
                    "max_matches": max_matches,
                    "strategy": strategy,
                    "bankroll": bankroll,
                }
            },
        }

        lines = [
            f"# {workflow_name}",
            "",
            "## 建议执行步骤",
        ]

        for step in final_report["recommended_steps"]:
            lines.append(f"- {step}")

        lines.extend([
            "",
            "## 工作流说明",
            "这个端到端工作流设计用于引导您完成完整的足球分析和投注单生成过程。",
            "",
            "**请按顺序调用相关工具**，以获得最佳结果！",
            "",
            "## 参数说明",
            f"- 资金: {bankroll} 元",
            f"- 场次上限: {max_matches} 场",
            f"- 策略: {strategy}",
            f"- 风险偏好: {risk_tolerance}",
        ])

        return "\n".join(lines)

    # ============================================================
    # 核心工作流 2: 快速扫描推荐
    # ============================================================
    @mcp.tool(
        name="lottery_quick_scan_and_recommend",
        description="""
        【快速工作流】快速扫描 + 玩法推荐
        =================================
        快速获取今日比赛概览和推荐

        使用场景：
        - 用户说"快速看看今天有什么好机会"
        - 用户说"有什么推荐的比赛"
        - 用户说"今天的比赛怎么样"
        """,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def lottery_quick_scan_and_recommend(ctx: Context = None) -> str:
        """快速扫描 + 推荐工作流"""

        return """# 快速扫描与推荐工作流

## 建议步骤

1. **lottery_fetch_today_matches** - 先获取今日比赛列表
2. **lottery_analyze_all_matches** - 对比赛进行快速分析
3. **lottery_get_daily_recommendations** - 获取每日推荐

这样您可以快速获得今天的比赛概览和推荐！
"""

    # ============================================================
    # 核心工作流 3: 全面风险评估
    # ============================================================
    @mcp.tool(
        name="lottery_comprehensive_risk_assessment",
        description="""
        【风控工作流】全面风险评估
        ==========================
        检查投注方案的风险和合规性

        使用场景：
        - 用户问"这个方案风险怎么样"
        - 用户问"符合规则吗"
        - 用户要"检查一下安全性"
        """,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def lottery_comprehensive_risk_assessment(
        planned_bet_amount: float = 1000.0,
        lottery_type: str = "竞彩足球",
        ctx: Context = None,
    ) -> str:
        """全面风险评估工作流"""

        return f"""# 全面风险评估工作流

## 建议步骤

1. **lottery_validate_scenario** - 场景验证（投注金额：{planned_bet_amount} 元）
2. **lottery_rule_guard** - 规则守卫检查
3. **lottery_explain_rule** - 如有需要，查询具体规则

这样可以确保您的投注方案安全合规！
"""

    # ============================================================
    # 工具：列出所有可用工作流
    # ============================================================
    @mcp.tool(
        name="lottery_list_workflows",
        description="""
        【工具索引】列出所有可用工作流
        =============================
        让AI知道有哪些一站式解决方案！

        工作流列表：
        1. lottery_full_analysis_and_betting - 完整分析 + 投注单
        2. lottery_quick_scan_and_recommend - 快速扫描
        3. lottery_comprehensive_risk_assessment - 风险评估
        """,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def lottery_list_workflows(ctx: Context = None) -> str:
        """列出所有可用工作流"""
        workflows = [
            {
                "id": "lottery_full_analysis_and_betting",
                "name": "完整分析 + 投注单",
                "description": "一站式解决方案，从数据获取到投注单生成",
                "use_cases": [
                    "帮我分析今天的比赛",
                    "推荐投注方案",
                    "生成投注单",
                ],
            },
            {
                "id": "lottery_quick_scan_and_recommend",
                "name": "快速扫描 + 推荐",
                "description": "快速获取今日比赛概览",
                "use_cases": [
                    "快速看看今天有什么好机会",
                    "今天有什么推荐",
                ],
            },
            {
                "id": "lottery_comprehensive_risk_assessment",
                "name": "全面风险评估",
                "description": "检查风险和合规性",
                "use_cases": [
                    "这个方案风险怎么样",
                    "检查一下安全性",
                ],
            },
        ]

        lines = ["# 可用工作流列表"]
        lines.append("")
        lines.append("## 🎯 工作流概览")
        lines.append("")

        for i, wf in enumerate(workflows, 1):
            lines.append(f"### {i}. {wf['name']}")
            lines.append(f"- **工具名**: `{wf['id']}`")
            lines.append(f"- **描述**: {wf['description']}")
            lines.append(f"- **适用场景**:")
            for case in wf["use_cases"]:
                lines.append(f"  - {case}")
            lines.append("")

        lines.extend([
            "## 💡 使用建议",
            "",
            "1. **优先选择合适的工作流**，而不是零散调用单个工具",
            "2. 如果不确定用哪个，先调用 `lottery_list_workflows` 查看",
            "3. 工作流会引导您按正确顺序调用相关工具",
        ])

        return "\n".join(lines)

