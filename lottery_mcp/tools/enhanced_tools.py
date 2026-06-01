"""
Lottery MCP 增强工具模块

提供高优先级的增强功能：
- 实时赔率监控
- 历史回测
- 投注记录追踪
- 智能止损提醒
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger("lottery_mcp")

# 数据存储路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.environ.get("LOTTERY_DATA_DIR", str(_PROJECT_ROOT / ".cache" / "lottery_data")))
BETS_DIR = DATA_DIR / "bets"
ODDS_DIR = DATA_DIR / "odds_history"

# 确保目录存在
BETS_DIR.mkdir(parents=True, exist_ok=True)
ODDS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 高优先级工具1：实时赔率监控
# ============================================================

class OddsMonitor:
    """赔率监控器"""
    
    def __init__(self):
        self.alert_thresholds = {
            "odds_drop": 0.05,      # 赔率下降5%预警
            "odds_rise": 0.05,      # 赔率上升5%预警
            "value_window": 0.10,   # 价值窗口10%
        }
    
    def monitor_odds_changes(
        self,
        match_id: str,
        play_type: str,
        current_odds: Dict[str, float],
        previous_odds: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """监控赔率变化
        
        Args:
            match_id: 比赛ID
            play_type: 玩法类型
            current_odds: 当前赔率 {"win": 2.10, "draw": 3.20, "lose": 3.50}
            previous_odds: 之前赔率（可选，用于对比）
            
        Returns:
            赔率变化分析结果
        """
        alerts = []
        changes = {}
        
        if previous_odds:
            for option, curr_odds in current_odds.items():
                prev_odds = previous_odds.get(option)
                if prev_odds and prev_odds > 0:
                    change_pct = (curr_odds - prev_odds) / prev_odds
                    
                    changes[option] = {
                        "previous": prev_odds,
                        "current": curr_odds,
                        "change_pct": round(change_pct * 100, 2),
                        "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "stable",
                    }
                    
                    # 检查预警条件
                    if change_pct <= -self.alert_thresholds["odds_drop"]:
                        alerts.append({
                            "type": "ODDS_DROP",
                            "severity": "WARNING",
                            "option": option,
                            "message": f"{option}赔率下降{abs(change_pct)*100:.1f}%，可能受市场热钱影响",
                            "previous": prev_odds,
                            "current": curr_odds,
                        })
                    elif change_pct >= self.alert_thresholds["odds_rise"]:
                        alerts.append({
                            "type": "ODDS_RISE",
                            "severity": "INFO",
                            "option": option,
                            "message": f"{option}赔率上升{change_pct*100:.1f}%，可能出现价值窗口",
                            "previous": prev_odds,
                            "current": curr_odds,
                        })
        
        # 计算隐含概率
        total_implied = sum(1/o for o in current_odds.values() if o > 0)
        implied_probs = {
            opt: round((1/o) / total_implied * 100, 2) if o > 0 else 0
            for opt, o in current_odds.items()
        }
        
        # 检测价值窗口
        value_windows = self._detect_value_windows(current_odds, implied_probs)
        if value_windows:
            alerts.extend(value_windows)
        
        return {
            "match_id": match_id,
            "play_type": play_type,
            "timestamp": datetime.now().isoformat(),
            "current_odds": current_odds,
            "changes": changes if changes else None,
            "implied_probabilities": implied_probs,
            "alerts": alerts if alerts else None,
            "summary": self._generate_summary(alerts, changes),
        }
    
    def _detect_value_windows(
        self,
        odds: Dict[str, float],
        implied_probs: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """检测价值窗口"""
        alerts = []
        
        # 简单的价值检测：高赔率选项可能有价值
        for option, prob in implied_probs.items():
            opt_odds = odds.get(option, 0)
            if opt_odds > 3.0 and prob < 25:  # 高赔率但有一定概率
                expected_value = prob * opt_odds / 100
                if expected_value > 0.8:  # 期望值接近1
                    alerts.append({
                        "type": "VALUE_WINDOW",
                        "severity": "INFO",
                        "option": option,
                        "message": f"{option}可能出现价值窗口：概率{prob}%，赔率{opt_odds}，期望值{expected_value:.2f}",
                        "probability": prob,
                        "odds": opt_odds,
                        "expected_value": round(expected_value, 3),
                    })
        
        return alerts
    
    def _generate_summary(
        self,
        alerts: List[Dict],
        changes: Dict,
    ) -> str:
        """生成摘要"""
        if not alerts and not changes:
            return "赔率稳定，无明显变化"
        
        parts = []
        if alerts:
            alert_count = len(alerts)
            warning_count = sum(1 for a in alerts if a.get("severity") == "WARNING")
            parts.append(f"{alert_count}条预警（{warning_count}条警告）")
        
        if changes:
            up_count = sum(1 for c in changes.values() if c.get("direction") == "up")
            down_count = sum(1 for c in changes.values() if c.get("direction") == "down")
            parts.append(f"{up_count}升{down_count}降")
        
        return "，".join(parts)
    
    def get_odds_history(
        self,
        match_id: str,
        play_type: str,
        hours: int = 24,
    ) -> Dict[str, Any]:
        """获取赔率历史
        
        Args:
            match_id: 比赛ID
            play_type: 玩法类型
            hours: 查询小时数
            
        Returns:
            赔率历史数据
        """
        history_file = ODDS_DIR / f"{match_id}_{play_type}.json"
        
        if not history_file.exists():
            return {
                "match_id": match_id,
                "play_type": play_type,
                "history": [],
                "message": "暂无历史数据",
            }
        
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                all_history = json.load(f)
            
            # 过滤时间范围
            cutoff = datetime.now() - timedelta(hours=hours)
            filtered = [
                h for h in all_history
                if datetime.fromisoformat(h.get("timestamp", "2000-01-01")) >= cutoff
            ]
            
            return {
                "match_id": match_id,
                "play_type": play_type,
                "hours": hours,
                "records": len(filtered),
                "history": filtered,
            }
        except Exception as e:
            return {
                "match_id": match_id,
                "play_type": play_type,
                "error": str(e),
                "history": [],
            }
    
    def save_odds_snapshot(
        self,
        match_id: str,
        play_type: str,
        odds: Dict[str, float],
        source: str = "unknown",
    ) -> Dict[str, Any]:
        """保存赔率快照
        
        Args:
            match_id: 比赛ID
            play_type: 玩法类型
            odds: 赔率数据
            source: 数据来源
            
        Returns:
            保存结果
        """
        history_file = ODDS_DIR / f"{match_id}_{play_type}.json"
        
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "odds": odds,
            "source": source,
        }
        
        try:
            # 读取现有历史
            if history_file.exists():
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            else:
                history = []
            
            # 添加新快照
            history.append(snapshot)
            
            # 保存
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            
            return {
                "success": True,
                "match_id": match_id,
                "play_type": play_type,
                "timestamp": snapshot["timestamp"],
                "total_records": len(history),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }


# ============================================================
# 高优先级工具2：历史回测
# ============================================================

class Backtester:
    """策略回测器"""
    
    def __init__(self):
        self.results_cache = {}
    
    def backtest_strategy(
        self,
        strategy_name: str,
        matches: List[Dict[str, Any]],
        strategy_func: Optional[callable] = None,
        initial_bankroll: float = 1000,
        stake_per_bet: float = 10,
    ) -> Dict[str, Any]:
        """回测投注策略
        
        Args:
            strategy_name: 策略名称
            matches: 历史比赛数据列表
            strategy_func: 策略函数（可选，默认使用价值投注策略）
            initial_bankroll: 初始资金
            stake_per_bet: 每注金额
            
        Returns:
            回测结果
        """
        bankroll = initial_bankroll
        bets_placed = 0
        bets_won = 0
        total_stake = 0
        total_return = 0
        bet_history = []
        
        for match in matches:
            # 获取比赛结果
            result = match.get("result", {})
            odds = match.get("odds", {})
            
            if not result or not odds:
                continue
            
            # 应用策略获取推荐
            if strategy_func:
                recommendation = strategy_func(match)
            else:
                recommendation = self._default_strategy(match)
            
            if not recommendation:
                continue
            
            # 模拟投注
            selection = recommendation.get("selection")
            sel_odds = odds.get(selection, 0)
            
            if sel_odds <= 0:
                continue
            
            # 扣除投注金额
            bankroll -= stake_per_bet
            total_stake += stake_per_bet
            bets_placed += 1
            
            # 判断结果
            actual_result = result.get("result", "")
            won = actual_result == selection
            
            if won:
                winnings = stake_per_bet * sel_odds
                bankroll += winnings
                total_return += winnings
                bets_won += 1
            
            bet_history.append({
                "match": match.get("match", "未知"),
                "selection": selection,
                "odds": sel_odds,
                "stake": stake_per_bet,
                "won": won,
                "bankroll_after": round(bankroll, 2),
            })
        
        # 计算统计指标
        win_rate = bets_won / bets_placed if bets_placed > 0 else 0
        roi = (total_return - total_stake) / total_stake if total_stake > 0 else 0
        profit = total_return - total_stake
        
        return {
            "strategy_name": strategy_name,
            "initial_bankroll": initial_bankroll,
            "final_bankroll": round(bankroll, 2),
            "profit": round(profit, 2),
            "roi": round(roi * 100, 2),
            "bets_placed": bets_placed,
            "bets_won": bets_won,
            "win_rate": round(win_rate * 100, 2),
            "total_stake": total_stake,
            "total_return": round(total_return, 2),
            "bet_history": bet_history[:20] if bet_history else [],  # 只返回前20条
            "assessment": self._assess_performance(win_rate, roi),
        }
    
    def _default_strategy(self, match: Dict) -> Optional[Dict]:
        """默认策略：价值投注"""
        odds = match.get("odds", {})
        if not odds:
            return None
        
        # 寻找价值选项（简化版）
        for option, opt_odds in odds.items():
            if opt_odds > 2.5:  # 高赔率选项
                implied_prob = 1 / opt_odds
                # 假设模型概率略高于隐含概率
                model_prob = implied_prob * 1.1
                if model_prob * opt_odds > 1.0:  # 正期望值
                    return {
                        "selection": option,
                        "odds": opt_odds,
                        "model_prob": model_prob,
                        "expected_value": model_prob * opt_odds,
                    }
        
        return None
    
    def _assess_performance(self, win_rate: float, roi: float) -> str:
        """评估策略表现"""
        if roi > 0.2:
            return "优秀：策略表现优异，可持续使用"
        elif roi > 0.05:
            return "良好：策略盈利，建议继续观察"
        elif roi > 0:
            return "一般：策略微利，需要优化"
        elif roi > -0.1:
            return "较差：策略亏损，建议调整参数"
        else:
            return "失败：策略严重亏损，需要重新设计"
    
    def compare_strategies(
        self,
        strategies: List[Dict[str, Any]],
        matches: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """比较多个策略
        
        Args:
            strategies: 策略列表 [{"name": "策略A", "params": {...}}, ...]
            matches: 历史比赛数据
            
        Returns:
            策略比较结果
        """
        results = []
        
        for strategy in strategies:
            result = self.backtest_strategy(
                strategy_name=strategy.get("name", "未命名策略"),
                matches=matches,
                initial_bankroll=strategy.get("initial_bankroll", 1000),
                stake_per_bet=strategy.get("stake_per_bet", 10),
            )
            results.append(result)
        
        # 排序
        results.sort(key=lambda x: x.get("roi", 0), reverse=True)
        
        return {
            "comparison_date": datetime.now().isoformat(),
            "matches_tested": len(matches),
            "strategies_tested": len(strategies),
            "rankings": [
                {
                    "rank": i + 1,
                    "strategy_name": r["strategy_name"],
                    "roi": r["roi"],
                    "win_rate": r["win_rate"],
                    "profit": r["profit"],
                }
                for i, r in enumerate(results)
            ],
            "best_strategy": results[0] if results else None,
            "detailed_results": results,
        }


# ============================================================
# 高优先级工具3：投注记录追踪
# ============================================================

class BetTracker:
    """投注记录追踪器"""
    
    def __init__(self):
        self.records_file = BETS_DIR / "bet_records.json"
        self._lock = threading.Lock()
        self._ensure_file()
    
    def _ensure_file(self):
        """确保记录文件存在"""
        if not self.records_file.exists():
            with open(self.records_file, "w", encoding="utf-8") as f:
                json.dump({"records": []}, f, ensure_ascii=False, indent=2)
    
    def record_bet(
        self,
        bet_id: str,
        match_id: str,
        match_name: str,
        play_type: str,
        selection: str,
        odds: float,
        stake: float,
        result: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """记录投注
        
        Args:
            bet_id: 投注ID
            match_id: 比赛ID
            match_name: 比赛名称
            play_type: 玩法类型
            selection: 投注选项
            odds: 赔率
            stake: 投注金额
            result: 投注结果（"won", "lost", "pending"）
            notes: 备注
            
        Returns:
            记录结果
        """
        record = {
            "bet_id": bet_id,
            "match_id": match_id,
            "match_name": match_name,
            "play_type": play_type,
            "selection": selection,
            "odds": odds,
            "stake": stake,
            "result": result or "pending",
            "notes": notes,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        try:
            with self._lock:
                with open(self.records_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                data["records"].append(record)
                
                with open(self.records_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            return {
                "success": True,
                "bet_id": bet_id,
                "message": "投注记录已保存",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    def update_bet_result(
        self,
        bet_id: str,
        result: str,
        actual_return: Optional[float] = None,
    ) -> Dict[str, Any]:
        """更新投注结果
        
        Args:
            bet_id: 投注ID
            result: 结果（"won", "lost", "void"）
            actual_return: 实际返还金额
            
        Returns:
            更新结果
        """
        try:
            with self._lock:
                with open(self.records_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for record in data["records"]:
                    if record.get("bet_id") == bet_id:
                        record["result"] = result
                        record["actual_return"] = actual_return
                        record["updated_at"] = datetime.now().isoformat()
                        break
                else:
                    return {
                        "success": False,
                        "error": f"未找到投注记录: {bet_id}",
                    }
                
                with open(self.records_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            return {
                "success": True,
                "bet_id": bet_id,
                "result": result,
                "message": "投注结果已更新",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    def get_statistics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        play_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取投注统计
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            play_type: 玩法类型过滤
            
        Returns:
            统计结果
        """
        try:
            with self._lock:
                with open(self.records_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            records = data.get("records", [])
            
            # 过滤
            if start_date:
                records = [r for r in records if r.get("created_at", "") >= start_date]
            if end_date:
                records = [r for r in records if r.get("created_at", "") <= end_date]
            if play_type:
                records = [r for r in records if r.get("play_type") == play_type]
            
            # 统计
            total_bets = len(records)
            total_stake = sum(r.get("stake", 0) for r in records)
            
            won_bets = [r for r in records if r.get("result") == "won"]
            lost_bets = [r for r in records if r.get("result") == "lost"]
            pending_bets = [r for r in records if r.get("result") == "pending"]
            
            total_winnings = sum(
                r.get("stake", 0) * r.get("odds", 0)
                for r in won_bets
            )
            total_return = sum(r.get("actual_return", 0) for r in won_bets)
            
            profit = total_return - total_stake
            roi = profit / total_stake if total_stake > 0 else 0
            
            # 按玩法统计
            by_play_type = {}
            for r in records:
                pt = r.get("play_type", "unknown")
                if pt not in by_play_type:
                    by_play_type[pt] = {"bets": 0, "won": 0, "stake": 0, "return": 0}
                by_play_type[pt]["bets"] += 1
                by_play_type[pt]["stake"] += r.get("stake", 0)
                if r.get("result") == "won":
                    by_play_type[pt]["won"] += 1
                    by_play_type[pt]["return"] += r.get("stake", 0) * r.get("odds", 0)
            
            return {
                "period": {
                    "start_date": start_date,
                    "end_date": end_date,
                },
                "total_bets": total_bets,
                "total_stake": round(total_stake, 2),
                "won_bets": len(won_bets),
                "lost_bets": len(lost_bets),
                "pending_bets": len(pending_bets),
                "win_rate": round(len(won_bets) / total_bets * 100, 2) if total_bets > 0 else 0,
                "total_return": round(total_return, 2),
                "profit": round(profit, 2),
                "roi": round(roi * 100, 2),
                "by_play_type": by_play_type,
                "recent_records": records[-10:] if records else [],
            }
        except Exception as e:
            return {
                "error": str(e),
                "total_bets": 0,
            }


# ============================================================
# 高优先级工具4：智能止损提醒
# ============================================================

class StopLossManager:
    """止损管理器"""
    
    def __init__(self):
        self.default_limits = {
            "daily_loss_limit": 500,      # 日亏损上限
            "weekly_loss_limit": 2000,    # 周亏损上限
            "monthly_loss_limit": 5000,   # 月亏损上限
            "consecutive_loss_limit": 5,  # 连续亏损次数上限
            "single_bet_limit": 500,      # 单注上限
        }
    
    def check_risk_status(
        self,
        bet_tracker: BetTracker,
        custom_limits: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """检查风险状态
        
        Args:
            bet_tracker: 投注追踪器
            custom_limits: 自定义限额
            
        Returns:
            风险状态报告
        """
        limits = {**self.default_limits, **(custom_limits or {})}
        
        # 获取统计数据
        today = datetime.now().strftime("%Y-%m-%d")
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
        month_start = datetime.now().strftime("%Y-%m") + "-01"
        
        today_stats = bet_tracker.get_statistics(start_date=today)
        week_stats = bet_tracker.get_statistics(start_date=week_start)
        month_stats = bet_tracker.get_statistics(start_date=month_start)
        
        alerts = []
        risk_level = "LOW"
        
        # 检查日亏损
        today_loss = today_stats.get("profit", 0)
        if today_loss < -limits["daily_loss_limit"]:
            alerts.append({
                "type": "DAILY_LOSS_EXCEEDED",
                "severity": "CRITICAL",
                "message": f"今日亏损{abs(today_loss):.0f}元，超过日限额{limits['daily_loss_limit']}元",
                "current": today_loss,
                "limit": -limits["daily_loss_limit"],
            })
            risk_level = "CRITICAL"
        elif today_loss < -limits["daily_loss_limit"] * 0.8:
            alerts.append({
                "type": "DAILY_LOSS_WARNING",
                "severity": "WARNING",
                "message": f"今日亏损{abs(today_loss):.0f}元，接近日限额",
                "current": today_loss,
                "limit": -limits["daily_loss_limit"],
            })
            risk_level = "HIGH" if risk_level != "CRITICAL" else risk_level
        
        # 检查周亏损
        week_loss = week_stats.get("profit", 0)
        if week_loss < -limits["weekly_loss_limit"]:
            alerts.append({
                "type": "WEEKLY_LOSS_EXCEEDED",
                "severity": "CRITICAL",
                "message": f"本周亏损{abs(week_loss):.0f}元，超过周限额{limits['weekly_loss_limit']}元",
                "current": week_loss,
                "limit": -limits["weekly_loss_limit"],
            })
            risk_level = "CRITICAL"
        
        # 检查月亏损
        month_loss = month_stats.get("profit", 0)
        if month_loss < -limits["monthly_loss_limit"]:
            alerts.append({
                "type": "MONTHLY_LOSS_EXCEEDED",
                "severity": "CRITICAL",
                "message": f"本月亏损{abs(month_loss):.0f}元，超过月限额{limits['monthly_loss_limit']}元",
                "current": month_loss,
                "limit": -limits["monthly_loss_limit"],
            })
            risk_level = "CRITICAL"
        
        # 检查连续亏损
        consecutive_losses = self._get_consecutive_losses(bet_tracker)
        if consecutive_losses >= limits["consecutive_loss_limit"]:
            alerts.append({
                "type": "CONSECUTIVE_LOSS_EXCEEDED",
                "severity": "WARNING",
                "message": f"已连续亏损{consecutive_losses}次，建议暂停投注",
                "current": consecutive_losses,
                "limit": limits["consecutive_loss_limit"],
            })
            risk_level = "HIGH" if risk_level not in ["CRITICAL"] else risk_level
        
        return {
            "risk_level": risk_level,
            "alerts": alerts if alerts else None,
            "statistics": {
                "today": {
                    "profit": today_stats.get("profit", 0),
                    "bets": today_stats.get("total_bets", 0),
                    "win_rate": today_stats.get("win_rate", 0),
                },
                "week": {
                    "profit": week_stats.get("profit", 0),
                    "bets": week_stats.get("total_bets", 0),
                    "win_rate": week_stats.get("win_rate", 0),
                },
                "month": {
                    "profit": month_stats.get("profit", 0),
                    "bets": month_stats.get("total_bets", 0),
                    "win_rate": month_stats.get("win_rate", 0),
                },
            },
            "limits": limits,
            "recommendations": self._generate_recommendations(risk_level, alerts),
        }
    
    def _get_consecutive_losses(self, bet_tracker: BetTracker) -> int:
        """获取连续亏损次数"""
        try:
            with open(bet_tracker.records_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            records = data.get("records", [])
            # 按时间倒序
            records.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            consecutive = 0
            for r in records:
                if r.get("result") == "lost":
                    consecutive += 1
                elif r.get("result") == "won":
                    break
            
            return consecutive
        except (KeyError, TypeError, AttributeError):
            return 0
    
    def _generate_recommendations(
        self,
        risk_level: str,
        alerts: List[Dict],
    ) -> List[str]:
        """生成建议"""
        recommendations = []
        
        if risk_level == "CRITICAL":
            recommendations.append("🛑 建议立即停止投注，冷静分析")
            recommendations.append("📊 回顾近期投注记录，找出问题所在")
            recommendations.append("⏰ 建议休息24小时后再考虑继续")
        elif risk_level == "HIGH":
            recommendations.append("⚠️ 风险较高，建议减少投注金额")
            recommendations.append("🎯 专注于高置信度的投注机会")
            recommendations.append("📝 记录每次投注的理由，便于复盘")
        elif risk_level == "MEDIUM":
            recommendations.append("💡 当前风险可控，保持谨慎")
            recommendations.append("📈 继续执行既定策略")
        else:
            recommendations.append("✅ 风险状态良好")
            recommendations.append("🎯 可按计划进行投注")
        
        return recommendations
    
    def should_stop_betting(
        self,
        bet_tracker: BetTracker,
        custom_limits: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """判断是否应该停止投注
        
        Args:
            bet_tracker: 投注追踪器
            custom_limits: 自定义限额
            
        Returns:
            止损判断结果
        """
        risk_status = self.check_risk_status(bet_tracker, custom_limits)
        
        should_stop = risk_status["risk_level"] == "CRITICAL"
        
        return {
            "should_stop": should_stop,
            "risk_level": risk_status["risk_level"],
            "reason": risk_status["alerts"][0]["message"] if risk_status.get("alerts") else None,
            "recommendations": risk_status["recommendations"],
        }


# ============================================================
# 工厂函数
# ============================================================

def get_odds_monitor() -> OddsMonitor:
    """获取赔率监控器实例"""
    return OddsMonitor()

def get_backtester() -> Backtester:
    """获取回测器实例"""
    return Backtester()

def get_bet_tracker() -> BetTracker:
    """获取投注追踪器实例"""
    return BetTracker()

def get_stop_loss_manager() -> StopLossManager:
    """获取止损管理器实例"""
    return StopLossManager()
