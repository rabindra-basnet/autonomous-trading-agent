"""Model & Strategy Experiment Registry."""

import json
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict
from app.core.models import ExperimentRecord, BacktestResult


class StrategyRegistry:
    def __init__(self, registry_file: str = "data/registry.json"):
        self.registry_file = registry_file
        os.makedirs(os.path.dirname(registry_file) if os.path.dirname(registry_file) else ".", exist_ok=True)
        self.records: List[ExperimentRecord] = []
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.records = [ExperimentRecord(**item) for item in data]
            except Exception:
                self.records = []

    def _save(self) -> None:
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump([r.model_dump(mode="json") for r in self.records], f, indent=2)

    def log_experiment(
        self,
        hypothesis: str,
        strategy_name: str,
        dataset_range: str,
        parameters: Dict,
        backtest_result: BacktestResult,
        promoted: bool = False,
        notes: str = "",
    ) -> ExperimentRecord:
        record = ExperimentRecord(
            experiment_id=f"exp_{int(datetime.now(timezone.utc).timestamp()*1000)}",
            created_at=datetime.now(timezone.utc),
            hypothesis=hypothesis,
            strategy_name=strategy_name,
            dataset_range=dataset_range,
            parameters=parameters,
            metrics={
                "sharpe_ratio": round(backtest_result.sharpe_ratio, 3),
                "total_return_pct": round(backtest_result.total_return_pct, 2),
                "max_drawdown_pct": round(backtest_result.max_drawdown_pct, 2),
                "win_rate_pct": round(backtest_result.win_rate_pct, 2),
                "profit_factor": round(backtest_result.profit_factor, 2),
            },
            promoted=promoted,
            notes=notes,
        )
        self.records.append(record)
        self._save()
        return record

    def get_promoted_strategies(self) -> List[ExperimentRecord]:
        return [r for r in self.records if r.promoted]
