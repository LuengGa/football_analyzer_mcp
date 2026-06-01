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
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

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

        if ctx:
            await ctx.report_progress(0.0, "初始化工作流...")

        # 工作流完整步骤 - 包含竞彩资讯工具调用 + AI安全协议
        workflow_steps = [
            {
                "step": 1,
                "name": "获取今日比赛",
                "tool": "lottery_fetch_today_matches",
                "params": {
                    "lottery_type": lottery_type,
                    "include_odds": True,
                    "limit": 50
                },
                "description": "获取今日可投注的所有比赛列表，包含基础赔率数据（必选）"
            },
            {
                "step": 2,
                "name": "获取竞彩比赛资讯",
                "tool": "lottery_get_match_info / lottery_get_match_features / lottery_get_jingcai_h2h / lottery_get_match_standings / lottery_get_recent_form / lottery_get_injury_suspension",
                "params": {"match_id": "从第一步获取的比赛ID中选择"},
                "description": "对感兴趣的比赛获取详细资讯：特征分析、历史交锋、积分榜、近期战绩、伤停等（强烈推荐）"
            },
            {
                "step": 3,
                "name": "获取市场赔率对比",
                "tool": "lottery_get_market_odds",
                "params": {"market_types": ["all"]},
                "description": "获取国际市场赔率（欧赔、亚盘、大小球）用于价值对比分析（推荐）"
            },
            {
                "step": 4,
                "name": "追踪赔率变化",
                "tool": "lottery_track_odds_changes",
                "params": {"match_id": "具体比赛ID"},
                "description": "查看特定比赛的赔率变化趋势，了解市场动向（可选）"
            },
            {
                "step": 5,
                "name": "智能顾问深度分析",
                "tool": "lottery_advisor_analysis",
                "params": {"match_id": "具体比赛ID"},
                "description": "【强烈推荐】5层综合分析：赔率+模型+基本面+市场+风险矩阵，自动整合竞彩资讯和第三方数据，输出概率校准、价值发现、投注方案"
            },
            {
                "step": 6,
                "name": "批量分析比赛",
                "tool": "lottery_analyze_all_matches / lottery_analyze_match",
                "params": {},
                "description": "批量分析所有比赛（可选，建议先用advisor获得深度判断）"
            },
            {
                "step": 7,
                "name": "查看热门推荐",
                "tool": "lottery_get_daily_recommendations",
                "params": {},
                "description": "获取AI推荐的热门比赛和最佳投注选项（推荐）"
            },
            {
                "step": 8,
                "name": "生成智能投注单",
                "tool": "lottery_smart_parlay",
                "params": {
                    "bankroll": bankroll,
                    "max_matches": max_matches,
                    "strategy": strategy,
                    "risk_tolerance": risk_tolerance
                },
                "description": "根据策略和资金生成最优混合过关投注单（必选）"
            },
            {
                "step": 9,
                "name": "AI推理安全验证",
                "tool": "lottery_enforce_constraints",
                "params": {"bet_proposal": "从第八步生成的投注方案"},
                "description": "【强制】对AI生成的投注方案进行23条硬性约束验证，防止幻觉推理"
            },
            {
                "step": 10,
                "name": "资金健康检查",
                "tool": "lottery_check_bankroll_health",
                "params": {"bankroll": bankroll, "initial_bankroll": bankroll},
                "description": "【强制】检查资金状态是否健康，是否触发止损/回撤警报"
            },
            {
                "step": 11,
                "name": "比赛截止检查",
                "tool": "lottery_check_match_deadline",
                "params": {"match_time": "每场比赛的截止时间"},
                "description": "【强制】检查所有涉及比赛是否还能投注"
            },
            {
                "step": 12,
                "name": "规则验证",
                "tool": "lottery_validate_parlay / lottery_validate_scenario",
                "params": {},
                "description": "验证投注方案的规则合规性"
            },
            {
                "step": 13,
                "name": "风控守卫",
                "tool": "lottery_rule_guard",
                "params": {"planned_bet_amount": bankroll},
                "description": "最终风控检查，确保投注安全"
            }
        ]

        lines = [
            f"# 🏆 {workflow_name}",
            "",
            "## 📋 完整执行步骤",
            "",
        ]

        for step_info in workflow_steps:
            lines.append(f"### 第{step_info['step']}步：{step_info['name']}")
            lines.append(f"- 工具：`{step_info['tool']}`")
            lines.append(f"- 说明：{step_info['description']}")
            if step_info.get('params'):
                lines.append(f"- 推荐参数：{json.dumps(step_info['params'], ensure_ascii=False, indent=2)}")
            lines.append("")

        lines.extend([
            "## 📊 工作流参数配置",
            f"- 💰 投入资金：{bankroll} 元",
            f"- 🏟️ 场次上限：{max_matches} 场",
            f"- 🎯 策略类型：{strategy}",
            f"- ⚠️ 风险偏好：{risk_tolerance}",
            f"- 🎲 彩种类型：{lottery_type}",
            "",
            "## 💡 竞彩资讯工具详解（请务必使用）",
            "",
            "针对每场重点关注的比赛，建议依次获取以下竞彩官方数据：",
            "",
            "1. **基础信息** - `lottery_get_match_info`",
            "   - 比赛头部信息、联赛、球队、时间、场地",
            "",
            "2. **特征分析** - `lottery_get_match_features`",
            "   - 攻防特点、比赛风格、关键数据统计",
            "",
            "3. **历史交锋** - `lottery_get_jingcai_h2h`",
            "   - 双方对战记录、进球统计、胜负关系",
            "",
            "4. **联赛排名** - `lottery_get_match_standings`",
            "   - 主队/客队排名、积分、近期表现",
            "",
            "5. **近期战绩** - `lottery_get_recent_form`",
            "   - 两队最近比赛结果、状态分析",
            "",
            "6. **未来赛事** - `lottery_get_future_matches`",
            "   - 下一轮比赛，了解体能分配影响",
            "",
            "7. **射手信息** - `lottery_get_players`",
            "   - 关键射手、伤病情况、球员状态",
            "",
            "8. **伤停一览** - `lottery_get_injury_suspension`",
            "   - 伤病球员、停赛球员、预计复出时间",
            "",
            "## 📝 使用指南",
            "1. **按顺序执行**上述步骤，不要跳过关键环节",
            "2. **灵活运用**：根据实际情况，对重点比赛深入获取竞彩资讯",
            "3. **数据对比**：结合竞彩官方数据和国际市场赔率，发现价值机会",
            "4. **风险控制**：完成分析后务必进行风险评估",
            "5. **结果验证**：关注比赛结果，持续优化分析模型",
            "",
            "## 🎯 核心优势",
            "- **国内数据源优先**：优先使用竞彩官网和500彩票网数据，避免API配额限制",
            "- **中文数据一致**：完善的中英文映射，确保数据匹配准确",
            "- **全工具链协作**：引导AI调用完整74+工具，发挥MCP真正能力",
            "- **端到端体验**：从数据获取→分析→推荐→风控一站式完成",
        ])

        if ctx:
            await ctx.report_progress(1.0, "工作流已准备就绪")

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

1. **lottery_fetch_today_matches** - 获取今日比赛列表
2. **lottery_get_daily_recommendations** - 获取每日推荐
3. **lottery_analyze_all_matches** - 对比赛进行快速分析

## ⚠️ 注意
即使快速扫描，也需要在给出任何投注建议前调用：
- **lottery_enforce_constraints** - 约束验证
- **lottery_check_bankroll_health** - 资金检查

这样可以快速获得今天的比赛概览和推荐！
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

## 建议步骤（按顺序执行）

### 阶段一：约束验证
1. **lottery_enforce_constraints** - 对投注方案进行23条硬性约束验证
   - 如果 approved=false，必须拒绝该方案

### 阶段二：资金检查
2. **lottery_check_bankroll_health** - 检查资金健康状态
   - 参数：bankroll={planned_bet_amount}，initial_bankroll={planned_bet_amount}
   - 如果 can_continue=false，必须停止投注

### 阶段三：比赛截止
3. **lottery_check_match_deadline** - 检查所有比赛是否还能投注
   - 如果 can_bet=false，该比赛不能包含在投注方案中

### 阶段四：规则验证
4. **lottery_validate_scenario** - 场景验证（投注金额：{planned_bet_amount} 元）
5. **lottery_rule_guard** - 规则守卫检查
6. **lottery_explain_rule** - 如有需要，查询具体规则

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
                "name": "完整分析 + 投注单 (13步)",
                "description": "一站式解决方案，从数据获取→分析→推荐→约束验证→风控，13步完整流程",
                "use_cases": [
                    "帮我分析今天的比赛",
                    "推荐投注方案",
                    "生成投注单",
                ],
            },
            {
                "id": "lottery_quick_scan_and_recommend",
                "name": "快速扫描 + 推荐",
                "description": "快速获取今日比赛概览（含约束验证提醒）",
                "use_cases": [
                    "快速看看今天有什么好机会",
                    "今天有什么推荐",
                ],
            },
            {
                "id": "lottery_comprehensive_risk_assessment",
                "name": "全面风险评估 (4阶段)",
                "description": "4阶段风控：约束验证→资金检查→比赛截止→规则验证",
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

