# Py_SUITE_TRADING/brokers/ib/ib_executor.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Union
import os
import time

from ib_insync import (
    IB,
    Stock,
    Future,
    Forex,
    Contract,
    MarketOrder,
    LimitOrder,
    StopOrder,
    Trade,
    Position,
)


@dataclass(frozen=True)
class IBConnectionConfig:
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 7
    readonly: bool = False
    connect_timeout_sec: float = 3.0


class IBExecutor:
    """
    Executor minimale per invio ordini a Interactive Brokers via IB Gateway/TWS.
    Nessun "flag paper/live": scegli la porta corretta nel config (o env).

    Env supportate (opzionali):
      - IB_HOST
      - IB_PORT
      - IB_CLIENT_ID
      - IB_READONLY (0/1)
    """

    def __init__(self, cfg: Optional[IBConnectionConfig] = None):
        self.cfg = cfg or self._cfg_from_env()
        self.ib = IB()
        self._connected = False

    # -------------------------
    # Connessione
    # -------------------------
    @staticmethod
    def _cfg_from_env() -> IBConnectionConfig:
        host = os.getenv("IB_HOST", "127.0.0.1")
        port = int(os.getenv("IB_PORT", "4002"))
        client_id = int(os.getenv("IB_CLIENT_ID", "7"))
        readonly = os.getenv("IB_READONLY", "0").strip() in ("1", "true", "TRUE", "yes", "YES")
        return IBConnectionConfig(host=host, port=port, client_id=client_id, readonly=readonly)

    def connect(self) -> None:
        if self._connected:
            return
        self.ib.connect(
            self.cfg.host,
            self.cfg.port,
            clientId=self.cfg.client_id,
            readonly=self.cfg.readonly,
            timeout=self.cfg.connect_timeout_sec,
        )
        self._connected = self.ib.isConnected()
        if not self._connected:
            raise ConnectionError(f"IB connect failed: host={self.cfg.host} port={self.cfg.port} clientId={self.cfg.client_id}")

    def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()
        self._connected = False

    def __enter__(self) -> "IBExecutor":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    # -------------------------
    # Contratti (builders)
    # -------------------------
    def contract_stock(self, symbol: str, currency: str = "USD", exchange: str = "SMART") -> Contract:
        return Stock(symbol, exchange, currency)

    def contract_forex(self, pair: str) -> Contract:
        # es: "EURUSD"
        return Forex(pair)

    def contract_future(
        self,
        symbol: str,
        expiry_yyyymm: str,
        exchange: str,
        currency: str = "USD",
    ) -> Contract:
        return Future(symbol=symbol, lastTradeDateOrContractMonth=expiry_yyyymm, exchange=exchange, currency=currency)

    def qualify(self, contract: Contract) -> Contract:
        self.connect()
        cs = self.ib.qualifyContracts(contract)
        if not cs:
            raise ValueError(f"Contract not qualified: {contract}")
        return cs[0]

    # -------------------------
    # Ordini (place + wait)
    # -------------------------
    def place_market(self, contract: Contract, action: str, qty: float) -> Trade:
        self.connect()
        c = self.qualify(contract)
        order = MarketOrder(action.upper(), qty)
        return self.ib.placeOrder(c, order)

    def place_limit(self, contract: Contract, action: str, qty: float, limit_price: float) -> Trade:
        self.connect()
        c = self.qualify(contract)
        order = LimitOrder(action.upper(), qty, limit_price)
        return self.ib.placeOrder(c, order)

    def place_stop(self, contract: Contract, action: str, qty: float, stop_price: float) -> Trade:
        self.connect()
        c = self.qualify(contract)
        order = StopOrder(action.upper(), qty, stop_price)
        return self.ib.placeOrder(c, order)

    def wait_done(self, trade: Trade, timeout_sec: float = 10.0, poll_sec: float = 0.2) -> Trade:
        """
        Attende fino a trade.isDone() oppure timeout.
        """
        t0 = time.time()
        while True:
            self.ib.sleep(poll_sec)  # integra event loop ib_insync
            if trade.isDone():
                return trade
            if (time.time() - t0) >= timeout_sec:
                return trade

    def trade_snapshot(self, trade: Trade) -> Dict[str, Any]:
        st = trade.orderStatus
        return {
            "status": st.status,
            "filled": float(st.filled or 0),
            "remaining": float(st.remaining or 0),
            "avgFillPrice": float(st.avgFillPrice or 0),
            "lastFillPrice": float(getattr(st, "lastFillPrice", 0) or 0),
            "permId": getattr(trade.order, "permId", None),
            "orderId": getattr(trade.order, "orderId", None),
        }

    # -------------------------
    # Query utili
    # -------------------------
    def positions(self) -> List[Position]:
        self.connect()
        return list(self.ib.positions())

    def open_trades(self) -> List[Trade]:
        self.connect()
        return list(self.ib.openTrades())

    def cancel_trade(self, trade: Trade) -> None:
        self.connect()
        self.ib.cancelOrder(trade.order)

    # -------------------------
    # Close position helper
    # -------------------------
    def close_position_market(self, contract: Contract, qty: Optional[float] = None) -> Trade:
        """
        Chiude una posizione a mercato. Se qty=None chiude tutta la posizione sul contratto.
        """
        self.connect()
        c = self.qualify(contract)

        pos_qty = 0.0
        for p in self.ib.positions():
            if p.contract.conId == c.conId:
                pos_qty = float(p.position)
                break

        if pos_qty == 0.0:
            raise ValueError("No position to close on this contract.")

        close_qty = float(abs(pos_qty) if qty is None else qty)
        action = "SELL" if pos_qty > 0 else "BUY"
        order = MarketOrder(action, close_qty)
        return self.ib.placeOrder(c, order)

