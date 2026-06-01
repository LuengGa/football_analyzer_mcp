#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
彩票数据获取模块
================
从竞彩官网获取比赛数据，支持竞彩足球、北单和传统足彩三种玩法。

API端点:
- 竞彩足球: https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry
- 北单: https://webapi.sporttery.cn/gateway/bjdc/football/getMatchListV1.qry
- 传统足彩: https://webapi.sporttery.cn/gateway/zc/football/getMatchListV1.qry

安全说明:
- 所有SSL连接使用证书验证（CERT_REQUIRED）
- 支持通过环境变量控制是否严格验证证书
"""

import json
import re
import ssl
import time
import urllib.request
import urllib.error
from typing import List, Dict, Optional, Any, Union
from datetime import datetime
import os


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
    # 检查环境变量是否禁用SSL验证（仅用于调试）
    verify_ssl = os.getenv("LOTTERY_SSL_VERIFY", "1") == "1"
    
    if verify_ssl:
        # 生产环境：严格验证证书
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        # 调试环境：允许禁用验证（会发出警告）
        import warnings
        warnings.warn(
            "SSL证书验证已被禁用！这仅应用于调试环境。",
            SecurityWarning,
            stacklevel=2
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    
    return ctx


class SecurityWarning(Warning):
    """安全警告类"""
    pass


# ============================================================================
# 常量定义
# ============================================================================

# API端点
API_ENDPOINTS = {
    "jingcai": "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry",
    "beidan": "https://webapi.sporttery.cn/gateway/bjdc/football/getMatchListV1.qry",
    "ctzc": "https://webapi.sporttery.cn/gateway/lottery/getFootBallConcernV1.qry",
}

# 传统足彩玩法代码
CTZC_GAME_CODES = {
    "sfc": "90",       # 14场胜负彩
    "rx9": "900129",   # 任选9场
    "bqc": "98",       # 6场半全场
    "jqc": "94",       # 4场进球彩
}

POOL_CODE_NAMES = {
    "had": "胜平负",
    "hhad": "让球胜平负",
    "crs": "比分",
    "ttg": "总进球",
    "hafu": "半全场",
    "spf": "胜平负",  # 北单
    "sf": "胜负",     # 北单胜负过关
}

# 半全场赔率字段映射
HAFU_FIELD_MAP = {
    "hh": "win_win", "hd": "win_draw", "ha": "win_loss",
    "dh": "draw_win", "dd": "draw_draw", "da": "draw_loss",
    "ah": "loss_win", "ad": "loss_draw", "aa": "loss_loss",
}

# 北单半全场字段映射
BEIDAN_HAFU_MAP = {
    "l33": "win_win", "l31": "win_draw", "l30": "win_loss",
    "l13": "draw_win", "l11": "draw_draw", "l10": "draw_loss",
    "l03": "loss_win", "l01": "loss_draw", "l00": "loss_loss",
}

# 总进球字段映射
TTG_FIELD_MAP = {
    "s0": "goals_0", "s1": "goals_1", "s2": "goals_2",
    "s3": "goals_3", "s4": "goals_4", "s5": "goals_5",
    "s6": "goals_6", "s7": "goals_7",
}

# 北单总进球字段映射
BEIDAN_TTG_MAP = {
    "j0": "goals_0", "j1": "goals_1", "j2": "goals_2",
    "j3": "goals_3", "j4": "goals_4", "j5": "goals_5",
    "j6": "goals_6", "j7": "goals_7",
}


# ============================================================================
# 网络请求工具（含重试机制）
# ============================================================================

def _fetch_url(url: str, headers: Optional[Dict] = None, timeout: int = 30,
              max_retries: int = 3, backoff_factor: float = 1.5) -> Optional[bytes]:
    """带指数退避重试的HTTP GET请求。

    Args:
        url: 请求URL
        headers: 请求头（可选）
        timeout: 单次请求超时（秒）
        max_retries: 最大重试次数
        backoff_factor: 退避因子（第N次等待 backoff_factor^(N-1) 秒）

    Returns:
        响应内容(bytes)，失败返回None
    """
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

    ctx = create_ssl_context()

    last_error = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = backoff_factor ** attempt
                time.sleep(wait)
        except Exception as e:
            last_error = e
            break

    return None


# ============================================================================
# 核心数据获取
# ============================================================================

def fetch_today_matches(lottery_type: str = "jingcai", issue_number: Optional[str] = None, timeout: int = 30) -> List[Dict[str, Any]]:
    """
    获取今日可投注比赛，支持多种彩票类型。
    
    Args:
        lottery_type: 彩票类型，可选值：
            - "jingcai": 竞彩足球（默认）
            - "beidan": 北京单场
            - "ctzc": 传统足彩
        issue_number: 期号（仅用于传统足彩，如"26075"）
        timeout: 请求超时时间（秒），默认30秒
    
    Returns:
        标准化后的比赛数据列表
    """
    if lottery_type == "jingcai":
        return fetch_jingcai_matches(timeout=timeout)
    elif lottery_type == "beidan":
        return fetch_beidan_matches(timeout=timeout)
    elif lottery_type == "ctzc":
        return fetch_ctzc_matches(issue_number, timeout=timeout)
    else:
        raise ValueError(f"不支持的彩票类型: {lottery_type}，可选值: jingcai, beidan, ctzc")


def fetch_jingcai_matches(timeout: int = 30) -> List[Dict[str, Any]]:
    """
    从竞彩官网获取今日所有可投注比赛。
    
    Args:
        timeout: 请求超时时间（秒），默认30秒
    
    Returns:
        标准化后的比赛数据列表，每个比赛包含:
        - match_id: 比赛ID
        - league: 联赛名称
        - home_team: 主队
        - away_team: 客队
        - match_time: 比赛时间
        - had: 胜平负赔率 {win, draw, lose}
        - hhad: 让球胜平负赔率 {win, draw, lose, handicap}
        - crs: 比分赔率 {options: [{score, odds}]}
        - ttg: 总进球赔率 {goals_0...goals_7}
        - hafu: 半全场赔率 {win_win...loss_loss}
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.sporttery.cn/',
        'Origin': 'https://www.sporttery.cn',
    }
    
    try:
        raw = _fetch_url(API_ENDPOINTS["jingcai"], headers=headers, timeout=timeout)
        if raw is None:
            raise ConnectionError("竞彩API请求失败（已重试3次）")
        data = json.loads(raw.decode('utf-8'))

        value = data.get('value', {})
        if isinstance(value, dict):
            date_groups = value.get('matchInfoList', [])
            all_matches = []
            for group in date_groups:
                matches = group.get('subMatchList', [])
                all_matches.extend(matches)

            if all_matches:
                return [normalize_jingcai_match(m) for m in all_matches]

            # 兼容旧格式
            old_matches = value.get('matchInfo', [])
            return [normalize_jingcai_match(m) for m in old_matches]
        return []

    except urllib.error.HTTPError as e:
        raise ConnectionError(f"HTTP {e.code}: 无法获取竞彩比赛数据")
    except Exception as e:
        raise ConnectionError(f"获取竞彩比赛数据失败: {e}")


def fetch_beidan_matches(timeout: int = 30) -> List[Dict[str, Any]]:
    """
    获取北京单场今日可投注比赛。
    
    北单特点：
    - 65%返还率
    - 小数让球（如0.5, 0/0.5, 0.5/1等）
    - SP值浮动
    - 销售区域：北京、天津、广东
    
    获取策略（降级机制）：
    1. 优先尝试官方API
    2. API失败时，基于竞彩比赛数据生成北单格式（比赛相同，赔率机制不同）
    
    Args:
        timeout: 请求超时时间（秒），默认30秒
    
    Returns:
        标准化后的比赛数据列表
    """
    # 策略1: 尝试官方API
    try:
        result = _fetch_beidan_from_api(timeout)
        if result:
            return result
    except Exception:
        pass
    
    # 策略2: 基于竞彩数据生成北单格式
    try:
        result = _fetch_beidan_from_jingcai(timeout)
        if result:
            return result
    except Exception:
        pass
    
    raise ConnectionError(
        "获取北单比赛数据失败：官方API不可用，降级方案也未成功。"
        "北单为区域联网游戏，其SP值数据主要通过体彩销售终端发布，"
        "公开互联网暂无可靠的实时数据源。"
    )


def _fetch_beidan_from_api(timeout: int = 30) -> List[Dict[str, Any]]:
    """尝试从官方API获取北单数据。"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.sporttery.cn/',
        'Origin': 'https://www.sporttery.cn',
    }
    
    raw = _fetch_url(API_ENDPOINTS["beidan"], headers=headers, timeout=timeout)
    if raw is None:
        return []  # 请求失败，触发降级
    data = json.loads(raw.decode('utf-8'))

    if data.get('success') == False or data.get('errorMessage'):
        return []  # API返回错误，触发降级

    if data.get('code') != 0:
        return []

    value = data.get('value', {})
    if isinstance(value, dict):
        match_list = value.get('matchList', [])
        if match_list:
            return [normalize_beidan_match(m) for m in match_list]
    return []


def _fetch_beidan_from_jingcai(timeout: int = 30) -> List[Dict[str, Any]]:
    """
    降级方案：基于竞彩比赛数据生成北单格式。
    
    北单和竞彩的比赛场次高度重合（相同的足球比赛），主要区别在于：
    - 北单赔率为SP值（浮动），竞彩为固定奖金
    - 北单返还率65%，竞彩返还率70%
    - 北单最高支持15关，竞彩最高8关
    
    此方法将竞彩比赛转换为北单格式，赔率标记为"参考SP值"。
    """
    jingcai_matches = fetch_jingcai_matches(timeout=timeout)
    if not jingcai_matches:
        return []
    
    beidan_matches = []
    for idx, m in enumerate(jingcai_matches):
        beidan_m = {
            "lottery_type": "beidan",
            "match_id": f"BD{m.get('match_id', '')}",
            "issue": "",
            "issue_num": str(idx + 1),
            "league": m.get('league', ''),
            "home_team": m.get('home_team', ''),
            "away_team": m.get('away_team', ''),
            "match_time": m.get('match_time', ''),
            "sell_status": "1",
            "data_source": "jingcai_fallback",
            "data_source_note": "北单官方API不可用，此数据基于竞彩赛程生成，SP值为参考值（竞彩固定奖金÷0.70×0.65≈北单SP值）",
        }
        
        # 将竞彩赔率转换为北单SP值参考
        # 北单SP ≈ 竞彩固定奖金 × (0.65/0.70)
        sp_ratio = 0.65 / 0.70  # ≈ 0.9286
        
        if 'had' in m and m['had']:
            had = m['had']
            beidan_m['had_odds'] = {
                "win": round(had.get('win', 0) * sp_ratio, 2),
                "draw": round(had.get('draw', 0) * sp_ratio, 2),
                "lose": round(had.get('lose', 0) * sp_ratio, 2),
                "handicap": "0",
                "note": "参考SP值（基于竞彩固定奖金换算）",
            }
        
        if 'hhad' in m and m['hhad']:
            hhad = m['hhad']
            beidan_m['hhad_odds'] = {
                "win": round(hhad.get('win', 0) * sp_ratio, 2),
                "draw": round(hhad.get('draw', 0) * sp_ratio, 2),
                "lose": round(hhad.get('lose', 0) * sp_ratio, 2),
                "handicap": hhad.get('handicap', ''),
                "note": "参考SP值（基于竞彩固定奖金换算）",
            }
        
        if 'crs' in m and m['crs']:
            crs = m['crs']
            if 'options' in crs:
                beidan_m['crs_odds'] = {
                    "options": [
                        {"score": o['score'], "odds": round(o['odds'] * sp_ratio, 2)}
                        for o in crs['options']
                    ],
                    "note": "参考SP值（基于竞彩固定奖金换算）",
                }
        
        if 'ttg' in m and m['ttg']:
            ttg = m['ttg']
            beidan_m['ttg_odds'] = {
                k: round(v * sp_ratio, 2) for k, v in ttg.items()
            }
            beidan_m['ttg_odds']['note'] = "参考SP值（基于竞彩固定奖金换算）"
        
        if 'hafu' in m and m['hafu']:
            hafu = m['hafu']
            beidan_m['hafu_odds'] = {
                k: round(v * sp_ratio, 2) for k, v in hafu.items()
            }
            beidan_m['hafu_odds']['note'] = "参考SP值（基于竞彩固定奖金换算）"
        
        beidan_matches.append(beidan_m)
    
    return beidan_matches


def fetch_ctzc_matches(issue_number: Optional[str] = None, timeout: int = 30) -> List[Dict[str, Any]]:
    """
    获取传统足彩当期比赛数据。
    
    传统足彩特点：
    - 65%返还率
    - 奖期制（每周2-3期）
    - 浮动奖金
    - 场次由官方指定
    
    获取策略（降级机制）：
    1. 优先尝试官方API
    2. API失败时，从HTML页面抓取数据
    3. HTML失败时，尝试500.com备用数据源
    
    Args:
        issue_number: 期号（如"26075"），不传则获取最新期
        timeout: 请求超时时间（秒），默认30秒
    
    Returns:
        标准化后的比赛数据列表
    """
    # 策略1: 尝试官方API
    try:
        result = _fetch_ctzc_from_api(issue_number, timeout)
        if result:
            return result
    except Exception:
        pass
    
    # 策略2: 从HTML页面抓取
    try:
        result = _fetch_ctzc_from_html(timeout)
        if result:
            return result
    except Exception:
        pass
    
    # 策略3: 500.com 备用数据源
    try:
        result = _fetch_ctzc_from_500(timeout)
        if result:
            return result
    except Exception:
        pass
    
    raise ConnectionError(
        "获取传统足彩数据失败：官方API、HTML页面和500.com备用源均不可用。"
        "请稍后重试，或访问 https://www.sporttery.cn/ctzc/szsc/index.html 手动查看。"
    )


def _fetch_ctzc_from_api(issue_number: Optional[str] = None, timeout: int = 30) -> List[Dict[str, Any]]:
    """
    从官方API获取传统足彩数据。
    
    API: /gateway/lottery/getFootBallConcernV1.qry
    参数:
    - param: 玩法代码,0 (如 "90,0" = 胜负游戏)
    - lotteryDrawNum: 期号 (可选，不传则获取最新期)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.sporttery.cn/ctzc/szsc/index.html',
    }
    
    ctx = create_ssl_context()
    
    # 默认获取胜负游戏(14场胜负彩)
    game_code = CTZC_GAME_CODES.get("sfc", "90")
    url = f"{API_ENDPOINTS['ctzc']}?param={game_code},0"
    if issue_number:
        url += f"&lotteryDrawNum={issue_number}"

    raw = _fetch_url(url, headers=headers, timeout=timeout)
    if raw is None:
        return []  # 请求失败，触发降级
    data = json.loads(raw.decode('utf-8'))

    if str(data.get('errorCode', '')) != '0':
        return []

    value = data.get('value', {})
    if not value or not isinstance(value, dict):
        return []

    draw_match = value.get('drawMatch', {})
    if not draw_match:
        return []

    lottery_draw_num = str(draw_match.get('lotteryDrawNum', ''))
    match_list = draw_match.get('matchList', [])

    if not match_list:
        return []

    # 转换为标准格式
    results = []
    for m in match_list:
        result = {
            "lottery_type": "ctzc",
            "match_id": str(m.get('gmMatchId', '')),
            "issue_number": lottery_draw_num,
            "match_index": int(m.get('matchNum', 0)),
            "league": m.get('matchName', ''),
            "home_team": m.get('masterTeamAllName', m.get('masterTeamName', '')),
            "away_team": m.get('guestTeamAllName', m.get('guestTeamName', '')),
            "home_team_abbr": m.get('masterTeamName', ''),
            "away_team_abbr": m.get('guestTeamName', ''),
            "match_time": m.get('startTime', ''),
            "is_stop": False,
            "data_source": "official_api",
        }

        # 附加期次信息（只在第一条记录中）
        if not results:
            result["sale_begin_time"] = draw_match.get('lotterySaleBeginTime', '')
            result["sale_end_time"] = draw_match.get('lotterySaleEndTime', '')
            result["draw_time"] = draw_match.get('lotteryDrawTime', '')

        results.append(result)

    return results


def _fetch_ctzc_from_html(timeout: int = 30, max_retries: int = 3) -> List[Dict[str, Any]]:
    """
    降级方案：从传统足彩HTML页面抓取赛程数据。
    
    数据来源: https://www.sporttery.cn/ctzc/szsc/index.html
    含重试机制和完整异常处理。
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.sporttery.cn/',
    }
    
    ctx = create_ssl_context()
    url = "https://www.sporttery.cn/ctzc/szsc/index.html"
    
    html = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                html = resp.read().decode('utf-8', errors='replace')
            break
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError) as e:
            if attempt < max_retries - 1:
                wait = 1.5 ** attempt
                time.sleep(wait)
        except Exception as e:
            continue
    
    if html is None:
        return []
    
    # 尝试从HTML中提取内嵌的JSON数据
    # sporttery.cn 通常在页面中嵌入 matchData 或类似变量
    json_patterns = [
        r'var\s+matchData\s*=\s*({.*?});',
        r'var\s+matchList\s*=\s*(\[.*?\]);',
        r'var\s+data\s*=\s*({.*?});',
        r'JSON\.parse\(["\']({.*?})["\']\)',
        r'"matchList"\s*:\s*(\[.*?\])',
    ]
    
    for pattern in json_patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                json_str = match.group(1)
                data = json.loads(json_str)
                
                if isinstance(data, list):
                    # 直接是比赛列表
                    return [_parse_ctzc_html_match(m, "HTML") for m in data]
                elif isinstance(data, dict):
                    # 可能包含matchList字段
                    for key in ['matchList', 'match_info', 'list', 'data']:
                        if key in data and isinstance(data[key], list):
                            return [_parse_ctzc_html_match(m, "HTML") for m in data[key]]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    
    # 尝试从HTML表格中提取比赛数据
    matches = _parse_ctzc_html_table(html)
    if matches:
        return matches
    
    return []


def _fetch_ctzc_from_500(timeout: int = 30, max_retries: int = 2) -> List[Dict[str, Any]]:
    """
    备用方案：从 500.com 获取传统足彩对阵数据。
    
    数据来源: https://trade.500.com/ctzc/
    含重试机制和完整异常处理。
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://trade.500.com/',
    }

    ctx = create_ssl_context()
    url = "https://trade.500.com/ctzc/"

    html = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                html = resp.read().decode('gb2312', errors='replace')
            break
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError):
            if attempt < max_retries - 1:
                time.sleep(1.5 ** attempt)
        except Exception:
            continue

    if html is None:
        return []

    json_patterns = [
        r'var\s+matchData\s*=\s*(\[.*?\]);',
        r'var\s+matchList\s*=\s*(\[.*?\]);',
        r'data-match\s*=\s*(\[.*?\])',
        r'"matchList"\s*:\s*(\[.*?\])',
    ]

    for pattern in json_patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                json_str = match.group(1)
                data = json.loads(json_str)
                if isinstance(data, list):
                    return [_parse_ctzc_html_match(m, "500.com") for m in data]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

    return []


def _parse_ctzc_html_match(raw: Dict, source: str = "HTML") -> Dict[str, Any]:
    """解析HTML页面中的传统足彩比赛数据。"""
    result = {
        "lottery_type": "ctzc",
        "match_id": str(raw.get('matchId', raw.get('id', raw.get('mid', '')))),
        "issue_number": str(raw.get('issue', raw.get('issueNumber', raw.get('qihao', '')))),
        "match_index": int(raw.get('matchIndex', raw.get('index', raw.get('num', 0)))),
        "league": raw.get('leagueName', raw.get('league', raw.get('comp', raw.get('saishi', '')))),
        "home_team": raw.get('homeTeamName', raw.get('home', raw.get('zhudui', ''))),
        "away_team": raw.get('awayTeamName', raw.get('away', raw.get('kedui', ''))),
        "match_time": raw.get('matchTime', raw.get('time', raw.get('bisaishijian', ''))),
        "is_stop": raw.get('isStop', False),
        "data_source": source.lower(),
    }
    
    # 尝试提取赔率
    had = raw.get('had', raw.get('odds', {}))
    if had and isinstance(had, dict):
        try:
            result['had_odds'] = {
                "win": float(had.get('h', had.get('win', 0))),
                "draw": float(had.get('d', had.get('draw', 0))),
                "lose": float(had.get('a', had.get('lose', 0))),
            }
        except (ValueError, TypeError):
            pass
    
    return result


def _parse_ctzc_html_table(html: str) -> List[Dict[str, Any]]:
    """从HTML表格中解析传统足彩赛程。"""
    matches = []
    
    # 查找包含比赛数据的表格行
    # 常见模式: <tr>...<td>序号</td><td>联赛</td><td>主队</td><td>客队</td>...</tr>
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    td_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE)
    
    for tr_match in tr_pattern.finditer(html):
        row_html = tr_match.group(1)
        cells = [re.sub(r'<[^>]+>', '', td.strip()) for td in td_pattern.findall(row_html)]
        
        # 过滤掉表头和空行
        if len(cells) < 4:
            continue
        
        # 检查是否是数据行（通常包含数字序号和队名）
        try:
            # 尝试匹配: 序号 | 联赛 | 主队 vs 客队 | 日期
            first_cell = cells[0].strip()
            if not first_cell.isdigit():
                continue
            
            match_index = int(first_cell)
            if match_index < 1 or match_index > 14:
                continue
            
            # 查找队名（通常包含"vs"或在不同单元格中）
            home_team = ""
            away_team = ""
            league = ""
            match_time = ""
            
            for i, cell in enumerate(cells):
                cell = cell.strip()
                if not cell:
                    continue
                # 查找vs分隔的对阵
                if 'vs' in cell.lower() or 'VS' in cell:
                    parts = re.split(r'\s*[Vv][Ss]\s*', cell)
                    if len(parts) == 2:
                        home_team = parts[0].strip()
                        away_team = parts[1].strip()
                # 查找日期模式
                if re.match(r'\d{2}-\d{2}', cell):
                    match_time = cell
            
            if home_team and away_team:
                matches.append({
                    "lottery_type": "ctzc",
                    "match_id": f"CTZC_HTML_{match_index}",
                    "issue_number": "",
                    "match_index": match_index,
                    "league": league,
                    "home_team": home_team,
                    "away_team": away_team,
                    "match_time": match_time,
                    "is_stop": False,
                    "data_source": "html_table",
                })
        except (ValueError, IndexError):
            continue
    
    return matches


# ============================================================================
# 数据标准化
# ============================================================================

def normalize_jingcai_match(match: Dict) -> Dict[str, Any]:
    """将竞彩足球原始比赛数据标准化。"""
    result = {
        "lottery_type": "jingcai",
        "match_id": str(match.get('matchId', '')),
        "league": match.get('leagueAbbName', match.get('leagueName', '')),
        "home_team": match.get('homeTeamAbbName', match.get('homeTeamName', '')),
        "away_team": match.get('awayTeamAbbName', match.get('awayTeamName', '')),
        "match_time": match.get('matchDate', '') + ' ' + match.get('matchTime', ''),
        "match_date": match.get('matchDate', ''),
        "match_time_only": match.get('matchTime', ''),
        "home_rank": match.get('homeTeamRank', ''),
        "away_rank": match.get('awayTeamRank', ''),
        "home_form": match.get('homeForm', ''),
        "away_form": match.get('awayForm', ''),
    }
    
    # 提取所有玩法赔率
    odds = extract_jingcai_odds(match)
    result.update(odds)
    
    return result


def normalize_beidan_match(match: Dict) -> Dict[str, Any]:
    """将北单原始比赛数据标准化。"""
    result = {
        "lottery_type": "beidan",
        "match_id": str(match.get('matchId', '')),
        "issue": match.get('issue', ''),
        "issue_num": match.get('issueNum', ''),
        "league": match.get('comp', match.get('leagueName', '')),
        "home_team": match.get('home', match.get('homeTeamName', '')),
        "away_team": match.get('away', match.get('awayTeamName', '')),
        "match_time": _timestamp_to_datetime(match.get('matchTime', 0)),
        "sell_status": match.get('sellStatus', ''),
    }
    
    # 提取北单赔率
    odds = extract_beidan_odds(match)
    result.update(odds)
    
    return result


def normalize_ctzc_match(match: Dict, issue: str = '') -> Dict[str, Any]:
    """将传统足彩原始比赛数据标准化。"""
    result = {
        "lottery_type": "ctzc",
        "match_id": str(match.get('matchId', '')),
        "issue_number": issue or match.get('issue', ''),
        "match_index": int(match.get('matchIndex', 0)) if match.get('matchIndex') else 0,
        "league": match.get('leagueName', match.get('comp', '')),
        "home_team": match.get('homeTeamName', match.get('home', '')),
        "away_team": match.get('awayTeamName', match.get('away', '')),
        "match_time": match.get('matchTime', '') if isinstance(match.get('matchTime'), str) else _timestamp_to_datetime(match.get('matchTime', 0)),
        "is_stop": match.get('isStop', False),
    }
    
    # 提取传统足彩赔率（参考赔率）
    odds = extract_ctzc_odds(match)
    result.update(odds)
    
    return result


def extract_jingcai_odds(match: Dict) -> Dict[str, Any]:
    """从竞彩比赛数据中提取所有玩法赔率。"""
    odds = {}
    
    # 从oddsList数组提取（新API主要方式）
    odds_list = match.get('oddsList', [])
    for item in odds_list:
        pool_code = item.get('poolCode', '').lower()
        std_odds = normalize_jingcai_pool_odds(item, pool_code)
        if std_odds:
            odds[pool_code] = std_odds
    
    # 从直接字段提取（仅当oddsList没有该玩法时）
    for pool_code in ["had", "hhad", "crs", "ttg", "hafu"]:
        if pool_code in odds:
            continue  # 已从oddsList获取，跳过直接字段避免重复
        pool_data = match.get(pool_code)
        if pool_data and isinstance(pool_data, dict):
            std_odds = normalize_jingcai_pool_odds(pool_data, pool_code)
            if std_odds:
                odds[pool_code] = std_odds
    
    return odds


def normalize_jingcai_pool_odds(raw_data: Dict, pool_code: str) -> Optional[Dict]:
    """将竞彩单个玩法的原始数据标准化。"""
    if not raw_data:
        return None
    
    if pool_code in ("had", "hhad"):
        h = raw_data.get('h', '')
        d = raw_data.get('d', '')
        a = raw_data.get('a', '')
        
        if h and d and a:
            try:
                result = {
                    "win": float(h),
                    "draw": float(d),
                    "lose": float(a),
                }
                if pool_code == "hhad":
                    goal_line = raw_data.get('goalLine', '')
                    if goal_line:
                        result['handicap'] = goal_line
                return result
            except (ValueError, TypeError):
                pass
    
    elif pool_code == "crs":
        options = []
        for key, val in raw_data.items():
            if key in ('goalLine', 'updateDate', 'updateTime', 'goalLineValue', 'allUp', 'allUpFlag'):
                continue
            if not val:
                continue
            score = parse_crs_field(key)
            if score:
                try:
                    options.append({"score": score, "odds": float(val)})
                except (ValueError, TypeError):
                    pass
        if options:
            return {"options": sorted(options, key=lambda x: x['odds'])}
    
    elif pool_code == "ttg":
        result = {}
        for api_key, std_key in TTG_FIELD_MAP.items():
            val = raw_data.get(api_key)
            if val:
                try:
                    result[std_key] = float(val)
                except (ValueError, TypeError):
                    pass
        return result if result else None
    
    elif pool_code == "hafu":
        result = {}
        for api_key, std_key in HAFU_FIELD_MAP.items():
            val = raw_data.get(api_key)
            if val:
                try:
                    result[std_key] = float(val)
                except (ValueError, TypeError):
                    pass
        return result if result else None
    
    return None


def extract_beidan_odds(match: Dict) -> Dict[str, Any]:
    """从北单比赛数据中提取所有玩法SP值。"""
    odds = {}
    odds_data = match.get('odds', {})
    
    if not odds_data:
        return odds
    
    # 胜平负 (spf)
    spf = odds_data.get('spf', {})
    if spf:
        try:
            odds['had_odds'] = {
                "win": float(spf.get('sf3', 0)),
                "draw": float(spf.get('sf1', 0)),
                "lose": float(spf.get('sf0', 0)),
                "handicap": spf.get('goal', ''),
            }
        except (ValueError, TypeError):
            pass
    
    # 总进球 (jq)
    jq = odds_data.get('jq', {})
    if jq:
        try:
            odds['ttg_odds'] = {
                "goals_0": float(jq.get('j0', 0)),
                "goals_1": float(jq.get('j1', 0)),
                "goals_2": float(jq.get('j2', 0)),
                "goals_3": float(jq.get('j3', 0)),
                "goals_4": float(jq.get('j4', 0)),
                "goals_5": float(jq.get('j5', 0)),
                "goals_6": float(jq.get('j6', 0)),
                "goals_7": float(jq.get('j7', 0)),
            }
        except (ValueError, TypeError):
            pass
    
    # 半全场 (bqc)
    bqc = odds_data.get('bqc', {})
    if bqc:
        try:
            odds['hafu_odds'] = {}
            for api_key, std_key in BEIDAN_HAFU_MAP.items():
                val = bqc.get(api_key)
                if val:
                    odds['hafu_odds'][std_key] = float(val)
        except (ValueError, TypeError):
            pass
    
    # 上下单双 (sxp)
    sxp = odds_data.get('sxp', {})
    if sxp:
        try:
            odds['sx_odds'] = {
                "up_odd": float(sxp.get('sx11', 0)),      # 上单
                "up_even": float(sxp.get('sx10', 0)),     # 上双
                "down_odd": float(sxp.get('sx01', 0)),    # 下单
                "down_even": float(sxp.get('sx00', 0)),   # 下双
            }
        except (ValueError, TypeError):
            pass
    
    # 比分 (bf)
    bf = odds_data.get('bf', {})
    if bf:
        try:
            options = []
            for key, val in bf.items():
                if not val:
                    continue
                score = parse_beidan_score_field(key)
                if score:
                    options.append({"score": score, "odds": float(val)})
            if options:
                odds['crs_odds'] = {"options": sorted(options, key=lambda x: x['odds'])}
        except (ValueError, TypeError):
            pass
    
    # 胜负过关 (sf) - 小数让球，无平局
    sf = odds_data.get('sf', {})
    if sf:
        try:
            odds['sf_odds'] = {
                "win": float(sf.get('sf3', 0)),   # 胜
                "lose": float(sf.get('sf0', 0)),  # 负
                "handicap": sf.get('goal', ''),   # 让球数（小数让球如0.5, 1.5等）
            }
        except (ValueError, TypeError):
            pass
    
    return odds


def extract_ctzc_odds(match: Dict, lottery_type: str = "sfc") -> Dict[str, Any]:
    """从传统足彩比赛数据中提取参考赔率。

    Args:
        match: 比赛数据字典
        lottery_type: 玩法类型 (sfc/rx9/jqc/bqc)，不同玩法需要不同的赔率数据
    """
    odds = {}

    # 根据玩法类型提取相应的参考赔率
    if lottery_type in ("sfc", "rx9"):
        # 胜负彩14场/任选9场: 主要需要胜平负赔率
        had = match.get('had', {})
        if had:
            try:
                odds['had_odds'] = {
                    "win": float(had.get('h', 0)),
                    "draw": float(had.get('d', 0)),
                    "lose": float(had.get('a', 0)),
                }
            except (ValueError, TypeError):
                pass

        # 部分接口可能直接提供h/d/a字段
        if 'had_odds' not in odds:
            h = match.get('h', '')
            d = match.get('d', '')
            a = match.get('a', '')
            if h and d and a:
                try:
                    odds['had_odds'] = {
                        "win": float(h),
                        "draw": float(d),
                        "lose": float(a),
                    }
                except (ValueError, TypeError):
                    pass

    elif lottery_type == "jqc":
        # 4场进球彩: 需要总进球数赔率
        ttg = match.get('ttg', {})
        if ttg:
            try:
                odds['ttg_odds'] = {
                    "goals_0": float(ttg.get('s0', 0)),
                    "goals_1": float(ttg.get('s1', 0)),
                    "goals_2": float(ttg.get('s2', 0)),
                    "goals_3": float(ttg.get('s3', 0)),
                    "goals_4": float(ttg.get('s4', 0)),
                    "goals_5": float(ttg.get('s5', 0)),
                    "goals_6": float(ttg.get('s6', 0)),
                    "goals_7+": float(ttg.get('s7', 0)),
                }
            except (ValueError, TypeError):
                pass
        # 同时保留had赔率作为参考
        had = match.get('had', {})
        if had:
            try:
                odds['had_odds'] = {
                    "win": float(had.get('h', 0)),
                    "draw": float(had.get('d', 0)),
                    "lose": float(had.get('a', 0)),
                }
            except (ValueError, TypeError):
                pass

    elif lottery_type == "bqc":
        # 6场半全场: 需要半全场赔率
        hafu = match.get('hafu', {})
        if hafu:
            try:
                odds['hafu_odds'] = {
                    "胜胜": float(hafu.get('hh', 0)),
                    "胜平": float(hafu.get('hd', 0)),
                    "胜负": float(hafu.get('ha', 0)),
                    "平胜": float(hafu.get('dh', 0)),
                    "平平": float(hafu.get('dd', 0)),
                    "平负": float(hafu.get('da', 0)),
                    "负胜": float(hafu.get('ah', 0)),
                    "负平": float(hafu.get('ad', 0)),
                    "负负": float(hafu.get('aa', 0)),
                }
            except (ValueError, TypeError):
                pass
        # 同时保留had赔率作为参考
        had = match.get('had', {})
        if had:
            try:
                odds['had_odds'] = {
                    "win": float(had.get('h', 0)),
                    "draw": float(had.get('d', 0)),
                    "lose": float(had.get('a', 0)),
                }
            except (ValueError, TypeError):
                pass

    return odds


# ============================================================================
# 工具函数
# ============================================================================

def parse_crs_field(field: str) -> Optional[str]:
    """解析竞彩比分字段格式 sXXsYY -> X:Y。"""
    if not field or not field.startswith('s'):
        return None
    
    if field.endswith('f'):
        field = field[:-1]
    
    try:
        parts = field.split('s')
        if len(parts) == 3:
            home = int(parts[1])
            away = int(parts[2])
            return f"{home}:{away}"
    except (ValueError, IndexError):
        pass
    return None


def parse_beidan_score_field(field: str) -> Optional[str]:
    """解析北单比分字段格式 sXX -> X:Y 或特殊格式。"""
    if not field or not field.startswith('s'):
        return None
    
    # 标准比分 s00, s01, s10 等
    if len(field) == 3 and field[1:].isdigit():
        home = int(field[1])
        away = int(field[2])
        return f"{home}:{away}"
    
    # 胜其他 sw, 平其他 sp, 负其他 sl
    if field == 'sw':
        return "胜其他"
    elif field == 'sp':
        return "平其他"
    elif field == 'sl':
        return "负其他"
    
    # s20, s21 等格式
    if len(field) == 3:
        try:
            home = int(field[1])
            away = int(field[2])
            return f"{home}:{away}"
        except ValueError:
            pass
    
    return None


def _timestamp_to_datetime(timestamp: Union[int, str]) -> str:
    """将时间戳转换为日期时间字符串。"""
    if isinstance(timestamp, str):
        return timestamp
    if timestamp == 0:
        return ''
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, OSError):
        return str(timestamp)


# ============================================================================
# 赔率历史管理
# ============================================================================

ODDS_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odds_history")


def ensure_history_dir():
    """确保历史数据目录存在。"""
    if not os.path.exists(ODDS_HISTORY_DIR):
        os.makedirs(ODDS_HISTORY_DIR)


def save_odds_snapshot(matches: List[Dict], lottery_type: str = "jingcai") -> int:
    """
    保存当前赔率快照到本地历史记录。
    
    Args:
        matches: 比赛数据列表
        lottery_type: 彩票类型
        
    Returns:
        保存的比赛数量
    """
    ensure_history_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    count = 0
    
    for match in matches:
        match_id = match.get('match_id')
        if not match_id:
            continue
        
        history_file = os.path.join(ODDS_HISTORY_DIR, f"{lottery_type}_{match_id}.json")
        
        # 加载现有历史
        history = []
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                try:
                    history = json.load(f)
                except json.JSONDecodeError:
                    history = []
        
        # 添加新记录
        record = {
            "timestamp": timestamp,
            "lottery_type": lottery_type,
        }
        
        # 根据不同类型保存不同的赔率字段
        if lottery_type == "jingcai":
            record["had"] = match.get('had', {})
            record["hhad"] = match.get('hhad', {})
        elif lottery_type == "beidan":
            record["had_odds"] = match.get('had_odds', {})
            record["ttg_odds"] = match.get('ttg_odds', {})
        elif lottery_type == "ctzc":
            record["had_odds"] = match.get('had_odds', {})
        
        history.append(record)
        
        # 保存
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        
        count += 1
    
    return count


def load_odds_history(match_id: str, lottery_type: str = "jingcai") -> List[Dict]:
    """
    加载指定比赛的赔率历史。
    
    Args:
        match_id: 比赛ID
        lottery_type: 彩票类型
        
    Returns:
        历史记录列表，按时间排序
    """
    history_file = os.path.join(ODDS_HISTORY_DIR, f"{lottery_type}_{match_id}.json")
    
    if not os.path.exists(history_file):
        return []
    
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    except FileNotFoundError:
        # 文件不存在时返回空列表
        return []
    except PermissionError:
        # 权限错误时返回空列表
        return []
    except Exception:
        # 其他异常返回空列表
        return []


def get_matches_with_history(lottery_type: Optional[str] = None) -> List[str]:
    """
    获取所有有历史记录的比赛ID列表。
    
    Args:
        lottery_type: 可选，指定彩票类型筛选
    """
    ensure_history_dir()
    files = [f for f in os.listdir(ODDS_HISTORY_DIR) if f.endswith('.json')]
    
    if lottery_type:
        prefix = f"{lottery_type}_"
        files = [f for f in files if f.startswith(prefix)]
        return [f.replace(prefix, '').replace('.json', '') for f in files]
    
    return [f.replace('.json', '') for f in files]


# ============================================================================
# 数据分析工具
# ============================================================================

def calculate_odds_change(history: List[Dict]) -> Dict[str, Any]:
    """
    计算赔率变化趋势。
    
    Args:
        history: 赔率历史记录列表
        
    Returns:
        变化分析结果
    """
    if len(history) < 2:
        return {
            "trend": "数据不足（需要至少2条记录才能分析变化）",
            "record_count": len(history),
            "time_span": history[0].get('timestamp', 'unknown') if history else '无数据',
            "changes": []
        }
    
    first = history[0]
    last = history[-1]
    lottery_type = first.get('lottery_type', 'jingcai')
    
    changes = []
    
    if lottery_type == "jingcai":
        # 胜平负变化
        if first.get('had') and last.get('had'):
            f_had = first['had']
            l_had = last['had']
            for key in ['win', 'draw', 'lose']:
                if key in f_had and key in l_had:
                    change = round(l_had[key] - f_had[key], 2)
                    if abs(change) > 0.01:
                        direction = "↑" if change > 0 else "↓"
                        changes.append(f"{key}: {f_had[key]}→{l_had[key]} {direction}")
        
        # 让球变化
        if first.get('hhad') and last.get('hhad'):
            f_hhad = first['hhad']
            l_hhad = last['hhad']
            for key in ['win', 'draw', 'lose']:
                if key in f_hhad and key in l_hhad:
                    change = round(l_hhad[key] - f_hhad[key], 2)
                    if abs(change) > 0.01:
                        direction = "↑" if change > 0 else "↓"
                        changes.append(f"让球{key}: {f_hhad[key]}→{l_hhad[key]} {direction}")
    
    elif lottery_type == "beidan":
        # 北单SP值变化
        if first.get('had_odds') and last.get('had_odds'):
            f_odds = first['had_odds']
            l_odds = last['had_odds']
            for key in ['win', 'draw', 'lose']:
                if key in f_odds and key in l_odds:
                    change = round(l_odds[key] - f_odds[key], 2)
                    if abs(change) > 0.01:
                        direction = "↑" if change > 0 else "↓"
                        changes.append(f"SP{key}: {f_odds[key]}→{l_odds[key]} {direction}")
    
    # 判断趋势
    if not changes:
        trend = "稳定"
    elif len([c for c in changes if '↑' in c]) > len([c for c in changes if '↓' in c]):
        trend = "主胜赔率上升（市场看好客队）"
    else:
        trend = "主胜赔率下降（市场看好主队）"
    
    return {
        "trend": trend,
        "record_count": len(history),
        "time_span": f"{history[0].get('timestamp', 'unknown')} ~ {history[-1].get('timestamp', 'unknown')}",
        "changes": changes[:5],  # 最多5条变化
    }


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("彩票数据获取模块测试")
    print("支持: 竞彩足球(jingcai) | 北单(beidan) | 传统足彩(ctzc)")
    print("=" * 60)
    
    # 测试竞彩足球
    print("\n【1. 测试竞彩足球数据获取】")
    try:
        matches = fetch_jingcai_matches()
        print(f"✓ 获取到 {len(matches)} 场竞彩比赛")
        
        if matches:
            m = matches[0]
            print(f"\n示例比赛:")
            print(f"  对阵: {m['home_team']} vs {m['away_team']}")
            print(f"  联赛: {m['league']}, 时间: {m['match_time']}")
            print(f"  ID: {m['match_id']}")
            
            if 'had' in m:
                print(f"  胜平负: {m['had']}")
            if 'hhad' in m:
                print(f"  让球: {m['hhad']}")
            
            # 保存快照
            count = save_odds_snapshot(matches[:3], "jingcai")
            print(f"\n✓ 已保存 {count} 场比赛的赔率快照")
    except Exception as e:
        print(f"✗ 竞彩数据获取失败: {e}")
    
    # 测试北单
    print("\n【2. 测试北单数据获取】")
    try:
        matches = fetch_beidan_matches()
        print(f"✓ 获取到 {len(matches)} 场北单比赛")
        
        if matches:
            m = matches[0]
            print(f"\n示例比赛:")
            print(f"  对阵: {m['home_team']} vs {m['away_team']}")
            print(f"  联赛: {m['league']}, 时间: {m['match_time']}")
            print(f"  期号: {m.get('issue', 'N/A')}, 序号: {m.get('issue_num', 'N/A')}")
            
            if 'had_odds' in m:
                print(f"  胜平负SP: {m['had_odds']}")
            if 'ttg_odds' in m:
                print(f"  总进球SP: 0球={m['ttg_odds'].get('goals_0', 'N/A')}, 1球={m['ttg_odds'].get('goals_1', 'N/A')}")
            
            # 保存快照
            count = save_odds_snapshot(matches[:3], "beidan")
            print(f"\n✓ 已保存 {count} 场比赛的SP快照")
    except Exception as e:
        print(f"✗ 北单数据获取失败: {e}")
    
    # 测试传统足彩
    print("\n【3. 测试传统足彩数据获取】")
    try:
        matches = fetch_ctzc_matches()
        print(f"✓ 获取到 {len(matches)} 场传统足彩比赛")
        
        if matches:
            m = matches[0]
            print(f"\n示例比赛:")
            print(f"  期号: {m.get('issue_number', 'N/A')}, 场次: {m.get('match_index', 'N/A')}")
            print(f"  对阵: {m['home_team']} vs {m['away_team']}")
            print(f"  联赛: {m['league']}, 时间: {m['match_time']}")
            
            if 'had_odds' in m:
                print(f"  参考赔率: {m['had_odds']}")
            
            # 保存快照
            count = save_odds_snapshot(matches[:3], "ctzc")
            print(f"\n✓ 已保存 {count} 场比赛的赔率快照")
    except Exception as e:
        print(f"✗ 传统足彩数据获取失败: {e}")
    
    # 测试统一接口
    print("\n【4. 测试统一接口 fetch_today_matches()】")
    for lot_type in ["jingcai", "beidan", "ctzc"]:
        try:
            matches = fetch_today_matches(lot_type)
            print(f"✓ {lot_type}: 获取到 {len(matches)} 场比赛")
        except Exception as e:
            print(f"✗ {lot_type}: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
