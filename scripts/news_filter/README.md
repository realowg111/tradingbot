# Filtre de news avec Jev (TypeSafe)

Jev lit une news et répond à des questions fermées pour chacun des actifs suivis (or, argent, BTC, ETH, SOL). Le script transforme ensuite ces réponses en un avis par actif.

Jev ne décide pas d'acheter ou de vendre. Il donne des probabilités, et la décision est prise dans `decide()` avec des règles lisibles.

## Lancer

```
pip install typesafe-sdk
export TYPESAFE_API_KEY="ta_clé"
python3 news_filter.py                     # analyse sample_news.json
python3 news_filter.py --news "texte"      # une news précise
python3 news_filter.py --log runs.jsonl    # garde les réponses pour les rejouer
python3 news_filter.py --dry-run           # montre la requête, sans appel API ni clé
```

## Questions (une requête par news, `questions.py`)

| Question | Type | Rôle |
|---|---|---|
| `is_confirmed` | Noul | fait officiel ou rumeur/prévision |
| `<actif>_concerned` | Noul | la news concerne-t-elle cet actif ? |
| `<actif>_direction` | Choice | hausse / baisse / pas d'effet clair |
| `<actif>_major` | Noul | événement majeur ou routine |

## Table de décision (`decide()`)

| Concerné | Direction | Confirmé | Avis |
|---|---|---|---|
| < 0,3 | – | – | ignoré |
| 0,3 – 0,7 | – | – | à vérifier |
| > 0,7 | hausse ≥ 0,6 | > 0,7 | haussier |
| > 0,7 | baisse ≥ 0,6 | > 0,7 | baissier |
| > 0,7 | hausse ou baisse ≥ 0,6 | ≤ 0,7 | à vérifier (rumeur) |
| > 0,7 | aucune ≥ 0,6 | – | neutre |

Les seuils sont des valeurs de départ. Il faut les ajuster sur de vraies news, sans les caler sur quelques exemples.

## Prochaines étapes

- Tester sur une vraie série de news datées, et comparer l'avis au mouvement de prix des heures suivantes.
- Utiliser l'avis comme filtre du trend hedge (par exemple, ne pas ouvrir de short juste après une news haussière majeure), plutôt que comme signal seul.
