"""Reinitialise le mot de passe admin dans MongoDB (a executer sur le VPS Windows).

Usage: C:\trading-bot\venv\Scripts\python.exe C:\trading-bot\reset_pw.py
"""
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from passlib.context import CryptContext
except Exception as e:
    print("ERREUR import:", e)
    print("Lancez: C:\\trading-bot\\venv\\Scripts\\pip.exe install passlib bcrypt pymongo python-dotenv")
    sys.exit(1)

# Charger le .env du backend (plusieurs emplacements possibles)
for cand in [
    r"C:\trading-bot\backend\.env",
    r"C:\trading-bot\.env",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", ".env"),
]:
    if os.path.exists(cand):
        load_dotenv(cand)
        print(f"[OK] .env charge: {cand}")
        break
else:
    print("[!] Aucun .env trouve, utilisation des valeurs par defaut")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "trading_bot")

NEW_EMAIL = "admin@trading.bot"
NEW_PASSWORD = "Trading2025!"

print(f"[OK] Connexion a MongoDB: {MONGO_URL} / base: {DB_NAME}")
client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
client.admin.command("ping")
db = client[DB_NAME]

print("\n--- Utilisateurs existants ---")
for u in db.users.find({}, {"email": 1, "is_admin": 1}):
    print(f"  - {u.get('email')} (admin: {u.get('is_admin', False)})")
print("------------------------------\n")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = pwd_ctx.hash(NEW_PASSWORD)

result = db.users.update_one(
    {"email": NEW_EMAIL},
    {
        "$set": {"password_hash": hashed, "is_admin": True},
        "$setOnInsert": {
            "id": str(uuid.uuid4()),
            "email": NEW_EMAIL,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    },
    upsert=True,
)

action = "cree" if result.upserted_id else "mis a jour"
print(f"[SUCCES] Compte admin {action} !")
print(f"  Email        : {NEW_EMAIL}")
print(f"  Mot de passe : {NEW_PASSWORD}")
print("\nVous pouvez maintenant vous connecter dans l'application.")
