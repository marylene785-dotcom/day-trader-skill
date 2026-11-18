#!/usr/bin/env python3
"""QG Claude: etudie les facons de gagner de l'argent avec Claude et ses connecteurs.

Bibliotheque standard uniquement, Python 3.8+. Tout l'etat vit dans un dossier
qg/ du projet (modifiable avec --dir).

  python3 qg.py init                       # cree qg/profil.json a partir de l'exemple
  python3 qg.py connecteurs                # ce que chaque connecteur permet, connecte ou non
  python3 qg.py etude [--top 5] [--write]  # classe les opportunites selon ton profil
  python3 qg.py fiche <id>                 # detail + plan de 30 jours
  python3 qg.py manque                     # quel connecteur ajouter en premier
  python3 qg.py journal add --id X --revenu 120 --cout 30 --heures 5 --note "..."
  python3 qg.py journal                    # les entrees
  python3 qg.py bilan                      # net, EUR/heure, objectif du mois, quoi arreter
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RISQUES = {"faible": 0, "moyen": 1, "eleve": 2}
PIVOT_JOURS = 30


def charger(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ecrire(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def catalogue():
    return charger(os.path.join(HERE, "opportunites.json"))["opportunites"]


def connecteurs():
    return charger(os.path.join(HERE, "connecteurs.json"))["connecteurs"]


def profil(qg_dir):
    path = os.path.join(qg_dir, "profil.json")
    if not os.path.exists(path):
        path = os.path.join(HERE, "profil.example.json")
    p = charger(path)
    p.setdefault("connecteurs", [])
    p.setdefault("heures_semaine", 10)
    p.setdefault("budget_depart_eur", 0)
    p.setdefault("objectif_mensuel_eur", 500)
    p.setdefault("competences", [])
    p.setdefault("risque_max", "moyen")
    return p


def eur(x):
    s = "{:,.0f}".format(x).replace(",", " ")
    return s + " EUR"


# ---------------------------------------------------------------- scoring

def noter(o, p):
    """Score 0-100 et raisons. Les poids: potentiel 30, vitesse 20, cout 10,
    temps 10, difficulte 10, risque 10, competences 10."""
    have = set(p["connecteurs"])
    manquants = [c for c in o["requis"] if c not in have]
    bonus = [c for c in o["optionnels"] if c in have]
    alertes = []

    bas, haut = o["revenu_mensuel_eur"]
    milieu = (bas + haut) / 2.0
    objectif = max(float(p["objectif_mensuel_eur"]), 1.0)
    potentiel = 30 * min(milieu / objectif, 2.0) / 2.0

    vitesse = 20 * max(0.0, 1 - o["jours_premier_euro"] / 120.0)

    budget = float(p["budget_depart_eur"])
    cout = o["cout_depart_eur"]
    if cout == 0:
        s_cout = 10.0
    elif budget <= 0:
        s_cout = 0.0
    else:
        s_cout = 10 * max(0.0, 1 - min(cout / budget, 1.0))
    if cout > budget:
        alertes.append("cout de depart %s au-dessus de ton budget %s" % (eur(cout), eur(budget)))

    h, hmin = float(p["heures_semaine"]), float(o["heures_min_semaine"])
    s_temps = 10.0 if h >= hmin else 10 * h / hmin
    if h < hmin:
        alertes.append("demande %g h/semaine, tu en as %g" % (hmin, h))

    s_diff = 10 * (5 - o["difficulte"]) / 4.0

    r = RISQUES[o["risque"]]
    s_risque = 10 - 5 * r
    if r > RISQUES.get(p["risque_max"], 1):
        s_risque -= 10
        alertes.append("risque %s au-dessus de ton maximum (%s)" % (o["risque"], p["risque_max"]))

    comp = o.get("competences", [])
    if comp:
        s_comp = 10.0 * len([c for c in comp if c in p["competences"]]) / len(comp)
    else:
        s_comp = 10.0

    total = potentiel + vitesse + s_cout + s_temps + s_diff + s_risque + s_comp
    total = max(0.0, min(100.0, total + min(len(bonus), 2)))  # petit bonus connecteurs optionnels
    return {
        "id": o["id"], "nom": o["nom"], "score": round(total, 1),
        "statut": "bloque" if manquants else "pret",
        "manquants": manquants, "bonus_connecteurs": bonus, "alertes": alertes,
        "revenu_mensuel_eur": o["revenu_mensuel_eur"], "jours_premier_euro": o["jours_premier_euro"],
        "cout_depart_eur": cout, "risque": o["risque"],
        "detail": {"potentiel": round(potentiel, 1), "vitesse": round(vitesse, 1), "cout": round(s_cout, 1),
                   "temps": round(s_temps, 1), "difficulte": round(s_diff, 1), "risque": round(s_risque, 1),
                   "competences": round(s_comp, 1)},
    }


def etude(p):
    notes = [noter(o, p) for o in catalogue()]
    notes.sort(key=lambda n: (n["statut"] != "pret", -n["score"]))
    return notes


def manque(p):
    """Pour chaque connecteur absent: les opportunites qu'il debloquerait a lui seul."""
    noms = {c["id"]: c["nom"] for c in connecteurs()}
    gains = {}
    for n in etude(p):
        if len(n["manquants"]) == 1:
            c = n["manquants"][0]
            g = gains.setdefault(c, {"id": c, "nom": noms.get(c, c), "debloque": [], "valeur": 0.0})
            g["debloque"].append(n["id"])
            g["valeur"] += n["score"]
    return sorted(gains.values(), key=lambda g: -g["valeur"])


# ---------------------------------------------------------------- affichage

def ligne(n):
    bas, haut = n["revenu_mensuel_eur"]
    return "%5.1f  %-26s %-7s %s a %s/mois, 1er euro ~%d j, depart %s, risque %s" % (
        n["score"], n["id"], n["statut"], eur(bas), eur(haut), n["jours_premier_euro"],
        eur(n["cout_depart_eur"]), n["risque"])


def rapport_md(p, notes, top):
    jour = dt.date.today().isoformat()
    out = ["# QG Claude: etude du %s" % jour, "",
           "Connecteurs: %s. Temps: %g h/semaine. Budget: %s. Objectif: %s/mois." % (
               ", ".join(p["connecteurs"]) or "aucun", p["heures_semaine"],
               eur(p["budget_depart_eur"]), eur(p["objectif_mensuel_eur"])), "",
           "## Pret a lancer", "", "| score | opportunite | revenu/mois (indicatif) | 1er euro | alertes |",
           "| --- | --- | --- | --- | --- |"]
    for n in [x for x in notes if x["statut"] == "pret"][:top]:
        bas, haut = n["revenu_mensuel_eur"]
        out.append("| %.1f | %s | %s a %s | ~%d j | %s |" % (
            n["score"], n["nom"], eur(bas), eur(haut), n["jours_premier_euro"], "; ".join(n["alertes"]) or "-"))
    bloques = [x for x in notes if x["statut"] == "bloque"]
    if bloques:
        out += ["", "## Bloque par un connecteur manquant", ""]
        for n in bloques:
            out.append("- %s: il manque %s" % (n["nom"], ", ".join(n["manquants"])))
    m = manque(p)
    if m:
        out += ["", "## Prochain connecteur a ajouter", "",
                "%s, qui debloque: %s." % (m[0]["nom"], ", ".join(m[0]["debloque"]))]
    out += ["", "Chiffres indicatifs, pas des promesses. Remplace-les par les tiens via le journal.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- journal

def journal_path(qg_dir):
    return os.path.join(qg_dir, "journal.json")


def lire_journal(qg_dir):
    path = journal_path(qg_dir)
    return charger(path) if os.path.exists(path) else []


def bilan(entrees, objectif, aujourd_hui=None):
    today = aujourd_hui or dt.date.today()
    par = {}
    for e in entrees:
        b = par.setdefault(e["id"], {"id": e["id"], "revenu": 0.0, "cout": 0.0, "heures": 0.0, "debut": e["date"]})
        b["revenu"] += e.get("revenu", 0)
        b["cout"] += e.get("cout", 0)
        b["heures"] += e.get("heures", 0)
        b["debut"] = min(b["debut"], e["date"])
    lignes = []
    for b in sorted(par.values(), key=lambda x: -(x["revenu"] - x["cout"])):
        b["net"] = round(b["revenu"] - b["cout"], 2)
        b["eur_heure"] = round(b["net"] / b["heures"], 2) if b["heures"] else None
        b["jours"] = (today - dt.date.fromisoformat(b["debut"])).days
        if b["jours"] >= PIVOT_JOURS and b["revenu"] == 0:
            b["verdict"] = "a pivoter ou arreter (%d jours sans revenu)" % b["jours"]
        elif b["eur_heure"] is not None and b["eur_heure"] < 0:
            b["verdict"] = "perd de l'argent"
        else:
            b["verdict"] = "continuer"
        lignes.append(b)
    mois = today.strftime("%Y-%m")
    net_mois = sum(e.get("revenu", 0) - e.get("cout", 0) for e in entrees if e["date"].startswith(mois))
    return {"projets": lignes, "mois": mois, "net_mois": round(net_mois, 2), "objectif": objectif,
            "progression": round(100.0 * net_mois / objectif, 1) if objectif else None}


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description="QG Claude: gagner de l'argent avec Claude et ses connecteurs")
    ap.add_argument("--dir", default="qg", help="dossier d'etat (defaut: qg)")
    ap.add_argument("--json", action="store_true", help="sortie JSON")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("init")
    sub.add_parser("connecteurs")
    e = sub.add_parser("etude")
    e.add_argument("--top", type=int, default=5)
    e.add_argument("--write", action="store_true", help="ecrit qg/etude.json et qg/etude.md")
    f = sub.add_parser("fiche")
    f.add_argument("id")
    sub.add_parser("manque")
    j = sub.add_parser("journal")
    j.add_argument("action", nargs="?", default="voir", choices=["voir", "add"])
    j.add_argument("--id")
    j.add_argument("--revenu", type=float, default=0.0)
    j.add_argument("--cout", type=float, default=0.0)
    j.add_argument("--heures", type=float, default=0.0)
    j.add_argument("--date", default=None)
    j.add_argument("--note", default="")
    sub.add_parser("bilan")
    a = ap.parse_args(argv)
    p = profil(a.dir)

    if a.cmd == "init":
        dest = os.path.join(a.dir, "profil.json")
        if os.path.exists(dest):
            print("%s existe deja." % dest)
        else:
            os.makedirs(a.dir, exist_ok=True)
            shutil.copy(os.path.join(HERE, "profil.example.json"), dest)
            print("Cree %s: adapte connecteurs, heures, budget, objectif." % dest)
        return 0

    if a.cmd == "connecteurs":
        rows = [dict(c, connecte=c["id"] in p["connecteurs"]) for c in connecteurs()]
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for c in rows:
                print("[%s] %-20s %-16s %s" % ("x" if c["connecte"] else " ", c["nom"], c["categorie"], c["argent"]))
        return 0

    if a.cmd == "etude":
        notes = etude(p)
        if a.write:
            ecrire(os.path.join(a.dir, "etude.json"), {"date": dt.date.today().isoformat(), "profil": p,
                                                        "classement": notes, "manque": manque(p)})
            with open(os.path.join(a.dir, "etude.md"), "w", encoding="utf-8") as fh:
                fh.write(rapport_md(p, notes, a.top))
        if a.json:
            print(json.dumps(notes, ensure_ascii=False, indent=2))
            return 0
        prets = [n for n in notes if n["statut"] == "pret"]
        print("PRET A LANCER (top %d sur %d)" % (min(a.top, len(prets)), len(prets)))
        for n in prets[:a.top]:
            print(ligne(n))
            for al in n["alertes"]:
                print("       ! " + al)
        bl = [n for n in notes if n["statut"] == "bloque"]
        if bl:
            print("\nBLOQUE")
            for n in bl:
                print("%5.1f  %-26s il manque: %s" % (n["score"], n["id"], ", ".join(n["manquants"])))
        print("\nIndicatif, non garanti. Detail: qg.py fiche <id>.")
        return 0

    if a.cmd == "fiche":
        o = next((x for x in catalogue() if x["id"] == a.id), None)
        if o is None:
            print("Inconnu: %s. Ids: %s" % (a.id, ", ".join(x["id"] for x in catalogue())), file=sys.stderr)
            return 2
        n = noter(o, p)
        if a.json:
            print(json.dumps(dict(o, note=n), ensure_ascii=False, indent=2))
            return 0
        print("%s  [%s, score %.1f]\n%s\n" % (o["nom"], n["statut"], n["score"], o["resume"]))
        print("Connecteurs requis: %s" % (", ".join(o["requis"]) or "aucun"))
        if n["manquants"]:
            print("  il te manque: %s" % ", ".join(n["manquants"]))
        print("Optionnels: %s" % ", ".join(o["optionnels"]))
        bas, haut = o["revenu_mensuel_eur"]
        print("Revenu indicatif apres ~3 mois: %s a %s/mois. Premier euro: ~%d jours. Depart: %s." % (
            eur(bas), eur(haut), o["jours_premier_euro"], eur(o["cout_depart_eur"])))
        print("\nPlan de 30 jours:")
        for s in o["plan"]:
            print("  - " + s)
        print("\nPieges:")
        for s in o["pieges"]:
            print("  - " + s)
        print("\nCadre legal: " + o["legal"])
        for al in n["alertes"]:
            print("! " + al)
        return 0

    if a.cmd == "manque":
        m = manque(p)
        if a.json:
            print(json.dumps(m, ensure_ascii=False, indent=2))
        elif not m:
            print("Aucune opportunite n'est bloquee par un seul connecteur.")
        else:
            for g in m:
                print("%-20s debloque %s" % (g["nom"], ", ".join(g["debloque"])))
        return 0

    if a.cmd == "journal":
        entrees = lire_journal(a.dir)
        if a.action == "add":
            ids = set(x["id"] for x in catalogue())
            if not a.id:
                print("--id requis", file=sys.stderr)
                return 2
            if a.id not in ids:
                print("Note: %s n'est pas dans le catalogue, enregistre quand meme." % a.id)
            e = {"date": a.date or dt.date.today().isoformat(), "id": a.id, "revenu": a.revenu,
                 "cout": a.cout, "heures": a.heures, "note": a.note}
            entrees.append(e)
            ecrire(journal_path(a.dir), entrees)
            print("Ajoute: %s %s +%s -%s %gh" % (e["date"], e["id"], eur(a.revenu), eur(a.cout), a.heures))
            return 0
        if a.json:
            print(json.dumps(entrees, ensure_ascii=False, indent=2))
        else:
            for e in entrees:
                print("%s  %-22s +%-10s -%-10s %5gh  %s" % (e["date"], e["id"], eur(e["revenu"]),
                                                          eur(e["cout"]), e["heures"], e.get("note", "")))
            if not entrees:
                print("Journal vide. qg.py journal add --id <id> --revenu ... --cout ... --heures ...")
        return 0

    if a.cmd == "bilan":
        b = bilan(lire_journal(a.dir), float(p["objectif_mensuel_eur"]))
        if a.json:
            print(json.dumps(b, ensure_ascii=False, indent=2))
            return 0
        for x in b["projets"]:
            print("%-22s net %-10s %s  %d j  -> %s" % (
                x["id"], eur(x["net"]),
                ("%s/h" % eur(x["eur_heure"])) if x["eur_heure"] is not None else "-/h",
                x["jours"], x["verdict"]))
        print("\n%s: net %s sur un objectif de %s (%s %%)." % (
            b["mois"], eur(b["net_mois"]), eur(b["objectif"]), b["progression"]))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
