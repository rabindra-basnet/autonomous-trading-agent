"""Pre-trade risk management, position sizing, and circuit breakers."""

import logging

from app.core.models import (
    PortfolioState,
    RiskCheckResult,
    SignalType,
    TradingSignal,
)

logger = logging.getLogger("RiskManager")


class RiskManager:
    def __init__(
        self,
        max_position_size_pct: float = 0.20,
        max_portfolio_exposure_pct: float = 0.80,
        max_drawdown_limit_pct: float = 0.10,
        max_single_trade_risk_pct: float = 0.02,
        default_stop_loss_pct: float = 0.03,
        default_take_profit_pct: float = 0.06,
    ):
        self.max_position_size_pct = max_position_size_pct
        self.max_portfolio_exposure_pct = max_portfolio_exposure_pct
        self.max_drawdown_limit_pct = max_drawdown_limit_pct
        self.max_single_trade_risk_pct = max_single_trade_risk_pct
        self.default_stop_loss_pct = default_stop_loss_pct
        self.default_take_profit_pct = default_take_profit_pct

    def check_portfolio_health(self, portfolio: PortfolioState) -> bool:
        """Verify if overall portfolio is healthy or if circuit breaker has tripped."""
        if portfolio.drawdown_pct >= self.max_drawdown_limit_pct:
            logger.critical(
                f"CIRCUIT BREAKER TRIGGERED! Drawdown {portfolio.drawdown_pct * 100:.2f}% exceeds limit {self.max_drawdown_limit_pct * 100:.2f}%"
            )
            return False
        return True

    def validate_signal(
        self,
        signal: TradingSignal,
        portfolio: PortfolioState,
        current_price: float,
    ) -> RiskCheckResult:
        """Validate and size trading signal before order dispatch."""
        if not self.check_portfolio_health(portfolio):
            return RiskCheckResult(
                approved=False,
                adjusted_size=0.0,
                rejection_reason="Circuit breaker active due to maximum drawdown breach.",
            )

        if current_price <= 0:
            return RiskCheckResult(
                approved=False,
                adjusted_size=0.0,
                rejection_reason=f"Invalid current price: {current_price}",
            )

        # Handle flat signal (close position)
        if signal.signal_type == SignalType.FLAT:
            current_pos = portfolio.positions.get(signal.symbol)
            if not current_pos or current_pos.size == 0:
                return RiskCheckResult(approved=False, adjusted_size=0.0, rejection_reason="No position to flatten.")
            return RiskCheckResult(approved=True, adjusted_size=current_pos.size)

        # Total portfolio allocated
        current_allocated_usd = sum(p.size * p.current_price for p in portfolio.positions.values())
        total_equity = portfolio.total_equity

        if total_equity <= 0:
            return RiskCheckResult(
                approved=False,
                adjusted_size=0.0,
                rejection_reason="Total equity is zero or negative.",
            )

        exposure_pct = current_allocated_usd / total_equity
        if exposure_pct >= self.max_portfolio_exposure_pct:
            return RiskCheckResult(
                approved=False,
                adjusted_size=0.0,
                rejection_reason=f"Max portfolio exposure reached ({exposure_pct * 100:.1f}% >= {self.max_portfolio_exposure_pct * 100:.1f}%)",
            )

        # Sizing calculation
        suggested_pct = min(signal.suggested_size_pct, self.max_position_size_pct)
        # Scale with signal strength (0.0 to 1.0)
        target_allocation_usd = total_equity * suggested_pct * max(0.1, signal.strength)

        # Adjust for remaining allowed exposure
        remaining_exposure_usd = (self.max_portfolio_exposure_pct * total_equity) - current_allocated_usd
        allowed_allocation_usd = min(target_allocation_usd, remaining_exposure_usd)

        # Size in asset units
        size_units = allowed_allocation_usd / current_price

        if size_units <= 0:
            return RiskCheckResult(
                approved=False,
                adjusted_size=0.0,
                rejection_reason="Calculated position size is zero.",
            )

        # Bracket stop loss & take profit prices
        stop_loss = signal.stop_loss
        take_profit = signal.target_price

        if signal.signal_type == SignalType.LONG:
            if not stop_loss:
                stop_loss = current_price * (1 - self.default_stop_loss_pct)
            if not take_profit:
                take_profit = current_price * (1 + self.default_take_profit_pct)
        elif signal.signal_type == SignalType.SHORT:
            if not stop_loss:
                stop_loss = current_price * (1 + self.default_stop_loss_pct)
            if not take_profit:
                take_profit = current_price * (1 - self.default_take_profit_pct)

        return RiskCheckResult(
            approved=True,
            adjusted_size=round(size_units, 6),
            adjusted_stop_loss=round(stop_loss, 4) if stop_loss else None,
            adjusted_take_profit=round(take_profit, 4) if take_profit else None,
        )
