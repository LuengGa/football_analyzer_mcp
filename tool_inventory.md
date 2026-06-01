# MCP工具清单 - 第一轮压力测试

## 工具分类总览

### 1. 数据获取类 (Data Tools) - 11个工具
| 工具名 | 功能 |
|--------|------|
| `lottery_fetch_today_matches` | 获取今日可投注比赛列表 |
| `lottery_get_match_data` | 获取比赛详细数据 |
| `lottery_track_odds_changes` | 获取竞彩赔率变化数据 |
| `lottery_verify_results` | 多源开奖结果验证 |
| `lottery_query_history` | 历史开奖综合查询 |
| `lottery_get_live_scores` | 获取实时比分 |
| `lottery_get_market_odds` | 获取市场赔率数据（统一入口） |
| `lottery_get_live_odds` | 获取实时赔率数据 |
| `lottery_get_match_info` | 获取竞彩比赛头部信息 |
| `lottery_get_match_features` | 获取竞彩比赛特征分析 |
| `lottery_get_jingcai_h2h` | 获取竞彩历史交锋 |
| `lottery_get_match_standings` | 获取竞彩积分榜 |
| `lottery_get_recent_form` | 获取竞彩近期战绩 |
| `lottery_get_future_matches` | 获取竞彩未来赛事 |
| `lottery_get_players` | 获取竞彩射手信息 |

### 2. 分析预测类 (Analysis Tools) - 14个工具
| 工具名 | 功能 |
|--------|------|
| `lottery_analyze_all_matches` | 分析所有比赛 |
| `lottery_analyze_with_pipeline` | 使用统一流水线分析所有比赛 |
| `lottery_analyze_match_plays` | 分析比赛的五大玩法 |
| `lottery_detect_risk_signals` | 检测比赛风险信号 |
| `lottery_compare_model_predictions` | 对比多个统计模型的预测结果 |
| `lottery_analyze_results` | 赛果统计分析 |
| `lottery_find_value_bets` | 发现价值投注 |
| `lottery_analyze_match` | 单场比赛深度分析 |
| `lottery_predict_with_model` | 使用ML模型预测比赛结果 |
| `lottery_get_market_sentiment` | 获取市场情绪分析 |
| `lottery_get_match_context` | 获取比赛完整上下文 |
| `lottery_quantify_injury_impact` | 量化伤停影响 |
| `lottery_assess_risk` | 多维度风险评估 |
| `lottery_simulate_scenarios` | 比赛情景模拟 |
| `lottery_generate_recommendation` | 生成综合投注建议 |
| `lottery_compare_matches` | 多场比赛对比分析 |

### 3. 投注生成类 (Prediction/Betting Tools) - 9个工具
| 工具名 | 功能 |
|--------|------|
| `lottery_generate_prediction_report` | 生成预测报告 |
| `lottery_smart_parlay` | 智能串关推荐 |
| `lottery_recommend_best_play` | 推荐最佳玩法 |
| `lottery_get_full_analysis_report` | 获取完整分析报告 |
| `lottery_analyze_mixed_parlay` | 混合过关分析 |
| `lottery_advanced_play_analysis` | 高级玩法分析 |
| `lottery_historical_analysis` | 历史数据分析 |
| `lottery_advanced_enhancements` | 高级增强功能 |
| `lottery_complete_ml_analysis` | 完整ML分析 |

### 4. 规则验证类 (Rules Tools) - 5个工具
| 工具名 | 功能 |
|--------|------|
| `lottery_validate_bet` | 验证单个投注合法性 |
| `lottery_validate_parlay` | 验证串关投注合法性 |
| `lottery_calculate_bonus` | 计算投注奖金 |
| `lottery_query_rules` | 查询彩票规则详情 |
| `lottery_explain_rule` | 解释彩票规则 |

### 5. 增强工具类 (Enhanced Tools) - 11个工具
| 工具名 | 功能 |
|--------|------|
| `lottery_monitor_odds` | 赔率监控 |
| `lottery_get_odds_history` | 赔率历史 |
| `lottery_save_odds_snapshot` | 保存赔率快照 |
| `lottery_track_bet` | 追踪投注 |
| `lottery_settle_bet` | 结算投注 |
| `lottery_get_bet_statistics` | 投注统计 |
| `lottery_check_risk_status` | 检查风险状态 |
| `lottery_should_stop_betting` | 是否应停止投注 |
| `lottery_list_local_odds_matches` | 列出本地赔率比赛 |
| `lottery_get_local_odds_history` | 获取本地赔率历史 |
| `lottery_analyze_local_odds_trend` | 分析本地赔率趋势 |

### 6. 投注管理类 (Betting Tools) - 4个工具
| 工具名 | 功能 |
|--------|------|
| `lottery_get_daily_recommendations` | 获取每日投注推荐 |
| `lottery_generate_betting_slips` | 生成投注单 |
| `lottery_generate_kelly_slips` | 生成凯利公式投注单 |
| `lottery_get_betting_stats` | 获取投注统计 |

### 7. 系统工具类 (System Tools) - 2个工具
| 工具名 | 功能 |
|--------|------|
| `lottery_get_system_status` | 获取系统运行状态 |
| `lottery_manage_config` | 管理系统配置 |

### 8. 历史数据类 (Historical Tools) - 7个工具
| 工具名 | 功能 |
|--------|------|
| `lottery_get_historical_data_summary` | 获取历史数据总览 |
| `lottery_search_league` | 搜索联赛 |
| `lottery_get_league_matches` | 获取联赛比赛列表 |
| `lottery_get_team_history` | 获取球队历史战绩 |
| `lottery_get_head_to_head` | 获取历史交锋记录 |
| `lottery_search_historical_matches` | 搜索历史比赛 |
| `lottery_get_team_stats` | 获取球队详细统计 |

---

## 总计: 63个MCP工具

### 工具分布
```
数据获取    : 15个  ████████████████
分析预测    : 16个  █████████████████
投注生成    : 9个   █████████
规则验证    : 5个   █████
增强工具    : 11个  ███████████
投注管理    : 4个   ████
系统工具    : 2个   ██
历史数据    : 7个   ███████
─────────────────────────────
总计        : 63个
```
