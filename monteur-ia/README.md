# Monteur IA — monter tes vidéos avec Claude Code

Tout ce que montre la vidéo « Monter avec Claude » (@melvynx.dev), prêt à l'emploi.
Ça tourne **sur ton ordinateur** (Mac, Windows ou Linux), pas sur le téléphone.

```
monteur-ia/
├── A-roll/        tes rushs (les prises brutes : rush-1.mov, prise-01.mp4…)
├── Références/    3-4 vidéos d'autres créateurs dont tu aimes le montage
└── Exports/       les vidéos finies arrivent ici
```

---

## Étape 1 — Installe

1. Installe l'app **Claude Code** (desktop) : https://claude.ai/download — pas la version web claude.ai.
2. Copie ce dossier `monteur-ia` sur ton ordinateur (ou clone le repo).
3. Dans Claude Code : **Nouvelle session** → environnement **Local** (pas Cloud) → **Choisir un dossier** → `monteur-ia`.

## Étape 2 — Les outils

| Outil | À quoi il sert |
|---|---|
| Skills de montage — github.com/Melvynx/video-agent-skills | Montent la vidéo |
| FFmpeg — github.com/FFmpeg/FFmpeg | Coupe et convertit |
| whisper.cpp — github.com/ggml-org/whisper.cpp | Ta voix en sous-titres |
| yt-dlp — github.com/yt-dlp/yt-dlp | Télécharge les vidéos |
| Chrome — google.com/chrome | Rend les animations |

**Option rapide** : lance `install-mac-linux.sh` (Mac/Linux) ou `install-windows.ps1` (Windows).

**Option vidéo** : colle ce prompt dans Claude Code :

```
Je veux que tu sois mon monteur vidéo.
Installe ces outils sur mon ordinateur :
1. Mes skills de montage : github.com/Melvynx/video-agent-skills
2. FFmpeg : github.com/FFmpeg/FFmpeg
3. whisper.cpp : github.com/ggml-org/whisper.cpp
4. yt-dlp : github.com/yt-dlp/yt-dlp
5. Chrome : google.com/chrome
Teste chacun d'eux, puis dis-moi quand tu es prêt.
```

Ensuite tape `/studio-setup` (≈15 min, une seule fois) : ton style, tes couleurs, tes polices, ta voix.

## Étape 3 — Ton style

Choisis 3-4 vidéos (Reels/TikTok) dont tu adores le montage, et colle :

```
Voici des vidéos dont j'adore le montage :
[TES LIENS]

Range-les dans Références, puis décortique-les
comme un monteur : typo, couleurs, sous-titres,
rythme des coupes, zooms, musique, bruitages.

Écris-moi un guide de montage d'une page, à mon
nom, qui garde cette énergie sans copier
personne.

Je le relis, et tu montes toutes mes vidéos avec.
```

Pour copier le style d'un créateur précis : `/steal <lien du reel>`.

## Étape 4 — Filme et monte

1. Filme-toi comme d'habitude (téléphone, webcam…) et mets la prise dans `A-roll/`.
2. Colle :

```
Monte ma nouvelle vidéo en reel Instagram :
[NOM DU FICHIER] dans mon dossier rushs
1. Coupe chaque pause de plus de 0,1 seconde.
2. Suis ma fiche de style.
3. Ajoute les sous-titres, la musique et les animations.
4. Utilise tout ce qu'il y a dans mon dossier références.
Montre-moi d'abord une page de review, puis
exporte la vidéo dans mon dossier exports.
```

3. Dans la page de review, commente ce qui ne te plaît pas (ex. « Titre plus gros » à 0:02), Claude corrige, puis exporte dans `Exports/`.

---

## Les skills utiles au quotidien

| Commande | Ce que ça fait |
|---|---|
| `/editing <ce que tu veux>` | Choisit le bon skill pour toi |
| `/short-editing` | Une prise brute → reel fini (coupes, sous-titres, musique, animations) |
| `/steal` | Copie le style de montage d'un autre créateur |
| `/broll` | Range tes plans de coupe et les place dans tes vidéos |
| `/clips` | Une longue vidéo → plusieurs shorts |
| `/studio-script` | Tes scripts de la semaine, avec hooks |
| `/publish` | Publie sur YouTube, Instagram, TikTok (avec ton accord) |

Note : les skills ont des noms récents (`/studio-setup`, `/short-editing`…). La vidéo montre aussi `studio` — c'est l'ancien nom.
