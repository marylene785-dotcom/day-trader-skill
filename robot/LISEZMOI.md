# Le robot d'alertes

Le robot surveille quelques actions américaines toutes les 5 minutes pendant
que la bourse de New York est ouverte (15 h 30 à 22 h, heure de Paris). Il vous
envoie une notification sur votre téléphone quand la règle dit :

- **ENTRÉE** : l'action vient de clôturer au-dessus du plus haut de ses
  15 premières minutes. La notification donne le prix d'entrée, le stop et
  l'objectif.
- **SORTIE : stop touché** : le prix est descendu jusqu'au stop.
- **SORTIE : objectif touché** : le prix est monté jusqu'à l'objectif.
- **SORTIE : fin de journée** : il est 21 h 55 à Paris (15 h 55 à New York),
  et la règle dit de tout fermer avant la clôture.

> **Le robot ne passe jamais d'ordre.** C'est un signal calculé par une règle,
> pas un conseil financier. La règle se trompe souvent, et la plupart des day
> traders perdent de l'argent. Les données Yahoo sont gratuites et peuvent
> avoir du retard. C'est toujours vous qui décidez, chez votre courtier.

## Installation (une seule fois)

1. **Python** : installez Python 3 depuis https://www.python.org/downloads/
   (sur Windows, cochez « Add Python to PATH »). Rien d'autre à installer.
2. **Le dépôt** : sur la page GitHub du dépôt, cliquez sur le bouton vert
   **Code**, puis **Download ZIP**, et décompressez-le, par exemple dans vos
   Documents.
3. **L'application ntfy** : installez l'application gratuite **ntfy** sur
   votre téléphone (App Store ou Google Play).
4. **Le réglage** : ouvrez un terminal (Windows : « Invite de commandes » ;
   Mac : « Terminal »), allez dans le dossier décompressé et lancez :

   ```
   cd Documents/day-trader-skill-main
   python3 robot/robot.py setup
   ```

   Sur Windows, tapez `python` au lieu de `python3`.

   Le robot affiche un nom de canal, comme `trader-robot-3f9a1c2b7d4e8a60`.
   Dans l'application ntfy, touchez **+** et abonnez-vous à ce nom. Une
   notification de test arrive sur votre téléphone. Gardez ce nom pour vous :
   toute personne qui le connaît peut lire vos alertes.

## Chaque jour de bourse

Avant 15 h 30 (heure de Paris), dans le même dossier :

```
python3 robot/robot.py run
```

Laissez la fenêtre ouverte et l'ordinateur allumé, sans mise en veille,
jusqu'à 22 h. Si vous le lancez plus tôt, il attend l'ouverture tout seul.
Pour l'arrêter, faites **Ctrl + C**.

Autres commandes :

| commande | ce qu'elle fait |
| --- | --- |
| `python3 robot/robot.py status` | les signaux du jour |
| `python3 robot/robot.py test` | renvoie une notification de test |
| `python3 robot/robot.py run --once` | un seul passage, puis s'arrête |

## Réglages

Ils sont dans `trader/robot.json`, à modifier avec n'importe quel éditeur de
texte :

| réglage | par défaut | rôle |
| --- | --- | --- |
| `symbols` | AAPL, MSFT, NVDA, AMZN, TSLA, META, GOOGL, AMD, NFLX, AVGO | les actions surveillées |
| `use_watchlist` | `false` | `true` : surveiller plutôt les actions trouvées par `/trader-scanner` |
| `max_signals_per_day` | `3` | au-delà, plus de nouvelle entrée ce jour-là |
| `target_r` | `2` | objectif = 2 fois la distance entre l'entrée et le stop |
| `flat_by` | `15:55` | heure de sortie, heure de New York |
| `no_entries_after` | `15:30` | plus de nouvelle entrée après cette heure, heure de New York |

## Les règles exactes

Le robot réutilise les règles des skills, sans les modifier :

- **Entrée** (`trader-entry`) : la plage d'ouverture correspond aux trois
  barres de 5 minutes de 9 h 30, 9 h 35 et 9 h 40, heure de New York. Le signal
  est donné à la clôture de la première barre qui termine au-dessus du plus
  haut de cette plage. Une simple mèche au-dessus ne compte pas. Il n'y a pas
  d'entrée avant 9 h 45 ni après 15 h 30.
- **Stop** (`trader-exit`) : le milieu de la plage d'ouverture, arrondi au
  centime inférieur. Le plan est refusé si le stop est trop serré.
- **Objectif** : 2R, c'est-à-dire l'entrée plus deux fois la distance entre
  l'entrée et le stop.
- **Si le stop et l'objectif sont touchés dans la même barre**, on ne sait pas
  lequel est venu en premier, donc le robot compte le stop.
- **Lancé en retard**, le robot ignore les signaux de plus de 15 minutes : il
  est trop tard pour eux.
- **Les jours fériés** et les fermetures anticipées à 13 h (New York) sont dans
  le calendrier. Ces jours-là, la sortie de fin de journée est donnée à
  12 h 55, heure de New York.
