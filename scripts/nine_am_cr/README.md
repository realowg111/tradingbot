# « 9am CR model » (TikTok @massimotsr)

Stratégie présentée comme « la seule à utiliser en 2026, elle se forme presque tous les jours ». Règles transcrites de la vidéo :
1. Sur l'unité d'1 heure, on marque le plus haut et le plus bas de la bougie de 8h (heure de New York).
2. Si la bougie de 9h touche d'abord le plus haut de 8h, on cherche une vente, avec pour objectif le plus bas de 8h. Si elle touche d'abord le plus bas, c'est un achat (miroir).
3. Entrée en bougies d'1 minute quand deux signaux apparaissent ensemble : un IFVG (une bougie clôture sous un fair value gap haussier) et un order block baissier (une bougie baissière clôture sous la dernière bougie haussière).
4. Stop sur le sommet atteint depuis le dépassement, objectif sur le bas de 8h. Un trade par jour.

Points que la vidéo laisse ouverts, testés dans une grille de 24 variantes : entrée avant 10h ou avant 11h, fair value gap de moins de 15, 30 ou 60 minutes, order block au plus bas ou à l'ouverture de la bougie, sortie forcée à 12h ou à 16h.

```
python3 nine_am_cr_backtest.py --qqq qqq.parquet --gold <brut HistData> --eurusd <brut OANDA>
```

## Résultats (1 % de risque par trade, rendements additionnés)

| Marché | Frais | Trades/an | Gagnants | R moyen | %/an | Avant 2019 | Depuis 2019 | Pire repli |
|---|---|---|---|---|---|---|---|---|
| Nasdaq (QQQ, 2014–2024) | sans | 96 | 33 % | +0,11 | +10,7 % | +2,5 % | +18,9 % | -38 % |
| Nasdaq | 0,01 % | 96 | 33 % | +0,06 | **+5,9 %** | +1,2 % | +10,6 % | **-61 %** |
| Or (2009–2026) | sans | 199 | 30 % | +0,08 | +16,5 % | +16,6 % | +16,2 % | -48 % |
| Or | ECN 0,007 % | 199 | 30 % | +0,01 | **+2,4 %** | +2,5 % | +2,2 % | **-87 %** |
| Or | standard 0,02 % | 199 | 30 % | -0,12 | -23,7 % | | | |
| EUR/USD (2009–2026) | sans | 208 | 26 % | +0,05 | +10,0 % | | | -123 % |
| EUR/USD | ECN 0,007 % | 208 | 26 % | -0,10 | **-21,5 %** | | | |

Grille de 24 variantes avec frais réalistes : Nasdaq toujours positif (de +4 à +9 %/an), or ECN toujours positif (de +0,3 à +9,7 %/an), EUR/USD toujours négatif (de -29 à -22 %/an).

Par année avec frais réalistes :
- Nasdaq : 2014 -4, 2015 +8, 2016 +3, 2017 +2, 2018 -3, 2019 -4, 2020 -21, 2021 +20, 2022 -15, 2023 +56.
- Or (ECN) : de -53 % (2018) à +38 % (2019) ; 2023, 2024 et 2025 sont négatives.

## Conclusion

- Le setup n'est pas du hasard : sans frais, il gagne un peu sur les trois marchés (+0,05 à +0,11 R par trade).
- Mais son stop est minuscule (0,06 à 0,32 % du prix), donc les frais pèsent très lourd. Sur l'EUR/USD, ils coûtent 0,12 R par trade et rendent la stratégie perdante. Sur l'or, il ne reste que +0,01 R avec un compte ECN, et elle perd avec un compte standard.
- Le Nasdaq est le meilleur cas, environ +6 %/an. Mais ce gain est irrégulier : environ +1 %/an jusqu'en 2018, et 2023 (+56 %) en fait la plus grande partie. La pire baisse atteint -61 %, avec 2 trades gagnants sur 3 perdus.
- « Elle se forme presque tous les jours » : vrai, entre 96 et 208 trades par an. Mais 67 à 74 % de ces trades perdent.
- Limite : QQQ entre 8h et 9h, c'est l'avant-séance, avec peu de volume. Les futures Nasdaq (NQ), que ces traders utilisent souvent, peuvent donner un résultat différent.

À comparer avec le momentum intraday sur le même Nasdaq (`../nasdaq_daytrade`) : +15,5 %/an, pire baisse -23 %, sur les mêmes données et avec les mêmes frais.
