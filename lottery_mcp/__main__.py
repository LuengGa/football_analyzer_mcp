#!/usr/bin/env python3
"""
Lottery MCP - 命令行入口

使用方法:
    python -m lottery_mcp
    python -m lottery_mcp --help
    python -m lottery_mcp --version
"""

import sys


def main():
    """主入口函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        prog="lottery_mcp",
        description="竞彩足球 MCP 服务器 - 彩票规则验证与风控助手",
    )
    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="显示版本信息"
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="执行启动健康检查"
    )
    
    args = parser.parse_args()
    
    if args.version:
        from . import __version__
        print(f"lottery_mcp version {__version__}")
        return 0
    
    if args.health_check:
        from .server import startup_health_check
        result = startup_health_check()
        print(f"健康检查状态: {result['overall_status']}")
        for check in result["checks"]:
            status = "OK" if check["status"] == "ok" else "FAIL"
            print(f"  [{status}] {check['name']}: {check['message']}")
        return 0 if result["overall_status"] == "ok" else 1
    
    # 默认启动 MCP 服务器
    from .server import run_mcp_server
    run_mcp_server()
    return 0


if __name__ == "__main__":
    sys.exit(main())
