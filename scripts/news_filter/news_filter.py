"""Filtre de news avec Jev (TypeSafe).

Jev lit chaque news et répond à des questions simples (actif concerné, sens,
importance, fait confirmé ou rumeur). Ce script transforme ces réponses en un
avis par actif, avec des règles écrites ici en clair.

Usage :
    python3 news_filter.py --dry-run            # affiche la requête, sans appel API
    python3 news_filter.py                      # appelle l'API (TYPESAFE_API_KEY requis)
    python3 news_filter.py --news "texte..."    # une news précise
"""

import argparse
import json
import sys
from pathlib import Path

from questions import ASSETS, DIRECTION_MIN, NO, YES, build_questions

HERE = Path(__file__).parent


def decide(nouls: dict, choices: dict) -> dict:
    """Table de décision : réponses de Jev -> avis par actif.

    Avis possibles : ignorer, a_verifier, haussier, baissier, neutre.
    Une rumeur (fait non confirmé) n'est jamais plus qu'à vérifier.
    """
    confirmed = nouls["is_confirmed"]
    verdicts = {}
    for key in ASSETS:
        concerned = nouls[f"{key}_concerned"]
        if concerned < NO:
            continue  # actif non concerné : rien à afficher
        if concerned < YES:
            verdicts[key] = {"avis": "a_verifier", "raison": f"lien avec l'actif incertain ({concerned:.2f})"}
            continue

        probs = choices[f"{key}_direction"]
        up, down = probs["up"], probs["down"]
        major = nouls[f"{key}_major"] > YES
        if up >= DIRECTION_MIN:
            avis = "haussier"
        elif down >= DIRECTION_MIN:
            avis = "baissier"
        else:
            avis = "neutre"

        if avis != "neutre" and confirmed < YES:
            raison = "rumeur ou prévision" if confirmed < NO else "fait non confirmé"
            verdicts[key] = {"avis": "a_verifier", "raison": f"{avis} mais {raison}"}
            continue

        verdicts[key] = {
            "avis": avis,
            "majeur": major,
            "raison": f"hausse {up:.2f} / baisse {down:.2f}",
        }
    return verdicts


def ask_jev(client, news: str) -> tuple[dict, dict]:
    response = client.system_one(state={"news": news}, questions=build_questions())
    nouls = {name: a.noul for name, a in response.nouls.items()}
    choices = {name: a.probabilities for name, a in response.choices.items()}
    return nouls, choices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--news", help="une news à analyser (sinon sample_news.json)")
    parser.add_argument("--dry-run", action="store_true", help="affiche la requête sans appeler l'API")
    parser.add_argument("--log", type=Path, help="fichier JSONL où enregistrer requêtes et réponses")
    args = parser.parse_args()

    news_list = [args.news] if args.news else json.loads((HERE / "sample_news.json").read_text())

    if args.dry_run:
        payload = {"state": {"news": news_list[0]}, "questions": build_questions()}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"\n{len(payload['questions'])} questions par news, {len(news_list)} news.", file=sys.stderr)
        return 0

    try:
        from typesafe_sdk import TypeSafeClient, TypeSafeError
    except ImportError:
        print("SDK manquant : pip install typesafe-sdk", file=sys.stderr)
        return 1

    log = args.log.open("a") if args.log else None
    with TypeSafeClient() as client:
        for news in news_list:
            print(f"\n# {news}")
            try:
                nouls, choices = ask_jev(client, news)
            except TypeSafeError as e:
                # Un appel raté est une erreur, jamais un « non ».
                print(f"  ERREUR API : {e}")
                continue
            if log:
                log.write(json.dumps({"news": news, "nouls": nouls, "choices": choices}, ensure_ascii=False) + "\n")
            verdicts = decide(nouls, choices)
            if not verdicts:
                print("  aucun actif suivi concerné")
            for key, v in verdicts.items():
                tag = " (MAJEUR)" if v.get("majeur") else ""
                print(f"  {ASSETS[key]:<28} {v['avis']}{tag} — {v['raison']}")
    if log:
        log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
