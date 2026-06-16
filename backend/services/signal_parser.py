"""Telegram message -> structured trading signal.

Uses Claude Sonnet 4.5 via Emergent LLM Key (emergentintegrations) for robust
parsing across various trader formats.

Returns a normalized dict:
{
  "is_signal": bool,
  "symbol": str,          # MT5 symbol (best-effort normalization)
  "side": "BUY"|"SELL",
  "entry": float|None,    # mid-range when a range like "4340-4337" is given
  "entry_low": float|None,
  "entry_high": float|None,
  "sl": float|None,
  "tps": [ {"value": float|None, "runner": bool, "raw": str} ],
  "confidence": float (0..1),
  "raw_excerpt": str
}
"""
import os
import re
import json
import logging
from typing import Optional

logger = logging.getLogger("signal_parser")

_SYMBOL_ALIASES = {
    "GOLD": "XAUUSD", "OR": "XAUUSD", "XAU": "XAUUSD",
    "SILVER": "XAGUSD", "ARGENT": "XAGUSD",
    "NAS100": "US100", "NASDAQ": "US100", "NDX": "US100", "NQ": "US100",
    "SPX500": "US500", "S&P": "US500", "SP500": "US500",
    "DOW": "US30", "DJ30": "US30", "DAX": "DE40", "GER40": "DE40",
    "BTC": "BTCUSD", "BITCOIN": "BTCUSD",
    "ETH": "ETHUSD", "ETHEREUM": "ETHUSD",
    "OIL": "WTI", "USOIL": "WTI", "CRUDE": "WTI",
}

_SYSTEM_PROMPT = (
    "You are a TRADING SIGNAL PARSER. Read a raw Telegram message and extract a structured\n"
    "JSON object describing the trade. ONLY output strict JSON, NO markdown, NO comments.\n\n"
    "Schema:\n"
    "{\n"
    '  "is_signal": boolean,\n'
    '  "symbol": string|null,   // raw symbol as written (e.g. XAUUSD, GOLD, BTCUSD, US30)\n'
    '  "side": "BUY"|"SELL"|null,\n'
    '  "entry_low": number|null,\n'
    '  "entry_high": number|null,\n'
    '  "sl": number|null,\n'
    '  "tps": [ { "value": number|null, "runner": boolean, "raw": string } ],\n'
    '  "confidence": number   // 0..1\n'
    "}\n\n"
    "Rules:\n"
    "- is_signal=false if the message is just chat, news, education, or NOT a trade signal.\n"
    "- When entry is a single value (not a range): set BOTH entry_low and entry_high to that same value.\n"
    "- When entry is a range like '4340-4337' or '4340 - 4337': entry_low=min, entry_high=max.\n"
    "- A TP marked as 'OUVERT', 'OPEN', 'RUNNER', 'TRAIL', 'OPEN-ENDED', '∞', 'OPEN TP' has value=null and runner=true.\n"
    "- Numeric TPs have runner=false and a numeric value.\n"
    "- 'raw' inside tp is the original substring (e.g. 'TP1: 4343', 'TP2: OUVERT').\n"
    "- side BUY = LONG / ACHAT / BUY. side SELL = SHORT / VENTE / SELL.\n"
    "- Confidence: 0.9+ if all fields clear, 0.6-0.8 if some inference needed, <0.5 if ambiguous.\n"
    "- If you cannot find a clear BUY/SELL keyword, is_signal=false.\n"
    "- Output ONLY the JSON object, nothing else."
)


def _normalize_symbol(raw_symbol: Optional[str]) -> Optional[str]:
    if not raw_symbol:
        return None
    s = raw_symbol.strip().upper().replace(" ", "").replace("/", "").replace("-", "")
    if s in _SYMBOL_ALIASES:
        return _SYMBOL_ALIASES[s]
    # Long form aliases
    for k, v in _SYMBOL_ALIASES.items():
        if s.startswith(k):
            return v
    return s


def _fallback_regex_parse(text: str) -> dict:
    """Lightweight regex fallback for the RentaTrade-style format."""
    upper = text.upper()
    side = None
    if re.search(r"\b(BUY|LONG|ACHAT)\b", upper):
        side = "BUY"
    elif re.search(r"\b(SELL|SHORT|VENTE)\b", upper):
        side = "SELL"

    # Symbol = first ticker-like token (3-6 alphanum, optionally suffix)
    sym_m = re.search(r"\b(BUY|SELL|LONG|SHORT|ACHAT|VENTE)\s+([A-Z0-9]{3,8})\b", upper)
    raw_symbol = sym_m.group(2) if sym_m else None

    # Entry: 'ENTRY[ :]*<num>[-<num>]?'
    entry_low = entry_high = None
    e_m = re.search(r"ENTRY[^0-9-]*([0-9]+(?:[\.,][0-9]+)?)\s*(?:[-–—]\s*([0-9]+(?:[\.,][0-9]+)?))?", upper)
    if e_m:
        a = float(e_m.group(1).replace(",", "."))
        b = float(e_m.group(2).replace(",", ".")) if e_m.group(2) else a
        entry_low, entry_high = min(a, b), max(a, b)

    sl_m = re.search(r"SL[^0-9-]*([0-9]+(?:[\.,][0-9]+)?)", upper)
    sl = float(sl_m.group(1).replace(",", ".")) if sl_m else None

    tps = []
    for m in re.finditer(r"TP\s*\d*\s*[:=]?\s*([^\n\r]+)", upper):
        token = m.group(1).strip()
        runner_kw = re.search(r"\b(OUVERT|OPEN|RUNNER|TRAIL)\b", token)
        num_m = re.search(r"([0-9]+(?:[\.,][0-9]+)?)", token)
        if runner_kw:
            tps.append({"value": None, "runner": True, "raw": m.group(0).strip()})
        elif num_m:
            tps.append({"value": float(num_m.group(1).replace(",", ".")), "runner": False, "raw": m.group(0).strip()})

    is_signal = bool(side and raw_symbol and sl and tps)
    return {
        "is_signal": is_signal,
        "symbol": raw_symbol,
        "side": side,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "sl": sl,
        "tps": tps,
        "confidence": 0.6 if is_signal else 0.1,
    }


async def parse_signal(text: str) -> dict:
    """Parse a Telegram message into a structured signal. Always returns a dict."""
    out_base = {
        "is_signal": False,
        "symbol": None,
        "side": None,
        "entry": None,
        "entry_low": None,
        "entry_high": None,
        "sl": None,
        "tps": [],
        "confidence": 0.0,
        "raw_excerpt": (text or "")[:400],
    }
    if not text or len(text.strip()) < 6:
        return out_base

    raw = None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        key = os.environ.get("EMERGENT_LLM_KEY")
        if not key:
            raise RuntimeError("EMERGENT_LLM_KEY missing")
        chat = (
            LlmChat(api_key=key, session_id="telegram-parser", system_message=_SYSTEM_PROMPT)
            .with_model("anthropic", "claude-sonnet-4-5-20250929")
        )
        msg = UserMessage(text=f"PARSE THIS:\n```\n{text}\n```")
        resp = await chat.send_message(msg)
        # Extract JSON
        m = re.search(r"\{[\s\S]*\}", resp or "")
        if m:
            raw = json.loads(m.group(0))
    except Exception as e:
        logger.warning("LLM parse failed (%s) -> fallback regex", e)
        raw = None

    if not raw:
        raw = _fallback_regex_parse(text)

    # Normalize symbol -> MT5 form (best effort, broker prefix added later at exec)
    raw_symbol = raw.get("symbol")
    norm_symbol = _normalize_symbol(raw_symbol)

    el = raw.get("entry_low")
    eh = raw.get("entry_high")
    entry_mid = None
    if el is not None and eh is not None:
        try:
            entry_mid = (float(el) + float(eh)) / 2.0
        except Exception:
            entry_mid = None
    elif el is not None:
        try:
            entry_mid = float(el)
        except Exception:
            entry_mid = None

    tps = []
    for t in (raw.get("tps") or [])[:6]:
        if not isinstance(t, dict):
            continue
        tps.append({
            "value": t.get("value"),
            "runner": bool(t.get("runner")),
            "raw": t.get("raw") or "",
        })

    out_base.update({
        "is_signal": bool(raw.get("is_signal") and norm_symbol and raw.get("side") in ("BUY", "SELL") and raw.get("sl") is not None and len(tps) > 0),
        "symbol": norm_symbol,
        "side": raw.get("side"),
        "entry": entry_mid,
        "entry_low": el,
        "entry_high": eh,
        "sl": raw.get("sl"),
        "tps": tps,
        "confidence": float(raw.get("confidence") or 0.0),
    })
    return out_base
