# 竞彩足球MCP可进化路径深度审评报告

## 一、已完成工作回顾

### 1.1 核心升级成果

| 升级项 | 文件位置 | 核心价值 | 实证依据 |
|--------|---------|---------|---------|
| **独立返还率体系** | `constants.py` | 跨玩法概率计算正确性 | 15场比赛数据验证 |
| **BF↔ZJQ校准器** | `bf_zjq_calibrator.py` | 最强约束（偏差1.0%） | 8场比赛100%验证 |
| **SPF↔BQC校准器** | `spf_bqc_calibrator.py` | 次强约束（偏差1.1%） | 8场比赛100%验证 |
| **矛盾检测器** | `cross_play_validator.py` | 异常信号识别 | 正常市场0矛盾 |
| **杠杆效应分析器** | `leverage_analyzer.py` | BF范围压缩至10% | 31→3个候选 |

### 1.2 实证返还率体系（核心突破）

```python
EMPIRICAL_RETURN_RATES = {
    "SPF": 0.886,      # 3选项层
    "RQSPF": 0.886,    # 3选项层
    "ZJQ": 0.797,      # 8选项层
    "BQC": 0.797,      # 9选项层
    "BF": 0.710,       # 31选项层
}
```

---

## 二、6种玩法进阶路径

### 2.1 SPF（胜平负）进阶路径

| 优先级 | 进阶方向 | 当前状态 | 预期收益 |
|--------|---------|---------|---------|
| **P0** | 主客场差异建模 | 未实现 | +5-10%准确率 |
| **P1** | 时间衰减权重 | 未实现 | 适应球队状态变化 |
| **P1** | 对手强度调整 | 未实现 | 强弱对决精度提升 |
| **P2** | 赔率变化追踪 | 未实现 | 捕获市场信息 |

**P0实施方案**：
```python
HOME_ADVANTAGE = {"英超": 0.35, "西甲": 0.38, "德甲": 0.32, "意甲": 0.30, "法甲": 0.28}

def adjust_for_home_advantage(base_prob, league, is_home):
    if is_home:
        return base_prob * (1 + HOME_ADVANTAGE.get(league, 0.30))
    return base_prob * (1 - HOME_ADVANTAGE.get(league, 0.30))
```

---

### 2.2 RQSPF（让球胜平负）进阶路径

| 优先级 | 进阶方向 | 当前状态 | 预期收益 |
|--------|---------|---------|---------|
| **P0** | 亚盘深度对标 | 基础实现 | 发现价值投注 |
| **P1** | 让球合理性深度评估 | 基础实现 | 识别异常盘口 |
| **P2** | 让球变化追踪 | 未实现 | 捕获盘口变化信号 |

---

### 2.3 BF（比分）进阶路径

| 优先级 | 进阶方向 | 当前状态 | 预期收益 |
|--------|---------|---------|---------|
| **P0** | 杠杆效应路径集成 | 已实现分析器 | 31→3候选压缩 |
| **P1** | 比分概率矩阵可视化 | 未实现 | 用户决策支持 |
| **P1** | 特殊比分检测 | 未实现 | 发现高赔价值 |
| **P2** | 时间相关比分 | 未实现 | 提升精度 |

---

### 2.4 ZJQ（总进球）进阶路径

| 优先级 | 进阶方向 | 当前状态 | 预期收益 |
|--------|---------|---------|---------|
| **P0** | BF聚合校验集成 | 已有校准器 | 强约束校验 |
| **P1** | 进球时间分布 | 未实现 | 提升精度 |
| **P1** | 大小球深度对标 | 基础实现 | 发现价值 |

---

### 2.5 BQC（半全场）进阶路径

| 优先级 | 进阶方向 | 当前状态 | 预期收益 |
|--------|---------|---------|---------|
| **P0** | 半场独立建模 | 未实现 | 提升半场精度 |
| **P1** | 逆转概率评估 | 未实现 | 识别逆转价值 |
| **P2** | 时间节点分析 | 未实现 | 提升精度 |

---

### 2.6 混合过关进阶路径

| 优先级 | 进阶方向 | 当前状态 | 预期收益 |
|--------|---------|---------|---------|
| **P0** | 跨玩法杠杆增强 | 未实现 | +10%组合EV |
| **P1** | 最优组合搜索 | 未实现 | 个性化推荐 |
| **P1** | 容错方案优化 | 未实现 | 风险收益平衡 |

---

## 三、可进化架构设计

### 3.1 模块化设计

```
lottery_mcp/analysis/
├── plays/                      # 玩法插件（已有）
├── calibration/                # 校准模块（已实现）
├── enhancement/                # 进阶模块（新增）
│   ├── home_advantage.py       # 主客场差异建模
│   ├── time_decay.py           # 时间衰减权重
│   ├── opponent_strength.py    # 对手强度调整
│   ├── odds_tracker.py         # 赔率变化追踪
│   ├── asian_handicap.py       # 亚盘对标
│   ├── special_score.py        # 特殊比分检测
│   └── half_time_model.py      # 半场独立建模
└── constants.py                # 统一常量
```

### 3.2 插件机制

```python
class EnhancementModuleBase:
    @property
    def name(self) -> str: pass
    
    @property
    def target_plays(self) -> List[PlayType]: pass
    
    def enhance(self, play_result, match_context) -> PlayAnalysisResult: pass

class EnhancementRegistry:
    _modules: Dict[str, EnhancementModuleBase] = {}
    
    @classmethod
    def register(cls, module: EnhancementModuleBase):
        cls._modules[module.name] = module
    
    @classmethod
    def get_enhancements(cls, play_type: PlayType) -> List[EnhancementModuleBase]:
        return [m for m in cls._modules.values() if play_type in m.target_plays]
```

### 3.3 配置化阈值

```python
ENHANCEMENT_CONFIG = {
    "home_advantage": {"enabled": True, "leagues": {"英超": 0.35, "西甲": 0.38}},
    "time_decay": {"enabled": True, "decay_rate": 0.05, "lookback_matches": 10},
    "opponent_strength": {"enabled": True, "elo_k_factor": 20},
    "odds_tracker": {"enabled": False, "track_interval": 3600},
}
```

---

## 四、实施路线图

### 第一阶段（P0，2周）

| 任务 | 目标玩法 | 预期收益 |
|------|---------|---------|
| 主客场差异建模 | SPF | +5-10%准确率 |
| 杠杆效应路径集成 | BF | 31→3候选 |
| BF聚合校验集成 | ZJQ | 强约束校验 |
| 跨玩法杠杆增强 | 混合过关 | +10%组合EV |

### 第二阶段（P1，4周）

| 任务 | 目标玩法 | 预期收益 |
|------|---------|---------|
| 亚盘深度对标 | RQSPF | 发现价值 |
| 时间衰减权重 | SPF | 适应状态变化 |
| 半场独立建模 | BQC | 提升半场精度 |
| 最优组合搜索 | 混合过关 | 个性化推荐 |

### 第三阶段（P2，3周）

| 任务 | 目标玩法 | 预期收益 |
|------|---------|---------|
| 赔率变化追踪 | SPF | 捕获市场信息 |
| 特殊比分检测 | BF | 高赔价值 |
| 进球时间分布 | ZJQ | 提升精度 |

---

## 五、核心发现总结

### 5.1 已完善

1. **校准体系**：BF↔ZJQ（1.0%偏差）、SPF↔BQC（1.1%偏差）已验证
2. **杠杆效应**：分析器可将BF的31种比分压缩至2-3种候选
3. **返还率体系**：5种玩法的独立实证返还率已确定

### 5.2 主要缺口

1. **SPF**：缺少主客场差异、时间衰减、对手强度建模
2. **RQSPF**：亚盘对标深度不足
3. **BF**：杠杆效应未完全集成到主流程
4. **ZJQ**：BF聚合校验未完全集成
5. **BQC**：半场独立建模缺失
6. **混合过关**：跨玩法杠杆增强、最优组合搜索未实现

### 5.3 架构建议

采用**模块化+插件机制+配置化+学习机制**的四层架构：
- **模块化**：每种进阶能力作为独立模块
- **插件机制**：动态加载进阶模块
- **配置化**：用户可自定义各进阶参数
- **学习机制**：从历史数据中学习最优参数

---

**报告生成时间**：2026-05-30  
**覆盖玩法**：SPF、RQSPF、BF、ZJQ、BQC、混合过关  
**P0任务数量**：4个  
**P1任务数量**：4个  
**P2任务数量**：3个
