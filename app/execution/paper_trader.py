"""High-fidelity Paper Trading execution engine."""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.core.models import (
    Order,
    OrderStatus,
    OrderSide,
    Position,
    PortfolioState,
)

logger = logging.getLogger("PaperTrader")


class PaperTradingEngine:
    def __init__(
        self,
        initial_cash: float = 100000.0,
        commission_rate: float = 0.001,  # 0.1%
        slippage_bps: float = 5.0,        # 0.05%
    ):
        self.cash_balance = initial_cash
        self.initial_capital = initial_cash
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_bps / 10000.0
        self.positions: Dict[str, Position] = {}
        self.filled_orders: List[Order] = []
        self.peak_equity = initial_cash
        self.realized_pnl = 0.0

    def get_portfolio_state(self, current_prices: Dict[str, float] | None = None) -> PortfolioState:
        now = datetime.now(timezone.utc)
        prices = current_prices or {}

        # Update position current prices and unrealized pnl
        unrealized_pnl = 0.0
        for sym, pos in self.positions.items():
            if sym in prices:
                pos.current_price = prices[sym]
            if pos.side == OrderSide.BUY:
                pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.size
            else:
                pos.unrealized_pnl = (pos.entry_price - pos.current_price) * pos.size
            pos.last_updated = now
            unrealized_pnl += pos.unrealized_pnl

        total_position_val = sum(
            p.size * p.current_price for p in self.positions.values()
        )
        total_equity = self.cash_balance + total_position_val

        if total_equity > self.peak_equity:
            self.peak_equity = total_equity

        drawdown_pct = (self.peak_equity - total_equity) / self.peak_equity if self.peak_equity > 0 else 0.0

        return PortfolioState(
            timestamp=now,
            cash_balance=round(self.cash_balance, 2),
            total_equity=round(total_equity, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            realized_pnl=round(self.realized_pnl, 2),
            peak_equity=round(self.peak_equity, 2),
            drawdown_pct=round(drawdown_pct, 4),
            positions={k: v.model_copy() for k, v in self.positions.items()},
        )

    async def execute_order(self, order: Order, current_market_price: float) -> Order:
        now = datetime.now(timezone.utc)

        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price = current_market_price * (1.0 + self.slippage_rate)
        else:
            fill_price = current_market_price * (1.0 - self.slippage_rate)

        trade_value = fill_price * order.size
        commission = trade_value * self.commission_rate

        if order.side == OrderSide.BUY:
            total_cost = trade_value + commission
            if self.cash_balance < total_cost:
                order.status = OrderStatus.REJECTED
                logger.warning(f"Insufficient cash ({self.cash_balance:.2f}) for BUY order cost {total_cost:.2f}")
                return order

            self.cash_balance -= total_cost

            # Update or create position
            if order.symbol in self.positions:
                existing = self.positions[order.symbol]
                new_size = existing.size + order.size
                avg_entry = ((existing.entry_price * existing.size) + (fill_price * order.size)) / new_size
                existing.size = new_size
                existing.entry_price = avg_entry
                existing.current_price = fill_price
                existing.stop_loss = order.stop_loss
                existing.take_profit = order.take_profit
                existing.last_updated = now
            else:
                self.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    side=OrderSide.BUY,
                    size=order.size,
                    entry_price=fill_price,
                    current_price=fill_price,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    opened_at=now,
                    last_updated=now,
                )
        else:
            # SELL order
            if order.symbol in self.positions:
                pos = self.positions[order.symbol]
                close_size = min(pos.size, order.size)
                pnl = (fill_price - pos.entry_price) * close_size
                self.realized_pnl += pnl
                self.cash_balance += (fill_price * close_size) - commission

                remaining_size = pos.size - close_size
                if remaining_size <= 1e-6:
                    del self.positions[order.symbol]
                else:
                    pos.size = remaining_size
                    pos.current_price = fill_price
                    pos.last_updated = now
            else:
                order.status = OrderStatus.REJECTED
                logger.warning(f"Cannot SELL {order.symbol}: No open position.")
                return order

        order.status = OrderStatus.FILLED
        order.filled_at = now
        order.avg_fill_price = round(fill_price, 4)
        order.commission = round(commission, 4)
        self.filled_orders.append(order)

        logger.info(
            f"Filled {order.side.value.upper()} {order.size} {order.symbol} @ {fill_price:.2f} (Comm: ${commission:.2f})"
        )
        return order
