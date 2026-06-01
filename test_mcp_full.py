"""
Lottery MCP 全流程深度测试脚本
Evaluates: data → analysis → prediction → betting → safety → workflow
"""
import asyncio, json, time, sys
from pydantic import create_model
from typing import Any

class MockContext:
    async def log_info(self, msg): print(f"  [INFO] {msg}")
    async def log_error(self, msg): print(f"  [ERROR] {msg}")
    async def report_progress(self, progress, message=None): pass
    async def read_resource(self, uri): return None

from lottery_mcp.server import create_mcp_server
mcp = create_mcp_server()
tools = mcp._tool_manager._tools

def build_params_model(tool, params_dict):
    """Build proper Pydantic model from tool schema and params dict"""
    if 'params' not in tool.parameters.get('properties', {}):
        return None

    param_ref = tool.parameters['properties']['params'].get('$ref', '')
    model_name = param_ref.split('/')[-1] if param_ref else None

    if not model_name or model_name not in tool.parameters.get('$defs', {}):
        return None

    model_schema = tool.parameters['$defs'][model_name]
    model_props = model_schema.get('properties', {})
    required = model_schema.get('required', [])

    fields = {}
    for key, prop in model_props.items():
        type_map = {'string': str, 'integer': int, 'number': float, 'boolean': bool, 'array': list, 'object': dict}
        py_type = type_map.get(prop.get('type', 'string'), Any)
        default_val = prop.get('default', ...)
        is_required = key in required

        if is_required:
            fields[key] = (py_type, ...)
        elif default_val != ...:
            fields[key] = (py_type, default_val)
        else:
            fields[key] = (py_type, None)

    if not fields:
        return None

    ParamModel = create_model(f'{model_name}Test', **fields)
    filtered = {k: v for k, v in params_dict.items() if k in fields}
    # Fill required with defaults
    for key in required:
        if key not in filtered:
            prop = model_props.get(key, {})
            filtered[key] = prop.get('default', '')
    return ParamModel(**filtered)


async def call_tool(name, params_dict):
    start = time.time()
    try:
        tool = tools[name]
        fn = tool.fn
        ctx = MockContext()
        params_model = build_params_model(tool, params_dict)

        if params_model is not None:
            result = await fn(params=params_model, ctx=ctx)
        elif hasattr(tool, 'context_kwarg') and tool.context_kwarg:
            result = await fn(ctx=ctx)
        else:
            result = await fn()

        elapsed = round(time.time() - start, 3)
        return {'status': 'ok', 'elapsed': elapsed, 'result': str(result)}
    except Exception as e:
        elapsed = round(time.time() - start, 3)
        return {'status': 'error', 'elapsed': elapsed, 'error': str(e)[:500]}


def check_depth(result_str: str) -> dict:
    """Evaluate analysis depth of tool output"""
    scores = {}

    # Data coverage
    if 'match_id' in result_str: scores['match_id'] = 1
    if 'league' in result_str: scores['league'] = 1
    if 'home_team' in result_str: scores['home_team'] = 1
    if 'odds' in result_str.lower(): scores['odds_data'] = 2
    if 'probability' in result_str.lower() or '概率' in result_str: scores['probability'] = 2
    if 'recommend' in result_str.lower() or '推荐' in result_str: scores['recommendation'] = 2
    if 'risk' in result_str.lower() or '风险' in result_str: scores['risk'] = 2
    if 'kelly' in result_str.lower() or '凯利' in result_str: scores['kelly'] = 2
    if 'confidence' in result_str.lower() or '置信' in result_str: scores['confidence'] = 2
    if 'model' in result_str.lower() or '模型' in result_str: scores['model'] = 2
    if len(result_str) > 500: scores['detail'] = 2
    if len(result_str) > 2000: scores['deep_analysis'] = 3

    scores['total'] = sum(scores.values())
    return scores


async def run_tests():
    print('=' * 80)
    print('LOTTERY MCP 深度分析预测全流程测试报告')
    print('=' * 80)
    print()

    # ================================================
    # STEP 1: Fetch today's matches
    # ================================================
    print('━' * 60)
    print('STEP 1: 数据获取 - 获取今日比赛列表')
    print('━' * 60)

    r = await call_tool('lottery_fetch_today_matches', {
        'lottery_type': '竞彩足球', 'limit': 5, 'include_odds': False
    })
    match_ids = []
    if r['status'] == 'ok':
        try:
            data = json.loads(r['result'])
            matches = data.get('data', {}).get('matches', [])
            match_ids = [m['match_id'] for m in matches]
            print(f'  ✓ 获取到 {len(matches)} 场比赛 ({r["elapsed"]}s)')
            for m in matches:
                print(f'    - [{m["match_id"]}] {m.get("league","")} | {m.get("home_team","")} vs {m.get("away_team","")} | {m.get("match_time","")}')
        except:
            print(f'  ✓ 获取成功 ({r["elapsed"]}s) - 无法解析JSON')
            print(f'    原始: {r["result"][:200]}')
    else:
        print(f'  ✗ 获取失败: {r["error"][:200]}')

    if not match_ids:
        print('\n⚠ 未获取到比赛数据，使用模拟ID继续测试...')
        match_ids = ['2025052510001']

    test_id = match_ids[0]
    print(f'\n  使用比赛ID: {test_id} 进行深度测试\n')

    # ================================================
    # STEP 2: Data Layer Deep Test
    # ================================================
    print('━' * 60)
    print('STEP 2: 数据层深度测试 (8维度)')
    print('━' * 60)

    data_tests = [
        ('比赛头部信息', 'lottery_get_match_info', {'match_id': test_id}),
        ('比赛特征分析', 'lottery_get_match_features', {'match_id': test_id, 'limit': 5}),
        ('积分榜数据', 'lottery_get_match_standings', {'match_id': test_id}),
        ('近期战绩', 'lottery_get_recent_form', {'match_id': test_id, 'limit': 5}),
        ('伤停信息', 'lottery_get_injury_suspension', {'match_id': test_id}),
        ('未来赛事', 'lottery_get_future_matches', {'match_id': test_id, 'limit': 3}),
        ('射手信息', 'lottery_get_players', {'match_id': test_id, 'limit': 3}),
        ('历史交锋', 'lottery_get_jingcai_h2h', {'match_id': test_id, 'limit': 5}),
    ]

    for label, tool_name, params in data_tests:
        r = await call_tool(tool_name, params)
        status = '✓' if r['status'] == 'ok' else '✗'
        depth = check_depth(r.get('result', '')) if r['status'] == 'ok' else {}
        depth_str = f' depth={depth.get("total",0)}' if depth else ''
        print(f'  {status} {label}: {r["elapsed"]}s{depth_str}')
        if r['status'] == 'error':
            print(f'      错误: {r["error"][:200]}')
        elif r['status'] == 'ok':
            result_str = r['result']
            if len(result_str) > 200:
                print(f'      结果: {result_str[:200]}...')
            else:
                print(f'      结果: {result_str}')

    # ================================================
    # STEP 3: Analysis Layer
    # ================================================
    print()
    print('━' * 60)
    print('STEP 3: 分析层深度测试 (5维度)')
    print('━' * 60)

    analysis_tests = [
        ('单场深度分析', 'lottery_analyze_match', {'match_id': test_id, 'league': '英超'}),
        ('玩法分析 (5类)', 'lottery_analyze_match_plays', {'match_id': test_id, 'play_types': ['SPF', 'RQSPF', 'BF', 'ZJQ', 'BQC']}),
        ('统一流水线分析', 'lottery_analyze_with_pipeline', {}),
        ('风险信号检测', 'lottery_detect_risk_signals', {'match_id': test_id}),
        ('多模型对比', 'lottery_compare_model_predictions', {'match_id': test_id}),
    ]

    for label, tool_name, params in analysis_tests:
        r = await call_tool(tool_name, params)
        status = '✓' if r['status'] == 'ok' else '✗'
        depth = check_depth(r.get('result', '')) if r['status'] == 'ok' else {}
        depth_str = f' depth={depth.get("total",0)}' if depth else ''
        print(f'  {status} {label}: {r["elapsed"]}s{depth_str}')
        if r['status'] == 'error':
            err = r['error'][:250]
            print(f'      错误: {err}')
        elif r['status'] == 'ok':
            result_str = r['result']
            print(f'      结果: {result_str[:300]}...')

    # ================================================
    # STEP 4: Prediction/Advanced Layer
    # ================================================
    print()
    print('━' * 60)
    print('STEP 4: 预测/高级分析层 (6维度)')
    print('━' * 60)

    pred_tests = [
        ('ML模型预测', 'lottery_predict_with_model', {'match_id': test_id}),
        ('高级玩法分析', 'lottery_advanced_play_analysis', {'match_id': test_id}),
        ('历史数据深度分析', 'lottery_historical_analysis', {'match_id': test_id}),
        ('高级深化功能', 'lottery_advanced_enhancements', {'match_id': test_id}),
        ('完整ML分析', 'lottery_complete_ml_analysis', {}),
        ('策略回测', 'lottery_strategy_backtest', {}),
    ]

    for label, tool_name, params in pred_tests:
        r = await call_tool(tool_name, params)
        status = '✓' if r['status'] == 'ok' else '✗'
        depth = check_depth(r.get('result', '')) if r['status'] == 'ok' else {}
        depth_str = f' depth={depth.get("total",0)}' if depth else ''
        print(f'  {status} {label}: {r["elapsed"]}s{depth_str}')
        if r['status'] == 'error':
            print(f'      错误: {r["error"][:250]}')
        elif r['status'] == 'ok':
            result_str = r['result']
            print(f'      结果: {result_str[:300]}...')

    # ================================================
    # STEP 5: Betting Layer
    # ================================================
    print()
    print('━' * 60)
    print('STEP 5: 投注层测试 (5维度)')
    print('━' * 60)

    betting_tests = [
        ('玩法智能推荐', 'lottery_recommend_best_play', {'match_id': test_id, 'play_types': ['SPF', 'RQSPF', 'BF', 'ZJQ', 'BQC']}),
        ('综合投注建议', 'lottery_generate_recommendation', {}),
        ('专业版预测报告', 'lottery_generate_prediction_report', {}),
        ('智能串关投注', 'lottery_smart_parlay', {}),
        ('混合过关分析', 'lottery_analyze_mixed_parlay', {}),
    ]

    for label, tool_name, params in betting_tests:
        r = await call_tool(tool_name, params)
        status = '✓' if r['status'] == 'ok' else '✗'
        depth = check_depth(r.get('result', '')) if r['status'] == 'ok' else {}
        depth_str = f' depth={depth.get("total",0)}' if depth else ''
        print(f'  {status} {label}: {r["elapsed"]}s{depth_str}')
        if r['status'] == 'error':
            print(f'      错误: {r["error"][:250]}')
        elif r['status'] == 'ok':
            result_str = r['result']
            print(f'      结果: {result_str[:300]}...')

    # ================================================
    # STEP 6: Safety/Guardrails Layer
    # ================================================
    print()
    print('━' * 60)
    print('STEP 6: 安全/风控层测试 (4维度)')
    print('━' * 60)

    # These need special handling
    print('  测试规则查询...')
    r = await call_tool('lottery_query_rules', {'rule_code': 'C001'})
    status = '✓' if r['status'] == 'ok' else '✗'
    print(f'    {status} 规则查询: {r["elapsed"]}s')
    if r['status'] == 'error':
        print(f'      错误: {r["error"][:200]}')

    print('  测试规则解释...')
    r = await call_tool('lottery_explain_rule', {'rule_code': 'SPF'})
    status = '✓' if r['status'] == 'ok' else '✗'
    print(f'    {status} 规则解释: {r["elapsed"]}s')
    if r['status'] == 'error':
        print(f'      错误: {r["error"][:200]}')

    print('  测试风险评估...')
    r = await call_tool('lottery_assess_risk', {'match_id': test_id})
    status = '✓' if r['status'] == 'ok' else '✗'
    print(f'    {status} 风险评估: {r["elapsed"]}s')
    if r['status'] == 'error':
        print(f'      错误: {r["error"][:200]}')

    print('  测试价值投注...')
    r = await call_tool('lottery_find_value_bets', {'match_id': test_id})
    status = '✓' if r['status'] == 'ok' else '✗'
    print(f'    {status} 价值投注: {r["elapsed"]}s')
    if r['status'] == 'error':
        print(f'      错误: {r["error"][:200]}')

    # ================================================
    # STEP 7: Workflow Layer
    # ================================================
    print()
    print('━' * 60)
    print('STEP 7: 工作流测试 (3维度)')
    print('━' * 60)

    workflow_tests = [
        ('完整分析+投注单 (13步)', 'lottery_full_analysis_and_betting', {}),
        ('快速扫描推荐', 'lottery_quick_scan_and_recommend', {}),
        ('全面风险评估', 'lottery_comprehensive_risk_assessment', {}),
    ]

    for label, tool_name, params in workflow_tests:
        r = await call_tool(tool_name, params)
        status = '✓' if r['status'] == 'ok' else '✗'
        depth = check_depth(r.get('result', '')) if r['status'] == 'ok' else {}
        depth_str = f' depth={depth.get("total",0)}' if depth else ''
        print(f'  {status} {label}: {r["elapsed"]}s{depth_str}')
        if r['status'] == 'error':
            print(f'      错误: {r["error"][:250]}')
        elif r['status'] == 'ok':
            result_str = r['result']
            print(f'      结果: {result_str[:400]}...')

    # ================================================
    # SUMMARY
    # ================================================
    print()
    print('=' * 80)
    print('TEST COMPLETE')
    print('=' * 80)

asyncio.run(run_tests())