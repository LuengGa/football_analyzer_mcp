#!/usr/bin/env python3
"""
MCP 工具和模块盘点脚本
用于扫描项目中的所有工具和模块，建立完整清单
"""

import os
import re
from pathlib import Path

WORKSPACE = Path("/workspace")
TOOLS_DIR = WORKSPACE / "lottery_mcp" / "tools"

def extract_tools_from_file(file_path):
    """从文件中提取工具信息"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tools = []
    
    # 匹配 @mcp.tool 装饰器和 name 属性
    pattern = re.compile(
        r'@mcp\.tool\(\s*\n?\s*name="([^"]+)"',
        re.DOTALL
    )
    
    matches = pattern.finditer(content)
    
    for match in matches:
        tool_name = match.group(1)
        
        # 尝试提取描述
        desc_match = re.search(
            r'description="""([^"]+?)"""',
            content[match.end(): match.end() + 5000],
            re.DOTALL
        )
        description = desc_match.group(1).strip() if desc_match else ""
        
        tools.append({
            "name": tool_name,
            "description": description[:200] + "..." if len(description) > 200 else description,
            "file": file_path.name
        })
    
    return tools

def main():
    print("=" * 80)
    print("📋 竞彩足球分析 MCP 工具清单")
    print("=" * 80)
    
    # 工具分类
    categories = {
        "端到端工作流": ["workflows.py"],
        "数据获取": ["data_tools.py"],
        "分析引擎": ["analysis_tools.py"],
        "投注推荐": ["betting_tools.py", "prediction_tools.py"],
        "规则验证": ["rules_tools.py"],
        "风控守卫": ["guardrails_tools.py"],
        "历史回测": ["historical_tools.py"],
        "增强工具": ["enhanced_tools_mcp.py"],
        "系统管理": ["system_tools.py"]
    }
    
    all_tools = []
    total_count = 0
    
    for category, files in categories.items():
        print(f"\n{'=' * 80}")
        print(f"📁 {category}")
        print(f"{'=' * 80}")
        
        cat_tools = []
        for file in files:
            file_path = TOOLS_DIR / file
            if file_path.exists():
                tools = extract_tools_from_file(file_path)
                cat_tools.extend(tools)
        
        all_tools.extend(cat_tools)
        total_count += len(cat_tools)
        
        for i, tool in enumerate(cat_tools, 1):
            print(f"  {i:2d}. {tool['name']}")
            if tool['description']:
                first_line = tool['description'].split('\n')[0]
                print(f"      {first_line[:60]}...")
    
    print(f"\n{'=' * 80}")
    print(f"📊 汇总：共 {total_count} 个工具")
    print(f"{'=' * 80}")
    
    # 检查关键工作流环节
    print(f"\n🔍 关键工作流环节检查")
    print(f"{'=' * 80}")
    
    critical_workflows = [
        ("数据获取", ["lottery_fetch_today_matches", "lottery_get_match_data", "lottery_get_market_odds"]),
        ("分析计算", ["lottery_analyze_with_pipeline", "lottery_analyze_match_plays", "lottery_analyze_with_models"]),
        ("投注推荐", ["lottery_smart_parlay", "lottery_get_full_analysis_report", "lottery_recommend_best_play"]),
        ("规则验证", ["lottery_validate_bet", "lottery_validate_parlay", "lottery_calculate_bonus"]),
        ("风控守卫", ["lottery_validate_scenario", "lottery_rule_guard"]),
        ("追踪记录", ["lottery_track_bet", "lottery_settle_bet", "lottery_get_bet_statistics"]),
    ]
    
    all_tool_names = {t['name'] for t in all_tools}
    
    for wf_name, required_tools in critical_workflows:
        print(f"\n  🎯 {wf_name}")
        missing = []
        found = []
        for tool in required_tools:
            if tool in all_tool_names:
                found.append(f"✅ {tool}")
            else:
                missing.append(f"❌ {tool}")
        
        if found:
            for t in found:
                print(f"    {t}")
        if missing:
            for t in missing:
                print(f"    {t}")
    
    print(f"\n{'=' * 80}")
    return all_tools

if __name__ == "__main__":
    main()
