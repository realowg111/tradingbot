# Déploiement VPS - Trading Bot

Guide complet de déploiement du bot de trading 24/7 sur un VPS Linux (Ubuntu 22.04 / Debian 12 recommandé).

## 🎯 VPS recommandés

| Provider | Plan | Prix/mois | RAM | CPU | Stockage |
|---|---|---|---|---|---|
| **Hetzner CX22** | Cloud | ~5€ | 4 Go | 2 vCPU | 40 Go SSD |
| **Contabo VPS S** | SSD | ~6€ | 8 Go | 4 vCPU | 50 Go NVMe |
| **OVH VPS Starter** | SSD | ~4€ | 2 Go | 1 vCPU | 40 Go |
| **DigitalOcean** | Basic | ~6$ | 1 Go | 1 vCPU | 25 Go |

> **Note MT5** : MetaTrader 5 nécessite Windows. Pour un VPS **Linux** (recommandé pour 24/7), MT5 ne peut tourner qu'avec Wine (instable) ou via un bridge depuis un PC/VPS Windows. Le bot fournit déjà un **simulateur interne** (paper trading) qui ne nécessite **aucun broker** pour fonctionner.

## 🚀 Installation rapide (Ubuntu 22.04 / Debian 12)

```bash
# 1. Connectez-vous en root au VPS
ssh root@VOTRE_IP_VPS

# 2. Téléchargez et lancez le script
curl -fsSL https://votre-domaine/install.sh -o install.sh
chmod +x install.sh
bash install.sh
```

Le script installe automatiquement :

- ✅ Python 3.11, Node.js 20 LTS
- ✅ MongoDB 7
- ✅ Service systemd `trading-bot` avec **Restart=always**
- ✅ Nginx reverse proxy (port 80 → 8001)
- ✅ UFW (firewall : SSH + HTTP/HTTPS uniquement)
- ✅ Fail2ban (anti brute-force SSH)
- ✅ Hardening systemd (NoNewPrivileges, PrivateTmp, ProtectHome…)
- ✅ Cron de redémarrage de sécurité (5h du matin)

## 📦 Déploiement manuel du code

```bash
# Sur le VPS, en tant que root après avoir lancé le script
cd /opt/trading-bot
# Clonez ou uploadez votre dossier backend ici
git clone https://votre-repo.git backend

# Créez le .env (clés différentes de la prod !)
cat > /opt/trading-bot/backend/.env <<EOF
MONGO_URL=mongodb://localhost:27017
DB_NAME=trading_bot
JWT_SECRET_KEY=$(openssl rand -base64 48)
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
AES_SECRET_KEY_BASE64=$(openssl rand -base64 32)
ADMIN_EMAIL=vous@exemple.com
ADMIN_PASSWORD=MotDePasseSolide123!
EOF

chown -R botuser:botuser /opt/trading-bot

# Installation Python deps
sudo -u botuser /opt/trading-bot/venv/bin/pip install -r /opt/trading-bot/backend/requirements.txt

# Démarrage
systemctl start trading-bot
systemctl status trading-bot
```

## 🔍 Monitoring

```bash
# Logs en direct
journalctl -u trading-bot -f

# Logs fichier
tail -f /var/log/trading-bot.log

# Status
systemctl status trading-bot

# Test API
curl http://localhost/api/health
```

## 🔐 HTTPS (recommandé)

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d votre-domaine.com
```

## 💰 Coûts estimés / mois

À ajouter dans le module **Coûts** de l'app :

| Poste | Estimation |
|---|---|
| VPS Linux (Hetzner CX22) | 5 € / mois |
| Domaine .com | 1 € / mois |
| MongoDB Atlas (si externalisé) | 0 € (free tier) ou 9 €+ |
| Données marché (si broker premium) | 0–30 € / mois |
| Maintenance / monitoring | variable |
| **TOTAL minimum** | **~6–10 € / mois** |

## 🛡️ Sécurité post-installation

1. **Désactivez le login root par mot de passe** dans `/etc/ssh/sshd_config` :
   ```
   PermitRootLogin prohibit-password
   PasswordAuthentication no
   ```
2. **Créez un utilisateur sudo non-root** pour vos accès SSH habituels.
3. **Sauvegardez régulièrement** MongoDB : `mongodump --out /backups/$(date +%F)`.
4. **Rotez les clés JWT/AES** annuellement (nécessite migration des credentials chiffrés).
5. **Activez les mises à jour automatiques** : `unattended-upgrades`.

## 🔄 Récupération après crash

systemd assure le redémarrage automatique. Pour vérifier la persistance d'état :

```bash
# L'état du bot est stocké dans MongoDB (collections bot_state, bot_config)
# Après crash, le bot reprend où il s'est arrêté.
# Vérifiez:
mongosh trading_bot --eval "db.bot_state.findOne()"
```

## 📞 Support

- Logs structurés JSON disponibles via `/api/audit/export?format=json`
- Métriques temps réel via `/api/bot/state`
