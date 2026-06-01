# 竞彩足球分析MCP全面升级总结

## 升级概览

基于4轮深度分析的实证结论，完成了系统性升级优化。

---

## 一、核心升级内容

### 1. 独立返还率体系（P0）

**文件**: `lottery_mcp/analysis/constants.py`

**新增内容**:
```python
# 实证返还率（基于2026-05-29竞彩网15场比赛数据）
EMPIRICAL_RETURN_RATES = {
    "SPF": 0.886,      # 3选项层
    "RQSPF": 0.886,    # 3选项层
    "ZJQ": 0.797,      # 8选项层
    "BQC": 0.797,      # 9选项层
    "BF": 0.710,       # 31选项层
}

# 返还率分层
RETURN_RATE_TIERS = {
    "tier_1_3options": ["SPF", "RQSPF"],      # ~88.6%
    "tier_2_8_9options": ["ZJQ", "BQC"],      # ~79.7%
    "tier_3_31options": ["BF"],                # ~71.0%
}
```

**价值**: 跨玩法概率计算必须使用各自独立的返还率，这是概率计算正确性的基石。

---

### 2. BF↔ZJQ双向校准器（P0）

**文件**: `lottery_mcp/analysis/calibration/bf_zjq_calibrator.py`

**核心功能**:
- `bf_to_zjq()`: 从BF比分赔率推导ZJQ总进球概率
- `zjq_to_bf()`: 从ZJQ赔率反推BF比分分布
- `validate()`: 双向校验，检测一致性
- `calibrate()`: 根据一致性调整概率分布

**实证验证**: 平均偏差仅1.0%，是10对玩法中约束最强的一对。

**使用示例**:
```python
from lottery_mcp.analysis.calibration import BFZJQCalibrator

calibrator = BFZJQCalibrator()
result = calibrator.validate(bf_odds, zjq_odds)
# result['is_consistent'] = True/False
# result['avg_deviation'] = 平均偏差
```

---

### 3. SPF↔BQC聚合校准器（P0）

**文件**: `lottery_mcp/analysis/calibration/spf_bqc_calibrator.py`

**核心功能**:
- `bqc_to_spf()`: 从BQC半全场赔率聚合推导SPF胜平负概率
- `spf_to_bqc_constraint()`: SPF约束BQC全场方向
- `validate()`: 双向校验
- `analyze_half_time_trends()`: 分析半场趋势

**实证验证**: 平均偏差仅1.1%，是10对玩法中约束第二强的一对。

---

### 4. 跨玩法赔率矛盾检测器（P0）

**文件**: `lottery_mcp/analysis/calibration/cross_play_validator.py`

**检测维度**:
1. 返还率一致性（同层玩法）
2. BF↔ZJQ数学约束
3. SPF↔BQC聚合约束
4. 对称比分赔率差异
5. 多玩法综合矛盾

**矛盾等级**:
- `normal`: 正常市场，未发现矛盾
- `low`: 轻度矛盾，可能存在价值机会
- `medium`: 中度矛盾，建议重点关注
- `high`: 高度矛盾，强烈建议深入分析

**使用示例**:
```python
from lottery_mcp.analysis.calibration import CrossPlayValidator

validator = CrossPlayValidator()
result = validator.validate_all(all_odds, spf_direction="home")
report = validator.generate_report(result)
```

---

### 5. 杠杆效应分析器（P1）

**文件**: `lottery_mcp/analysis/calibration/leverage_analyzer.py`

**杠杆路径**:
```
SPF(锁定方向) → 排除BF一半比分
    +
RQSPF(锁定让球) → 进一步缩小BF范围
    +
ZJQ(锁定进球数) → 最终锁定2-3个候选比分
```

**核心功能**:
- `spf_constraint()`: SPF方向约束BF
- `rqspf_constraint()`: 让球数约束BF
- `zjq_constraint()`: 进球数约束BF
- `combined_leverage()`: 多玩法叠加约束

**使用示例**:
```python
from lottery_mcp.analysis.calibration import LeverageAnalyzer

analyzer = LeverageAnalyzer()
result = analyzer.combined_leverage(
    spf_result={"best": "胜"},
    rqspf_result={"handicap": -1, "best": "负"},
    zjq_result={"best": "2"},
    bf_odds=bf_odds,
)
# result['compression_ratio'] = 压缩比例
# result['final_candidates'] = 最终候选比分
```

---

## 二、测试验证

**测试文件**: `/data/user/work/test_calibration.py`

**测试结果**:
```
✅ BF↔ZJQ校准器: 通过
✅ SPF↔BQC校准器: 通过
✅ 跨玩法矛盾检测: 通过
✅ 杠杆效应分析: 通过

🎉 所有测试通过！
```

**测试覆盖**:
- BF→ZJQ推导验证
- SPF↔BQC聚合验证
- 跨玩法矛盾检测
- 杠杆效应压缩比例验证

---

## 三、文件结构

```
lottery_mcp/analysis/
├── constants.py                          # 新增：独立返还率体系
├── calibration/
│   ├── __init__.py                       # 新增：模块导出
│   ├── bf_zjq_calibrator.py              # 新增：BF↔ZJQ校准器
│   ├── spf_bqc_calibrator.py             # 新增：SPF↔BQC校准器
│   ├── cross_play_validator.py           # 新增：跨玩法矛盾检测器
│   └── leverage_analyzer.py              # 新增：杠杆效应分析器
```

---

## 四、关键阈值配置

```python
# BF↔ZJQ双向校准阈值（最强约束，平均偏差1.0%）
BF_ZJQ_CALIBRATION_THRESHOLD = 0.03  # 3%

# SPF↔BQC聚合校准阈值（次强约束，平均偏差1.1%）
SPF_BQC_CALIBRATION_THRESHOLD = 0.025  # 2.5%

# 跨玩法赔率矛盾检测阈值
CROSS_PLAY_CONTRADICTION_THRESHOLD = 0.10  # 10%

# 对称比分赔率差异阈值
SYMMETRIC_SCORE_ODDS_DIFF_THRESHOLD = 1.0  # 赔率差值

# 同层玩法返还率差异阈值
RETURN_RATE_CONSISTENCY_THRESHOLD = 0.01  # 1%
```

---

## 五、后续集成建议

### 1. 集成到现有分析流程

在 `analysis_tools_mcp.py` 的 `analyze_match` 工具中，添加跨玩法校验步骤：

```python
from lottery_mcp.analysis.calibration import CrossPlayValidator

# 在分析完成后进行校验
validator = CrossPlayValidator()
validation = validator.validate_all(all_odds, spf_direction=spf_best)
result["cross_play_validation"] = validation
```

### 2. 集成到BF预测

在 `bf_plugin.py` 中，使用杠杆效应分析器缩小候选范围：

```python
from lottery_mcp.analysis.calibration import LeverageAnalyzer

analyzer = LeverageAnalyzer()
leverage = analyzer.combined_leverage(
    spf_result=spf_result,
    rqspf_result=rqspf_result,
    zjq_result=zjq_result,
    bf_odds=bf_odds,
)
# 使用leverage['final_candidates']作为候选
```

### 3. 新增专门工具

可以新增 `validate_cross_play` 工具，专门用于检测跨玩法矛盾：

```python
@mcp.tool()
async def validate_cross_play(
    match_id: str,
    ctx: Context,
) -> CrossPlayValidationOutput:
    """检测比赛的跨玩法赔率一致性"""
    ...
```

---

## 六、升级价值总结

| 升级项 | 核心价值 | 实证依据 |
|--------|---------|---------|
| 独立返还率体系 | 概率计算正确性 | 15场比赛数据验证 |
| BF↔ZJQ校准器 | 最强约束（偏差1.0%） | 8场比赛100%验证 |
| SPF↔BQC校准器 | 次强约束（偏差1.1%） | 8场比赛100%验证 |
| 矛盾检测器 | 异常信号识别 | 正常市场0矛盾 |
| 杠杆效应分析器 | BF范围压缩至10% | 31→3个候选 |

---

## 七、下一步建议

1. **集成到现有工具**: 将校准器集成到 `enhanced_tools_mcp.py` 的分析流程中
2. **新增专用工具**: 创建 `validate_cross_play` 和 `analyze_leverage` 专用工具
3. **前端展示**: 在分析结果中展示跨玩法校验状态和杠杆效应推荐
4. **持续监控**: 收集实际使用中的校准偏差数据，持续优化阈值

---

**升级完成时间**: 2026-05-29  
**基于数据**: 竞彩网15场比赛实证分析  
**测试状态**: 全部通过 ✅
