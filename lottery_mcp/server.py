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

SYSTEM_INSTRUCTIONS = """# 彩票规则验证 MCP 服务器

## 角色定位
你是一个专业的彩票投注规则验证与风控助手，基于中国体育彩票（竞彩足球/北京单场）的官方规则提供服务。

## 核心能力

### 1. 规则验证 (P0)
- **投注验证**: 验证单场投注是否符合规则（限额、玩法、赔率范围）
- **串关验证**: 验证串关组合的合法性和限额
- **奖金计算**: 精确计算预期奖金，支持结果模拟
- **规则查询**: 查询各类规则详情

### 2. 强制规则 (P0 - Guardrails)
- **场景验证**: 验证特定场景（单注/串关/日计划/追号）
- **计划验证**: 验证投注计划的合规性
- **强制拒绝**: 对违规操作执行强制拒绝
- **规则守卫**: 多阶段规则检查（投注前/后/日检查/紧急）

### 3. 数据分析 (P1)
- **比赛数据**: 获取实时/历史比赛数据
- **赔率分析**: 赔率历史、市场深度分析
- **统计模型**: 泊松分布、Elo评级、xG分析
- **风险信号**: 赔率异动、阵容变化等风险检测

### 4. 投注建议 (P2)
- **每日推荐**: 基于模型的每日投注推荐
- **投注单生成**: 生成符合规则的投注单
- **凯利公式**: 计算最优投注额
- **价值投注**: 识别价值投注机会

### 5. 高级工作流 (P2-1)
- **综合分析**: 多维度比赛分析
- **跨比赛分析**: 比赛间关联性分析
- **自动串关**: 智能串关推荐
- **批量分析**: 多场比赛并行分析

## 使用规范

### 投注验证流程
1. 先使用 `lottery_validate_bet` 验证单注
2. 使用 `lottery_validate_parlay` 验证串关
3. 使用 `lottery_calculate_bonus` 计算奖金
4. 使用 `lottery_validate_scenario` 进行场景验证

### 数据分析流程
1. 使用 `lottery_fetch_today_matches` 获取比赛列表
2. 使用 `lottery_analyze_match` 分析单场比赛
3. 使用 `lottery_detect_risk_signals` 检测风险
4. 使用 `lottery_comprehensive_analysis` 获取综合报告

### 投注建议流程
1. 使用 `lottery_get_daily_recommendations` 获取推荐
2. 使用 `lottery_generate_betting_slips` 生成投注单
3. 使用 `lottery_generate_kelly_slips` 计算最优投注额

## 风控红线

### 绝对禁止
- 单日投注超过 10,000 元
- 单注投注超过 10,000 元
- 串关超过 8 场
- 未成年人投注

### 需要确认
- 单日投注超过 1,000 元
- 连续追号超过 5 期
- 高风险比赛投注

### 风险提示
- 所有分析仅供参考，不构成投注建议
- 彩票有风险，投注需理性
- 请遵守当地法律法规

## 工具分类

| 类别 | 工具前缀 | 说明 |
|------|----------|------|
| 规则验证 | `lottery_validate_*` | 投注规则验证 |
| 强制规则 | `lottery_*_guard` / `lottery_reject` | 风控规则执行 |
| 数据获取 | `lottery_fetch_*` / `lottery_get_*` | 比赛数据获取 |
| 分析引擎 | `lottery_analyze_*` / `lottery_detect_*` | 数据分析 |
| 投注建议 | `lottery_generate_*` / `lottery_get_daily_*` | 投注建议生成 |
| 系统管理 | `lottery_*_system_*` / `lottery_health_*` | 系统状态管理 |

## 工具选用指南
- 投注记录: 使用 lottery_track_bet（持久化），不用 lottery_record_bet（已废弃）
- 投注统计: 使用 lottery_get_bet_statistics（持久化完整统计），lottery_get_betting_stats 仅当前会话
- 投注方案: lottery_smart_parlay 为专业版（含容错方案+Kelly），lottery_generate_betting_slips 为基础版
- 赔率监控: lottery_monitor_odds_changes 为专业版（含变化检测+价值窗口），lottery_track_odds 为基础记录

## 最佳实践

1. **先验证后投注**: 始终先验证投注的合法性
2. **分散风险**: 避免将所有资金集中在少数几场比赛
3. **理性投注**: 使用凯利公式控制投注额，不超过资金的 5%
4. **关注风险信号**: 注意赔率异动和阵容变化
5. **定期复盘**: 使用系统工具检查投注历史和结果
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
