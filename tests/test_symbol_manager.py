"""Tests for dynamic SymbolManager registry and normalization."""

from app.core.symbol_manager import SymbolManager


def test_symbol_manager_initialization():
    sm = SymbolManager(["BTC/USDT", "ETH/USDT"])
    assert "BTC/USDT" in sm.get_active_symbols()
    assert "ETH/USDT" in sm.get_active_symbols()
    assert len(sm.get_active_symbols()) == 2


def test_symbol_manager_dynamic_add_and_remove():
    sm = SymbolManager(["BTC/USDT"])
    
    # Add new symbols
    added = sm.add_symbol("SOL/USDT")
    assert added == "SOL/USDT"
    assert "SOL/USDT" in sm.get_active_symbols()
    assert len(sm.get_active_symbols()) == 2

    # Add normalized e.g. AVAXUSDT -> AVAX/USDT
    sm.add_symbol("AVAXUSDT")
    assert "AVAX/USDT" in sm.get_active_symbols()
    assert len(sm.get_active_symbols()) == 3

    # Details
    details = sm.get_symbol_details()
    symbols = [d.symbol for d in details]
    assert "BTC/USDT" in symbols
    assert "SOL/USDT" in symbols
    assert "AVAX/USDT" in symbols

    # Remove symbol
    removed = sm.remove_symbol("SOL/USDT")
    assert removed is True
    assert "SOL/USDT" not in sm.get_active_symbols()
    assert len(sm.get_active_symbols()) == 2
