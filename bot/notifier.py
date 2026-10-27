"""Journal de bord : logs, fichier CSV des trades et notifications Telegram facultatives."""
from __future__ import annotations

import csv
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

log = logging.getLogger("bot")


def setup_logging(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in (RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"), logging.StreamHandler()):
        h.setFormatter(fmt)
        root.addHandler(h)


class Notifier:
    def __init__(self, cfg: dict):
        self.enabled = bool(cfg.get("enabled"))
        self.token = os.getenv("TELEGRAM_TOKEN", "")
        self.chat = os.getenv("TELEGRAM_CHAT_ID", "")

    def send(self, text: str) -> None:
        log.info(text.replace("\n", " | "))
        if not (self.enabled and self.token and self.chat):
            return
        try:
            import requests
            requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                          json={"chat_id": self.chat, "text": text}, timeout=10)
        except Exception as e:  # une notification ratée ne doit jamais bloquer le trading
            log.warning("Telegram : %s", e)


class Journal:
    FIELDS = ["closed_at", "symbol", "side", "setup", "score", "opened_at", "entry", "initial_sl",
              "volume", "risk_amount", "pnl", "r", "tp1_hit", "reason"]

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with self.path.open("w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, self.FIELDS).writeheader()

    def write(self, row: dict) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, self.FIELDS, extrasaction="ignore").writerow(row)
