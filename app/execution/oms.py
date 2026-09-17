"""Order Management System (OMS)."""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.core.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TradingSignal,
    RiskCheckResult,
    SignalType,
)


class OrderManagementSystem:
    def __init__(self):
        self.orders: Dict[str, Order] = {}

    def create_order_from_signal(
        self,
        signal: TradingSignal,
        risk_result: RiskCheckResult,
        current_price: float,
    ) -> Optional[Order]:
        if not risk_result.approved:
            return None

        side = OrderSide.BUY if signal.signal_type == SignalType.LONG else OrderSide.SELL
        order_id = f"ord_{uuid.uuid4().hex[:10]}"

        order = Order(
            id=order_id,
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            price=current_price,
            size=risk_result.adjusted_size,
            status=OrderStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            stop_loss=risk_result.adjusted_stop_loss,
            take_profit=risk_result.adjusted_take_profit,
            strategy_name=signal.strategy_name,
        )
        self.orders[order.id] = order
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)
