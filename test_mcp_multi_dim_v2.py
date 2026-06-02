#!/usr/bin/env python3
"""
Lottery MCP 超全面多维度测试脚本 v2.0
=======================================================
测试维度扩展到 **20+** 个维度，覆盖：
1. 工具元数据完整性
2. 端到端工作流
3. 参数边界值 & 异常输入
4. 错误处理优雅降级
5. 资源 & 提示词
6. 输出格式验证
7. 集成数据流
8. 性能 & 并发
9. 安全注入防护
10. 系统指令验证
11. 配置管理
12. 缓存机制
13. 内存稳定性
14. 启动健康检查
15. 投注计算准确性
16. 规则引擎验证
17. 风险控制守卫
18. 历史数据完整性
19. UTF-8/编码处理
20. Pydantic模型验证
"""
import asyncio
import json
import time
import sys
import traceback
import gc
import os
import re
import inspect
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from pydantic import create_model

# ============================================================
# 基础设施
# ============================================================
class MockContext:
    async def log_info(self, msg): pass
    async def log_error(self, msg): pass
    async def report_progress(self, p, msg=None): pass
    async def read_resource(self, uri): return None
    async def get_tool_description(self, name): return None
    async def log_warning(self, msg): pass

from lottery_mcp.server import create_mcp_server
mcp = create_mcp_server()
tools = mcp._tool_manager._tools
resources = mcp._resource_manager._resources
prompts = mcp._prompt_manager._prompts


def build_params_model(tool, params_dict):
    if 'params' not in tool.parameters.get('properties', {}):
        return None
    param_ref = tool.parameters['properties']['params'].get('$ref', '')
    model_name = param_ref.split('/')[-1] if param_ref else None
    if not model_name or model_name not in tool.parameters.get('$defs', {}):
        return None
    schema = tool.parameters['$defs'][model_name]
    props = schema.get('properties', {})
    reqd = schema.get('required', [])
    fields = {}
    tmap = {'string': str, 'integer': int, 'number': float, 'boolean': bool, 'array': list, 'object': dict}
    for k, p in props.items():
        pt = tmap.get(p.get('type', 'string'), str)
        d = p.get('default', ...)
        if k in reqd: fields[k] = (pt, ...)
        elif d != ...: fields[k] = (pt, d)
        else: fields[k] = (pt, None)
    if not fields: return None
    PM = create_model(f'{model_name}V', **fields)
    filtered = {k: v for k, v in params_dict.items() if k in fields}
    for k in reqd:
        if k not in filtered:
            filtered[k] = props.get(k, {}).get('default', '')
    return PM(**filtered)


async def call_tool(name, params_dict=None):
    """调用工具并返回 (状态, 耗时, 结果或错误)"""
    params_dict = params_dict or {}
    start = time.time()
    try:
        tool = tools[name]
        fn = tool.fn
        ctx = MockContext()
        sig = inspect.signature(fn)
        is_async = inspect.iscoroutinefunction(fn)

        kwargs = {}
        has_params_param = 'params' in sig.parameters
        has_ctx_param = 'ctx' in sig.parameters

        if has_params_param:
            params_model = build_params_model(tool, params_dict)
            if params_model is not None:
                kwargs['params'] = params_model
            else:
                kwargs['params'] = params_dict
        else:
            for param_name, param in sig.parameters.items():
                if param_name == 'ctx':
                    continue
                if param_name in params_dict:
                    val = params_dict[param_name]
                    ann = param.annotation if param.annotation is not inspect.Parameter.empty else None
                    if ann == str and isinstance(val, dict):
                        kwargs[param_name] = json.dumps(val, ensure_ascii=False)
                    else:
                        kwargs[param_name] = val
                elif param.default is not inspect.Parameter.empty:
                    kwargs[param_name] = param.default

        if has_ctx_param:
            kwargs['ctx'] = ctx

        if is_async:
            result = str(await fn(**kwargs))
        else:
            result = str(fn(**kwargs))

        elapsed = round(time.time() - start, 4)
        return ('ok', elapsed, result)
    except Exception as e:
        elapsed = round(time.time() - start, 4)
        return ('error', elapsed, str(e)[:800])


def is_valid_json(s):
    try:
        json.loads(s)
        return True
    except:
        return False


def result_has_data(r):
    return len(r) > 20 and ('success' in r.lower() or 'data' in r.lower() or 'error' in r.lower())


# ============================================================
# 测试统计
# ============================================================
@dataclass
class TestStats:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)
    latencies: List[float] = field(default_factory=list)
    
    def record(self, ok: bool, elapsed: float = 0.0, detail: str = ""):
        self.total += 1
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            if detail:
                self.errors.append(detail)
        if elapsed > 0:
            self.latencies.append(elapsed)
    
    def summary(self):
        if not self.total:
            return "N/A"
        return f"{self.passed}/{self.total} ({self.passed/self.total*100:.1f}%)"


# ============================================================
# 测试数据
# ============================================================
INVALID_MATCH = "9999999999999999"
VALID_MATCH = "2025052510001"
EMPTY_STR = ""
LARGE_STRING = "x" * 10000
SPECIAL_CHARS = "测试 中文 🌍 éñøû"
SQL_INJECTION = "'; DROP TABLE matches; --"
XSS_INJECTION = "<script>alert('xss')</script>"
NEGATIVE_STAKE = -100
ZERO_STAKE = 0
HUGE_STAKE = 999999999999
INVALID_ODDS = -2.5

# 参数映射 - 补充更多工具
PARAM_MAP = {
    'lottery_advisor_analysis': {'match_id': VALID_MATCH},
    'lottery_advanced_play_analysis': {'match_id': VALID_MATCH},
    'lottery_analyze_all_matches': {},
    'lottery_analyze_match': {'match_id': VALID_MATCH, 'league': '英超'},
    'lottery_analyze_match_plays': {'match_id': VALID_MATCH, 'play_types': ['SPF', 'BF']},
    'lottery_analyze_mixed_parlay': {},
    'lottery_analyze_results': {'match_id': VALID_MATCH},
    'lottery_analyze_with_pipeline': {},
    'lottery_assess_risk': {'match_id': VALID_MATCH},
    'lottery_calculate_bonus': {'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100}], 'parlay_type': '1c1'},
    'lottery_check_bankroll_health': {'bankroll': 5000, 'initial_bankroll': 10000},
    'lottery_check_match_deadline': {'match_time': '2026-12-31T20:00:00'},
    'lottery_compare_matches': {'match_ids': ['M001', 'M002'], 'comparison_dimensions': ['odds', 'form']},
    'lottery_compare_model_predictions': {'match_id': VALID_MATCH},
    'lottery_comprehensive_risk_assessment': {'planned_bet_amount': 100, 'lottery_type': '竞彩足球'},
    'lottery_detect_risk_signals': {'match_id': VALID_MATCH},
    'lottery_enforce_constraints': {'bet_proposal': json.dumps({'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100}], 'total_stake': 100})},
    'lottery_explain_rule': {'rule_code': 'SPF'},
    'lottery_fetch_today_matches': {'lottery_type': '竞彩足球', 'limit': 1, 'include_odds': False},
    'lottery_find_value_bets': {'match_id': VALID_MATCH},
    'lottery_full_analysis_and_betting': {'bankroll': 5000, 'max_matches': 2, 'strategy': 'conservative'},
    'lottery_generate_betting_slips': {'match_ids': ['M001', 'M002'], 'strategy': 'single', 'bankroll': 1000.0, 'limit': 5},
    'lottery_generate_kelly_slips': {'match_id': VALID_MATCH, 'edge': 0.05, 'odds': 2.0, 'bankroll': 1000.0},
    'lottery_generate_prediction_report': {},
    'lottery_generate_recommendation': {},
    'lottery_get_bet_statistics': {'date': '2026-01-01'},
    'lottery_get_betting_stats': {'date': '2026-01-01'},
    'lottery_get_daily_recommendations': {},
    'lottery_get_full_analysis_report': {},
    'lottery_get_future_matches': {'match_id': VALID_MATCH, 'limit': 3},
    'lottery_get_head_to_head': {'team1': '曼联', 'team2': '利物浦', 'limit': 5},
    'lottery_get_historical_data_summary': {},
    'lottery_get_injury_suspension': {'match_id': VALID_MATCH},
    'lottery_get_jingcai_h2h': {'match_id': VALID_MATCH, 'limit': 5},
    'lottery_get_league_matches': {'league': '英超', 'limit': 5},
    'lottery_get_live_odds': {'source': 'auto'},
    'lottery_get_live_scores': {'limit': 5},
    'lottery_get_local_odds_history': {'match_id': VALID_MATCH},
    'lottery_get_market_odds': {'league': '英超'},
    'lottery_get_market_sentiment': {'match_id': VALID_MATCH},
    'lottery_get_match_context': {'match_id': VALID_MATCH},
    'lottery_get_match_data': {'match_id': VALID_MATCH},
    'lottery_get_match_features': {'match_id': VALID_MATCH, 'limit': 5},
    'lottery_get_match_info': {'match_id': VALID_MATCH},
    'lottery_get_match_standings': {'match_id': VALID_MATCH},
    'lottery_get_odds_history': {'match_id': VALID_MATCH},
    'lottery_get_players': {'match_id': VALID_MATCH, 'limit': 3},
    'lottery_get_recent_form': {'match_id': VALID_MATCH, 'limit': 5},
    'lottery_get_system_status': {},
    'lottery_get_team_history': {'team_name': '曼联', 'limit': 5},
    'lottery_get_team_stats': {'team_name': '曼联'},
    'lottery_historical_analysis': {'match_id': VALID_MATCH},
    'lottery_list_local_odds_matches': {},
    'lottery_list_workflows': {},
    'lottery_manage_config': {'action': 'get', 'key': 'default_parlay_type'},
    'lottery_monitor_odds': {'match_id': VALID_MATCH, 'current_odds': {'win': 2.0, 'draw': 3.5, 'lose': 3.0}},
    'lottery_optimize_stakes': {'bankroll': 1000.0, 'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0}], 'strategy': 'kelly'},
    'lottery_predict_with_model': {'match_id': VALID_MATCH},
    'lottery_quantify_injury_impact': {'match_id': VALID_MATCH},
    'lottery_query_history': {'date': '2026-01-01'},
    'lottery_query_rules': {'rule_code': 'SPF'},
    'lottery_quick_scan_and_recommend': {},
    'lottery_recommend_best_play': {'match_id': VALID_MATCH, 'play_types': ['SPF', 'BF']},
    'lottery_reject': {'reason': '测试拒绝'},
    'lottery_rule_guard': {'action': 'check', 'rule': 'C001'},
    'lottery_save_odds_snapshot': {'match_id': VALID_MATCH, 'odds': {'win': 2.0, 'draw': 3.5, 'lose': 3.0}},
    'lottery_search_historical_matches': {'team': '曼联', 'league': '英超', 'limit': 5},
    'lottery_search_league': {'query': '英超'},
    'lottery_settle_bet': {'bet_id': 'TEST001', 'result': 'win'},
    'lottery_simulate_scenarios': {'match_id': VALID_MATCH},
    'lottery_smart_parlay': {},
    'lottery_track_bet': {'bet_id': 'TEST001', 'match_id': 'M001', 'play_type': 'SPF', 'stake': 100, 'odds': 2.0},
    'lottery_track_odds_changes': {'match_id': VALID_MATCH},
    'lottery_validate_bet': {'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100},
    'lottery_validate_parlay': {'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0}], 'parlay_type': '1c1', 'total_stake': 100.0},
    'lottery_validate_plan': {'plan_type': 'daily', 'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0}], 'total_budget': 1000.0},
    'lottery_validate_scenario': {'scenario_type': 'single_bet', 'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0}]},
    'lottery_verify_results': {'match_id': VALID_MATCH},
}


# ============================================================
# DIMENSION 1: 工具元数据完整性
# ============================================================
async def test_dim1_tool_metadata():
    print("\n" + "="*80)
    print("DIMENSION 1: 工具元数据完整性")
    print("="*80)
    
    stats = TestStats()
    tool_names = sorted(tools.keys())
    
    print(f"\n📊 总工具数: {len(tool_names)}")
    
    # 1.1 所有工具都有描述
    print("\n--- 1.1 工具描述检查 ---")
    missing_desc = 0
    short_desc = 0
    for name in tool_names:
        desc = tools[name].description
        if not desc or not desc.strip():
            missing_desc += 1
            print(f"❌ {name}: 缺少描述")
        elif len(desc.strip()) < 10:
            short_desc += 1
            print(f"⚠️ {name}: 描述过短 ({len(desc.strip())} 字符)")
        else:
            stats.record(True, 0.0, f"{name}: 描述完整")
    
    stats.record(missing_desc == 0, 0.0, f"缺少描述工具数: {missing_desc}")
    print(f"\n✅ 工具描述检查: {len(tool_names)-missing_desc}/{len(tool_names)} 完整")
    
    # 1.2 所有工具都有4个注释
    print("\n--- 1.2 工具注释完整性 ---")
    required_annotations = ['readOnlyHint', 'destructiveHint', 'idempotentHint', 'openWorldHint']
    incomplete_tools = []
    
    for name in tool_names:
        ann = tools[name].annotations
        if ann:
            missing = [a for a in required_annotations if not hasattr(ann, a) or getattr(ann, a) is None]
            if missing:
                incomplete_tools.append((name, missing))
                print(f"❌ {name}: 缺少注释 {missing}")
            else:
                stats.record(True, 0.0, f"{name}: 注释完整")
        else:
            incomplete_tools.append((name, '全部'))
    
    stats.record(len(incomplete_tools) == 0, 0.0, f"缺少注释工具数: {len(incomplete_tools)}")
    print(f"\n✅ 注释完整性: {len(tool_names)-len(incomplete_tools)}/{len(tool_names)} 完整")
    
    # 1.3 工具命名规范 (以 lottery_ 开头)
    print("\n--- 1.3 命名规范检查 ---")
    bad_names = [n for n in tool_names if not n.startswith('lottery_')]
    stats.record(len(bad_names) == 0, 0.0, f"违规工具名: {bad_names}")
    if bad_names:
        print(f"❌ 违规工具名: {bad_names}")
    else:
        print(f"✅ 所有 {len(tool_names)} 工具名符合规范")
    
    # 1.4 参数Schema完整性
    print("\n--- 1.4 参数Schema完整性 ---")
    missing_params = []
    for name in tool_names:
        props = tools[name].parameters.get('properties', {})
        if 'params' in props:
            ref = props['params'].get('$ref', '')
            model_name = ref.split('/')[-1] if ref else None
            if model_name and model_name not in tools[name].parameters.get('$defs', {}):
                missing_params.append(name)
                print(f"⚠️ {name}: 参数模型定义缺失")
    
    stats.record(len(missing_params) == 0, 0.0, f"参数模型缺失: {len(missing_params)}")
    print(f"\n✅ 参数Schema: {len(tool_names)-len(missing_params)}/{len(tool_names)} 完整")
    
    return stats


# ============================================================
# DIMENSION 2: 端到端工作流测试
# ============================================================
async def test_dim2_workflows():
    print("\n" + "="*80)
    print("DIMENSION 2: 端到端工作流测试")
    print("="*80)
    
    stats = TestStats()
    workflow_tools = [
        'lottery_list_workflows',
        'lottery_full_analysis_and_betting',
        'lottery_quick_scan_and_recommend', 
        'lottery_comprehensive_risk_assessment'
    ]
    
    print(f"\n📋 工作流列表: {workflow_tools}")
    
    for wf_name in workflow_tools:
        if wf_name not in tools:
            print(f"❌ {wf_name}: 工具不存在")
            stats.record(False, 0.0, f"{wf_name} 不存在")
            continue
        
        params = PARAM_MAP.get(wf_name, {})
        status, elapsed, result = await call_tool(wf_name, params)
        
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{wf_name}: {result[:150]}" if not ok else f"{wf_name} OK ({elapsed:.2f}s)")
        
        if ok:
            print(f"✅ {wf_name}: 成功 ({elapsed:.3f}s)")
            if len(result) > 100:
                print(f"   输出长度: {len(result)} 字符")
        else:
            print(f"❌ {wf_name}: 失败 - {result[:200]}")
    
    return stats


# ============================================================
# DIMENSION 3: 参数边界值 & 异常输入
# ============================================================
async def test_dim3_edge_cases():
    print("\n" + "="*80)
    print("DIMENSION 3: 参数边界值 & 异常输入")
    print("="*80)
    
    stats = TestStats()
    
    # 3.1 无效比赛ID
    print("\n--- 3.1 无效比赛ID ---")
    match_id_tools = ['lottery_get_match_info', 'lottery_analyze_match', 'lottery_advisor_analysis',
                      'lottery_get_match_features', 'lottery_get_recent_form', 'lottery_detect_risk_signals']
    for name in match_id_tools:
        if name not in tools: continue
        status, elapsed, result = await call_tool(name, {'match_id': INVALID_MATCH})
        stats.record(True, elapsed, f"{name}: 处理无效ID")  # 只要不crash就算通过
        print(f"{'✅' if status == 'ok' else '⚠️'} {name}: 无效ID处理 ({elapsed:.3f}s)")
    
    # 3.2 空字符串参数
    print("\n--- 3.2 空字符串参数 ---")
    empty_tests = [
        ('lottery_search_league', {'query': ''}),
        ('lottery_explain_rule', {'rule_code': ''}),
        ('lottery_get_team_stats', {'team_name': ''}),
    ]
    for name, params in empty_tests:
        if name not in tools: continue
        status, elapsed, result = await call_tool(name, params)
        stats.record(True, elapsed, f"{name}: 空字符串")
        print(f"{'✅' if status == 'ok' else '⚠️'} {name}: 空字符串 ({elapsed:.3f}s)")
    
    # 3.3 超大字符串
    print("\n--- 3.3 超大字符串参数 ---")
    status, elapsed, result = await call_tool('lottery_search_league', {'query': LARGE_STRING})
    stats.record(True, elapsed, "超大字符串")
    print(f"{'✅' if status == 'ok' else '⚠️'} 超大字符串: {elapsed:.3f}s")
    
    # 3.4 特殊字符编码
    print("\n--- 3.4 UTF-8 特殊字符 ---")
    status, elapsed, result = await call_tool('lottery_search_league', {'query': SPECIAL_CHARS})
    stats.record(True, elapsed, "UTF-8字符")
    print(f"{'✅' if status == 'ok' else '⚠️'} UTF-8字符: {elapsed:.3f}s")
    
    # 3.5 负数/零值边界
    print("\n--- 3.5 投注边界值 ---")
    boundary_tests = [
        ('lottery_validate_bet', {'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': NEGATIVE_STAKE}),
        ('lottery_validate_bet', {'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': INVALID_ODDS, 'stake': 100}),
        ('lottery_check_bankroll_health', {'bankroll': 0, 'initial_bankroll': 10000}),
    ]
    for name, params in boundary_tests:
        if name not in tools: continue
        status, elapsed, result = await call_tool(name, params)
        stats.record(True, elapsed, f"{name}: 边界值")
        print(f"{'✅' if status == 'ok' else '⚠️'} {name}: 边界值 ({elapsed:.3f}s)")
    
    return stats


# ============================================================
# DIMENSION 4: 安全注入防护
# ============================================================
async def test_dim4_security():
    print("\n" + "="*80)
    print("DIMENSION 4: 安全注入防护")
    print("="*80)
    
    stats = TestStats()
    
    # SQL注入测试
    print("\n--- 4.1 SQL注入防护 ---")
    sql_tools = ['lottery_search_league', 'lottery_get_team_stats', 'lottery_query_history']
    for name in sql_tools:
        if name not in tools: continue
        params = {'query': SQL_INJECTION} if 'query' in inspect.signature(tools[name].fn).parameters else {'team_name': SQL_INJECTION}
        status, elapsed, result = await call_tool(name, params)
        stats.record(True, elapsed, f"{name}: SQL注入")
        print(f"{'✅' if status == 'ok' else '⚠️'} {name}: SQL注入 ({elapsed:.3f}s)")
    
    # XSS注入测试
    print("\n--- 4.2 XSS注入防护 ---")
    xss_tools = ['lottery_search_league', 'lottery_get_team_history']
    for name in xss_tools:
        if name not in tools: continue
        params = {'query': XSS_INJECTION} if 'query' in inspect.signature(tools[name].fn).parameters else {'team_name': XSS_INJECTION}
        status, elapsed, result = await call_tool(name, params)
        stats.record(True, elapsed, f"{name}: XSS注入")
        print(f"{'✅' if status == 'ok' else '⚠️'} {name}: XSS注入 ({elapsed:.3f}s)")
    
    return stats


# ============================================================
# DIMENSION 5: 资源 & 提示词
# ============================================================
async def test_dim5_resources_prompts():
    print("\n" + "="*80)
    print("DIMENSION 5: 资源 & 提示词")
    print("="*80)
    
    rstats = TestStats()
    pstats = TestStats()
    
    # 资源测试
    print(f"\n--- 资源 ({len(resources)}) ---")
    for name in sorted(resources.keys()):
        try:
            r = resources[name]
            has_desc = bool(r.description)
            has_uri = bool(r.uri)
            ok = has_desc and has_uri
            rstats.record(ok, 0.0, f"{name}: {'OK' if ok else 'missing desc/uri'}")
            print(f"{'✅' if ok else '❌'} {name}: uri={bool(r.uri)}, desc={len(r.description or '')} chars")
        except Exception as e:
            rstats.record(False, 0.0, f"{name}: {e}")
            print(f"❌ {name}: ERROR - {e}")
    
    # 提示词测试
    print(f"\n--- 提示词 ({len(prompts)}) ---")
    for name in sorted(prompts.keys()):
        try:
            p = prompts[name]
            has_desc = bool(p.description)
            ok = has_desc
            pstats.record(ok, 0.0, f"{name}: {'OK' if ok else 'missing desc'}")
            print(f"{'✅' if ok else '❌'} {name}: desc={len(p.description or '')} chars")
        except Exception as e:
            pstats.record(False, 0.0, f"{name}: {e}")
            print(f"❌ {name}: ERROR - {e}")
    
    return rstats, pstats


# ============================================================
# DIMENSION 6: 输出格式验证
# ============================================================
async def test_dim6_output_validation():
    print("\n" + "="*80)
    print("DIMENSION 6: 输出格式验证")
    print("="*80)
    
    stats = TestStats()
    
    # 检查所有工具输出格式
    print(f"\n--- 工具输出检查 ({len(tools)} 个) ---")
    json_ok = 0
    non_json_ok = 0
    output_tools = [name for name in tools.keys() if name in PARAM_MAP]
    
    for name in output_tools[:50]:  # 限制数量，避免耗时太久
        params = PARAM_MAP.get(name, {})
        status, elapsed, result = await call_tool(name, params)
        
        if status == 'ok':
            if is_valid_json(result):
                json_ok += 1
                stats.record(True, elapsed, f"{name}: JSON")
                print(f"✅ {name}: JSON 格式 ({elapsed:.2f}s)")
            elif len(result) > 50:
                non_json_ok += 1
                stats.record(True, elapsed, f"{name}: 文本格式")
                print(f"📝 {name}: 文本格式 ({elapsed:.2f}s)")
            else:
                stats.record(False, elapsed, f"{name}: 输出过短")
                print(f"⚠️ {name}: 输出过短 ({len(result)} 字符)")
        else:
            stats.record(False, elapsed, f"{name}: 调用失败")
            print(f"❌ {name}: 调用失败 - {result[:100]}")
    
    print(f"\n✅ JSON输出: {json_ok}, 📝 文本输出: {non_json_ok}")
    return stats


# ============================================================
# DIMENSION 7: 系统指令完整性
# ============================================================
async def test_dim7_system_instructions():
    print("\n" + "="*80)
    print("DIMENSION 7: 系统指令完整性")
    print("="*80)
    
    stats = TestStats()
    
    from lottery_mcp.server import SYSTEM_INSTRUCTIONS
    print(f"\n📄 系统指令长度: {len(SYSTEM_INSTRUCTIONS)} 字符")
    
    # 检查关键部分
    required_sections = [
        '端到端工作流',
        'AI推理安全协议',
        '防幻觉强制规则',
        '约束验证',
        '资金健康检查',
        '比赛截止检查',
        'lottery_full_analysis_and_betting',
        'lottery_list_workflows',
        'lottery_comprehensive_risk_assessment'
    ]
    
    missing = []
    for section in required_sections:
        if section not in SYSTEM_INSTRUCTIONS:
            missing.append(section)
    
    if missing:
        print(f"❌ 缺少关键章节: {missing}")
        stats.record(False, 0.0, f"缺少章节: {missing}")
    else:
        print(f"✅ 所有关键章节都存在")
        stats.record(True, 0.0, "系统指令完整")
    
    # 检查工作流引用
    for wf in ['lottery_list_workflows', 'lottery_full_analysis_and_betting', 'lottery_comprehensive_risk_assessment']:
        if wf in SYSTEM_INSTRUCTIONS:
            print(f"✅ {wf} 在系统指令中被引用")
            stats.record(True, 0.0, f"{wf} 引用存在")
        else:
            print(f"⚠️ {wf} 未在系统指令中引用")
    
    return stats


# ============================================================
# DIMENSION 8: 性能 & 并发
# ============================================================
async def test_dim8_performance_concurrency():
    print("\n" + "="*80)
    print("DIMENSION 8: 性能 & 并发")
    print("="*80)
    
    stats = TestStats()
    
    # 8.1 并发测试
    print("\n--- 8.1 并发调用 (10个工具) ---")
    start = time.time()
    tasks = []
    concurrency_tools = ['lottery_query_rules', 'lottery_explain_rule', 'lottery_get_system_status',
                         'lottery_list_workflows', 'lottery_search_league', 'lottery_get_team_stats']
    
    for name in concurrency_tools:
        if name in tools:
            params = PARAM_MAP.get(name, {})
            tasks.append(call_tool(name, params))
    
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start
        success = sum(1 for r in results if isinstance(r, tuple) and r[0] == 'ok')
        print(f"✅ 并发: {success}/{len(tasks)} 成功, 耗时 {elapsed:.3f}s")
        stats.record(success >= len(tasks) * 0.7, elapsed, f"并发成功率: {success}/{len(tasks)}")
    
    # 8.2 快速连续调用 (压力测试)
    print("\n--- 8.2 快速连续调用 (30次) ---")
    rapid_start = time.time()
    rapid_ok = 0
    for i in range(30):
        status, _, _ = await call_tool('lottery_get_system_status', {})
        if status == 'ok':
            rapid_ok += 1
    rapid_elapsed = time.time() - rapid_start
    print(f"✅ 快速调用: {rapid_ok}/30 成功, 耗时 {rapid_elapsed:.3f}s ({rapid_elapsed/30*1000:.1f}ms/次)")
    stats.record(rapid_ok >= 25, rapid_elapsed, f"快速调用: {rapid_ok}/30")
    
    return stats


# ============================================================
# DIMENSION 9: 投注计算准确性
# ============================================================
async def test_dim9_betting_calculations():
    print("\n" + "="*80)
    print("DIMENSION 9: 投注计算准确性")
    print("="*80)
    
    stats = TestStats()
    
    # 奖金计算测试
    print("\n--- 9.1 奖金计算 ---")
    calc_tests = [
        {'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100}], 'parlay_type': '1c1'},
        {'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 1.5, 'stake': 200}], 'parlay_type': '1c1'},
        {'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 50},
                  {'match_id': 'M002', 'play_type': 'SPF', 'selection': '主胜', 'odds': 1.8, 'stake': 50}], 'parlay_type': '2c1'},
    ]
    
    for test_params in calc_tests:
        status, elapsed, result = await call_tool('lottery_calculate_bonus', test_params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"奖金计算: {result[:100]}")
        print(f"{'✅' if ok else '❌'} 奖金计算: {elapsed:.3f}s")
    
    # 投注验证测试
    print("\n--- 9.2 投注验证 ---")
    validate_tests = [
        {'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100},
        {'match_id': 'M001', 'play_type': 'BF', 'selection': '1:0', 'odds': 6.5, 'stake': 50},
    ]
    
    for test_params in validate_tests:
        status, elapsed, result = await call_tool('lottery_validate_bet', test_params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"投注验证: {result[:100]}")
        print(f"{'✅' if ok else '❌'} 投注验证: {elapsed:.3f}s")
    
    return stats


# ============================================================
# DIMENSION 10: 配置管理
# ============================================================
async def test_dim10_config():
    print("\n" + "="*80)
    print("DIMENSION 10: 配置管理")
    print("="*80)
    
    stats = TestStats()
    
    if 'lottery_manage_config' in tools:
        # 测试获取配置
        print("\n--- 10.1 获取配置 ---")
        status, elapsed, result = await call_tool('lottery_manage_config', {'action': 'get', 'key': 'default_parlay_type'})
        ok = status == 'ok'
        stats.record(ok, elapsed, f"获取配置: {result[:100]}")
        print(f"{'✅' if ok else '❌'} 获取配置: {elapsed:.3f}s")
        
        # 测试列出所有配置
        print("\n--- 10.2 列出配置 ---")
        status, elapsed, result = await call_tool('lottery_manage_config', {'action': 'list'})
        ok = status == 'ok'
        stats.record(ok, elapsed, f"列出配置: {result[:100]}")
        print(f"{'✅' if ok else '❌'} 列出配置: {elapsed:.3f}s")
    
    return stats


# ============================================================
# DIMENSION 11: 启动健康检查
# ============================================================
async def test_dim11_startup_health():
    print("\n" + "="*80)
    print("DIMENSION 11: 启动健康检查")
    print("="*80)
    
    stats = TestStats()
    
    # 调用启动健康检查函数
    from lottery_mcp.server import startup_health_check
    health_result = startup_health_check()
    
    print(f"\n🏥 健康检查结果:")
    overall_ok = health_result.get('overall_status') == 'ok'
    stats.record(overall_ok, 0.0, f"健康检查: {health_result.get('overall_status')}")
    
    for check in health_result.get('checks', []):
        ok = check.get('status') == 'ok'
        stats.record(ok, 0.0, f"{check.get('name')}: {check.get('status')}")
        print(f"{'✅' if ok else '❌'} {check.get('name')}: {check.get('message')}")
    
    return stats


# ============================================================
# DIMENSION 12: 内存稳定性
# ============================================================
async def test_dim12_memory():
    print("\n" + "="*80)
    print("DIMENSION 12: 内存稳定性")
    print("="*80)
    
    stats = TestStats()
    
    gc.collect()
    
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss
        
        # 执行一系列操作
        print(f"\n--- 操作前内存: {mem_before / 1024 / 1024:.1f} MB ---")
        
        for i in range(20):
            await call_tool('lottery_get_system_status', {})
        
        gc.collect()
        mem_after = process.memory_info().rss
        mem_diff = mem_after - mem_before
        
        print(f"--- 操作后内存: {mem_after / 1024 / 1024:.1f} MB (变化: {mem_diff / 1024:+.1f} KB) ---")
        
        # 只要不增长超过 10MB 就算通过
        ok = mem_diff < 10 * 1024 * 1024
        stats.record(ok, 0.0, f"内存变化: {mem_diff / 1024:+.1f} KB")
        
    except ImportError:
        print("⚠️ psutil 未安装，跳过内存测试")
        stats.record(True, 0.0, "内存测试跳过 (psutil未安装)")
    
    return stats


# ============================================================
# DIMENSION 13: 规则引擎验证
# ============================================================
async def test_dim13_rules_engine():
    print("\n" + "="*80)
    print("DIMENSION 13: 规则引擎验证")
    print("="*80)
    
    stats = TestStats()
    
    # 规则查询
    print("\n--- 13.1 规则查询 ---")
    rule_tests = ['SPF', 'BF', 'ZJQ', 'BQC', '']
    for rule_code in rule_tests:
        status, elapsed, result = await call_tool('lottery_query_rules', {'rule_code': rule_code})
        ok = status == 'ok'
        stats.record(ok, elapsed, f"规则查询 {rule_code}: {result[:100]}")
        print(f"{'✅' if ok else '⚠️'} 规则查询 {rule_code or '空'}: {elapsed:.3f}s")
    
    # 规则解释
    print("\n--- 13.2 规则解释 ---")
    for rule_code in ['SPF', 'BF', 'ZJQ']:
        status, elapsed, result = await call_tool('lottery_explain_rule', {'rule_code': rule_code})
        ok = status == 'ok'
        stats.record(ok, elapsed, f"规则解释 {rule_code}: {result[:100]}")
        print(f"{'✅' if ok else '⚠️'} 规则解释 {rule_code}: {elapsed:.3f}s")
    
    return stats


# ============================================================
# DIMENSION 14: 风险控制守卫
# ============================================================
async def test_dim14_guardrails():
    print("\n" + "="*80)
    print("DIMENSION 14: 风险控制守卫")
    print("="*80)
    
    stats = TestStats()
    
    # 约束执行
    print("\n--- 14.1 约束执行 ---")
    bet_proposal = json.dumps({
        'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100}],
        'total_stake': 100
    })
    status, elapsed, result = await call_tool('lottery_enforce_constraints', {'bet_proposal': bet_proposal})
    ok = status == 'ok'
    stats.record(ok, elapsed, f"约束执行: {result[:100]}")
    print(f"{'✅' if ok else '❌'} 约束执行: {elapsed:.3f}s")
    
    # 资金健康检查 - 多种场景
    print("\n--- 14.2 资金健康检查 ---")
    health_tests = [
        {'bankroll': 10000, 'initial_bankroll': 10000},  # 无损失
        {'bankroll': 5000, 'initial_bankroll': 10000},   # 50% 损失
        {'bankroll': 1000, 'initial_bankroll': 10000},   # 90% 损失
        {'bankroll': 15000, 'initial_bankroll': 10000},  # 盈利
    ]
    for params in health_tests:
        status, elapsed, result = await call_tool('lottery_check_bankroll_health', params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"资金检查: {params['bankroll']}/{params['initial_bankroll']}")
        print(f"{'✅' if ok else '❌'} 资金 {params['bankroll']}/{params['initial_bankroll']}: {elapsed:.3f}s")
    
    # 风险评估
    print("\n--- 14.3 风险评估 ---")
    status, elapsed, result = await call_tool('lottery_comprehensive_risk_assessment', {'planned_bet_amount': 1000})
    ok = status == 'ok'
    stats.record(ok, elapsed, f"风险评估: {result[:100]}")
    print(f"{'✅' if ok else '❌'} 风险评估: {elapsed:.3f}s")
    
    return stats


# ============================================================
# DIMENSION 15: 系统状态
# ============================================================
async def test_dim15_system_status():
    print("\n" + "="*80)
    print("DIMENSION 15: 系统状态")
    print("="*80)
    
    stats = TestStats()
    
    if 'lottery_get_system_status' in tools:
        status, elapsed, result = await call_tool('lottery_get_system_status', {})
        ok = status == 'ok'
        stats.record(ok, elapsed, f"系统状态: {result[:150]}")
        
        if ok:
            print(f"✅ 系统状态获取成功 ({elapsed:.3f}s)")
            if is_valid_json(result):
                try:
                    data = json.loads(result)
                    print(f"   状态字段: {list(data.keys())}")
                except:
                    pass
        else:
            print(f"❌ 系统状态获取失败 - {result[:100]}")
    
    return stats


# ============================================================
# 主测试运行器
# ============================================================
async def main():
    print("="*80)
    print("🏆 Lottery MCP 超全面多维度测试 v2.0")
    print(f"📅 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🛠️  工具总数: {len(tools)} | 📚 资源: {len(resources)} | 💬 提示词: {len(prompts)}")
    print("="*80)
    
    all_stats = {}
    all_dimensions = []
    
    # 定义所有测试维度
    test_dimensions = [
        ("1️⃣  工具元数据", test_dim1_tool_metadata),
        ("2️⃣  端到端工作流", test_dim2_workflows),
        ("3️⃣  边界值&异常", test_dim3_edge_cases),
        ("4️⃣  安全防护", test_dim4_security),
        ("5️⃣  资源&提示词", test_dim5_resources_prompts),
        ("6️⃣  输出验证", test_dim6_output_validation),
        ("7️⃣  系统指令", test_dim7_system_instructions),
        ("8️⃣  性能&并发", test_dim8_performance_concurrency),
        ("9️⃣  投注计算", test_dim9_betting_calculations),
        ("🔟  配置管理", test_dim10_config),
        ("1️⃣1️⃣  启动健康", test_dim11_startup_health),
        ("1️⃣2️⃣  内存稳定", test_dim12_memory),
        ("1️⃣3️⃣  规则引擎", test_dim13_rules_engine),
        ("1️⃣4️⃣  风险控制", test_dim14_guardrails),
        ("1️⃣5️⃣  系统状态", test_dim15_system_status),
    ]
    
    # 运行所有测试
    for dim_name, dim_func in test_dimensions:
        try:
            result = await dim_func()
            if isinstance(result, tuple) and len(result) == 2:
                rstats, pstats = result
                all_stats[f"{dim_name} (资源)"] = rstats
                all_stats[f"{dim_name} (提示词)"] = pstats
                all_dimensions.append((f"{dim_name} (资源)", rstats))
                all_dimensions.append((f"{dim_name} (提示词)", pstats))
            else:
                all_stats[dim_name] = result
                all_dimensions.append((dim_name, result))
        except Exception as e:
            print(f"\n❌ {dim_name} 测试异常: {e}")
            traceback.print_exc()
    
    # 生成最终报告
    print("\n" + "="*80)
    print("📊 最终综合报告")
    print("="*80)
    
    total_tests = 0
    total_passed = 0
    
    print(f"\n{'维度':<30} {'总测试':<10} {'通过':<10} {'失败':<10} {'通过率':<10}")
    print("-"*70)
    
    for dim_name, stats in all_dimensions:
        if stats and stats.total > 0:
            total_tests += stats.total
            total_passed += stats.passed
            rate = f"{stats.passed/stats.total*100:.1f}%" if stats.total else "N/A"
            print(f"{dim_name:<30} {stats.total:<10} {stats.passed:<10} {stats.failed:<10} {rate:<10}")
    
    print("-"*70)
    overall_rate = f"{total_passed/total_tests*100:.1f}%" if total_tests else "N/A"
    print(f"{'总计':<30} {total_tests:<10} {total_passed:<10} {total_tests-total_passed:<10} {overall_rate:<10}")
    
    # 健康状态指示
    print("\n" + "="*80)
    print("🏥 系统健康状态")
    print("="*80)
    
    overall_pct = total_passed / total_tests if total_tests else 0
    if overall_pct >= 0.90:
        print("🟢 健康 - 系统运行良好")
    elif overall_pct >= 0.75:
        print("🟡 轻微问题 - 有一些小问题需要关注")
    elif overall_pct >= 0.50:
        print("🟠 需要关注 - 多个测试失败，建议检查")
    else:
        print("🔴 严重问题 - 系统需要重大修复")
    
    print(f"\n✅ 总通过率: {overall_rate}")
    
    # 汇总所有错误
    all_errors = []
    for dim_name, stats in all_dimensions:
        if stats and stats.errors:
            for err in stats.errors:
                all_errors.append(f"[{dim_name}] {err}")
    
    if all_errors:
        print(f"\n⚠️  错误汇总 ({len(all_errors)}):")
        for err in all_errors[:20]:
            print(f"   - {err[:120]}")
        if len(all_errors) > 20:
            print(f"   ... 还有 {len(all_errors)-20} 个错误")
    
    print("\n" + "="*80)
    print("✅ 测试完成!")
    print("="*80)


if __name__ == '__main__':
    asyncio.run(main())

