# Lottery MCP - 竞彩足球 MCP 服务包

基于中国体育彩票（竞彩足球/北京单场/传统足彩）官方规则，提供投注验证、风控规则、数据分析、投注建议等服务。

## 安装

```bash
# 从源码安装
pip install -e .

# 或使用 uv
uv pip install -e .
```

## 使用方法

### 作为 MCP 服务器运行

```bash
# 方式1: 使用入口命令
lottery-mcp

# 方式2: 使用模块方式
python -m lottery_mcp

# 方式3: 查看版本
python -m lottery_mcp --version

# 方式4: 健康检查
python -m lottery_mcp --health-check
```

### 编程方式使用

```python
# 创建服务器实例
from lottery_mcp import create_server
server = create_server()
server.run()

# 或直接运行
from lottery_mcp import run_server
run_server()
```

## 项目结构

```
lottery_mcp/
├── __init__.py          # 主包入口
├── __main__.py          # 命令行入口
├── server.py            # MCP 服务器核心
├── py.typed             # PEP 561 类型标记
│
├── data/                # 数据获取模块
│   ├── fetcher.py       # 竞彩/北单/传统足彩数据获取
│   ├── sources.py       # 多源聚合数据（国际API + 国内网站）
│   └── team_mapping.py  # 球队名称映射
│
├── analysis/            # 分析引擎模块
│   ├── engine.py        # 分析引擎核心
│   ├── models.py        # 统计模型（泊松/Elo/xG）
│   ├── strategy.py      # 比赛策略分析
│   └── play_analysis.py # 五大玩法分析
│
├── betting/             # 投注推荐模块
│   ├── engine.py        # 投注引擎核心
│   ├── value.py         # 价值发现引擎
│   └── ai.py            # AI 分析器
│
├── rules/               # 规则引擎模块
│   ├── engine.py        # 规则验证核心
│   └── guardrails.py    # 风控守卫
│
├── tools/               # MCP 工具注册
│   ├── data_tools.py    # 数据获取工具
│   ├── analysis_tools.py # 分析引擎工具
│   ├── betting_tools.py # 投注推荐工具
│   ├── rules_tools.py   # 规则验证工具
│   ├── guardrails_tools.py # 风控守卫工具
│   ├── system_tools.py  # 系统管理工具
│   ├── helpers.py       # 共享工具函数
│   ├── resources.py     # MCP 资源
│   └── prompts.py       # MCP 提示词
│
├── models/              # Pydantic 模型
│   └── schemas.py       # 输入输出模型定义
│
└── knowledge/           # 知识库
    └── jingcai/         # 竞彩规则知识库
        └── play_types/  # 玩法规则
```

## 核心功能

### 1. 规则验证 (P0)

```python
from lottery_mcp.rules import validate_bet, validate_parlay, calculate_bonus

# 验证单注
result = validate_bet(
    match_id="20240115_001",
    play_type="SPF",
    selection="主胜",
    odds=2.15,
    stake=100,
    lottery_type="竞彩足球"
)

# 验证串关
result = validate_parlay(
    bets=[...],
    parlay_type="2x1",
    total_stake=100,
    lottery_type="竞彩足球"
)

# 计算奖金
bonus = calculate_bonus(bets=[...], parlay_type="2x1")
```

### 2. 数据获取 (P1)

```python
from lottery_mcp.data import fetch_today_matches, FreeDataSourceManager

# 获取今日比赛
matches = fetch_today_matches("jingcai")  # 或 "beidan", "ctzc"

# 多源数据管理器
manager = FreeDataSourceManager()
standings = manager.get_standings("英超")
```

### 3. 分析引擎 (P1)

```python
from lottery_mcp.analysis import StatisticalEngine, PoissonModel

# 统计分析
engine = StatisticalEngine()
result = engine.analyze(match_data)

# 泊松模型
poisson = PoissonModel()
prediction = poisson.predict(home_odds=2.0, draw_odds=3.3, away_odds=3.5)
```

### 4. 投注推荐 (P2)

```python
from lottery_mcp.betting import get_daily_recommendations, generate_betting_slips

# 获取每日推荐
recommendations = get_daily_recommendations(count=5, strategy="balanced")

# 生成投注单
slips = generate_betting_slips(
    match_ids=["m1", "m2"],
    strategy="single",
    bankroll=1000
)
```

## 工具分类

| 类别 | 工具前缀 | 说明 |
|------|----------|------|
| 规则验证 | `lottery_validate_*` | 投注规则验证 |
| 强制规则 | `lottery_*_guard` / `lottery_reject` | 风控规则执行 |
| 数据获取 | `lottery_fetch_*` / `lottery_get_*` | 比赛数据获取 |
| 分析引擎 | `lottery_analyze_*` / `lottery_detect_*` | 数据分析 |
| 投注建议 | `lottery_generate_*` / `lottery_get_daily_*` | 投注建议生成 |
| 系统管理 | `lottery_*_system_*` / `lottery_health_*` | 系统状态管理 |

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/

# 类型检查
mypy lottery_mcp/

# 代码格式化
black lottery_mcp/
ruff check lottery_mcp/
```

## 许可证

MIT License
