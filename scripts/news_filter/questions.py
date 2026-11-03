"""Toutes les questions posées à Jev, et les seuils pour lire les réponses.

C'est le seul fichier à modifier pour changer la formulation ou les seuils.
Les questions sont en anglais (langue la plus sûre pour le modèle) ; les news
peuvent être en français ou en anglais.
"""

# Actifs suivis. La description donne au modèle les faits qu'il pourrait ignorer
# (ex. que XAUUSD désigne l'or).
ASSETS = {
    "gold": "Gold (XAUUSD, also PAXG)",
    "silver": "Silver (XAGUSD)",
    "btc": "Bitcoin (BTC)",
    "eth": "Ethereum (ETH)",
    "sol": "Solana (SOL)",
}

# Seuils de départ recommandés pour un Noul : > 0,7 = oui, < 0,3 = non,
# entre les deux = pas tranché.
YES = 0.7
NO = 0.3

# Probabilité minimale d'une direction pour la retenir.
DIRECTION_MIN = 0.6


def build_questions() -> dict:
    """Une seule requête par news : toutes les questions lisent la même news.

    Les questions de direction et d'importance sont posées pour chaque actif,
    même s'il n'est pas concerné (« question spéculative ») : le code ne lit
    leur réponse que si l'actif est concerné.
    """
    questions = {
        "is_confirmed": {
            "type": "noul",
            "instructions": "Does `news` report something that has already happened or been officially announced?",
            "criteria": {
                "true": "The news reports a published figure, an official decision, or an event that took place.",
                "false": "The news reports a rumor, an unnamed source, a forecast, or an analyst's opinion.",
            },
        },
    }
    for key, name in ASSETS.items():
        questions[f"{key}_concerned"] = {
            "type": "noul",
            "instructions": f"Does `news` give a reason for the price of {name} to move?",
            "criteria": {
                "true": f"The news is about {name} itself, or about something that directly drives its price.",
                "false": f"The news is about another market or topic with no direct link to {name}.",
            },
        }
        questions[f"{key}_direction"] = {
            "type": "choice",
            "instructions": f"Which way does `news` push the price of {name}?",
            "criteria": {
                "up": f"The news makes {name} more attractive to buyers.",
                "down": f"The news makes holders of {name} more likely to sell.",
                "no_clear_effect": f"The news has no clear effect on {name}, or its effects cancel out.",
            },
        }
        questions[f"{key}_major"] = {
            "type": "noul",
            "instructions": f"Is `news` a major event for {name}?",
            "criteria": {
                "true": f"Traders of {name} would treat this as a headline event, like a central bank rate decision or an exchange collapse.",
                "false": f"Traders of {name} would treat this as routine daily news.",
            },
        }
    return questions
