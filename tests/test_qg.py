import contextlib
import datetime as dt
import io
import json
import os
import re
import tempfile
import unittest

from _load import ROOT, load

QG = os.path.join(".claude", "skills", "qg-claude")
qg = load(QG, "qg")
BASE = {"connecteurs": ["canva", "gmail", "notion", "perplexity", "shopify", "github", "claude_docs"],
        "heures_semaine": 10, "budget_depart_eur": 200, "objectif_mensuel_eur": 500,
        "competences": ["redaction", "design"], "risque_max": "moyen"}


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = qg.main(list(argv))
    return code, out.getvalue()


class Catalogue(unittest.TestCase):
    def test_every_required_connector_is_described(self):
        known = set(c["id"] for c in qg.connecteurs())
        ids = [o["id"] for o in qg.catalogue()]
        self.assertEqual(len(ids), len(set(ids)))
        for o in qg.catalogue():
            for c in o["requis"] + o["optionnels"]:
                self.assertIn(c, known, o["id"])
            self.assertEqual(len(o["plan"]), 4, o["id"])
            self.assertLessEqual(o["revenu_mensuel_eur"][0], o["revenu_mensuel_eur"][1])
            self.assertIn(o["risque"], qg.RISQUES)
            self.assertTrue(o["legal"])

    def test_skill_frontmatter_and_safety(self):
        with open(os.path.join(ROOT, QG, "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        fm = re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1)
        self.assertIn("name: qg-claude\n", fm + "\n")
        low = " ".join(text.lower().split())
        self.assertIn("not financial advice", low)
        self.assertIn("create_draft", low)
        self.assertIn("pas de promesse", low)


class Scoring(unittest.TestCase):
    def test_missing_required_connector_blocks(self):
        notes = {n["id"]: n for n in qg.etude(dict(BASE))}
        self.assertEqual(notes["pubs-video-ia"]["statut"], "bloque")
        self.assertEqual(notes["pubs-video-ia"]["manquants"], ["higgsfield"])
        self.assertEqual(notes["produits-numeriques"]["statut"], "pret")

    def test_ready_ranked_before_blocked_and_sorted(self):
        notes = qg.etude(dict(BASE))
        statuts = [n["statut"] for n in notes]
        self.assertEqual(statuts, sorted(statuts, key=lambda s: s != "pret"))
        prets = [n["score"] for n in notes if n["statut"] == "pret"]
        self.assertEqual(prets, sorted(prets, reverse=True))
        for n in notes:
            self.assertTrue(0 <= n["score"] <= 100)

    def test_risk_above_max_is_flagged_and_penalised(self):
        o = next(x for x in qg.catalogue() if x["id"] == "education-trading")
        bas = qg.noter(o, dict(BASE))
        haut = qg.noter(o, dict(BASE, risque_max="eleve"))
        self.assertTrue(any("risque" in a for a in bas["alertes"]))
        self.assertLess(bas["score"], haut["score"])

    def test_budget_and_time_alerts(self):
        o = next(x for x in qg.catalogue() if x["id"] == "print-on-demand")
        n = qg.noter(o, dict(BASE, budget_depart_eur=50, heures_semaine=2))
        self.assertEqual(len(n["alertes"]), 2)

    def test_no_connectors_unblocks_nothing_but_newsletter(self):
        prets = [n["id"] for n in qg.etude(dict(BASE, connecteurs=[])) if n["statut"] == "pret"]
        self.assertEqual(prets, ["newsletter-niche"])

    def test_manque_suggests_higgsfield(self):
        m = qg.manque(dict(BASE))
        self.assertEqual(m[0]["id"], "higgsfield")
        self.assertIn("pubs-video-ia", m[0]["debloque"])


class Journal(unittest.TestCase):
    def test_bilan_verdicts(self):
        today = dt.date(2026, 11, 18)
        entrees = [
            {"date": "2026-10-01", "id": "templates-notion", "revenu": 0, "cout": 0, "heures": 3},
            {"date": "2026-11-10", "id": "redaction-freelance", "revenu": 250, "cout": 10, "heures": 6},
            {"date": "2026-11-12", "id": "print-on-demand", "revenu": 20, "cout": 80, "heures": 4},
        ]
        b = qg.bilan(entrees, 500, today)
        v = {p["id"]: p for p in b["projets"]}
        self.assertEqual(v["redaction-freelance"]["eur_heure"], 40.0)
        self.assertEqual(v["redaction-freelance"]["verdict"], "continuer")
        self.assertTrue(v["templates-notion"]["verdict"].startswith("a pivoter"))
        self.assertEqual(v["print-on-demand"]["verdict"], "perd de l'argent")
        self.assertEqual(b["net_mois"], 180.0)
        self.assertEqual(b["progression"], 36.0)

    def test_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run("--dir", d, "init")[0], 0)
            code, out = run("--dir", d, "etude", "--write")
            self.assertEqual(code, 0)
            self.assertIn("PRET A LANCER", out)
            with open(os.path.join(d, "etude.json"), encoding="utf-8") as fh:
                self.assertIn("classement", json.load(fh))
            self.assertTrue(os.path.exists(os.path.join(d, "etude.md")))
            run("--dir", d, "journal", "add", "--id", "redaction-freelance", "--revenu", "100", "--heures", "4")
            code, out = run("--dir", d, "--json", "bilan")
            self.assertEqual(json.loads(out)["projets"][0]["net"], 100.0)
            code, out = run("--dir", d, "fiche", "produits-numeriques")
            self.assertIn("Plan de 30 jours", out)


if __name__ == "__main__":
    unittest.main()
