"""High-performance technical analysis indicators."""

import numpy as np

from app.core.models import Candle


class TechnicalIndicators:
    @staticmethod
    def sma(prices: np.ndarray, period: int) -> np.ndarray:
        if len(prices) < period:
            return np.full_like(prices, np.nan)
        weights = np.ones(period) / period
        res = np.convolve(prices, weights, mode="valid")
        pad = np.full(period - 1, np.nan)
        return np.concatenate((pad, res))

    @staticmethod
    def ema(prices: np.ndarray, period: int) -> np.ndarray:
        if len(prices) == 0:
            return np.array([])
        alpha = 2.0 / (period + 1.0)
        ema_arr = np.zeros_like(prices, dtype=float)
        ema_arr[0] = prices[0]
        for i in range(1, len(prices)):
            ema_arr[i] = alpha * prices[i] + (1 - alpha) * ema_arr[i - 1]
        return ema_arr

    @classmethod
    def rsi(cls, prices: np.ndarray, period: int = 14) -> np.ndarray:
        if len(prices) <= period:
            return np.full_like(prices, 50.0)
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = np.zeros(len(prices))
        avg_loss = np.zeros(len(prices))

        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])

        for i in range(period + 1, len(prices)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

        rs = np.divide(
            avg_gain,
            avg_loss,
            out=np.zeros_like(avg_gain),
            where=avg_loss != 0,
        )
        rsi_vals = 100.0 - (100.0 / (1.0 + rs))
        rsi_vals[:period] = 50.0
        return rsi_vals

    @classmethod
    def macd(
        cls, prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        fast_ema = cls.ema(prices, fast)
        slow_ema = cls.ema(prices, slow)
        macd_line = fast_ema - slow_ema
        signal_line = cls.ema(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @classmethod
    def bollinger_bands(
        cls, prices: np.ndarray, period: int = 20, num_std: float = 2.0
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        sma = cls.sma(prices, period)
        std = np.zeros_like(prices)
        for i in range(period - 1, len(prices)):
            std[i] = np.std(prices[i - period + 1 : i + 1])
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        return upper, sma, lower

    @classmethod
    def atr(cls, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
        if len(closes) < 2:
            return np.zeros_like(closes)
        prev_closes = np.roll(closes, 1)
        prev_closes[0] = closes[0]

        tr1 = highs - lows
        tr2 = np.abs(highs - prev_closes)
        tr3 = np.abs(lows - prev_closes)
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        atr_arr = np.zeros_like(tr)
        if len(tr) >= period:
            atr_arr[period - 1] = np.mean(tr[:period])
            for i in range(period, len(tr)):
                atr_arr[i] = (atr_arr[i - 1] * (period - 1) + tr[i]) / period
        return atr_arr

    @classmethod
    def extract_features(cls, candles: list[Candle]) -> dict[str, float]:
        """Compute latest technical feature set from a list of candles."""
        if not candles:
            return {}

        closes = np.array([c.close for c in candles], dtype=float)
        highs = np.array([c.high for c in candles], dtype=float)
        lows = np.array([c.low for c in candles], dtype=float)
        volumes = np.array([c.volume for c in candles], dtype=float)

        ema_12 = cls.ema(closes, 12)[-1] if len(closes) >= 12 else closes[-1]
        ema_26 = cls.ema(closes, 26)[-1] if len(closes) >= 26 else closes[-1]
        ema_50 = cls.ema(closes, 50)[-1] if len(closes) >= 50 else closes[-1]
        ema_200 = cls.ema(closes, 200)[-1] if len(closes) >= 200 else closes[-1]

        rsi_val = cls.rsi(closes, 14)[-1]
        macd_line, sig_line, hist = cls.macd(closes)
        bb_upper, bb_mid, bb_lower = cls.bollinger_bands(closes, 20)
        atr_val = cls.atr(highs, lows, closes, 14)[-1]

        # Momentum (return over last 5 and 20 periods)
        ret_5 = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else 0.0
        ret_20 = (closes[-1] - closes[-21]) / closes[-21] if len(closes) >= 21 else 0.0

        # Realized volatility (std of log returns)
        log_rets = np.diff(np.log(np.maximum(1e-8, closes[-30:]))) if len(closes) >= 5 else np.array([0.0])
        realized_vol = float(np.std(log_rets) * np.sqrt(365 * 24)) if len(log_rets) > 1 else 0.0

        # VWAP
        cum_vol = np.sum(volumes[-24:]) if len(volumes) >= 1 else 1.0
        vwap_24h = (
            float(np.sum(((highs + lows + closes) / 3.0)[-24:] * volumes[-24:]) / cum_vol)
            if cum_vol > 0
            else closes[-1]
        )

        return {
            "close": float(closes[-1]),
            "ema_12": float(ema_12),
            "ema_26": float(ema_26),
            "ema_50": float(ema_50),
            "ema_200": float(ema_200),
            "rsi_14": float(rsi_val),
            "macd": float(macd_line[-1]),
            "macd_signal": float(sig_line[-1]),
            "macd_hist": float(hist[-1]),
            "bb_upper": float(bb_upper[-1]) if not np.isnan(bb_upper[-1]) else closes[-1],
            "bb_lower": float(bb_lower[-1]) if not np.isnan(bb_lower[-1]) else closes[-1],
            "bb_bandwidth": float((bb_upper[-1] - bb_lower[-1]) / bb_mid[-1])
            if (not np.isnan(bb_mid[-1]) and bb_mid[-1] > 0)
            else 0.0,
            "atr_14": float(atr_val),
            "ret_5": float(ret_5),
            "ret_20": float(ret_20),
            "realized_vol": float(realized_vol),
            "vwap_24h": float(vwap_24h),
        }
