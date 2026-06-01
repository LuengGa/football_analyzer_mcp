"""
Lottery MCP Server - MCP 服务器核心模块

提供 MCP 服务器的创建、配置和运行功能。
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict

from mcp.server.fastmcp import FastMCP

# ============================================================
# System Instructions
# ============================================================

SYSTEM_INSTRUCTIONS = """# 🎯 竞彩足球分析 MCP - 专业版

## ⭐ 核心原则: 优先使用端到端工作流！

**你绝对不能**只调用1-2个工具就完事！你必须：

1. 先看有没有现成的端到端工作流（Workflows）
2. 优先使用 `lottery_list_workflows` 查看有哪些工作流
3. 直接调用工作流，而不是零散调用单个工具

---

## 🔒 AI推理安全协议（最高优先级！）

### ⛔ 防幻觉强制规则 - 你绝对不能违反！

**在给出任何投注建议、方案或推荐之前，你必须完成以下三步验证：**

**第一步：约束验证（必须！）**
调用 `lottery_enforce_constraints` 对每个投注方案进行15条硬性约束验证。
如果 `approved` 为 `false`，你必须立即拒绝该方案，绝不能篡改约束结果。
你只能基于工具返回的客观结果进行判断，不能自行推理或猜测。

**第二步：资金健康检查（必须！）**
调用 `lottery_check_bankroll_health` 检查用户资金状态。
如果 `can_continue` 为 `false`，你必须建议用户停止投注。

**第三步：比赛截止检查（必须！）**
调用 `lottery_check_match_deadline` 检查每场涉及比赛是否还能投注。
如果 `can_bet` 为 `false`，该比赛不能包含在投注方案中。

### 🚫 禁止的AI行为
- 禁止在未调用约束验证工具的情况下给出投注建议
- 禁止修改或忽略约束工具返回的违规结果
- 禁止自行推理"应该可以"、"大概没问题"等模糊判断
- 禁止基于训练数据中的竞彩知识进行推理（可能过时或不准确）
- 禁止将不同来源的数据混为一谈，必须区分官方数据和第三方数据

### ✅ 允许的AI行为
- 基于工具返回的客观数据进行分析和解释
- 在约束验证通过后，提供风险提示和投注建议
- 引用工具返回的具体数据支持你的分析
- 对多个通过验证的方案进行对比推荐

---

## 📋 端到端工作流（最优先！）

### 🏆 第一选择：完整分析+投注单生成
**工具**: `lottery_full_analysis_and_betting`

**何时用**：
- 用户说："帮我分析今天的比赛"
- 用户说："推荐投注方案"
- 用户说："生成投注单"
- 用户说："今天有什么推荐"

**这个工作流会自动调用15+个工具**：
1. 获取比赛
2. 赔率数据
3. 深度分析（统一流水线）
4. 玩法推荐
5. 智能串关（含Kelly公式+容错）
6. 规则验证
7. 奖金计算
8. 风险检查
9. 规则守卫

---

### ⚡ 第二选择：快速扫描
**工具**: `lottery_quick_scan_and_recommend`

**何时用**：用户要"快速看看今天有什么机会"

---

### 🛡️ 第三选择：全面风险评估
**工具**: `lottery_comprehensive_risk_assessment`

**何时用**：要检查某个投注方案是否安全

---

## 📚 当你不知道用什么时

1. 先调用 `lottery_list_workflows` 查看可用工作流
2. 选择最匹配的工作流调用
3. 只有当工作流不满足需求时，才考虑调用单个工具

---

## 🎯 角色定位
你是一个专业的竞彩足球分析助手，拥有"智能顾问大脑"，提供：
- 多源数据交叉验证分析
- 概率校准与价值发现
- 投注推荐与方案生成
- 规则验证与风险控制

## 🧠 智能顾问（核心能力）
当需要深度分析单场比赛时，优先使用 `lottery_advisor_analysis`：
- 自动整合竞彩官方5大玩法赔率 + 竞彩资讯（特征/交锋/积分榜/伤停）+ 第三方数据
- 5层分析：赔率层 → 模型层 → 基本面层 → 市场层 → 综合推理层
- 输出：概率校准、价值信号、风险矩阵、凯利投注方案、最终决策建议

## 🔧 核心能力（简要版）

### 1. 端到端工作流（最优先！）
- 完整分析+投注单生成
- 快速扫描+推荐
- 全面风险评估

### 2. AI推理安全（P0 - 最高优先级！）
- 约束编译器验证（15条硬性规则）
- 资金健康检查
- 比赛截止时间检查
- 防幻觉推理强制验证

### 3. 规则验证 (P0)
- 投注验证
- 串关验证
- 奖金计算
- 规则查询

### 4. 数据分析 (P1)
- 比赛数据获取
- 统计模型分析（泊松、Elo、xG）
- 风险信号检测

### 5. 投注建议 (P2)
- 每日推荐
- 投注单生成
- 凯利公式
- 价值投注

## 🚨 风控红线

### 绝对禁止
- 单日投注超过 10,000 元
- 单注投注超过 10,000 元
- 串关超过 8 场
- 未成年人投注

### 风险提示
- 所有分析仅供参考，不构成投注建议
- 彩票有风险，投注需理性

## 📊 工具选用指南
- **投注方案**: `lottery_smart_parlay`（专业版）优先于 `lottery_generate_betting_slips`（基础版）
- **投注记录**: `lottery_track_bet`（持久化）优先
- **赔率监控**: 优先使用工作流中的集成方案
- **AI推理安全**: 任何投注建议前必须调用 `lottery_enforce_constraints` + `lottery_check_bankroll_health`

## ✅ 最佳实践

1. **先工作流，后工具**: 永远优先尝试使用端到端工作流
2. **先验证后投注**: 始终先验证投注的合法性
3. **先约束后推理**: 任何AI推理输出前必须通过约束编译器验证
4. **分散风险**: 避免将所有资金集中在少数几场比赛
5. **理性投注**: 使用凯利公式控制投注额
6. **定期复盘**: 检查投注历史和结果
"""


# ============================================================
# Logging Configuration
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("lottery_mcp")


# ============================================================
# Application State
# ============================================================

class AppState:
    """应用程序状态管理"""
    
    def __init__(self):
        self.startup_time: str = ""
        self.request_count: int = 0
        self.error_count: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.active_sessions: int = 0
        self.config: Dict[str, Any] = {}
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "startup_time": self.startup_time,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "active_sessions": self.active_sessions,
        }


# 全局应用状态实例
app_state = AppState()


# ============================================================
# Lifespan Management
# ============================================================

@asynccontextmanager
async def app_lifespan(server: Any) -> AsyncIterator[AppState]:
    """MCP应用生命周期管理
    
    处理应用的启动和关闭逻辑。
    
    Args:
        server: MCP服务器实例
        
    Yields:
        AppState: 应用状态对象
    """
    from datetime import datetime
    
    # 启动逻辑
    logger.info("=" * 60)
    logger.info("彩票规则验证 MCP 服务器启动")
    logger.info("=" * 60)
    
    # 初始化应用状态
    app_state.startup_time = datetime.now().isoformat()
    app_state.request_count = 0
    app_state.error_count = 0
    app_state.cache_hits = 0
    app_state.cache_misses = 0
    app_state.active_sessions = 0
    
    # 记录启动信息
    logger.info(f"启动时间: {app_state.startup_time}")
    logger.info(f"系统指令版本: 1.0.0")
    logger.info(f"支持彩种: 竞彩足球, 北京单场, 传统足彩")
    
    try:
        # 初始化缓存
        logger.info("初始化缓存系统...")
        _init_cache()
        
        # 加载规则引擎
        logger.info("加载规则引擎...")
        _init_rules_engine()
        
        # 初始化数据源
        logger.info("初始化数据源...")
        _init_data_sources()
        
        logger.info("启动完成，等待连接...")
        logger.info("-" * 60)
        
        yield app_state
        
    finally:
        # 关闭逻辑
        logger.info("-" * 60)
        logger.info("MCP 服务器关闭中...")
        
        # 记录运行统计
        logger.info(f"运行统计:")
        logger.info(f"  - 总请求数: {app_state.request_count}")
        logger.info(f"  - 错误数: {app_state.error_count}")
        logger.info(f"  - 缓存命中: {app_state.cache_hits}")
        logger.info(f"  - 缓存未命中: {app_state.cache_misses}")
        
        # 清理资源
        logger.info("清理资源...")
        _cleanup_resources()
        
        logger.info("服务器已关闭")
        logger.info("=" * 60)


def _init_cache():
    """初始化缓存系统"""
    import os
    from pathlib import Path

    cache_dir = Path(os.environ.get("LOTTERY_DATA_DIR",
        str(Path(__file__).resolve().parent.parent / ".cache" / "lottery_data")))
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"缓存目录: {cache_dir} (存在: {cache_dir.exists()})")


def _init_rules_engine():
    """初始化规则引擎"""
    try:
        from lottery_mcp.tools.rules_tools import RulesEngine
        engine = RulesEngine()
        supported_lotteries = list(engine.PLAY_LIMITS.keys())
        logger.info(f"规则引擎初始化成功，支持彩种: {supported_lotteries}")
        for lottery, limits in engine.PLAY_LIMITS.items():
            logger.info(f"  {lottery} 玩法: {list(limits.keys())}")
    except Exception as e:
        logger.warning(f"规则引擎初始化失败（将使用内置默认值）: {e}")


def _init_data_sources():
    """初始化数据源"""
    try:
        from lottery_mcp.data.sources import FreeDataSourceManager
        manager = FreeDataSourceManager()
        logger.info(f"数据源管理器初始化成功，已加载 {len(manager.api_keys)} 个API密钥")
        cache_info = manager.cache.info()
        logger.info(f"  缓存状态: {cache_info['total_entries']} 条目, TTL={cache_info['ttl_seconds']}s")
    except Exception as e:
        logger.warning(f"数据源初始化失败（将在首次请求时重试）: {e}")


def _cleanup_resources():
    """清理资源"""
    try:
        from lottery_mcp.data.sources import get_manager
        manager = get_manager()
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.http.close())
        else:
            loop.run_until_complete(manager.http.close())
        logger.info("HTTP客户端已关闭")
    except Exception as e:
        logger.warning(f"清理HTTP客户端时出错: {e}")

    try:
        from lottery_mcp.data.sources import get_manager
        manager = get_manager()
        manager.cache.clear()
        logger.info("缓存已清理")
    except Exception as e:
        logger.warning(f"清理缓存时出错: {e}")


# ============================================================
# Health Check
# ============================================================

def startup_health_check() -> Dict[str, Any]:
    """启动健康检查
    
    检查所有依赖项是否正常工作。
    
    Returns:
        健康检查结果
    """
    checks = []
    overall_status = "ok"
    
    # 检查 numpy
    try:
        import numpy as np
        checks.append({
            "name": "numpy",
            "status": "ok",
            "message": f"版本 {np.__version__}"
        })
    except ImportError as e:
        checks.append({
            "name": "numpy",
            "status": "error",
            "message": str(e)
        })
        overall_status = "error"
    
    # 检查 scipy
    try:
        import scipy
        checks.append({
            "name": "scipy",
            "status": "ok",
            "message": f"版本 {scipy.__version__}"
        })
    except ImportError as e:
        checks.append({
            "name": "scipy",
            "status": "error",
            "message": str(e)
        })
        overall_status = "error"
    
    # 检查 pydantic
    try:
        import pydantic
        checks.append({
            "name": "pydantic",
            "status": "ok",
            "message": f"版本 {pydantic.__version__}"
        })
    except ImportError as e:
        checks.append({
            "name": "pydantic",
            "status": "error",
            "message": str(e)
        })
        overall_status = "error"
    
    # 检查 mcp
    try:
        import mcp
        checks.append({
            "name": "mcp",
            "status": "ok",
            "message": "已安装"
        })
    except ImportError as e:
        checks.append({
            "name": "mcp",
            "status": "error",
            "message": str(e)
        })
        overall_status = "error"
    
    return {
        "overall_status": overall_status,
        "checks": checks,
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================
# Server Creation
# ============================================================

def create_mcp_server() -> FastMCP:
    """创建 MCP 服务器实例
    
    Returns:
        配置好的 FastMCP 实例
    """
    mcp = FastMCP(
        "lottery_mcp",
        lifespan=app_lifespan,
        instructions=SYSTEM_INSTRUCTIONS,
    )
    
    # 注册所有工具、资源、提示词
    _register_all_components(mcp)
    
    return mcp


def _register_all_components(mcp: FastMCP):
    """注册所有 MCP 组件
    
    Args:
        mcp: FastMCP 实例
    """
    # 注册工具
    from .tools import register_all_tools
    register_all_tools(mcp)
    
    # 注册资源
    from .tools.resources import register_resources
    register_resources(mcp)
    
    # 注册提示词
    from .tools.prompts import register_prompts
    register_prompts(mcp)


def run_mcp_server():
    """运行 MCP 服务器（入口点函数）"""
    health = startup_health_check()
    logger.info(f"[启动] MCP健康检查: {health['overall_status']}")
    for check in health["checks"]:
        status = check["status"]
        icon = "OK" if status == "ok" else "WARN" if status == "warning" else "FAIL"
        logger.info(f"  [{icon}] {check['name']}: {check['message']}")
    
    mcp = create_mcp_server()
    mcp.run()
