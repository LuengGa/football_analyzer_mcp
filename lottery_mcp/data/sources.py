#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
免费数据获取模块 - 多源聚合 + 智能降级
========================================
整合所有免费数据源（国际API + 国内网站爬取），为体育彩票投注分析提供数据。

数据源架构:
  国际API:
    - api-football (100次/天)       : 积分榜、交锋、伤停、赛程
    - football-data.org (10次/分钟) : 积分榜、交锋、赛程
    - TheSportsDB (免费)            : 球队状态、近期战绩
    - The Odds API (500次/月)       : 多机构赔率对比
    - Odds-API.io                   : 赔率对比备用

  国内数据:
    - sporttery.cn (竞彩官网)        : 竞彩赔率变化
    - zx.500.com (500彩票网)        : 竞彩赛果开奖
    - kaijiang.500.com (500开奖网)  : 传统足彩开奖(胜负彩/进球彩/半全场)
    - zx.500.com/zqdc (500北单)     : 北京单场开奖
    - trade.500.com/bjdc (500交易)  : 北京单场当前对阵

设计原则:
  1. 多源降级: 主源失败自动切换备用源
  2. 内置缓存: TTL 1小时，减少API调用
  3. 频率控制: api-football 100次/天需精打细算
  4. 统一格式: 所有方法返回 {"source", "data", "cached", "remaining_quota"}
  5. 配额追踪: 每次调用记录剩余次数

安全说明:
  - 所有SSL连接默认启用证书验证
  - 可通过环境变量 LOTTERY_SSL_VERIFY=0 禁用（仅用于调试）
"""

import json
import time
import asyncio
import hashlib
import logging
import os
import ssl
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("lottery_mcp")


# ============================================================================
# 安全配置
# ============================================================================

def create_ssl_context() -> ssl.SSLContext:
    """
    创建安全的SSL上下文
    
    默认启用证书验证，可通过环境变量 LOTTERY_SSL_VERIFY=0 禁用（仅用于调试）
    
    Returns:
        配置好的SSL上下文
    """
    verify_ssl = os.getenv("LOTTERY_SSL_VERIFY", "1") == "1"
    
    if verify_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        import warnings
        warnings.warn(
            "SSL证书验证已被禁用！这仅应用于调试环境。",
            RuntimeWarning,
            stacklevel=2
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    
    return ctx

# ============================================================================
# 常量与配置
# ============================================================================

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
API_KEYS_FILE = os.environ.get("LOTTERY_API_KEYS_FILE", str(_PROJECT_ROOT / ".env.api_keys"))
DEFAULT_TIMEOUT = 10  # 秒
CACHE_TTL_SECONDS = 3600  # 1小时

# api-football 免费层: 100次/天
API_FOOTBALL_DAILY_LIMIT = 100

# The Odds API 免费层: 500次/月
THE_ODDS_API_MONTHLY_LIMIT = 500

# football-data.org 免费层: 10次/分钟
FOOTBALL_DATA_RATE_LIMIT = 10  # 每分钟

# 联赛代码映射 (用于 football-data.org)
# football-data.org 使用 competition code, 如 "PL", "PD", "BL1", "SA", "FL1"
LEAGUE_CODE_MAP = {
    "英超": "PL", "EPL": "PL", "premier_league": "PL", "PL": "PL",
    "西甲": "PD", "La Liga": "PD", "la_liga": "PD", "PD": "PD",
    "德甲": "BL1", "Bundesliga": "BL1", "bundesliga": "BL1", "BL1": "BL1",
    "意甲": "SA", "Serie A": "SA", "serie_a": "SA", "SA": "SA",
    "法甲": "FL1", "Ligue 1": "FL1", "ligue_1": "FL1", "FL1": "FL1",
    "中超": "CL", "CSL": "CL", "csl": "CL", "CL": "CL",
    "欧冠": "CL", "Champions League": "CL", "champions_league": "CL",
    "欧联杯": "EL", "Europa League": "EL", "europa_league": "EL",
}

# 联赛ID映射 (用于 api-football)
LEAGUE_ID_MAP = {
    "英超": 39, "EPL": 39, "premier_league": 39,
    "西甲": 140, "La Liga": 140, "la_liga": 140,
    "德甲": 78, "Bundesliga": 78, "bundesliga": 78,
    "意甲": 135, "Serie A": 135, "serie_a": 135,
    "法甲": 61, "Ligue 1": 61, "ligue_1": 61,
    "中超": 16, "CSL": 16, "csl": 16,
    "欧冠": 2, "Champions League": 2,
    "欧联杯": 3, "Europa League": 3,
}

# The Odds API 联赛映射
THE_ODDS_API_LEAGUE_MAP = {
    "英超": "epl", "EPL": "epl",
    "西甲": "la_liga", "La Liga": "la_liga",
    "德甲": "bundesliga", "Bundesliga": "bundesliga",
    "意甲": "serie_a", "Serie A": "serie_a",
    "法甲": "ligue_1", "Ligue 1": "ligue_1",
    "欧冠": "uefa_champions_league", "Champions League": "uefa_champions_league",
}


# ============================================================================
# 数据缓存
# ============================================================================

class DataCache:
    """线程安全的内存缓存，支持TTL过期"""

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() - entry["timestamp"] > self._ttl:
                del self._cache[key]
                return None
            return entry["data"]

    def set(self, key: str, data: Any) -> None:
        with self._lock:
            self._cache[key] = {
                "data": data,
                "timestamp": time.time(),
            }

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def info(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            valid = sum(1 for e in self._cache.values() if now - e["timestamp"] <= self._ttl)
            return {
                "total_entries": len(self._cache),
                "valid_entries": valid,
                "ttl_seconds": self._ttl,
            }


# ============================================================================
# 配额追踪器
# ============================================================================

class QuotaTracker:
    """API配额追踪 - 跟踪每个源的剩余调用次数"""

    def __init__(self):
        self._quotas: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def init_quota(self, source: str, daily_limit: int, monthly_limit: int = 0):
        """初始化某个源的配额"""
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            month = datetime.now().strftime("%Y-%m")
            self._quotas[source] = {
                "daily_limit": daily_limit,
                "daily_used": 0,
                "daily_date": today,
                "monthly_limit": monthly_limit,
                "monthly_used": 0,
                "monthly_date": month,
            }

    def consume(self, source: str, count: int = 1) -> int:
        """消耗配额，返回剩余次数。如果配额不足返回 -1"""
        with self._lock:
            if source not in self._quotas:
                return -1

            q = self._quotas[source]
            today = datetime.now().strftime("%Y-%m-%d")
            month = datetime.now().strftime("%Y-%m")

            # 检查日期重置
            if q["daily_date"] != today:
                q["daily_used"] = 0
                q["daily_date"] = today
            if q["monthly_date"] != month:
                q["monthly_used"] = 0
                q["monthly_date"] = month

            # 检查日限额 (仅当设置了日限额时)
            if q["daily_limit"] > 0 and q["daily_used"] + count > q["daily_limit"]:
                return -1

            # 检查月限额 (仅当设置了月限额时)
            if q["monthly_limit"] > 0 and q["monthly_used"] + count > q["monthly_limit"]:
                return -1

            q["daily_used"] += count
            q["monthly_used"] += count

            # 计算剩余配额: 优先返回日剩余，否则返回月剩余，否则返回-1(无限制)
            if q["daily_limit"] > 0:
                return q["daily_limit"] - q["daily_used"]
            elif q["monthly_limit"] > 0:
                return q["monthly_limit"] - q["monthly_used"]
            else:
                return -1  # 无限制

    def get_remaining(self, source: str) -> int:
        """获取剩余次数"""
        with self._lock:
            if source not in self._quotas:
                return -1
            q = self._quotas[source]
            remaining = q["daily_limit"] - q["daily_used"] if q["daily_limit"] > 0 else -1
            return max(0, remaining)

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有源的配额状态"""
        with self._lock:
            result = {}
            for source, q in self._quotas.items():
                remaining = q["daily_limit"] - q["daily_used"] if q["daily_limit"] > 0 else -1
                result[source] = {
                    "daily_limit": q["daily_limit"],
                    "daily_used": q["daily_used"],
                    "daily_remaining": max(0, remaining) if remaining >= 0 else "unlimited",
                    "monthly_limit": q["monthly_limit"],
                    "monthly_used": q["monthly_used"],
                }
            return result


# ============================================================================
# 统一返回格式
# ============================================================================

def make_response(
    source: str,
    data: Any,
    cached: bool = False,
    remaining_quota: int = -1,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """构建统一返回格式"""
    result = {
        "source": source,
        "data": data,
        "cached": cached,
        "remaining_quota": remaining_quota,
        "timestamp": datetime.now().isoformat(),
    }
    if error:
        result["error"] = error
    return result


# ============================================================================
# HTTP客户端
# ============================================================================

class AsyncHTTPClient:
    """统一的异步HTTP客户端，基于httpx.AsyncClient"""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )

    async def get(self, url: str, headers: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """发送GET请求，返回 {"ok": bool, "data": ..., "status_code": int, "headers": dict, "error": str|None}"""
        try:
            resp = await self._client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return {"ok": True, "data": data, "status_code": 200,
                            "headers": dict(resp.headers), "error": None}
                except Exception:
                    return {"ok": False, "data": None, "status_code": 200,
                            "headers": dict(resp.headers), "error": "JSON解析失败"}
            else:
                return {"ok": False, "data": None, "status_code": resp.status_code,
                        "headers": dict(resp.headers), "error": f"HTTP {resp.status_code}"}
        except httpx.TimeoutException:
            return {"ok": False, "data": None, "status_code": 0,
                    "headers": {}, "error": "请求超时"}
        except httpx.ConnectError:
            return {"ok": False, "data": None, "status_code": 0,
                    "headers": {}, "error": "连接失败"}
        except Exception as e:
            return {"ok": False, "data": None, "status_code": 0,
                    "headers": {}, "error": str(e)}

    async def get_html(self, url: str, headers: Optional[Dict] = None,
                       params: Optional[Dict] = None, encoding: str = None) -> Dict[str, Any]:
        """
        发送GET请求并返回HTML文本。
        返回 {"ok": bool, "data": str, "status_code": int, "headers": dict, "error": str|None}

        Args:
            url: 请求URL
            headers: 自定义请求头
            params: 查询参数
            encoding: 指定编码 (如 "gb2312"), 默认自动检测
        """
        try:
            resp = await self._client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                if encoding:
                    text = resp.content.decode(encoding, errors="replace")
                else:
                    text = resp.text
                return {"ok": True, "data": text, "status_code": 200,
                        "headers": dict(resp.headers), "error": None}
            else:
                return {"ok": False, "data": None, "status_code": resp.status_code,
                        "headers": dict(resp.headers), "error": f"HTTP {resp.status_code}"}
        except httpx.TimeoutException:
            return {"ok": False, "data": None, "status_code": 0,
                    "headers": {}, "error": "请求超时"}
        except httpx.ConnectError:
            return {"ok": False, "data": None, "status_code": 0,
                    "headers": {}, "error": "连接失败"}
        except Exception as e:
            return {"ok": False, "data": None, "status_code": 0,
                    "headers": {}, "error": str(e)}

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False


# ============================================================================
# 免费数据源管理器
# ============================================================================

class FreeDataSourceManager:
    """免费数据源管理器 - 多源聚合 + 智能降级"""

    def __init__(self, api_keys_file: str = API_KEYS_FILE):
        self.api_keys = self._load_api_keys(api_keys_file)
        self.cache = DataCache(ttl_seconds=CACHE_TTL_SECONDS)
        self.quota = QuotaTracker()
        self.http = AsyncHTTPClient(timeout=DEFAULT_TIMEOUT)
        self._last_request_time: Dict[str, float] = {}  # 限流用

        # 初始化配额
        self._init_quotas()

    def _load_api_keys(self, filepath: str) -> Dict[str, Any]:
        """加载API密钥（优先环境变量，其次KEY=VALUE文件，最后JSON文件）"""
        api_keys = {}
        
        # 1. 优先从环境变量读取
        from_env = {
            "the_odds_api": {"api_key": os.getenv("THE_ODDS_API_KEY")},
            "api_football": {"api_key": os.getenv("API_FOOTBALL_KEY")},
            "football_data_org": {"api_key": os.getenv("FOOTBALL_DATA_ORG_KEY")},
            "the_sports_db": {"api_key": os.getenv("THESPORTSDB_KEY")},
            "odds_api_io": {"api_key": os.getenv("ODDS_API_IO_KEY")},
        }
        
        # 移除空值
        api_keys = {k: v for k, v in from_env.items() if v.get("api_key")}
        
        # 2. 如果环境变量没找到，尝试从文件读取
        if not api_keys:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                # 尝试解析为 KEY=VALUE 格式
                key_values = {}
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key_values[key.strip()] = value.strip()
                
                if key_values:
                    # 转换为期望的格式
                    api_keys = {
                        "the_odds_api": {"api_key": key_values.get("THE_ODDS_API_KEY")},
                        "api_football": {"api_key": key_values.get("API_FOOTBALL_KEY")},
                        "football_data_org": {"api_key": key_values.get("FOOTBALL_DATA_ORG_KEY")},
                        "the_sports_db": {"api_key": key_values.get("THESPORTSDB_KEY")},
                        "odds_api_io": {"api_key": key_values.get("ODDS_API_IO_KEY")},
                    }
                    # 移除空值
                    api_keys = {k: v for k, v in api_keys.items() if v.get("api_key")}
                    logger.info(f"从 {filepath} 加载 API keys (KEY=VALUE 格式)")
                else:
                    # 尝试 JSON 格式
                    api_keys = json.loads(content)
                    logger.info(f"从 {filepath} 加载 API keys (JSON 格式)")
            
            except FileNotFoundError:
                logger.warning(f"API密钥文件不存在: {filepath}")
            except json.JSONDecodeError:
                logger.warning(f"API密钥文件格式错误，无法解析")
            except Exception as e:
                logger.warning(f"加载API密钥失败: {e}")
        
        if api_keys:
            logger.info(f"成功加载 {len(api_keys)} 个数据源的 API 密钥")
        else:
            logger.warning("未找到任何 API 密钥")
            
        return api_keys

    def _init_quotas(self):
        """初始化各数据源的配额"""
        self.quota.init_quota("api-football", daily_limit=API_FOOTBALL_DAILY_LIMIT)
        self.quota.init_quota("football-data.org", daily_limit=0)  # 10次/分钟, 不按天限制
        self.quota.init_quota("the-odds-api", daily_limit=0, monthly_limit=THE_ODDS_API_MONTHLY_LIMIT)
        self.quota.init_quota("the-sports-db", daily_limit=0)  # 免费, 不限制
        self.quota.init_quota("odds-api-io", daily_limit=0)  # 不确定限制
        self.quota.init_quota("sporttery.cn", daily_limit=0)  # 国内网站, 不限制
        self.quota.init_quota("500.com", daily_limit=0)  # 国内网站, 不限制

    def _get_api_config(self, source: str) -> Dict[str, Any]:
        """获取API配置"""
        config_map = {
            "api-football": "api_football",
            "football-data.org": "football_data_org",
            "the-odds-api": "the_odds_api",
            "the-sports-db": "the_sports_db",
            "odds-api-io": "odds_api_io",
        }
        key = config_map.get(source, source)
        return self.api_keys.get(key, {})

    async def _rate_limit(self, source: str, min_interval: float = 6.0):
        """请求频率控制"""
        now = time.time()
        last = self._last_request_time.get(source, 0)
        elapsed = now - last
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_request_time[source] = time.time()

    def _cache_key(self, method: str, **kwargs) -> str:
        """生成缓存键"""
        param_str = json.dumps(kwargs, sort_keys=True, default=str)
        raw = f"{method}:{param_str}"
        return hashlib.md5(raw.encode()).hexdigest()

    # ========================================================================
    # 国际API部分 - 积分榜
    # ========================================================================

    async def get_standings(self, league_code: str, season: int = None) -> Dict[str, Any]:
        """
        获取积分榜 - 用于实力分析(权重25%)
        优先级: api-football -> football-data.org -> OpenLigaDB

        Args:
            league_code: 联赛代码，如 "英超", "PL", "EPL"
            season: 赛季年份，如 2024 表示2024-25赛季

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        if season is None:
            now = datetime.now()
            season = now.year if now.month >= 8 else now.year - 1

        cache_key = self._cache_key("standings", league_code=league_code, season=season)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        # 尝试 api-football
        result = await self._get_standings_api_football(league_code, season)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        # 尝试 football-data.org
        result = await self._get_standings_football_data_org(league_code, season)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        return make_response(source="none", data=None, error="所有积分榜数据源均失败")

    async def _get_standings_api_football(self, league_code: str, season: int) -> Optional[Dict]:
        """api-football 积分榜"""
        remaining = self.quota.consume("api-football")
        if remaining < 0:
            logger.warning("api-football 配额已用完")
            return None

        config = self._get_api_config("api-football")
        if not config.get("api_key"):
            return None

        league_id = LEAGUE_ID_MAP.get(league_code)
        if not league_id:
            return None

        await self._rate_limit("api-football", min_interval=6.0)

        url = f"{config['base_url']}/standings"
        headers = {"x-apisports-key": config["api_key"]}
        params = {"league": league_id, "season": season}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            logger.warning(f"api-football standings 失败: {resp['error']}")
            return None

        data = resp["data"]
        standings = self._parse_api_football_standings(data)
        return {"source": "api-football", "data": standings, "remaining": remaining}

    def _parse_api_football_standings(self, raw: Dict) -> List[Dict]:
        """解析 api-football 积分榜响应"""
        standings = []
        for league_data in raw.get("response", []):
            for group in league_data.get("league", {}).get("standings", []):
                for team in group:
                    games = team.get("games", {})
                    goals = team.get("goals", {})
                    team_info = team.get("team", {})
                    standings.append({
                        "rank": team.get("rank", 0),
                        "team_id": team_info.get("id", 0),
                        "team_name": team_info.get("name", ""),
                        "team_logo": team_info.get("logo", ""),
                        "points": team.get("points", 0),
                        "played": games.get("played", 0),
                        "wins": games.get("win", {}).get("total", 0),
                        "draws": games.get("draw", {}).get("total", 0),
                        "losses": games.get("lose", {}).get("total", 0),
                        "goals_for": goals.get("for", {}).get("total", 0),
                        "goals_against": goals.get("against", {}).get("total", 0),
                        "goal_diff": team.get("goalsDiff", 0),
                        "form": team.get("form", ""),
                        # 主场
                        "home_wins": games.get("win", {}).get("home", 0),
                        "home_draws": games.get("draw", {}).get("home", 0),
                        "home_losses": games.get("lose", {}).get("home", 0),
                        "home_goals_for": goals.get("for", {}).get("home", {}).get("total", 0),
                        "home_goals_against": goals.get("against", {}).get("home", {}).get("total", 0),
                        # 客场
                        "away_wins": games.get("win", {}).get("away", 0),
                        "away_draws": games.get("draw", {}).get("away", 0),
                        "away_losses": games.get("lose", {}).get("away", 0),
                        "away_goals_for": goals.get("for", {}).get("away", {}).get("total", 0),
                        "away_goals_against": goals.get("against", {}).get("away", {}).get("total", 0),
                    })
        return standings

    async def _get_standings_football_data_org(self, league_code: str, season: int) -> Optional[Dict]:
        """football-data.org 积分榜"""
        config = self._get_api_config("football-data.org")
        if not config.get("api_key"):
            return None

        comp_code = LEAGUE_CODE_MAP.get(league_code)
        if not comp_code:
            return None

        await self._rate_limit("football-data.org", min_interval=6.5)

        url = f"{config['base_url']}/competitions/{comp_code}/standings"
        headers = {"X-Auth-Token": config["api_key"]}

        resp = await self.http.get(url, headers=headers)
        if not resp["ok"]:
            logger.warning(f"football-data.org standings 失败: {resp['error']}")
            return None

        data = resp["data"]
        standings = self._parse_football_data_org_standings(data)
        return {"source": "football-data.org", "data": standings, "remaining": -1}

    def _parse_football_data_org_standings(self, raw: Dict) -> List[Dict]:
        """解析 football-data.org 积分榜响应"""
        standings = []
        for table in raw.get("standings", []):
            if table.get("type") == "TOTAL":
                for entry in table.get("table", []):
                    standings.append({
                        "rank": entry.get("position", 0),
                        "team_id": entry.get("team", {}).get("id", 0),
                        "team_name": entry.get("team", {}).get("name", ""),
                        "team_logo": entry.get("team", {}).get("crest", ""),
                        "points": entry.get("points", 0),
                        "played": entry.get("playedGames", 0),
                        "wins": entry.get("won", 0),
                        "draws": entry.get("draw", 0),
                        "losses": entry.get("lost", 0),
                        "goals_for": entry.get("goalsFor", 0),
                        "goals_against": entry.get("goalsAgainst", 0),
                        "goal_diff": entry.get("goalDifference", 0),
                        "form": entry.get("form", ""),
                        "home_wins": 0, "home_draws": 0, "home_losses": 0,
                        "home_goals_for": 0, "home_goals_against": 0,
                        "away_wins": 0, "away_draws": 0, "away_losses": 0,
                        "away_goals_for": 0, "away_goals_against": 0,
                    })
        return standings

    # ========================================================================
    # 国际API部分 - 历史交锋
    # ========================================================================

    async def get_head_to_head(self, team1: str, team2: str, limit: int = 10) -> Dict[str, Any]:
        """
        获取历史交锋 - 用于交锋分析(权重15%)
        优先级: api-football -> football-data.org

        Args:
            team1: 主队名称
            team2: 客队名称
            limit: 返回场次限制

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        cache_key = self._cache_key("h2h", team1=team1, team2=team2, limit=limit)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        # 尝试 api-football (需要team ID, 先搜索)
        result = await self._get_h2h_api_football(team1, team2, limit)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        # 尝试 football-data.org
        result = await self._get_h2h_football_data_org(team1, team2, limit)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        return make_response(source="none", data=None, error="所有交锋数据源均失败")

    async def _get_h2h_api_football(self, team1: str, team2: str, limit: int) -> Optional[Dict]:
        """api-football 历史交锋"""
        remaining = self.quota.consume("api-football")
        if remaining < 0:
            return None

        config = self._get_api_config("api-football")
        if not config.get("api_key"):
            return None

        # 先搜索球队获取ID
        team1_id = await self._search_team_id_api_football(team1, config)
        team2_id = await self._search_team_id_api_football(team2, config)
        if not team1_id or not team2_id:
            return None

        await self._rate_limit("api-football", min_interval=6.0)

        url = f"{config['base_url']}/fixtures/headtohead"
        headers = {"x-apisports-key": config["api_key"]}
        params = {"h2h": f"{team1_id}-{team2_id}", "last": limit}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            logger.warning(f"api-football h2h 失败: {resp['error']}")
            return None

        data = self._parse_api_football_h2h(resp["data"], team1_id, team2_id)
        return {"source": "api-football", "data": data, "remaining": remaining}

    async def _search_team_id_api_football(self, team_name: str, config: Dict) -> Optional[int]:
        """搜索球队ID (消耗1次配额)"""
        remaining = self.quota.consume("api-football")
        if remaining < 0:
            return None

        await self._rate_limit("api-football", min_interval=6.0)

        url = f"{config['base_url']}/teams"
        headers = {"x-apisports-key": config["api_key"]}
        params = {"search": team_name}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            return None

        results = resp["data"].get("response", [])
        if results:
            return results[0].get("team", {}).get("id")
        return None

    def _parse_api_football_h2h(self, raw: Dict, team1_id: int, team2_id: int) -> Dict:
        """解析 api-football 交锋记录"""
        matches = []
        team1_wins = 0
        draws = 0
        team2_wins = 0

        for fixture in raw.get("response", []):
            home = fixture.get("teams", {}).get("home", {})
            away = fixture.get("teams", {}).get("away", {})
            goals = fixture.get("goals", {})
            home_score = goals.get("home", 0) or 0
            away_score = goals.get("away", 0) or 0

            if home_score > away_score:
                result = "home_win"
            elif home_score < away_score:
                result = "away_win"
            else:
                result = "draw"

            # 统计
            home_id = home.get("id")
            if home_id == team1_id:
                if result == "home_win":
                    team1_wins += 1
                elif result == "draw":
                    draws += 1
                else:
                    team2_wins += 1
            else:
                if result == "away_win":
                    team1_wins += 1
                elif result == "draw":
                    draws += 1
                else:
                    team2_wins += 1

            matches.append({
                "date": fixture.get("fixture", {}).get("date", ""),
                "home_team": home.get("name", ""),
                "away_team": away.get("name", ""),
                "home_score": home_score,
                "away_score": away_score,
                "result": result,
                "league": fixture.get("league", {}).get("name", ""),
            })

        return {
            "total_matches": len(matches),
            "team1_wins": team1_wins,
            "draws": draws,
            "team2_wins": team2_wins,
            "recent_matches": matches,
        }

    async def _get_h2h_football_data_org(self, team1: str, team2: str, limit: int) -> Optional[Dict]:
        """football-data.org 历史交锋 (需要team ID)"""
        config = self._get_api_config("football-data.org")
        if not config.get("api_key"):
            return None

        # football-data.org 的 h2h 需要 team ID
        # 先搜索球队
        team1_id = await self._search_team_id_football_data_org(team1, config)
        team2_id = await self._search_team_id_football_data_org(team2, config)
        if not team1_id or not team2_id:
            return None

        await self._rate_limit("football-data.org", min_interval=6.5)

        url = f"{config['base_url']}/teams/{team1_id}/matches"
        headers = {"X-Auth-Token": config["api_key"]}
        params = {"limit": limit}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            return None

        # 过滤出与 team2 的比赛
        all_matches = resp["data"].get("matches", [])
        h2h_matches = [m for m in all_matches
                       if any(t.get("id") == team2_id
                              for t in [m.get("homeTeam", {}), m.get("awayTeam", {})])]

        matches = []
        team1_wins = 0
        draws = 0
        team2_wins = 0

        for m in h2h_matches[:limit]:
            home_team = m.get("homeTeam", {})
            away_team = m.get("awayTeam", {})
            score = m.get("score", {})
            full_time = score.get("fullTime", {})
            home_score = full_time.get("home") or 0
            away_score = full_time.get("away") or 0

            if home_score > away_score:
                result = "home_win"
            elif home_score < away_score:
                result = "away_win"
            else:
                result = "draw"

            home_id = home_team.get("id")
            if home_id == team1_id:
                if result == "home_win":
                    team1_wins += 1
                elif result == "draw":
                    draws += 1
                else:
                    team2_wins += 1
            else:
                if result == "away_win":
                    team1_wins += 1
                elif result == "draw":
                    draws += 1
                else:
                    team2_wins += 1

            matches.append({
                "date": m.get("utcDate", ""),
                "home_team": home_team.get("name", ""),
                "away_team": away_team.get("name", ""),
                "home_score": home_score,
                "away_score": away_score,
                "result": result,
                "league": m.get("competition", {}).get("name", ""),
            })

        if not matches:
            return None

        return {
            "source": "football-data.org",
            "data": {
                "total_matches": len(matches),
                "team1_wins": team1_wins,
                "draws": draws,
                "team2_wins": team2_wins,
                "recent_matches": matches,
            },
            "remaining": -1,
        }

    async def _search_team_id_football_data_org(self, team_name: str, config: Dict) -> Optional[int]:
        """搜索球队ID (football-data.org)"""
        await self._rate_limit("football-data.org", min_interval=6.5)

        url = f"{config['base_url']}/teams"
        headers = {"X-Auth-Token": config["api_key"]}
        params = {"name": team_name}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            return None

        results = resp["data"].get("teams", [])
        if results:
            return results[0].get("id")
        return None

    # ========================================================================
    # 国际API部分 - 球队近期状态
    # ========================================================================

    async def get_team_form(self, team_name: str, limit: int = 5) -> Dict[str, Any]:
        """
        获取球队近期状态 - 用于状态动量分析
        优先级: api-football -> football-data.org -> TheSportsDB

        Args:
            team_name: 球队名称
            limit: 近期场次数

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        cache_key = self._cache_key("team_form", team_name=team_name, limit=limit)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        # 尝试 api-football
        result = await self._get_team_form_api_football(team_name, limit)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        # 尝试 football-data.org
        result = await self._get_team_form_football_data_org(team_name, limit)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        # 尝试 TheSportsDB
        result = await self._get_team_form_the_sports_db(team_name, limit)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        return make_response(source="none", data=None, error="所有球队状态数据源均失败")

    async def _get_team_form_api_football(self, team_name: str, limit: int) -> Optional[Dict]:
        """api-football 球队近期状态"""
        remaining = self.quota.consume("api-football")
        if remaining < 0:
            return None

        config = self._get_api_config("api-football")
        if not config.get("api_key"):
            return None

        team_id = await self._search_team_id_api_football(team_name, config)
        if not team_id:
            return None

        await self._rate_limit("api-football", min_interval=6.0)

        url = f"{config['base_url']}/fixtures"
        headers = {"x-apisports-key": config["api_key"]}
        params = {"team": team_id, "last": limit}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            return None

        form = self._parse_api_football_form(resp["data"])
        return {"source": "api-football", "data": form, "remaining": remaining}

    def _parse_api_football_form(self, raw: Dict) -> Dict:
        """解析近期状态"""
        fixtures = raw.get("response", [])
        results = []
        wins = draws = losses = goals_for = goals_against = 0

        for f in fixtures:
            home = f.get("teams", {}).get("home", {})
            away = f.get("teams", {}).get("away", {})
            goals = f.get("goals", {})
            hs = goals.get("home", 0) or 0
            as_ = goals.get("away", 0) or 0

            if hs > as_:
                result = "W"
                wins += 1
            elif hs < as_:
                result = "L"
                losses += 1
            else:
                result = "D"
                draws += 1

            goals_for += hs + as_
            goals_against += as_ + hs

            results.append({
                "date": f.get("fixture", {}).get("date", ""),
                "home_team": home.get("name", ""),
                "away_team": away.get("name", ""),
                "home_score": hs,
                "away_score": as_,
                "result": result,
                "league": f.get("league", {}).get("name", ""),
            })

        return {
            "team_name": fixtures[0].get("teams", {}).get("home", {}).get("name", "") if fixtures else "",
            "last_matches": results,
            "form_string": ",".join(r["result"] for r in results),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "win_rate": round(wins / len(results) * 100, 1) if results else 0,
        }

    async def _get_team_form_football_data_org(self, team_name: str, limit: int) -> Optional[Dict]:
        """football-data.org 球队近期状态"""
        config = self._get_api_config("football-data.org")
        if not config.get("api_key"):
            return None

        team_id = await self._search_team_id_football_data_org(team_name, config)
        if not team_id:
            return None

        await self._rate_limit("football-data.org", min_interval=6.5)

        url = f"{config['base_url']}/teams/{team_id}/matches"
        headers = {"X-Auth-Token": config["api_key"]}
        params = {"limit": limit, "status": "FINISHED"}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            return None

        matches = resp["data"].get("matches", [])
        results = []
        wins = draws = losses = 0

        for m in matches:
            home = m.get("homeTeam", {})
            away = m.get("awayTeam", {})
            score = m.get("score", {}).get("fullTime", {})
            hs = score.get("home") or 0
            as_ = score.get("away") or 0

            if hs > as_:
                result = "W"
                wins += 1
            elif hs < as_:
                result = "L"
                losses += 1
            else:
                result = "D"
                draws += 1

            results.append({
                "date": m.get("utcDate", ""),
                "home_team": home.get("name", ""),
                "away_team": away.get("name", ""),
                "home_score": hs,
                "away_score": as_,
                "result": result,
                "league": m.get("competition", {}).get("name", ""),
            })

        if not results:
            return None

        return {
            "source": "football-data.org",
            "data": {
                "team_name": team_name,
                "last_matches": results,
                "form_string": ",".join(r["result"] for r in results),
                "wins": wins, "draws": draws, "losses": losses,
                "win_rate": round(wins / len(results) * 100, 1),
            },
            "remaining": -1,
        }

    async def _get_team_form_the_sports_db(self, team_name: str, limit: int) -> Optional[Dict]:
        """TheSportsDB 球队近期状态"""
        config = self._get_api_config("the-sports-db")
        if not config.get("api_key"):
            return None

        # 先搜索球队
        search_url = f"{config['base_url']}/{config['api_key']}/searchteams.php"
        resp = await self.http.get(search_url, params={"t": team_name})
        if not resp["ok"]:
            return None

        teams = resp["data"]
        if not teams:
            return None

        team_id = teams[0].get("idTeam")
        team_name_actual = teams[0].get("strTeam", team_name)

        # 获取最近5场比赛
        events_url = f"{config['base_url']}/{config['api_key']}/eventslast.php"
        resp = await self.http.get(events_url, params={"id": team_id})
        if not resp["ok"]:
            return None

        results = resp["data"].get("results", [])
        if not results:
            return None

        parsed = []
        wins = draws = losses = 0

        for event in results[:limit]:
            home = event.get("strHomeTeam", "")
            away = event.get("strAwayTeam", "")
            hs = int(event.get("intHomeScore", 0) or 0)
            as_ = int(event.get("intAwayScore", 0) or 0)

            if hs > as_:
                result = "W"
                wins += 1
            elif hs < as_:
                result = "L"
                losses += 1
            else:
                result = "D"
                draws += 1

            parsed.append({
                "date": event.get("dateEvent", ""),
                "home_team": home,
                "away_team": away,
                "home_score": hs,
                "away_score": as_,
                "result": result,
                "league": event.get("strLeague", ""),
            })

        return {
            "source": "the-sports-db",
            "data": {
                "team_name": team_name_actual,
                "last_matches": parsed,
                "form_string": ",".join(r["result"] for r in parsed),
                "wins": wins, "draws": draws, "losses": losses,
                "win_rate": round(wins / len(parsed) * 100, 1) if parsed else 0,
            },
            "remaining": -1,
        }

    # ========================================================================
    # 国际API部分 - 伤停信息
    # ========================================================================

    async def get_injuries(self, team_name: str) -> Dict[str, Any]:
        """
        获取伤停信息 - 用于背景分析(权重15%)
        数据源: api-football

        Args:
            team_name: 球队名称

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        cache_key = self._cache_key("injuries", team_name=team_name)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        result = await self._get_injuries_api_football(team_name)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        return make_response(source="none", data=None, error="伤停数据获取失败")

    async def _get_injuries_api_football(self, team_name: str) -> Optional[Dict]:
        """api-football 伤停信息"""
        remaining = self.quota.consume("api-football")
        if remaining < 0:
            return None

        config = self._get_api_config("api-football")
        if not config.get("api_key"):
            return None

        team_id = await self._search_team_id_api_football(team_name, config)
        if not team_id:
            return None

        await self._rate_limit("api-football", min_interval=6.0)

        url = f"{config['base_url']}/injuries"
        headers = {"x-apisports-key": config["api_key"]}
        params = {"team": team_id, "season": self._current_season()}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            return None

        injuries = self._parse_api_football_injuries(resp["data"])
        return {"source": "api-football", "data": injuries, "remaining": remaining}

    def _parse_api_football_injuries(self, raw: Dict) -> Dict:
        """解析伤停信息"""
        player_list = []
        for item in raw.get("response", []):
            player = item.get("player", {})
            fixture = item.get("fixture", {})
            player_list.append({
                "player_name": player.get("name", ""),
                "player_type": item.get("player", {}).get("type", ""),
                "reason": item.get("player", {}).get("reason", ""),
                "date": fixture.get("date", ""),
                "league": fixture.get("league", {}).get("name", ""),
            })

        return {
            "team_name": "",
            "total_injured": len(player_list),
            "injury_list": player_list,
        }

    # ========================================================================
    # 国际API部分 - 赛程
    # ========================================================================

    async def get_fixtures(self, league_code: str, date: str = None) -> Dict[str, Any]:
        """
        获取赛程 - 用于赛程密度分析
        优先级: api-football -> football-data.org

        Args:
            league_code: 联赛代码
            date: 日期，格式 YYYY-MM-DD，默认今天

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        cache_key = self._cache_key("fixtures", league_code=league_code, date=date)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        # 尝试 api-football
        result = await self._get_fixtures_api_football(league_code, date)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        # 尝试 football-data.org
        result = await self._get_fixtures_football_data_org(league_code, date)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        return make_response(source="none", data=None, error="所有赛程数据源均失败")

    async def _get_fixtures_api_football(self, league_code: str, date: str) -> Optional[Dict]:
        """api-football 赛程"""
        remaining = self.quota.consume("api-football")
        if remaining < 0:
            return None

        config = self._get_api_config("api-football")
        if not config.get("api_key"):
            return None

        league_id = LEAGUE_ID_MAP.get(league_code)
        if not league_id:
            return None

        await self._rate_limit("api-football", min_interval=6.0)

        url = f"{config['base_url']}/fixtures"
        headers = {"x-apisports-key": config["api_key"]}
        params = {"league": league_id, "season": self._current_season(), "date": date}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            return None

        fixtures = self._parse_api_football_fixtures(resp["data"])
        return {"source": "api-football", "data": fixtures, "remaining": remaining}

    def _parse_api_football_fixtures(self, raw: Dict) -> Dict:
        """解析赛程"""
        matches = []
        for f in raw.get("response", []):
            home = f.get("teams", {}).get("home", {})
            away = f.get("teams", {}).get("away", {})
            goals = f.get("goals", {})
            matches.append({
                "fixture_id": f.get("fixture", {}).get("id", 0),
                "date": f.get("fixture", {}).get("date", ""),
                "status": f.get("fixture", {}).get("status", {}).get("short", ""),
                "home_team": home.get("name", ""),
                "away_team": away.get("name", ""),
                "home_score": goals.get("home"),
                "away_score": goals.get("away"),
                "league": f.get("league", {}).get("name", ""),
            })

        return {
            "date": "",
            "total_matches": len(matches),
            "matches": matches,
        }

    async def _get_fixtures_football_data_org(self, league_code: str, date: str) -> Optional[Dict]:
        """football-data.org 赛程"""
        config = self._get_api_config("football-data.org")
        if not config.get("api_key"):
            return None

        comp_code = LEAGUE_CODE_MAP.get(league_code)
        if not comp_code:
            return None

        await self._rate_limit("football-data.org", min_interval=6.5)

        url = f"{config['base_url']}/competitions/{comp_code}/matches"
        headers = {"X-Auth-Token": config["api_key"]}
        params = {"dateFrom": date, "dateTo": date}

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            return None

        matches = []
        for m in resp["data"].get("matches", []):
            home = m.get("homeTeam", {})
            away = m.get("awayTeam", {})
            score = m.get("score", {}).get("fullTime", {})
            matches.append({
                "fixture_id": m.get("id", 0),
                "date": m.get("utcDate", ""),
                "status": m.get("status", ""),
                "home_team": home.get("name", ""),
                "away_team": away.get("name", ""),
                "home_score": score.get("home"),
                "away_score": score.get("away"),
                "league": m.get("competition", {}).get("name", ""),
            })

        if not matches:
            return None

        return {
            "source": "football-data.org",
            "data": {
                "date": date,
                "total_matches": len(matches),
                "matches": matches,
            },
            "remaining": -1,
        }

    # ========================================================================
    # 多机构赔率部分
    # ========================================================================

    async def get_market_odds(self, match_id: str = None, sport: str = "soccer",
                              league: str = None) -> Dict[str, Any]:
        """
        获取多机构欧赔对比 - 用于市场共识分析
        优先级: The Odds API -> Odds-API.io -> nowgoal.com爬取

        Args:
            match_id: 比赛ID (可选, 用于特定比赛)
            sport: 运动类型，默认 "soccer"
            league: 联赛代码 (可选, 用于获取联赛所有比赛赔率)

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        cache_key = self._cache_key("market_odds", match_id=match_id, sport=sport, league=league)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        # 尝试 The Odds API
        result = await self._get_market_odds_the_odds_api(sport, league)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        # 尝试 Odds-API.io
        result = await self._get_market_odds_odds_api_io(sport, league)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=result.get("remaining", -1))

        # 尝试网页爬取降级（球探网/捷报比分）
        result = await self._get_market_odds_web_scrape(match_id)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=-1)

        return make_response(source="none", data=None, error="所有赔率数据源均失败")

    async def _get_market_odds_the_odds_api(self, sport: str, league: str = None) -> Optional[Dict]:
        """The Odds API 多机构赔率（含欧指、亚盘、大小球）"""
        remaining = self.quota.consume("the-odds-api")
        if remaining < 0:
            return None

        config = self._get_api_config("the-odds-api")
        if not config.get("api_key"):
            return None

        await self._rate_limit("the-odds-api", min_interval=1.0)

        odds_league = THE_ODDS_API_LEAGUE_MAP.get(league, "") if league else ""
        url = f"{config['base_url']}/sports/{sport}/odds"
        params = {
            "apiKey": config["api_key"],
            "regions": "eu",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "decimal",
        }
        if odds_league:
            url = f"{config['base_url']}/sports/{odds_league}/odds"

        resp = await self.http.get(url, params=params)
        if not resp["ok"]:
            return None

        data = resp["data"]
        # data是列表，remaining在响应头中
        remaining_from_api = resp.get("headers", {}).get("x-requests-remaining", 0)
        if isinstance(remaining_from_api, str):
            remaining_from_api = int(remaining_from_api)

        # 更新配额
        self.quota.init_quota("the-odds-api", daily_limit=0,
                              monthly_limit=max(0, remaining_from_api))

        odds_list = self._parse_the_odds_api(data)
        return {"source": "the-odds-api", "data": odds_list, "remaining": remaining_from_api}

    def _parse_the_odds_api(self, raw: List) -> List[Dict]:
        """解析 The Odds API 赔率（含欧指、亚盘、大小球）

        解析三种市场:
          - h2h: 欧指（胜平负）
          - spreads: 亚盘
          - totals: 大小球

        同时计算市场共识(平均赔率、返还率)和凯利指数。
        """
        results = []
        for match in raw:
            home_team = match.get("home_team", "")
            away_team = match.get("away_team", "")

            european_odds = []   # 欧指
            asian_handicap = []  # 亚盘
            over_under = []      # 大小球

            for bm in match.get("bookmakers", []):
                bm_name = bm.get("title", "")
                last_update = bm.get("last_update", "")

                for market in bm.get("markets", []):
                    market_key = market.get("key", "")
                    outcomes = market.get("outcomes", [])

                    if market_key == "h2h":
                        # 解析欧指
                        odds_data = {"bookmaker": bm_name, "update_time": last_update}
                        for p in outcomes:
                            name = p.get("name", "")
                            price = p.get("price")
                            if name == home_team:
                                odds_data["home_win"] = price
                            elif name == away_team:
                                odds_data["away_win"] = price
                            elif name == "Draw":
                                odds_data["draw"] = price
                        if "home_win" in odds_data and "away_win" in odds_data:
                            european_odds.append(odds_data)

                    elif market_key == "spreads":
                        # 解析亚盘
                        spread_data = {"bookmaker": bm_name, "update_time": last_update}
                        for p in outcomes:
                            name = p.get("name", "")
                            price = p.get("price")
                            point = p.get("point")
                            if name == home_team:
                                spread_data["home_handicap"] = point
                                spread_data["home_odds"] = price
                            elif name == away_team:
                                spread_data["away_handicap"] = point
                                spread_data["away_odds"] = price
                        if "home_handicap" in spread_data:
                            asian_handicap.append(spread_data)

                    elif market_key == "totals":
                        # 解析大小球
                        totals_data = {"bookmaker": bm_name, "update_time": last_update}
                        for p in outcomes:
                            name = p.get("name", "")
                            price = p.get("price")
                            point = p.get("point")
                            if name == "Over":
                                totals_data["line"] = point
                                totals_data["over_odds"] = price
                            elif name == "Under":
                                totals_data["line"] = point
                                totals_data["under_odds"] = price
                        if "line" in totals_data:
                            over_under.append(totals_data)

            # 计算市场共识（平均赔率）
            consensus = self._calc_consensus(european_odds)

            # 计算凯利指数
            kelly = self._calc_kelly(european_odds)

            results.append({
                "home_team": home_team,
                "away_team": away_team,
                "match_time": match.get("commence_time", ""),
                "european_odds": european_odds,
                "asian_handicap": asian_handicap,
                "over_under": over_under,
                "consensus": consensus,
                "kelly": kelly,
            })

        return results

    @staticmethod
    def _calc_consensus(european_odds: List[Dict]) -> Dict:
        """计算欧指市场共识（平均赔率和返还率）

        Args:
            european_odds: 欧指列表，每项包含 home_win/draw/away_win

        Returns:
            {"avg_home_win": float, "avg_draw": float, "avg_away_win": float, "payout_rate": float}
        """
        if not european_odds:
            return {}

        home_odds = [e["home_win"] for e in european_odds if e.get("home_win")]
        draw_odds = [e["draw"] for e in european_odds if e.get("draw")]
        away_odds = [e["away_win"] for e in european_odds if e.get("away_win")]

        if not home_odds or not draw_odds or not away_odds:
            return {}

        avg_home = sum(home_odds) / len(home_odds)
        avg_draw = sum(draw_odds) / len(draw_odds)
        avg_away = sum(away_odds) / len(away_odds)

        # 返还率 = 1 / (1/home + 1/draw + 1/away)
        implied_sum = 1.0 / avg_home + 1.0 / avg_draw + 1.0 / avg_away
        payout_rate = round(1.0 / implied_sum, 4) if implied_sum > 0 else 0

        return {
            "avg_home_win": round(avg_home, 3),
            "avg_draw": round(avg_draw, 3),
            "avg_away_win": round(avg_away, 3),
            "payout_rate": payout_rate,
            "bookmaker_count": len(european_odds),
        }

    @staticmethod
    def _calc_kelly(european_odds: List[Dict]) -> Dict:
        """计算凯利指数

        凯利指数 = 平均赔率 * 隐含概率 / 返还率
        隐含概率 = 1 / 赔率
        凯利 < 1 表示该结果被低估（有价值），凯利 > 1 表示被高估

        Args:
            european_odds: 欧指列表

        Returns:
            {"home_kelly": float, "draw_kelly": float, "away_kelly": float}
        """
        if not european_odds:
            return {}

        home_odds = [e["home_win"] for e in european_odds if e.get("home_win")]
        draw_odds = [e["draw"] for e in european_odds if e.get("draw")]
        away_odds = [e["away_win"] for e in european_odds if e.get("away_win")]

        if not home_odds or not draw_odds or not away_odds:
            return {}

        avg_home = sum(home_odds) / len(home_odds)
        avg_draw = sum(draw_odds) / len(draw_odds)
        avg_away = sum(away_odds) / len(away_odds)

        # 隐含概率
        prob_home = 1.0 / avg_home
        prob_draw = 1.0 / avg_draw
        prob_away = 1.0 / avg_away

        # 返还率
        implied_sum = prob_home + prob_draw + prob_away
        payout_rate = 1.0 / implied_sum if implied_sum > 0 else 1.0

        # 凯利指数
        home_kelly = round((avg_home * prob_home) / payout_rate, 4) if payout_rate > 0 else 0
        draw_kelly = round((avg_draw * prob_draw) / payout_rate, 4) if payout_rate > 0 else 0
        away_kelly = round((avg_away * prob_away) / payout_rate, 4) if payout_rate > 0 else 0

        return {
            "home_kelly": home_kelly,
            "draw_kelly": draw_kelly,
            "away_kelly": away_kelly,
        }

    async def _get_market_odds_odds_api_io(self, sport: str = "football", league: str = None) -> Optional[Dict]:
        """Odds-API.io 赔率对比 - 正确的v3 API端点"""
        config = self._get_api_config("odds-api-io")
        if not config.get("api_key"):
            return None

        await self._rate_limit("odds-api-io", min_interval=1.0)

        # 步骤1: 获取events列表
        events_url = f"{config['base_url']}/events"
        params = {
            "apiKey": config["api_key"],
            "sport": sport,
            "limit": 20,
        }
        if league:
            params["league"] = league

        resp = await self.http.get(events_url, params=params)
        if not resp["ok"]:
            return None

        events = resp["data"]
        if not events or not isinstance(events, list):
            return None

        # 步骤2: 获取第一个event的odds
        event_id = events[0].get("id")
        if not event_id:
            return None

        odds_url = f"{config['base_url']}/odds"
        odds_params = {
            "apiKey": config["api_key"],
            "eventId": event_id,
            "bookmakers": "Bet365,Unibet,Pinnacle",
        }

        odds_resp = await self.http.get(odds_url, params=odds_params)
        if not odds_resp["ok"]:
            return None

        odds_data = odds_resp["data"]
        parsed = self._parse_odds_api_io(odds_data)
        return {"source": "odds-api.io", "data": parsed, "remaining": -1}

    def _parse_odds_api_io(self, raw: Dict) -> Dict:
        """解析 Odds-API.io 赔率响应"""
        bookmakers = raw.get("bookmakers", {})
        parsed_bookmakers = []

        for bm_name, markets in bookmakers.items():
            for market in markets:
                if market.get("name") == "ML":  # Moneyline = 胜平负
                    odds = market.get("odds", [{}])[0]
                    parsed_bookmakers.append({
                        "bookmaker": bm_name,
                        "home_win": float(odds.get("home", 0)),
                        "draw": float(odds.get("draw", 0)),
                        "away_win": float(odds.get("away", 0)),
                        "last_update": market.get("updatedAt", ""),
                    })

        return {
            "home_team": raw.get("home", ""),
            "away_team": raw.get("away", ""),
            "match_time": raw.get("date", ""),
            "bookmakers": parsed_bookmakers,
        }

    async def _get_market_odds_web_scrape(self, match_id: str = None) -> Optional[Dict]:
        """网页爬取降级 - 球探网/捷报比分

        当所有 API 数据源失败时，通过爬取公开网页获取赔率数据。
        需要 match_id（球探网/捷报比赛ID）才能爬取。

        Args:
            match_id: 比赛ID

        Returns:
            {"source": str, "data": {...}, "remaining": int}
        """
        if not match_id:
            return None

        try:
            from mcp_server.web_scraper import OddsScraperManager
            scraper = OddsScraperManager(http_client=self.http)
            result = scraper.get_all_odds(match_id)
            if result:
                return {
                    "source": result["source"],
                    "data": result["data"],
                    "remaining": -1,
                }
        except Exception as e:
            logger.warning(f"网页爬取降级失败: {e}")

        return None

    # ========================================================================
    # 国内数据部分 - 竞彩赔率变化
    # ========================================================================

    async def get_lottery_odds_change(self, match_id: str) -> Dict[str, Any]:
        """
        获取竞彩赔率变化 - lottery.gov.cn / sporttery.cn 爬取

        Args:
            match_id: 比赛ID

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        cache_key = self._cache_key("lottery_odds_change", match_id=match_id)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        result = await self._get_lottery_odds_from_sporttery(match_id)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=-1)

        return make_response(source="none", data=None, error="竞彩赔率变化获取失败")

    async def _get_lottery_odds_from_sporttery(self, match_id: str = None) -> Optional[Dict]:
        """从 sporttery.cn 获取竞彩赔率变化（5种赔率玩法全量数据）

        竞彩足球官方共6种玩法：胜平负、让球胜平负、比分、总进球、半全场、混合过关
        其中混合过关是投注方式，不是独立赔率玩法
        本API提取5种赔率数据: HAD(胜平负), HHAD(让球胜平负), CRS(比分), TTG(总进球), HAFU(半全场)
        请求参数: poolCode=had,hhad,crs,ttg,hafu&channel=c

        Args:
            match_id: 比赛ID，如果为None或'all'则返回所有比赛
        """
        url = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.sporttery.cn/",
        }
        params = {
            "poolCode": "had,hhad,crs,ttg,hafu",
            "channel": "c",
        }

        resp = await self.http.get(url, headers=headers, params=params)
        if not resp["ok"]:
            return None

        data = resp["data"]
        value = data.get("value", {})
        if not isinstance(value, dict):
            return None

        # 收集所有比赛
        all_matches = []
        for group in value.get("matchInfoList", []):
            all_matches.extend(group.get("subMatchList", []))

        if not all_matches:
            return None

        # 如果请求所有比赛
        if match_id is None or match_id == 'all':
            matches_data = []
            for m in all_matches:
                parsed = self._parse_sporttery_match(m)
                if parsed:
                    matches_data.append(parsed)

            return {
                "source": "sporttery.cn",
                "data": matches_data,
                "remaining": -1,
            }

        # 搜索指定 match_id
        target = None
        for m in all_matches:
            if str(m.get("matchId", "")) == str(match_id):
                target = m
                break

        if not target:
            return None

        parsed = self._parse_sporttery_match(target)
        if not parsed:
            return None

        return {
            "source": "sporttery.cn",
            "data": parsed,
            "remaining": -1,
        }

    def _parse_sporttery_match(self, m: Dict) -> Optional[Dict]:
        """解析单场比赛的6种玩法赔率数据

        Args:
            m: sporttery API返回的单场比赛原始数据

        Returns:
            解析后的比赛数据字典，包含 had/hhad/crs/ttg/hafu 全部赔率
        """
        match_id = m.get("matchId", "")
        if not match_id:
            return None

        result = {
            "match_id": str(match_id),
            "match_num": m.get("matchNumStr", "") or m.get("matchNum", ""),
            "match_num_str": m.get("matchNumStr", ""),
            "league": m.get("leagueAbbName", ""),
            "home_team": m.get("homeTeamAbbName", ""),
            "away_team": m.get("awayTeamAbbName", ""),
            "match_time": m.get("matchDate", "") + " " + m.get("matchTime", ""),
            "sell_status": m.get("sellStatus", ""),
            "home_rank": m.get("homeRank", ""),
            "away_rank": m.get("awayRank", ""),
        }

        # 解析 oddsList 中的 HAD 和 HHAD
        for item in m.get("oddsList", []):
            pool = item.get("poolCode", "").lower()
            if pool == "had":
                result["had"] = {
                    "win": item.get("h", ""),
                    "draw": item.get("d", ""),
                    "lose": item.get("a", ""),
                    "update_time": item.get("updateTime", ""),
                }
            elif pool == "hhad":
                result["hhad"] = {
                    "win": item.get("h", ""),
                    "draw": item.get("d", ""),
                    "lose": item.get("a", ""),
                    "handicap": item.get("goalLine", ""),
                    "update_time": item.get("updateTime", ""),
                }

        # 解析 CRS (比分) - 在 match.crs 字段
        crs_raw = m.get("crs", {})
        if crs_raw and isinstance(crs_raw, dict):
            crs_data = {}
            for key, val in crs_raw.items():
                if not val:
                    continue
                label = self._parse_crs_key(key)
                if label:
                    crs_data[label] = val
            if crs_data:
                crs_data["update_time"] = m.get("crsUpdateTime", "") or m.get("updateTime", "")
                result["crs"] = crs_data

        # 解析 TTG (总进球) - 在 match.ttg 字段
        ttg_raw = m.get("ttg", {})
        if ttg_raw and isinstance(ttg_raw, dict):
            ttg_data = {}
            for key, val in ttg_raw.items():
                if not val:
                    continue
                # s0-s7 对应 0-7球
                match_t = key.startswith("s") and key[1:].isdigit()
                if match_t:
                    goals = int(key[1:])
                    if goals <= 6:
                        ttg_data[str(goals)] = val
                    elif goals == 7:
                        ttg_data["7+"] = val
            if ttg_data:
                ttg_data["update_time"] = m.get("ttgUpdateTime", "") or m.get("updateTime", "")
                result["ttg"] = ttg_data

        # 解析 HAFU (半全场) - 在 match.hafu 字段
        hafu_raw = m.get("hafu", {})
        if hafu_raw and isinstance(hafu_raw, dict):
            hafu_data = {}
            hafu_map = {
                "aa": "胜胜", "ad": "胜平", "ah": "胜负",
                "da": "平胜", "dd": "平平", "dh": "平负",
                "ha": "负胜", "hd": "负平", "hh": "负负",
            }
            for key, val in hafu_raw.items():
                if not val:
                    continue
                label = hafu_map.get(key)
                if label:
                    hafu_data[label] = val
            if hafu_data:
                hafu_data["update_time"] = m.get("hafuUpdateTime", "") or m.get("updateTime", "")
                result["hafu"] = hafu_data

        return result

    @staticmethod
    def _parse_crs_key(key: str) -> Optional[str]:
        """解析CRS赔率键名为中文标签

        CRS键名格式:
          s{h}s{a} = 主{h}客{a} 的比分赔率, 如 s00s00 = 0:0, s01s02 = 1:2
          s{h}sa  = 主{h} 其他胜赔率, 如 s1sa = 胜其他(主1+)
          s{h}sd  = 主{h} 其他平赔率
          s{h}sh  = 主{h} 其他负赔率

        Args:
            key: CRS原始键名，如 "s00s00", "s01s02", "s1sa"

        Returns:
            中文标签，如 "0:0", "1:2", "胜其他", "平其他", "负其他"
        """
        if not key or not key.startswith("s"):
            return None

        # 其他类型: s1sa, s1sd, s1sh
        if key.endswith("sa"):
            return "胜其他"
        if key.endswith("sd"):
            return "平其他"
        if key.endswith("sh"):
            return "负其他"

        # 标准比分: s{h}s{a}, 如 s00s00, s01s02, s10s00
        # 格式: s + 主队进球 + s + 客队进球
        parts = key.split("s")
        if len(parts) == 3 and parts[0] == "" and parts[2] != "":
            home = parts[1]
            away = parts[2]
            # 验证都是数字
            if home.isdigit() and away.isdigit():
                return f"{int(home)}:{int(away)}"

        return None

    # ========================================================================
    # 竞彩网 uniform 接口 - 比赛资讯（7个接口）
    # ========================================================================

    BASE_URL_UNIFORM = "https://webapi.sporttery.cn/gateway/uniform/football"

    async def get_match_head(self, match_id: str) -> Dict[str, Any]:
        """获取比赛头部信息

        Args:
            match_id: 竞彩比赛ID

        Returns:
            {"source": str, "data": {...}, "cached": bool}
        """
        cache_key = self._cache_key("match_head", match_id=match_id)
        cached = self.cache.get(cache_key)
        if cached:
            return make_response(source="cache", data=cached, cached=True)

        url = f"{self.BASE_URL_UNIFORM}/getMatchHeadV1.qry"
        headers = {"Referer": "https://www.sporttery.cn/"}
        params = {"source": "web", "sportteryMatchId": match_id}

        resp = await self.http.get(url, headers=headers, params=params)
        if resp["ok"]:
            data = resp["data"].get("value", {})
            self.cache.set(cache_key, data)
            return make_response(source="sporttery.cn", data=data, cached=False)

        return make_response(source="none", data=None, error="获取比赛头部信息失败")

    async def get_match_feature(self, match_id: str, term_limits: int = 10) -> Dict[str, Any]:
        """获取特征分析

        Args:
            match_id: 竞彩比赛ID
            term_limits: 统计场次数

        Returns:
            {"source": str, "data": {...}, "cached": bool}
        """
        cache_key = self._cache_key("match_feature", match_id=match_id, term=term_limits)
        cached = self.cache.get(cache_key)
        if cached:
            return make_response(source="cache", data=cached, cached=True)

        url = f"{self.BASE_URL_UNIFORM}/getMatchFeatureV1.qry"
        headers = {"Referer": "https://www.sporttery.cn/"}
        params = {"sportteryMatchId": match_id, "termLimits": term_limits}

        resp = await self.http.get(url, headers=headers, params=params)
        if resp["ok"]:
            data = resp["data"].get("value", {})
            self.cache.set(cache_key, data)
            return make_response(source="sporttery.cn", data=data, cached=False)

        return make_response(source="none", data=None, error="获取特征分析失败")

    async def get_result_history(self, match_id: str, term_limits: int = 10,
                                  tournament_flag: int = 0, home_away_flag: int = 0) -> Dict[str, Any]:
        """获取历史交锋

        Args:
            match_id: 竞彩比赛ID
            term_limits: 返回场次数
            tournament_flag: 0=全部赛制, 1=相同赛制
            home_away_flag: 0=不区分主客, 1=相同主客

        Returns:
            {"source": str, "data": {...}, "cached": bool}
        """
        cache_key = self._cache_key("result_history", match_id=match_id, term=term_limits)
        cached = self.cache.get(cache_key)
        if cached:
            return make_response(source="cache", data=cached, cached=True)

        url = f"{self.BASE_URL_UNIFORM}/getResultHistoryV1.qry"
        headers = {"Referer": "https://www.sporttery.cn/"}
        params = {
            "sportteryMatchId": match_id,
            "termLimits": term_limits,
            "tournamentFlag": tournament_flag,
            "homeAwayFlag": home_away_flag,
        }

        resp = await self.http.get(url, headers=headers, params=params)
        if resp["ok"]:
            data = resp["data"].get("value", {})
            self.cache.set(cache_key, data)
            return make_response(source="sporttery.cn", data=data, cached=False)

        return make_response(source="none", data=None, error="获取历史交锋失败")

    async def get_match_tables(self, match_id: str) -> Dict[str, Any]:
        """获取积分榜

        Args:
            match_id: 竞彩比赛ID

        Returns:
            {"source": str, "data": {...}, "cached": bool}
        """
        cache_key = self._cache_key("match_tables", match_id=match_id)
        cached = self.cache.get(cache_key)
        if cached:
            return make_response(source="cache", data=cached, cached=True)

        url = f"{self.BASE_URL_UNIFORM}/getMatchTablesV2.qry"
        headers = {"Referer": "https://www.sporttery.cn/"}
        params = {"gmMatchId": match_id}

        resp = await self.http.get(url, headers=headers, params=params)
        if resp["ok"]:
            data = resp["data"].get("value", {})
            self.cache.set(cache_key, data)
            return make_response(source="sporttery.cn", data=data, cached=False)

        return make_response(source="none", data=None, error="获取积分榜失败")

    async def get_match_recent_form(self, match_id: str, term_limits: int = 10) -> Dict[str, Any]:
        """获取比赛近况（各队近期战绩）

        Args:
            match_id: 竞彩比赛ID
            term_limits: 返回场次数

        Returns:
            {"source": str, "data": {...}, "cached": bool}
        """
        cache_key = self._cache_key("match_recent_form", match_id=match_id, term=term_limits)
        cached = self.cache.get(cache_key)
        if cached:
            return make_response(source="cache", data=cached, cached=True)

        url = f"{self.BASE_URL_UNIFORM}/getMatchResultV1.qry"
        headers = {"Referer": "https://www.sporttery.cn/"}
        params = {
            "sportteryMatchId": match_id,
            "termLimits": term_limits,
            "tournamentFlag": 0,
            "homeAwayFlag": 0,
        }

        resp = await self.http.get(url, headers=headers, params=params)
        if resp["ok"]:
            data = resp["data"].get("value", {})
            self.cache.set(cache_key, data)
            return make_response(source="sporttery.cn", data=data, cached=False)

        return make_response(source="none", data=None, error="获取比赛近况失败")

    async def get_future_matches(self, match_id: str, term_limits: int = 4) -> Dict[str, Any]:
        """获取未来赛事

        Args:
            match_id: 竞彩比赛ID
            term_limits: 返回场次数

        Returns:
            {"source": str, "data": {...}, "cached": bool}
        """
        cache_key = self._cache_key("future_matches", match_id=match_id, term=term_limits)
        cached = self.cache.get(cache_key)
        if cached:
            return make_response(source="cache", data=cached, cached=True)

        url = f"{self.BASE_URL_UNIFORM}/getFutureMatchesV1.qry"
        headers = {"Referer": "https://www.sporttery.cn/"}
        params = {"sportteryMatchId": match_id, "termLimits": term_limits}

        resp = await self.http.get(url, headers=headers, params=params)
        if resp["ok"]:
            data = resp["data"].get("value", {})
            self.cache.set(cache_key, data)
            return make_response(source="sporttery.cn", data=data, cached=False)

        return make_response(source="none", data=None, error="获取未来赛事失败")

    async def get_match_players(self, match_id: str, term_limits: int = 3) -> Dict[str, Any]:
        """获取射手信息

        Args:
            match_id: 竞彩比赛ID
            term_limits: 返回球员数

        Returns:
            {"source": str, "data": {...}, "cached": bool}
        """
        cache_key = self._cache_key("match_players", match_id=match_id, term=term_limits)
        cached = self.cache.get(cache_key)
        if cached:
            return make_response(source="cache", data=cached, cached=True)

        url = f"{self.BASE_URL_UNIFORM}/getMatchPlayerV1.qry"
        headers = {"Referer": "https://www.sporttery.cn/"}
        params = {"sportteryMatchId": match_id, "termLimits": term_limits}

        resp = await self.http.get(url, headers=headers, params=params)
        if resp["ok"]:
            data = resp["data"].get("value", {})
            self.cache.set(cache_key, data)
            return make_response(source="sporttery.cn", data=data, cached=False)

        return make_response(source="none", data=None, error="获取射手信息失败")

    async def get_injury_suspension(self, match_id: str) -> Dict[str, Any]:
        """获取伤停一览

        Args:
            match_id: 竞彩比赛ID

        Returns:
            {"source": str, "data": {...}, "cached": bool}
        """
        cache_key = self._cache_key("injury_suspension", match_id=match_id)
        cached = self.cache.get(cache_key)
        if cached:
            return make_response(source="cache", data=cached, cached=True)

        url = f"{self.BASE_URL_UNIFORM}/getInjurySuspensionV1.qry"
        headers = {"Referer": "https://www.sporttery.cn/"}
        params = {"sportteryMatchId": match_id}

        resp = await self.http.get(url, headers=headers, params=params)
        if resp["ok"]:
            data = resp["data"].get("value", {})
            self.cache.set(cache_key, data)
            return make_response(source="sporttery.cn", data=data, cached=False)

        return make_response(source="none", data=None, error="获取伤停信息失败")

    # ========================================================================
    # 国内数据部分 - 竞彩赛果开奖
    # ========================================================================

    async def get_lottery_results(self, date: str = None) -> Dict[str, Any]:
        """
        获取竞彩赛果开奖 - zx.500.com 爬取

        Args:
            date: 日期，格式 YYYY-MM-DD，默认今天

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        cache_key = self._cache_key("lottery_results", date=date)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        result = await self._get_lottery_results_from_500(date)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=-1)

        # 备用: 从 sporttery.cn 获取
        result = await self._get_lottery_results_from_sporttery(date)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=-1)

        return make_response(source="none", data=None, error="赛果数据获取失败")

    async def _get_lottery_results_from_500(self, date: str) -> Optional[Dict]:
        """从 500.com 获取竞彩赛果"""
        # 500.com 竞彩开奖页面
        date_formatted = date.replace("-", "")
        url = f"https://zx.500.com/jczq/kaijiang.php?date={date_formatted}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        resp = await self.http.get(url, headers=headers)
        if not resp["ok"]:
            return None

        # 500.com 返回HTML，需要解析
        # 这里返回原始HTML标记，实际使用时可用 BeautifulSoup 解析
        return {
            "source": "500.com",
            "data": {
                "date": date,
                "raw_html": resp["data"][:2000] if isinstance(resp["data"], str) else str(resp["data"])[:2000],
                "note": "HTML数据需要使用BeautifulSoup解析，此处返回原始内容前2000字符",
                "parse_required": True,
            },
            "remaining": -1,
        }

    async def _get_lottery_results_from_sporttery(self, date: str) -> Optional[Dict]:
        """从 sporttery.cn 获取赛果（备用）"""
        url = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.sporttery.cn/",
        }

        resp = await self.http.get(url, headers=headers)
        if not resp["ok"]:
            return None

        data = resp["data"]
        value = data.get("value", {})
        if not isinstance(value, dict):
            return None

        all_matches = []
        for group in value.get("matchInfoList", []):
            all_matches.extend(group.get("subMatchList", []))

        results = []
        for m in all_matches:
            match_date = m.get("matchDate", "")
            if match_date != date.replace("-", ""):
                continue

            results.append({
                "match_id": m.get("matchId", ""),
                "league": m.get("leagueAbbName", ""),
                "home_team": m.get("homeTeamAbbName", ""),
                "away_team": m.get("awayTeamAbbName", ""),
                "match_time": match_date + " " + m.get("matchTime", ""),
                "status": m.get("matchStatus", ""),
                "home_score": m.get("homeGoalNum", ""),
                "away_score": m.get("awayGoalNum", ""),
            })

        if not results:
            return None

        return {
            "source": "sporttery.cn",
            "data": {
                "date": date,
                "total_matches": len(results),
                "results": results,
            },
            "remaining": -1,
        }

    # ========================================================================
    # 传统足彩数据 (胜负彩14场/任选9场/4场进球/6场半全场)
    # 数据源: kaijiang.500.com (开奖) + zx.500.com/zc/ (当前对阵)
    # ========================================================================

    async def get_ctzc_results(self, expect: str = None, lottery_type: str = "sfc") -> Dict[str, Any]:
        """
        获取传统足彩开奖结果 + 参考赔率

        Args:
            expect: 期号，如 "26076"。默认最新期
            lottery_type: 彩种类型
                - "sfc": 胜负彩14场 (默认)
                - "rx9": 任选9场
                - "jqc": 4场进球彩
                - "bqc": 6场半全场

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
            data中包含:
            - 开奖结果 (from 500.com)
            - reference_odds: 参考赔率 (from sporttery.cn API, 可能不可用)
        """
        cache_key = self._cache_key("ctzc_results", expect=expect, lottery_type=lottery_type)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        # 1. 获取开奖结果 (500.com)
        result = await self._get_ctzc_results_from_500(expect, lottery_type)
        if not result:
            return make_response(source="none", data=None, error="传统足彩开奖数据获取失败")

        # 2. 尝试获取参考赔率 (sporttery.cn API)
        odds_data = self._get_ctzc_reference_odds(expect, lottery_type)
        if odds_data:
            result["data"]["reference_odds"] = odds_data
            result["data"]["odds_source"] = "sporttery.cn"
        else:
            result["data"]["reference_odds"] = None
            result["data"]["odds_source"] = "unavailable"
            result["data"]["odds_note"] = (
                "参考赔率暂不可用: sporttery.cn API需要特定请求头，"
                "500.com开奖页面不包含赔率数据。"
                "可通过 lottery_data_fetcher.fetch_ctzc_matches() 获取赔率。"
            )

        self.cache.set(cache_key, result)
        return make_response(source=result["source"], data=result["data"],
                             cached=False, remaining_quota=-1)

    def _get_ctzc_reference_odds(self, expect: str, lottery_type: str) -> Optional[List[Dict]]:
        """
        从 sporttery.cn API 获取传统足彩参考赔率。

        API: https://webapi.sporttery.cn/gateway/zc/football/getMatchListV1.qry
        该API可能被WAF拦截，返回None表示不可用。

        Args:
            lottery_type: 玩法类型 (sfc/rx9/jqc/bqc)，不同玩法需要不同的赔率数据
        """
        import json
        import ssl
        import urllib.request
        import urllib.error

        url = "https://webapi.sporttery.cn/gateway/zc/football/getMatchListV1.qry"
        if expect:
            url += f"?issue={expect}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.sporttery.cn/",
            "Origin": "https://www.sporttery.cn",
        }

        ctx = create_ssl_context()

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("code") != 0:
                return None

            value = data.get("value", {})
            if not isinstance(value, dict):
                return None

            match_list = value.get("matchList", [])
            if not match_list:
                return None

            odds_results = []
            for m in match_list:
                odds_entry = {
                    "match_id": str(m.get("matchId", "")),
                    "match_index": m.get("matchIndex", ""),
                    "league": m.get("leagueName", ""),
                    "home_team": m.get("homeTeamName", ""),
                    "away_team": m.get("awayTeamName", ""),
                    "match_time": m.get("matchTime", ""),
                }

                # 根据玩法类型提取相应的参考赔率
                if lottery_type in ("sfc", "rx9"):
                    # 胜负彩14场/任选9场: 需要胜平负赔率
                    had = m.get("had", {})
                    if had and had.get("h"):
                        try:
                            odds_entry["had_odds"] = {
                                "win": float(had.get("h", 0)),
                                "draw": float(had.get("d", 0)),
                                "lose": float(had.get("a", 0)),
                            }
                        except (ValueError, TypeError):
                            pass
                    elif m.get("h"):
                        # 备用格式: 直接字段
                        try:
                            odds_entry["had_odds"] = {
                                "win": float(m.get("h", 0)),
                                "draw": float(m.get("d", 0)),
                                "lose": float(m.get("a", 0)),
                            }
                        except (ValueError, TypeError):
                            pass

                elif lottery_type == "jqc":
                    # 4场进球彩: 需要总进球数赔率
                    ttg = m.get("ttg", {})
                    if ttg:
                        try:
                            odds_entry["ttg_odds"] = {
                                "goals_0": float(ttg.get("s0", 0)),
                                "goals_1": float(ttg.get("s1", 0)),
                                "goals_2": float(ttg.get("s2", 0)),
                                "goals_3": float(ttg.get("s3", 0)),
                                "goals_4": float(ttg.get("s4", 0)),
                                "goals_5": float(ttg.get("s5", 0)),
                                "goals_6": float(ttg.get("s6", 0)),
                                "goals_7+": float(ttg.get("s7", 0)),
                            }
                        except (ValueError, TypeError):
                            pass
                    # 同时保留had赔率作为参考
                    had = m.get("had", {})
                    if had and had.get("h"):
                        try:
                            odds_entry["had_odds"] = {
                                "win": float(had.get("h", 0)),
                                "draw": float(had.get("d", 0)),
                                "lose": float(had.get("a", 0)),
                            }
                        except (ValueError, TypeError):
                            pass

                elif lottery_type == "bqc":
                    # 6场半全场: 需要半全场赔率
                    hafu = m.get("hafu", {})
                    if hafu:
                        try:
                            odds_entry["hafu_odds"] = {
                                "胜胜": float(hafu.get("hh", 0)),
                                "胜平": float(hafu.get("hd", 0)),
                                "胜负": float(hafu.get("ha", 0)),
                                "平胜": float(hafu.get("dh", 0)),
                                "平平": float(hafu.get("dd", 0)),
                                "平负": float(hafu.get("da", 0)),
                                "负胜": float(hafu.get("ah", 0)),
                                "负平": float(hafu.get("ad", 0)),
                                "负负": float(hafu.get("aa", 0)),
                            }
                        except (ValueError, TypeError):
                            pass
                    # 同时保留had赔率作为参考
                    had = m.get("had", {})
                    if had and had.get("h"):
                        try:
                            odds_entry["had_odds"] = {
                                "win": float(had.get("h", 0)),
                                "draw": float(had.get("d", 0)),
                                "lose": float(had.get("a", 0)),
                            }
                        except (ValueError, TypeError):
                            pass

                odds_results.append(odds_entry)

            return odds_results if odds_results else None

        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, Exception):
            return None

    async def _get_ctzc_results_from_500(self, expect: str, lottery_type: str) -> Optional[Dict]:
        """从 kaijiang.500.com 获取传统足彩开奖数据"""
        # 传统足彩官方4种玩法: 胜负彩14场、任选9场、6场半全场、4场进球
        # 任选9场与14场共用同一期比赛数据，但中奖结果不同
        url_map = {
            "sfc": "https://kaijiang.500.com/sfc.shtml",
            "rx9": "https://kaijiang.500.com/sfc.shtml",  # 任选9场与14场同页面
            "jqc": "https://kaijiang.500.com/jq4.shtml",
            "bqc": "https://kaijiang.500.com/zc6.shtml",
        }
        url = url_map.get(lottery_type)
        if not url:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        resp = await self.http.get_html(url, headers=headers, encoding="gb2312")
        if not resp["ok"]:
            return None

        raw_html = resp["data"]
        if not isinstance(raw_html, str):
            return None

        return await self._parse_ctzc_html(raw_html, lottery_type, expect)

    async def _parse_ctzc_html(self, html: str, lottery_type: str, expect: str = None) -> Optional[Dict]:
        """
        解析传统足彩HTML开奖数据

        HTML结构 (kaijiang.500.com):
        - 胜负彩14场: 14列, 每列一个场次 (title="主队 VS 客队")
        - 4场进球彩: 8列 (4场 x 主客各1), title="主队VS客队"
        - 6场半全场: 12列 (6场 x 半场/全场各1), title="主队 VS 客队"
        """
        import re

        # 提取期号 - 尝试多种格式
        period_match = re.search(r'<strong>(\d+)</strong>\s*期', html)
        if not period_match:
            period_match = re.search(r'id="change_date"[^>]*>(\d+)</a>', html)
        if not period_match:
            period_match = re.search(r'shtml/\w+/(\d+)\.shtml', html)
        period = period_match.group(1) if period_match else expect or ""

        # 如果指定了期号，检查是否匹配
        if expect and period and period != expect:
            # 尝试找指定期号的详情页
            detail_url_map = {
                "sfc": f"https://kaijiang.500.com/shtml/sfc/{expect}.shtml",
                "rx9": f"https://kaijiang.500.com/shtml/sfc/{expect}.shtml",  # 任选9场与14场同页面
                "jqc": f"https://kaijiang.500.com/shtml/jq4/{expect}.shtml",
                "bqc": f"https://kaijiang.500.com/shtml/zc6/{expect}.shtml",
            }
            detail_url = detail_url_map.get(lottery_type)
            if detail_url:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                }
                resp = await self.http.get_html(detail_url, headers=headers, encoding="gb2312")
                if resp["ok"]:
                    html = resp["data"]
                    if not isinstance(html, str):
                        return None
                    period_match = re.search(r'<strong>(\d+)</strong>\s*期', html)
                    if period_match:
                        period = period_match.group(1)

        # 提取开奖日期
        date_match = re.search(r'开奖日期：(\d+)年(\d+)月(\d+)日', html)
        draw_date = ""
        if date_match:
            draw_date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

        # 提取兑奖截止日期
        deadline_match = re.search(r'兑奖截止日期：(\d+)年(\d+)月(\d+)日', html)
        deadline = ""
        if deadline_match:
            deadline = f"{deadline_match.group(1)}-{deadline_match.group(2).zfill(2)}-{deadline_match.group(3).zfill(2)}"

        # 提取所有kj_tablelist02表格
        tables = re.findall(r'<table[^>]*class="kj_tablelist02"[^>]*>(.*?)</table>', html, re.DOTALL)
        if not tables:
            return None

        main_table = tables[0]

        if lottery_type == "sfc":
            return self._parse_sfc_table(main_table, period, draw_date, deadline, play_type="sfc")
        elif lottery_type == "rx9":
            return self._parse_sfc_table(main_table, period, draw_date, deadline, play_type="rx9")
        elif lottery_type == "jqc":
            return self._parse_jqc_table(main_table, period, draw_date, deadline)
        elif lottery_type == "bqc":
            return self._parse_bqc_table(main_table, period, draw_date, deadline)

        return None

    def _parse_sfc_table(self, table_html: str, period: str, draw_date: str, deadline: str, play_type: str = "sfc") -> Optional[Dict]:
        """解析胜负彩14场/任选9场开奖表格

        Args:
            play_type: "sfc"表示胜负彩14场, "rx9"表示任选9场
        """
        import re

        # 提取对阵信息 (title属性)
        titles = re.findall(r'title="([^"]+)"', table_html)
        # title格式: "主队 VS 客队" 或 "主队&nbsp;VS&nbsp;客队"
        vs_titles = [t for t in titles if "VS" in t or "vs" in t]

        # 提取彩果
        results = re.findall(r'cfont5\s*">(\d)</span>', table_html)

        matches = []
        for i, title in enumerate(vs_titles):
            # 清理title中的HTML实体
            clean_title = re.sub(r'&nbsp;', ' ', title).strip()
            parts = re.split(r'\s+VS\s+', clean_title, flags=re.IGNORECASE)
            if len(parts) == 2:
                home_team = parts[0].strip()
                away_team = parts[1].strip()
            else:
                home_team = clean_title
                away_team = ""

            match_data = {
                "match_num": i + 1,
                "home_team": home_team,
                "away_team": away_team,
                "result": results[i] if i < len(results) else "",
            }
            matches.append(match_data)

        # 提取奖金信息
        prize_info = self._extract_prize_info(table_html, play_type=play_type)

        # 根据玩法类型设置返回信息
        if play_type == "rx9":
            lottery_type_name = "任选9场"
            play_note = "从14场比赛中任选9场竞猜，全部猜中才能中奖"
        else:
            lottery_type_name = "胜负彩14场"
            play_note = "猜中全部14场中一等奖，猜中13场中二等奖"

        return {
            "source": "500.com",
            "data": {
                "lottery_type": lottery_type_name,
                "period": period,
                "draw_date": draw_date,
                "deadline": deadline,
                "total_matches": len(matches),
                "matches": matches,
                "prize_info": prize_info,
                "play_note": play_note,
            },
            "remaining": -1,
        }

    def _parse_jqc_table(self, table_html: str, period: str, draw_date: str, deadline: str) -> Optional[Dict]:
        """解析4场进球彩开奖表格"""
        import re

        # 进球彩的HTML结构:
        # - 每场有2个td (主队简称, 客队简称), title="主队VS客队"
        # - 每场有2个彩果 (主队进球数, 客队进球数)
        # 提取所有td内容 (去除HTML标签)
        tds = re.findall(r'<td[^>]*>(.*?)</td>', table_html, re.DOTALL)
        td_texts = []
        for td in tds:
            clean = re.sub(r'<[^>]+>', '', td).strip()
            # 跳过空内容、期号行、日期行等
            if clean and clean not in ['半', '全', '胜', '平', '负'] and not re.match(r'^[\d,元\s]+$', clean):
                td_texts.append(clean)

        # 提取彩果
        results = re.findall(r'cfont5\s*">(\d)</span>', table_html)

        # 进球彩每场: 2个球队名td + 2个彩果
        # 球队名从td内容中提取 (跳过标题行等非球队数据)
        # 找到第一个球队名的位置
        team_names = []
        in_teams = False
        for text in td_texts:
            if '进球彩' in text or '期' in text or '开奖' in text or '兑奖' in text:
                continue
            if '销量' in text or '奖池' in text:
                break
            # 球队名通常是2-6个中文字符
            if re.match(r'^[\u4e00-\u9fff]{2,8}$', text):
                team_names.append(text)

        matches = []
        num_matches = len(results) // 2
        for i in range(num_matches):
            home_team = team_names[i * 2] if i * 2 < len(team_names) else ""
            away_team = team_names[i * 2 + 1] if i * 2 + 1 < len(team_names) else ""
            home_goals = results[i * 2] if i * 2 < len(results) else ""
            away_goals = results[i * 2 + 1] if i * 2 + 1 < len(results) else ""

            match_data = {
                "match_num": i + 1,
                "home_team": home_team,
                "away_team": away_team,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "result": f"{home_goals}:{away_goals}",
            }
            matches.append(match_data)

        # 提取奖金信息
        prize_info = self._extract_prize_info(table_html)

        return {
            "source": "500.com",
            "data": {
                "lottery_type": "4场进球彩",
                "period": period,
                "draw_date": draw_date,
                "deadline": deadline,
                "total_matches": len(matches),
                "matches": matches,
                "prize_info": prize_info,
            },
            "remaining": -1,
        }

    def _parse_bqc_table(self, table_html: str, period: str, draw_date: str, deadline: str) -> Optional[Dict]:
        """解析6场半全场开奖表格"""
        import re

        # 提取对阵信息
        titles = re.findall(r'title="([^"]+)"', table_html)
        vs_titles = [t for t in titles if "VS" in t or "vs" in t]

        # 提取彩果 - 半全场每场有2个彩果(半场结果, 全场结果)
        results = re.findall(r'cfont5\s*">(\d)</span>', table_html)

        matches = []
        for i, title in enumerate(vs_titles):
            clean_title = re.sub(r'&nbsp;', ' ', title).strip()
            parts = re.split(r'\s+VS\s+', clean_title, flags=re.IGNORECASE)
            if len(parts) == 2:
                home_team = parts[0].strip()
                away_team = parts[1].strip()
            else:
                home_team = clean_title
                away_team = ""

            # 半全场每场有2个彩果(半场, 全场)
            ht_result = results[i * 2] if i * 2 < len(results) else ""
            ft_result = results[i * 2 + 1] if i * 2 + 1 < len(results) else ""

            match_data = {
                "match_num": i + 1,
                "home_team": home_team,
                "away_team": away_team,
                "half_time_result": ht_result,
                "full_time_result": ft_result,
                "result": f"{ht_result}-{ft_result}",
            }
            matches.append(match_data)

        # 提取奖金信息
        prize_info = self._extract_prize_info(table_html)

        return {
            "source": "500.com",
            "data": {
                "lottery_type": "6场半全场",
                "period": period,
                "draw_date": draw_date,
                "deadline": deadline,
                "total_matches": len(matches),
                "matches": matches,
                "prize_info": prize_info,
            },
            "remaining": -1,
        }

    def _extract_prize_info(self, table_html: str, play_type: str = "sfc") -> List[Dict]:
        """从开奖表格中提取奖金信息

        Args:
            play_type: "sfc"表示胜负彩14场, "rx9"表示任选9场
        """
        import re

        prize_info = []

        # 任选9场只有一等奖，奖金结构不同
        if play_type == "rx9":
            # 任选9场格式: 一等奖 X注 X元
            prize_patterns = re.findall(
                r'<td>([^<]*一等奖)</td>\s*<td>(\d+)</td>\s*<td>([^<]*)</td>',
                table_html
            )
            for name, count, amount in prize_patterns:
                prize_info.append({
                    "prize_name": "任选9场一等奖",
                    "winners": int(count),
                    "prize_amount": amount.strip().replace(",", ""),
                    "note": "从14场中任选9场，全部猜中才能中奖"
                })
        else:
            # 胜负彩14场格式: 一等奖 X注 X元, 二等奖 X注 X元
            prize_patterns = re.findall(
                r'<td>([^<]*奖)</td>\s*<td>(\d+)</td>\s*<td>([^<]*)</td>',
                table_html
            )
            for name, count, amount in prize_patterns:
                prize_info.append({
                    "prize_name": name.strip(),
                    "winners": int(count),
                    "prize_amount": amount.strip().replace(",", ""),
                })

        return prize_info

    async def get_ctzc_matches(self, expect: str = None) -> Dict[str, Any]:
        """
        获取传统足彩当前期对阵数据 (胜负彩14场)

        Args:
            expect: 期号，如 "26077"。默认当前期

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        cache_key = self._cache_key("ctzc_matches", expect=expect)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        result = await self._get_ctzc_matches_from_500(expect)
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=-1)

        return make_response(source="none", data=None, error="传统足彩对阵数据获取失败")

    async def _get_ctzc_matches_from_500(self, expect: str) -> Optional[Dict]:
        """从 zx.500.com/zc/ 获取传统足彩当前期对阵"""
        import re

        url = "https://zx.500.com/zc/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        resp = await self.http.get_html(url, headers=headers)
        if not resp["ok"]:
            return None

        html = resp["data"]
        if not isinstance(html, str):
            return None

        # 提取当前期号
        period_match = re.search(r'value="(\d+)"\s+selected="selected"', html)
        period = period_match.group(1) if period_match else expect or ""

        # 提取截止时间
        deadline_match = re.search(r'截止时间[^>]*>\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', html)
        deadline = deadline_match.group(1) if deadline_match else ""

        # 500.com足彩对阵通过JS动态加载，服务端HTML中只有表头
        # 尝试从页面中提取已有的静态数据
        matches = []

        # 尝试从页面中提取对阵数据 (有些版本可能有静态数据)
        match_pattern = re.findall(
            r'<a[^>]*href="https://liansai\.500\.com/zuqiu-\d+/"[^>]*>([^<]+)</a>.*?'
            r'(\d{2}-\d{2}\s+\d{2}:\d{2}).*?'
            r'\[(\d+)\]\s*<a[^>]*>([^<]+)</a>\s*\*?VS\*?\s*<a[^>]*>([^<]+)</a>\s*\*\[(\d+)\]',
            html, re.DOTALL
        )

        if match_pattern:
            for i, (league, match_time, home_rank, home_team, away_team, away_rank) in enumerate(match_pattern):
                matches.append({
                    "match_num": i + 1,
                    "league": league.strip(),
                    "match_time": match_time.strip(),
                    "home_team": home_team.strip(),
                    "home_rank": int(home_rank),
                    "away_team": away_team.strip(),
                    "away_rank": int(away_rank),
                })

        # 即使没有提取到对阵数据，也返回基本信息 (期号、截止时间等)
        return {
            "source": "500.com",
            "data": {
                "lottery_type": "胜负彩14场/任选9场",
                "period": period,
                "deadline": deadline,
                "total_matches": len(matches),
                "matches": matches,
                "note": ("对阵数据通过JS动态加载" if not matches else ""),
                "url": "https://zx.500.com/zc/",
            },
            "remaining": -1,
        }

    # ========================================================================
    # 北京单场数据
    # 数据源: zx.500.com/zqdc/kaijiang.php (开奖) + trade.500.com/bjdc/ (对阵)
    # ========================================================================

    async def get_beidan_results(self) -> Dict[str, Any]:
        """
        获取北京单场开奖结果

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        cache_key = self._cache_key("beidan_results")
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        result = await self._get_beidan_results_from_500()
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=-1)

        return make_response(source="none", data=None, error="北单开奖数据获取失败")

    async def _get_beidan_results_from_500(self) -> Optional[Dict]:
        """从 zx.500.com/zqdc/kaijiang.php 获取北单开奖数据"""
        import re

        url = "https://zx.500.com/zqdc/kaijiang.php"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        resp = await self.http.get_html(url, headers=headers, encoding="gb2312")
        if not resp["ok"]:
            return None

        raw = resp["data"]
        if not isinstance(raw, str):
            return None

        return self._parse_beidan_html(raw)

    def _parse_beidan_html(self, html: str) -> Optional[Dict]:
        """
        解析北单开奖HTML，提取所有6种玩法的SP值明细。

        数据源: zx.500.com/zqdc/kaijiang.php
        每行包含: 场次、联赛、时间、主队、让球、客队、比分、
                   让球胜平负(彩果+SP)、总进球(彩果+SP)、比分(彩果+SP)、
                   上下单双(彩果+SP)、半全场(彩果+SP)

        HTML结构示例 (每行tr中的td序列):
          <td>1</td>                          -- 场次
          <td><a class="league" title="澳超">澳超</a></td>  -- 联赛
          <td class="eng">05-15 17:35</td>    -- 时间
          <td class="text_r"><a title="阿德莱德联">...</a></td>  -- 主队
          <td class="eng"><span class="black">0</span></td>  -- 让球
          <td class="text_l"><a title="奥克兰FC">...</a></td>  -- 客队
          <td class="eng">(0:1) 0:3</td>      -- 半全场比分
          <td>&nbsp;</td>                     -- 分隔
          <td>0</td>                          -- 让球胜平负彩果
          <td class="eng"><span class="red">3.48</span></td>  -- 让球胜平负SP
          <td>&nbsp;</td>                     -- 分隔
          <td class="eng">3</td>              -- 总进球彩果
          <td class="eng"><span class="red">4.61</span></td>  -- 总进球SP
          <td>&nbsp;</td>                     -- 分隔
          <td class="eng">0:3</td>            -- 比分彩果
          <td class="eng"><span class="red">59.91</span></td> -- 比分SP
          <td>&nbsp;</td>                     -- 分隔
          <td>上单</td>                       -- 上下单双彩果
          <td class="eng"><span class="red">3.05</span></td>  -- 上下单双SP
          <td>&nbsp;</td>                     -- 分隔
          <td class="eng">负-负</td>          -- 半全场彩果
          <td class="eng"><span class="red">8.11</span></td>  -- 半全场SP
        """
        import re

        # 找到所有包含比赛数据的tr行
        tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

        # 提取期号
        period_match = re.search(r'(\d{5})期', html)
        period = period_match.group(1) if period_match else ""

        matches = []
        for tr in tr_matches:
            # 检查是否包含球队链接 (标识为比赛数据行)
            if '<a href="https://liansai.500.com/team/' not in tr:
                continue
            if not re.search(r'<td>\d+</td>', tr):
                continue

            # 提取场次编号
            num_match = re.search(r'<td>(\d+)</td>', tr)
            match_num = int(num_match.group(1)) if num_match else 0

            # 提取联赛
            league_match = re.search(
                r'class="league"[^>]*title="([^"]+)"', tr
            )
            league = league_match.group(1) if league_match else ""

            # 提取比赛时间
            time_match = re.search(r'class="eng">(\d{2}-\d{2}\s+\d{2}:\d{2})', tr)
            match_time = time_match.group(1) if time_match else ""

            # 提取主队
            home_match = re.search(
                r'class="text_r"><a[^>]*title="([^"]+)"', tr
            )
            home_team = home_match.group(1) if home_match else ""

            # 提取让球数 (支持 +N, -N, 0 等格式)
            handicap_match = re.search(
                r'class="eng"><span class="(?:black|red)">([+-]?\d+)</span>', tr
            )
            handicap = handicap_match.group(1) if handicap_match else "0"

            # 提取客队
            away_match = re.search(
                r'class="text_l"><a[^>]*title="([^"]+)"', tr
            )
            away_team = away_match.group(1) if away_match else ""

            # 提取比分
            score_match = re.search(
                r'\((\d+:\d+)\)\s*(\d+:\d+)', tr
            )
            half_score = ""
            full_score = ""
            if score_match:
                half_score = score_match.group(1)
                full_score = score_match.group(2)

            # === 提取各玩法SP值明细 ===
            # 将tr内容中的所有td提取出来，按顺序分析
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)

            # 找到比分td之后的td列表 (跳过前面的基础信息td)
            # 比分td的特征: 包含 (X:Y) X:Y 格式
            score_td_idx = -1
            for i, td in enumerate(tds):
                if re.search(r'\(\d+:\d+\)\s*\d+:\d+', td):
                    score_td_idx = i
                    break

            # 从比分td之后开始，每2个td为一组 (彩果 + SP值)，中间有&nbsp;分隔td
            sp_details = self._extract_beidan_sp_from_tds(tds, score_td_idx)

            match_data = {
                "match_num": match_num,
                "league": league,
                "match_time": match_time,
                "home_team": home_team,
                "handicap": handicap,
                "away_team": away_team,
                "half_score": half_score,
                "full_score": full_score,
                "sp_details": sp_details,
            }
            matches.append(match_data)

        if not matches:
            return None

        return {
            "source": "500.com",
            "data": {
                "lottery_type": "北京单场",
                "period": period,
                "total_matches": len(matches),
                "matches": matches,
                "play_types": ["胜平负", "总进球", "比分", "上下单双", "半全场", "胜负过关"],
                "play_types_note": "胜负过关数据需从其他数据源获取",
                "fetch_time": datetime.now().isoformat(),
            },
            "remaining": -1,
        }

    def _extract_beidan_sp_from_tds(self, tds: list, score_td_idx: int) -> Dict[str, Any]:
        """
        从td列表中提取北单各玩法SP值明细。

        比分td之后的td序列模式:
          [分隔&nbsp;] [彩果td] [SP值td] [分隔&nbsp;] [彩果td] [SP值td] ...
        共5组: 胜平负、总进球、比分、上下单双、半全场
        注意: 北单官方6种玩法，500.com开奖页面提供其中5种，胜负过关需从其他源获取
        """
        import re

        if score_td_idx < 0 or score_td_idx >= len(tds) - 1:
            return {}

        # 收集比分td之后的所有非空td内容
        remaining_tds = []
        for i in range(score_td_idx + 1, len(tds)):
            content = re.sub(r'<[^>]+>', '', tds[i]).strip()
            content = content.replace('&nbsp;', '').strip()
            if content:
                remaining_tds.append(content)

        # remaining_tds 应该是交替的 [彩果, SP值, 彩果, SP值, ...] 共10个元素
        # 但有些场次可能还没开奖 (以"-"表示)，此时td数量可能不足
        # 北单官方玩法: 胜平负(含让球)、上下单双、比分、半全场、总进球、胜负过关
        play_names = ["胜平负", "总进球", "比分", "上下单双", "半全场"]
        play_keys = ["spf", "ttg", "crs", "sxd", "hafu"]
        sp_details = {}

        for i, (name, key) in enumerate(zip(play_names, play_keys)):
            result_idx = i * 2
            sp_idx = i * 2 + 1

            result_val = remaining_tds[result_idx] if result_idx < len(remaining_tds) else ""
            sp_val = remaining_tds[sp_idx] if sp_idx < len(remaining_tds) else ""

            # 跳过未开赛场次
            if not result_val or result_val == "-":
                continue

            # 尝试将SP值转为float
            try:
                sp_float = float(sp_val) if sp_val else 0.0
            except (ValueError, TypeError):
                sp_float = 0.0

            sp_details[key] = {
                "play_name": name,
                "result": result_val,
                "sp_value": sp_val,
                "sp_float": sp_float,
            }

        return sp_details

    async def get_beidan_matches(self) -> Dict[str, Any]:
        """
        获取北京单场当前可投注对阵数据

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        cache_key = self._cache_key("beidan_matches")
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        result = await self._get_beidan_matches_from_500()
        if result:
            self.cache.set(cache_key, result)
            return make_response(source=result["source"], data=result["data"],
                                 cached=False, remaining_quota=-1)

        return make_response(source="none", data=None, error="北单对阵数据获取失败")

    async def _get_beidan_matches_from_500(self) -> Optional[Dict]:
        """从 trade.500.com/bjdc/ 获取北单当前对阵"""
        import re

        url = "https://trade.500.com/bjdc/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        resp = await self.http.get_html(url, headers=headers, encoding="gb2312")
        if not resp["ok"]:
            return None

        raw = resp["data"]
        if not isinstance(raw, str):
            return None

        # trade.500.com/bjdc/ 的对阵数据嵌入在HTML的value属性中
        # 格式: value="{index:'28',leagueName:'英超',homeTeam:'阿斯顿维拉',guestTeam:'利物浦',...}"
        pattern = r"value=\"\{index:'(\d+)',leagueName:'([^']*)',homeTeam:'([^']*)',guestTeam:'([^']*)',endTime:'([^']*)',rangqiuNum:'([^']*)',scheduleDate:'([^']*)'[^\"]*\""

        match_entries = re.findall(pattern, raw)

        matches = []
        for idx, league, home, away, end_time, handicap, sched_date in match_entries:
            matches.append({
                "match_num": int(idx),
                "league": league,
                "home_team": home,
                "away_team": away,
                "end_time": end_time,
                "handicap": handicap,
                "schedule_date": sched_date,
            })

        if not matches:
            return None

        return {
            "source": "500.com",
            "data": {
                "lottery_type": "北京单场",
                "total_matches": len(matches),
                "matches": matches,
                "fetch_time": datetime.now().isoformat(),
            },
            "remaining": -1,
        }

    # ========================================================================
    # 综合分析数据
    # ========================================================================

    async def compare_odds(self, match_id: str) -> Dict[str, Any]:
        """对比竞彩赔率与欧指/亚盘，发现价值投注信号

        通过对比竞彩官方赔率与国际市场欧指、亚盘的差异，
        识别返还率差异、盘口偏差、凯利指数异常等价值信号。

        Args:
            match_id: 竞彩比赛ID

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
            data 包含:
              - match: 比赛基本信息
              - jc_had: 竞彩胜平负赔率
              - eu_avg: 欧指平均赔率
              - payout_diff: 返还率差异
              - asian_vs_hhad: 亚盘 vs 竞彩让球对比
              - value_signals: 价值信号列表
              - kelly_analysis: 凯利指数分析
        """
        cache_key = self._cache_key("compare_odds", match_id=match_id)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return make_response(source=cached.get("source", "cache"),
                                 data=cached.get("data"),
                                 cached=True,
                                 remaining_quota=cached.get("remaining_quota", -1))

        # 1. 获取竞彩赔率
        jc_resp = await self.get_lottery_odds_change(match_id)
        jc_data = jc_resp.get("data") if jc_resp.get("data") else None

        if not jc_data:
            return make_response(source="none", data=None,
                                 error=f"未找到竞彩比赛 {match_id} 的赔率数据")

        # 2. 获取欧指/亚盘（通过球队名和联赛匹配）
        home_team = jc_data.get("home_team", "")
        away_team = jc_data.get("away_team", "")
        league = jc_data.get("league", "")

        eu_resp = await self.get_market_odds(league=league)
        eu_list = eu_resp.get("data") if eu_resp.get("data") else []

        # 尝试匹配同一比赛
        eu_matched = self._match_eu_to_jc(eu_list, home_team, away_team)

        # 3. 构建对比结果
        comparison = self._build_comparison(jc_data, eu_matched)

        result = {
            "source": "compare_analysis",
            "data": comparison,
            "remaining": -1,
        }
        self.cache.set(cache_key, result)
        return make_response(source="compare_analysis", data=comparison,
                             cached=False, remaining_quota=-1)

    def _match_eu_to_jc(self, eu_list: List[Dict], home_team: str,
                        away_team: str) -> Optional[Dict]:
        """将欧指数据与竞彩比赛进行匹配

        通过球队名称模糊匹配，找到对应的欧指数据。

        Args:
            eu_list: 欧指数据列表
            home_team: 竞彩主队名
            away_team: 竞彩客队名

        Returns:
            匹配到的欧指数据，未匹配返回None
        """
        if not eu_list:
            return None

        # 精确匹配
        for eu in eu_list:
            if (eu.get("home_team") == home_team and
                    eu.get("away_team") == away_team):
                return eu

        # 模糊匹配：检查是否包含关键字
        for eu in eu_list:
            eu_home = eu.get("home_team", "").lower()
            eu_away = eu.get("away_team", "").lower()
            jc_home = home_team.lower()
            jc_away = away_team.lower()

            # 检查主队和客队是否互相包含（处理缩写等情况）
            home_match = (jc_home in eu_home or eu_home in jc_home or
                          self._team_name_similarity(jc_home, eu_home) > 0.6)
            away_match = (jc_away in eu_away or eu_away in jc_away or
                          self._team_name_similarity(jc_away, eu_away) > 0.6)

            if home_match and away_match:
                return eu

        return None

    @staticmethod
    def _team_name_similarity(name1: str, name2: str) -> float:
        """简单的球队名称相似度计算（基于公共字符比例）"""
        if not name1 or not name2:
            return 0.0
        set1 = set(name1.lower())
        set2 = set(name2.lower())
        intersection = set1 & set2
        union = set1 | set2
        return len(intersection) / len(union) if union else 0.0

    def _build_comparison(self, jc_data: Dict, eu_data: Optional[Dict]) -> Dict:
        """构建竞彩与欧指的对比分析结果

        Args:
            jc_data: 竞彩赔率数据
            eu_data: 匹配到的欧指数据（可能为None）

        Returns:
            完整的对比分析字典
        """
        comparison = {
            "match": {
                "match_id": jc_data.get("match_id", ""),
                "match_num": jc_data.get("match_num_str", ""),
                "league": jc_data.get("league", ""),
                "home_team": jc_data.get("home_team", ""),
                "away_team": jc_data.get("away_team", ""),
                "match_time": jc_data.get("match_time", ""),
                "sell_status": jc_data.get("sell_status", ""),
            },
            "jc_had": {},
            "jc_hhad": {},
            "eu_avg": {},
            "payout_diff": {},
            "asian_vs_hhad": {},
            "value_signals": [],
            "kelly_analysis": {},
        }

        # 竞彩胜平负
        jc_had = jc_data.get("had", {})
        if jc_had:
            comparison["jc_had"] = {
                "win": jc_had.get("win", ""),
                "draw": jc_had.get("draw", ""),
                "lose": jc_had.get("lose", ""),
            }

        # 竞彩让球
        jc_hhad = jc_data.get("hhad", {})
        if jc_hhad:
            comparison["jc_hhad"] = {
                "win": jc_hhad.get("win", ""),
                "draw": jc_hhad.get("draw", ""),
                "lose": jc_hhad.get("lose", ""),
                "handicap": jc_hhad.get("handicap", ""),
            }

        if not eu_data:
            comparison["value_signals"].append({
                "type": "数据缺失",
                "detail": "未匹配到对应的欧指数据，无法进行对比分析",
                "level": "低",
            })
            return comparison

        # 欧指平均赔率
        consensus = eu_data.get("consensus", {})
        if consensus:
            comparison["eu_avg"] = {
                "home_win": consensus.get("avg_home_win", 0),
                "draw": consensus.get("avg_draw", 0),
                "away_win": consensus.get("avg_away_win", 0),
            }

        # 返还率差异
        self._analyze_payout_diff(comparison, jc_had, consensus)

        # 亚盘 vs 竞彩让球
        self._analyze_handicap_diff(comparison, jc_hhad, eu_data)

        # 凯利指数分析
        kelly = eu_data.get("kelly", {})
        if kelly:
            comparison["kelly_analysis"] = kelly
            self._analyze_kelly_signals(comparison, kelly, jc_had)

        return comparison

    @staticmethod
    def _analyze_payout_diff(comparison: Dict, jc_had: Dict, consensus: Dict):
        """分析返还率差异"""
        if not jc_had or not consensus:
            return

        try:
            jc_win = float(jc_had.get("win", 0))
            jc_draw = float(jc_had.get("draw", 0))
            jc_lose = float(jc_had.get("lose", 0))

            if jc_win <= 0 or jc_draw <= 0 or jc_lose <= 0:
                return

            # 竞彩返还率
            jc_implied = 1.0 / jc_win + 1.0 / jc_draw + 1.0 / jc_lose
            jc_payout = round(1.0 / jc_implied, 4) if jc_implied > 0 else 0

            # 欧指返还率
            eu_payout = consensus.get("payout_rate", 0)

            diff = round(abs(jc_payout - eu_payout), 4)

            comparison["payout_diff"] = {
                "jc": jc_payout,
                "eu": eu_payout,
                "diff": diff,
            }

            # 生成信号
            if diff > 0.15:
                level = "高"
            elif diff > 0.08:
                level = "中"
            else:
                level = "低"

            comparison["value_signals"].append({
                "type": "返还率差异",
                "detail": (f"竞彩返还率{jc_payout:.1%} vs 欧指{eu_payout:.1%}，"
                           f"差异{diff:.1%}"),
                "level": level,
            })
        except (ValueError, TypeError):
            pass

    @staticmethod
    def _analyze_handicap_diff(comparison: Dict, jc_hhad: Dict, eu_data: Dict):
        """分析亚盘与竞彩让球差异"""
        if not jc_hhad:
            return

        jc_handicap_str = jc_hhad.get("handicap", "")
        if not jc_handicap_str:
            return

        try:
            jc_handicap = float(jc_handicap_str)
        except (ValueError, TypeError):
            return

        # 从欧指亚盘数据中提取盘口
        asian_list = eu_data.get("asian_handicap", [])
        if not asian_list:
            return

        # 取第一个有数据的亚盘
        asian = asian_list[0] if asian_list else {}
        asian_handicap = asian.get("home_handicap")

        if asian_handicap is None:
            return

        diff = round(abs(jc_handicap - asian_handicap), 2)

        comparison["asian_vs_hhad"] = {
            "asian_handicap": asian_handicap,
            "jc_handicap": jc_handicap,
            "diff": diff,
            "asian_bookmaker": asian.get("bookmaker", ""),
        }

        # 生成信号
        if diff >= 0.5:
            level = "高"
        elif diff >= 0.25:
            level = "中"
        else:
            level = "低"

        direction = "竞彩让球更多" if jc_handicap < asian_handicap else "竞彩让球更少"
        comparison["value_signals"].append({
            "type": "盘口差异",
            "detail": (f"亚盘{asian_handicap} vs 竞彩{jc_handicap}，"
                       f"{direction}"),
            "level": level,
        })

    @staticmethod
    def _analyze_kelly_signals(comparison: Dict, kelly: Dict, jc_had: Dict):
        """分析凯利指数异常信号"""
        if not kelly or not jc_had:
            return

        try:
            jc_win = float(jc_had.get("win", 0))
            jc_draw = float(jc_had.get("draw", 0))
            jc_lose = float(jc_had.get("lose", 0))
        except (ValueError, TypeError):
            return

        home_kelly = kelly.get("home_kelly", 0)
        draw_kelly = kelly.get("draw_kelly", 0)
        away_kelly = kelly.get("away_kelly", 0)

        # 凯利 < 0.95 认为有价值
        signals = []
        if home_kelly < 0.95 and home_kelly > 0:
            signals.append(f"主胜凯利{home_kelly:.3f}偏低，可能被低估")
        if draw_kelly < 0.95 and draw_kelly > 0:
            signals.append(f"平局凯利{draw_kelly:.3f}偏低，可能被低估")
        if away_kelly < 0.95 and away_kelly > 0:
            signals.append(f"客胜凯利{away_kelly:.3f}偏低，可能被低估")

        if signals:
            comparison["value_signals"].append({
                "type": "凯利指数异常",
                "detail": "；".join(signals),
                "level": "中" if len(signals) == 1 else "高",
            })

    async def get_match_analysis_data(self, home_team: str, away_team: str,
                                       league: str) -> Dict[str, Any]:
        """
        获取单场比赛的完整分析数据
        返回: 积分榜、交锋、近期状态、伤停、赛程密度、多机构赔率

        Args:
            home_team: 主队名称
            away_team: 客队名称
            league: 联赛代码

        Returns:
            {"source": str, "data": {...}, "cached": bool, "remaining_quota": int}
        """
        analysis = {
            "home_team": home_team,
            "away_team": away_team,
            "league": league,
            "fetch_time": datetime.now().isoformat(),
        }

        sources_used = []
        errors = []

        # 1. 积分榜
        try:
            standings_resp = await self.get_standings(league)
            if standings_resp.get("data"):
                analysis["standings"] = standings_resp["data"]
                sources_used.append(standings_resp["source"])
            else:
                errors.append(f"积分榜: {standings_resp.get('error', '未知错误')}")
        except Exception as e:
            errors.append(f"积分榜: {str(e)}")

        # 2. 历史交锋
        try:
            h2h_resp = await self.get_head_to_head(home_team, away_team)
            if h2h_resp.get("data"):
                analysis["head_to_head"] = h2h_resp["data"]
                sources_used.append(h2h_resp["source"])
            else:
                errors.append(f"交锋: {h2h_resp.get('error', '未知错误')}")
        except Exception as e:
            errors.append(f"交锋: {str(e)}")

        # 3. 主队近期状态
        try:
            home_form_resp = await self.get_team_form(home_team)
            if home_form_resp.get("data"):
                analysis["home_team_form"] = home_form_resp["data"]
                sources_used.append(home_form_resp["source"])
            else:
                errors.append(f"主队状态: {home_form_resp.get('error', '未知错误')}")
        except Exception as e:
            errors.append(f"主队状态: {str(e)}")

        # 4. 客队近期状态
        try:
            away_form_resp = await self.get_team_form(away_team)
            if away_form_resp.get("data"):
                analysis["away_team_form"] = away_form_resp["data"]
                sources_used.append(away_form_resp["source"])
            else:
                errors.append(f"客队状态: {away_form_resp.get('error', '未知错误')}")
        except Exception as e:
            errors.append(f"客队状态: {str(e)}")

        # 5. 伤停信息
        try:
            injuries_resp = await self.get_injuries(home_team)
            if injuries_resp.get("data"):
                analysis["home_injuries"] = injuries_resp["data"]
                sources_used.append(injuries_resp["source"])
            else:
                errors.append(f"主队伤停: {injuries_resp.get('error', '未知错误')}")
        except Exception as e:
            errors.append(f"主队伤停: {str(e)}")

        try:
            injuries_resp = await self.get_injuries(away_team)
            if injuries_resp.get("data"):
                analysis["away_injuries"] = injuries_resp["data"]
                sources_used.append(injuries_resp["source"])
            else:
                errors.append(f"客队伤停: {injuries_resp.get('error', '未知错误')}")
        except Exception as e:
            errors.append(f"客队伤停: {str(e)}")

        # 6. 赛程密度
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            fixtures_resp = await self.get_fixtures(league, today)
            if fixtures_resp.get("data"):
                analysis["fixtures"] = fixtures_resp["data"]
                sources_used.append(fixtures_resp["source"])
            else:
                errors.append(f"赛程: {fixtures_resp.get('error', '未知错误')}")
        except Exception as e:
            errors.append(f"赛程: {str(e)}")

        # 7. 多机构赔率
        try:
            odds_resp = await self.get_market_odds(league=league)
            if odds_resp.get("data"):
                analysis["market_odds"] = odds_resp["data"]
                sources_used.append(odds_resp["source"])
            else:
                errors.append(f"赔率: {odds_resp.get('error', '未知错误')}")
        except Exception as e:
            errors.append(f"赔率: {str(e)}")

        analysis["sources_used"] = list(set(sources_used))
        analysis["errors"] = errors
        analysis["data_completeness"] = round(
            (7 - len(errors)) / 7 * 100, 1
        )

        # 获取当前配额状态
        analysis["quota_status"] = self.quota.get_all_status()

        return make_response(
            source="free-data-manager",
            data=analysis,
            cached=False,
            remaining_quota=self.quota.get_remaining("api-football"),
        )

    # ========================================================================
    # 工具方法
    # ========================================================================

    def _current_season(self) -> int:
        """获取当前赛季年份"""
        now = datetime.now()
        return now.year if now.month >= 8 else now.year - 1

    def get_quota_status(self) -> Dict[str, Any]:
        """获取所有数据源的配额状态"""
        return self.quota.get_all_status()

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存状态"""
        return self.cache.info()

    def clear_cache(self) -> None:
        """清空缓存"""
        self.cache.clear()

    async def close(self):
        """关闭HTTP客户端"""
        await self.http.close()


# ============================================================================
# 便捷函数
# ============================================================================

_manager_instance: Optional[FreeDataSourceManager] = None
_manager_lock = threading.Lock()


def get_manager() -> FreeDataSourceManager:
    """获取全局管理器实例"""
    global _manager_instance
    with _manager_lock:
        if _manager_instance is None:
            _manager_instance = FreeDataSourceManager()
        return _manager_instance


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    async def main():
        print("=" * 70)
        print("免费数据获取模块 - 测试")
        print("=" * 70)

        mgr = FreeDataSourceManager()

        # 显示配额状态
        print("\n[配额状态]")
        for source, status in mgr.get_quota_status().items():
            print(f"  {source}: 已用 {status['daily_used']}/{status['daily_limit']} (日) "
                  f"| {status['monthly_used']}/{status['monthly_limit']} (月)")

        # 1. 测试积分榜
        print("\n[1] 测试积分榜 (get_standings)...")
        try:
            result = await mgr.get_standings("英超")
            print(f"  数据源: {result['source']}")
            print(f"  缓存: {result['cached']}")
            if result.get("data"):
                for team in result["data"][:5]:
                    print(f"    {team['rank']}. {team['team_name']} - "
                          f"{team['points']}分 ({team['wins']}胜{team['draws']}平{team['losses']}负)")
            else:
                print(f"  错误: {result.get('error')}")
        except Exception as e:
            print(f"  异常: {e}")

        # 2. 测试历史交锋
        print("\n[2] 测试历史交锋 (get_head_to_head)...")
        try:
            result = await mgr.get_head_to_head("Manchester City", "Arsenal")
            print(f"  数据源: {result['source']}")
            print(f"  缓存: {result['cached']}")
            if result.get("data"):
                d = result["data"]
                print(f"  总场次: {d['total_matches']}")
                print(f"  队1胜/平/队2胜: {d['team1_wins']}/{d['draws']}/{d['team2_wins']}")
            else:
                print(f"  错误: {result.get('error')}")
        except Exception as e:
            print(f"  异常: {e}")

        # 3. 测试球队状态
        print("\n[3] 测试球队近期状态 (get_team_form)...")
        try:
            result = await mgr.get_team_form("Manchester City")
            print(f"  数据源: {result['source']}")
            print(f"  缓存: {result['cached']}")
            if result.get("data"):
                d = result["data"]
                print(f"  球队: {d.get('team_name')}")
                print(f"  近期状态: {d.get('form_string')}")
                print(f"  胜率: {d.get('win_rate')}%")
            else:
                print(f"  错误: {result.get('error')}")
        except Exception as e:
            print(f"  异常: {e}")

        # 4. 测试伤停
        print("\n[4] 测试伤停信息 (get_injuries)...")
        try:
            result = await mgr.get_injuries("Manchester City")
            print(f"  数据源: {result['source']}")
            print(f"  缓存: {result['cached']}")
            if result.get("data"):
                d = result["data"]
                print(f"  伤停人数: {d.get('total_injured')}")
            else:
                print(f"  错误: {result.get('error')}")
        except Exception as e:
            print(f"  异常: {e}")

        # 5. 测试赛程
        print("\n[5] 测试赛程 (get_fixtures)...")
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            result = await mgr.get_fixtures("英超", today)
            print(f"  数据源: {result['source']}")
            print(f"  缓存: {result['cached']}")
            if result.get("data"):
                d = result["data"]
                print(f"  比赛场次: {d.get('total_matches')}")
            else:
                print(f"  错误: {result.get('error')}")
        except Exception as e:
            print(f"  异常: {e}")

        # 6. 测试多机构赔率
        print("\n[6] 测试多机构赔率 (get_market_odds)...")
        try:
            result = await mgr.get_market_odds(league="英超")
            print(f"  数据源: {result['source']}")
            print(f"  缓存: {result['cached']}")
            if result.get("data"):
                if isinstance(result["data"], list) and result["data"]:
                    match = result["data"][0]
                    print(f"  示例: {match.get('home_team')} vs {match.get('away_team')}")
                    print(f"  机构数: {len(match.get('bookmakers', []))}")
                elif isinstance(result["data"], dict):
                    print(f"  数据: {json.dumps(result['data'], ensure_ascii=False)[:200]}")
            else:
                print(f"  错误: {result.get('error')}")
        except Exception as e:
            print(f"  异常: {e}")

        # 7. 测试竞彩赔率变化（6种玩法全量）
        print("\n[7] 测试竞彩赔率变化 - 6种玩法全量 (get_lottery_odds_change)...")
        test_match_id = None
        try:
            # 先获取全部比赛列表
            result_all = await mgr.get_lottery_odds_change("all")
            print(f"  数据源: {result_all['source']}")
            print(f"  缓存: {result_all['cached']}")
            if result_all.get("data") and isinstance(result_all["data"], list):
                matches = result_all["data"]
                print(f"  总比赛场次: {len(matches)}")
                if matches:
                    # 展示第一场比赛的完整6种玩法
                    sample = matches[0]
                    print(f"  示例比赛: [{sample.get('match_num_str')}] "
                          f"{sample.get('league')} {sample.get('home_team')} vs {sample.get('away_team')}")
                    print(f"    比赛时间: {sample.get('match_time')}")
                    print(f"    销售状态: {sample.get('sell_status')}")
                    print(f"    主队排名: {sample.get('home_rank')}, 客队排名: {sample.get('away_rank')}")

                    # HAD
                    had = sample.get("had", {})
                    if had:
                        print(f"    HAD(胜平负): 胜={had.get('win')} 平={had.get('draw')} 负={had.get('lose')}")

                    # HHAD
                    hhad = sample.get("hhad", {})
                    if hhad:
                        print(f"    HHAD(让球): 让{hhad.get('handicap')} 胜={hhad.get('win')} "
                              f"平={hhad.get('draw')} 负={hhad.get('lose')}")

                    # CRS
                    crs = sample.get("crs", {})
                    if crs:
                        crs_items = {k: v for k, v in crs.items() if k != "update_time"}
                        print(f"    CRS(比分): {len(crs_items)}个选项, "
                              f"如 1:0={crs_items.get('1:0', '-')}, 0:1={crs_items.get('0:1', '-')}, "
                              f"胜其他={crs_items.get('胜其他', '-')}")

                    # TTG
                    ttg = sample.get("ttg", {})
                    if ttg:
                        ttg_items = {k: v for k, v in ttg.items() if k != "update_time"}
                        print(f"    TTG(总进球): {ttg_items}")

                    # HAFU
                    hafu = sample.get("hafu", {})
                    if hafu:
                        hafu_items = {k: v for k, v in hafu.items() if k != "update_time"}
                        print(f"    HAFU(半全场): {hafu_items}")

                    # 记录一个match_id用于后续测试
                    test_match_id = sample.get("match_id")
            else:
                print(f"  错误: {result_all.get('error')}")
        except Exception as e:
            print(f"  异常: {e}")

        # 7b. 测试单场比赛查询
        if test_match_id:
            print(f"\n[7b] 测试单场比赛查询 (match_id={test_match_id})...")
            try:
                result = await mgr.get_lottery_odds_change(test_match_id)
                if result.get("data"):
                    d = result["data"]
                    print(f"  比赛: {d.get('home_team')} vs {d.get('away_team')}")
                    print(f"  玩法数: ", end="")
                    play_count = sum(1 for k in ["had", "hhad", "crs", "ttg", "hafu"] if d.get(k))
                    print(f"{play_count}/5 (had/hhad/crs/ttg/hafu)")
                else:
                    print(f"  错误: {result.get('error')}")
            except Exception as e:
                print(f"  异常: {e}")

        # 8. 测试多机构赔率（含亚盘、大小球）
        print("\n[8] 测试多机构赔率 - 欧指+亚盘+大小球 (get_market_odds)...")
        try:
            result = await mgr.get_market_odds(league="英超")
            print(f"  数据源: {result['source']}")
            print(f"  缓存: {result['cached']}")
            if result.get("data"):
                if isinstance(result["data"], list) and result["data"]:
                    match = result["data"][0]
                    print(f"  示例: {match.get('home_team')} vs {match.get('away_team')}")
                    eu_odds = match.get("european_odds", [])
                    print(f"  欧指机构数: {len(eu_odds)}")
                    if eu_odds:
                        print(f"    首家: {eu_odds[0].get('bookmaker')} - "
                              f"主{eu_odds[0].get('home_win')} 平{eu_odds[0].get('draw')} "
                              f"客{eu_odds[0].get('away_win')}")

                    asian = match.get("asian_handicap", [])
                    print(f"  亚盘机构数: {len(asian)}")
                    if asian:
                        print(f"    首家: {asian[0].get('bookmaker')} - "
                              f"盘口{asian[0].get('home_handicap')} "
                              f"主{asian[0].get('home_odds')} 客{asian[0].get('away_odds')}")

                    ou = match.get("over_under", [])
                    print(f"  大小球机构数: {len(ou)}")
                    if ou:
                        print(f"    首家: {ou[0].get('bookmaker')} - "
                              f"盘口{ou[0].get('line')} "
                              f"大{ou[0].get('over_odds')} 小{ou[0].get('under_odds')}")

                    consensus = match.get("consensus", {})
                    if consensus:
                        print(f"  市场共识: 平均主胜={consensus.get('avg_home_win')} "
                              f"平={consensus.get('avg_draw')} 客={consensus.get('avg_away_win')} "
                              f"返还率={consensus.get('payout_rate')}")

                    kelly = match.get("kelly", {})
                    if kelly:
                        print(f"  凯利指数: 主{kelly.get('home_kelly')} "
                              f"平{kelly.get('draw_kelly')} 客{kelly.get('away_kelly')}")
            else:
                print(f"  错误: {result.get('error')}")
        except Exception as e:
            print(f"  异常: {e}")

        # 9. 测试赔率对比分析
        if test_match_id:
            print(f"\n[9] 测试赔率对比分析 (compare_odds, match_id={test_match_id})...")
            try:
                result = await mgr.compare_odds(test_match_id)
                print(f"  数据源: {result['source']}")
                if result.get("data"):
                    d = result["data"]
                    match_info = d.get("match", {})
                    print(f"  比赛: [{match_info.get('match_num')}] "
                          f"{match_info.get('home_team')} vs {match_info.get('away_team')}")

                    jc_had = d.get("jc_had", {})
                    if jc_had:
                        print(f"  竞彩HAD: 胜={jc_had.get('win')} 平={jc_had.get('draw')} 负={jc_had.get('lose')}")

                    eu_avg = d.get("eu_avg", {})
                    if eu_avg:
                        print(f"  欧指均值: 主={eu_avg.get('home_win')} 平={eu_avg.get('draw')} 客={eu_avg.get('away_win')}")

                    payout = d.get("payout_diff", {})
                    if payout:
                        print(f"  返还率: 竞彩={payout.get('jc')} 欧指={payout.get('eu')} 差异={payout.get('diff')}")

                    handicap = d.get("asian_vs_hhad", {})
                    if handicap:
                        print(f"  盘口对比: 亚盘={handicap.get('asian_handicap')} "
                              f"竞彩={handicap.get('jc_handicap')} 差异={handicap.get('diff')}")

                    signals = d.get("value_signals", [])
                    if signals:
                        print(f"  价值信号 ({len(signals)}条):")
                        for sig in signals:
                            print(f"    [{sig.get('level')}] {sig.get('type')}: {sig.get('detail')}")

                    kelly = d.get("kelly_analysis", {})
                    if kelly:
                        print(f"  凯利分析: 主={kelly.get('home_kelly')} "
                              f"平={kelly.get('draw_kelly')} 客={kelly.get('away_kelly')}")
                else:
                    print(f"  错误: {result.get('error')}")
            except Exception as e:
                print(f"  异常: {e}")

        # 10. 测试竞彩赛果
        print("\n[10] 测试竞彩赛果 (get_lottery_results)...")
        try:
            result = await mgr.get_lottery_results()
            print(f"  数据源: {result['source']}")
            print(f"  缓存: {result['cached']}")
            if result.get("data"):
                d = result["data"]
                if isinstance(d, dict) and d.get("total_matches"):
                    print(f"  比赛场次: {d.get('total_matches')}")
                else:
                    print(f"  数据类型: {type(d)}")
            else:
                print(f"  错误: {result.get('error')}")
        except Exception as e:
            print(f"  异常: {e}")

        # 显示最终配额
        print("\n[最终配额状态]")
        for source, status in mgr.get_quota_status().items():
            print(f"  {source}: 已用 {status['daily_used']}/{status['daily_limit']} (日) "
                  f"| {status['monthly_used']}/{status['monthly_limit']} (月)")

        print("\n[缓存状态]")
        print(f"  {mgr.get_cache_info()}")

        await mgr.close()

        print("\n" + "=" * 70)
        print("测试完成")
        print("=" * 70)

    asyncio.run(main())
