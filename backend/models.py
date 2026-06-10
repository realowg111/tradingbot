"""Pydantic models for requests/responses."""
from datetime import datetime, timezone
from typing import Optional, Dict, List, Literal
from pydantic import BaseModel, EmailStr, Field, field_validator
import uuid


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid.uuid4())


# ---------- Auth ----------
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    is_admin: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---------- MT5 ----------
def _clean_str(v):
    """Strip whitespace + wrapping quotes; empty string -> None."""
    if isinstance(v, str):
        v = v.strip().strip('"').strip("'").strip()
        return v or None
    return v


class MT5CredentialsIn(BaseModel):
    login: str
    password: Optional[str] = None  # Optional: if empty, existing password is kept
    server: str
    broker: Optional[str] = None
    path: Optional[str] = None  # Optional explicit path to terminal64.exe

    @field_validator("login", "server", "broker", "path", mode="before")
    @classmethod
    def clean(cls, v):
        return _clean_str(v)


class MT5CredentialsOut(BaseModel):
    login: str
    server: str
    broker: Optional[str] = None
    path: Optional[str] = None
    saved: bool = True


class MT5PathPatch(BaseModel):
    path: str

    @field_validator("path", mode="before")
    @classmethod
    def clean(cls, v):
        return _clean_str(v) or ""


# ---------- Bot config & state ----------
class RiskConfig(BaseModel):
    capital_allocation_pct: float = 10.0  # progressive exposure (10%)
    risk_per_trade_pct: float = 1.0       # % of capital risked per trade
    risk_reward_ratio: float = 2.0        # TP = RR * SL
    stop_loss_pct: float = 1.0            # %
    take_profit_pct: float = 2.0          # %
    daily_drawdown_limit_pct: float = 5.0
    max_open_positions: int = 5
    max_trades_per_day: int = 20
    volatility_pause: bool = True


class StrategyConfig(BaseModel):
    enabled: List[str] = Field(default_factory=lambda: ["multi"])  # ids
    rsi_period: int = 14
    rsi_overbought: float = 70
    rsi_oversold: float = 30
    ema_fast: int = 9
    ema_slow: int = 21
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0


class BotConfig(BaseModel):
    id: str = Field(default_factory=uid)
    mode: Literal["demo", "real"] = "demo"
    enabled: bool = False
    starting_balance: float = 10000.0
    symbols: List[str] = Field(default_factory=lambda: ["EURUSD", "GBPUSD", "XAUUSD", "US100", "BTCUSD"])
    risk: RiskConfig = Field(default_factory=RiskConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    # Paper validation gates (fully configurable - disabled by default)
    paper_validation_enabled: bool = False
    paper_validation_days: int = 7
    paper_validation_min_trades: int = 10
    paper_validation_min_winrate: float = 40.0
    # Live MT5 trading toggle - when True AND mode=real AND mt5 connected,
    # the bot places orders directly on MT5 (visible in your MT5 terminal live)
    live_mt5_trading_enabled: bool = False
    # Adaptive strategy: when True, detect market regime per symbol and
    # restrict active strategies + scale risk accordingly.
    adaptive_enabled: bool = True
    real_validation_token: Optional[str] = None
    updated_at: datetime = Field(default_factory=utc_now)


class BotState(BaseModel):
    id: str = Field(default_factory=uid)
    balance: float = 10000.0
    equity: float = 10000.0
    daily_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    open_positions: int = 0
    trades_today: int = 0
    daily_start_balance: float = 10000.0
    last_daily_reset: datetime = Field(default_factory=utc_now)
    paused_reason: Optional[str] = None
    paper_start: datetime = Field(default_factory=utc_now)
    real_unlocked: bool = False
    kill_switch_engaged: bool = False
    updated_at: datetime = Field(default_factory=utc_now)


# ---------- Trades & positions ----------
class Position(BaseModel):
    id: str = Field(default_factory=uid)
    symbol: str
    side: Literal["BUY", "SELL"]
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    opened_at: datetime = Field(default_factory=utc_now)
    strategy: str
    reason: str
    status: Literal["OPEN", "CLOSED"] = "OPEN"
    mode: Literal["demo", "real"] = "demo"


class Trade(BaseModel):
    id: str = Field(default_factory=uid)
    symbol: str
    side: Literal["BUY", "SELL"]
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    fees: float = 0.0
    slippage: float = 0.0
    strategy: str
    open_reason: str
    close_reason: str
    opened_at: datetime
    closed_at: datetime = Field(default_factory=utc_now)
    duration_sec: float = 0.0
    mode: Literal["demo", "real"] = "demo"


# ---------- Audit ----------
class AuditLog(BaseModel):
    id: str = Field(default_factory=uid)
    ts: datetime = Field(default_factory=utc_now)
    level: Literal["INFO", "SIGNAL", "TRADE", "RISK", "ERROR", "SYSTEM"] = "INFO"
    event: str
    details: Dict = Field(default_factory=dict)


# ---------- Costs ----------
class CostItem(BaseModel):
    id: str = Field(default_factory=uid)
    category: Literal["vps", "api", "data", "maintenance", "other"]
    label: str
    amount: float
    currency: str = "EUR"
    recurring: Literal["once", "monthly", "yearly"] = "monthly"
    date: datetime = Field(default_factory=utc_now)
    notes: Optional[str] = None


class CostItemCreate(BaseModel):
    category: Literal["vps", "api", "data", "maintenance", "other"]
    label: str
    amount: float
    currency: str = "EUR"
    recurring: Literal["once", "monthly", "yearly"] = "monthly"
    notes: Optional[str] = None


# ---------- Mode switch ----------
class ModeSwitchRequest(BaseModel):
    target_mode: Literal["demo", "real"]
    confirmation_phrase: Optional[str] = None  # must equal "JE CONFIRME LE PASSAGE EN REEL" for real


# ---------- Backtest ----------
class BacktestRequest(BaseModel):
    symbol: str = "EURUSD"
    strategy: str = "multi"
    candles: int = 500
    starting_balance: float = 10000.0


class BacktestResult(BaseModel):
    symbol: str
    strategy: str
    starting_balance: float
    ending_balance: float
    total_trades: int
    wins: int
    losses: int
    winrate: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe: float
    expectancy: float
    trades: List[Trade]
