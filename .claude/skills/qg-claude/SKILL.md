---
name: qg-claude
description: >-
  Le QG Claude. Etudie les moyens de gagner de l'argent avec Claude et les
  connecteurs qui s'y branchent (Shopify, Canva, Gmail, Notion, Perplexity
  Computer, GitHub, Claude Docs, Higgsfield, Stripe...). Fait l'inventaire
  des connecteurs reellement connectes, classe 15 opportunites (produits
  numeriques, print-on-demand, templates Notion, redaction freelance, contenu
  pour commerces, automatisations PME, skills Claude, gestion de boutiques,
  ebooks, formations, etudes de marche, assistant virtuel, pubs video IA,
  newsletter, pedagogie trading) selon ton temps, ton budget, ton objectif
  et ton niveau de risque, donne un plan de 30 jours connecteur par
  connecteur, dit quel connecteur ajouter ensuite, et tient un journal des
  revenus, couts et heures pour savoir quoi continuer ou arreter. Use when
  the user says "gagner de l'argent avec Claude", "QG", "quelle activite
  lancer", "side business", "revenus complementaires", "monetiser mes
  connecteurs", "quel connecteur ajouter", "bilan de mes projets", "make
  money with Claude", or "run the QG".
argument-hint: "[etude | fiche <id> | manque | journal | bilan]"
---

# qg-claude: le QG des revenus avec Claude

Le QG repond a trois questions, dans l'ordre:

1. **Avec ce que j'ai deja connecte, qu'est-ce que je peux lancer ?**
2. **Quel connecteur ajouter pour ouvrir de nouvelles pistes ?**
3. **Parmi ce que j'ai lance, qu'est-ce qui rapporte vraiment ?**

Outil dans ce dossier (Python standard, 3.8+, rien a installer):

```bash
python3 "${CLAUDE_SKILL_DIR}/qg.py" --help
```

Fichiers:

- `opportunites.json`: le catalogue (connecteurs requis et optionnels, cout de
  depart, heures, delai avant le premier euro, fourchette de revenu
  indicative, risque, plan de 30 jours, pieges, cadre legal en France).
- `connecteurs.json`: ce que chaque connecteur permet et a quoi il sert pour
  gagner de l'argent.
- `qg/profil.json` (dans le projet): tes connecteurs, heures par semaine,
  budget de depart, objectif mensuel, competences, risque maximum.
- `qg/etude.json`, `qg/etude.md`: le dernier classement.
- `qg/journal.json`: tes vrais chiffres, entree par entree.

## Les regles

- **Pas de promesse.** Les fourchettes du catalogue sont des ordres de
  grandeur pour une personne seule apres environ 3 mois. Le bas de la
  fourchette est souvent 0. Dis-le a chaque etude. Les chiffres du journal
  remplacent ceux du catalogue des qu'ils existent.
- **Rien ne part sans un oui.** Un email s'ecrit en brouillon
  (`create_draft`), jamais `send_message` sans un oui explicite pour cet
  email precis. Pas de boutique, produit publie, remise, page Notion
  partagee ou design exporte vers un client sans accord. Les actions sur la
  boutique ou la boite mail d'un client exigent son accord ecrit.
- **Honnetete commerciale.** Jamais de faux avis, faux temoignages ou
  fausses urgences. Pas de prospection de particuliers sans consentement
  (RGPD); en B2B, un email pertinent avec un moyen de se desinscrire.
- **Pas de contrefacon.** Ni logos, ni personnages, ni oeuvres protegees
  dans les designs.
- **Trading: pedagogie seulement.** Pas de signaux ni de conseil
  personnalise (statut CIF, AMF). Not financial advice.
- **Declarer.** Tout revenu se declare (micro-entreprise en general). Le QG
  le rappelle, il ne remplace pas un comptable.

## Etape 1: inventaire des connecteurs

Appelle `ListConnectors` (chargee via ToolSearch si besoin). Retiens ceux qui
sont `connected: true`, traduis leurs noms en ids de `connecteurs.json`
(Shopify -> shopify, Perplexity Computer -> perplexity, etc.). GitHub et
Claude Docs comptent s'ils sont disponibles dans la session. Un connecteur
`connect_incomplete` (ex: Higgsfield) n'est pas connecte: dis a l'utilisateur
qu'il peut finir la connexion dans les reglages des connecteurs de Claude.

```bash
python3 "${CLAUDE_SKILL_DIR}/qg.py" init          # cree qg/profil.json
python3 "${CLAUDE_SKILL_DIR}/qg.py" connecteurs   # [x] = connecte dans le profil
```

Mets a jour `qg/profil.json`. S'il manque heures, budget ou objectif, pose
une seule question groupee; sinon garde les valeurs par defaut et dis-le.

## Etape 2: l'etude

```bash
python3 "${CLAUDE_SKILL_DIR}/qg.py" etude --top 5 --write
```

Score sur 100: potentiel par rapport a ton objectif (30), vitesse du premier
euro (20), cout de depart face au budget (10), temps disponible (10),
difficulte (10), risque (10), competences (10), plus un petit bonus par
connecteur optionnel deja branche. Une opportunite dont un connecteur requis
manque est **bloquee** et listee a part. Les alertes (budget, temps, risque)
s'affichent sous la ligne.

Si l'utilisateur veut des chiffres a jour, fais une recherche web rapide sur
les 3 premieres pistes (prix pratiques, demande, concurrence) et cite les
sources; ne modifie pas le catalogue sans le dire.

Presente le top 3 en clair: pourquoi il sort, combien de temps avant le
premier euro, ce qui peut rater. Recommande **une** piste, deux au maximum en
parallele.

## Etape 3: la fiche et le plan de 30 jours

```bash
python3 "${CLAUDE_SKILL_DIR}/qg.py" fiche redaction-freelance
```

Chaque semaine du plan nomme les outils des connecteurs a utiliser
(Shopify `generate-business-names`, `create-digital-product`,
`create-discount`, `run-analytics-query`; Canva `generate-design`,
`resize-design`, `export-design`; Gmail `create_draft`; Notion
`notion-create-database`, `notion-create-pages`; Claude Docs pour les
livrables; Perplexity Computer pour les tableaux de bord). Propose de creer
le plan dans Notion (une base "Pipeline QG" avec taches par semaine) si
l'utilisateur le veut.

## Etape 4: quel connecteur ajouter

```bash
python3 "${CLAUDE_SKILL_DIR}/qg.py" manque
```

Classe les connecteurs absents par la valeur des pistes qu'ils debloquent a
eux seuls. Pour en recommander un, cherche-le avec `SearchMcpRegistry` puis
montre-le avec `SuggestConnectors`. Ne dis jamais qu'un connecteur existe
sans l'avoir verifie.

## Etape 5: le journal et le bilan

```bash
python3 "${CLAUDE_SKILL_DIR}/qg.py" journal add --id redaction-freelance --revenu 250 --cout 0 --heures 6 --note "1er client"
python3 "${CLAUDE_SKILL_DIR}/qg.py" bilan
```

Le bilan donne par projet le net, les euros par heure, le nombre de jours
depuis le debut et un verdict: continuer, perd de l'argent, ou a pivoter
apres 30 jours sans revenu. Il compare le net du mois a l'objectif. Si
l'utilisateur vend sur Shopify, propose de lire les commandes du mois
(`list-orders`, `run-analytics-query`) pour remplir le journal sans saisie,
apres son accord.

Un bilan hebdomadaire peut tourner tout seul: propose `/loop` ou une tache
planifiee le lundi matin, seulement si l'utilisateur le demande.

## Etape 6: le tableau de bord (optionnel)

Sur demande, transforme `qg/etude.json` et le bilan en page Artifact
(classement, pistes bloquees, progression vers l'objectif). Elle peut ensuite
partir vers Perplexity Computer pour etre enrichie.

## Ce que le QG ne fait pas

- Il ne garantit aucun revenu et ne remplace ni un comptable ni un avocat.
- Il n'envoie, ne publie et n'achete rien sans un oui.
- Il ne connecte aucun service tout seul: il recommande, tu connectes.
