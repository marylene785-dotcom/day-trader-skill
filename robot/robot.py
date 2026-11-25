#!/usr/bin/env python3
"""Le robot d'alertes : surveille une liste d'actions toutes les 5 minutes
pendant la séance de New York et envoie une alerte sur le téléphone quand la
règle du pack dit d'entrer ou de sortir. Bibliothèque standard seulement.

Il réutilise les règles des skills, sans les réécrire :
  - entrée  : trader-entry, cassure de la plage d'ouverture (le premier bar de
              5 minutes qui CLÔTURE au-dessus du plus haut des 15 premières minutes) ;
  - stop et objectif : trader-exit, stop au milieu de la plage d'ouverture,
              objectif à 2R (deux fois la distance entrée - stop) ;
  - sortie  : le stop touché, l'objectif touché, ou l'heure de fin (15:55 NY).

Il ne passe JAMAIS d'ordre. C'est un signal calculé par une règle, pas un
conseil financier : c'est vous qui décidez, chez votre courtier.

    python3 robot/robot.py setup        # crée trader/robot.json et votre canal ntfy, envoie un test
    python3 robot/robot.py test         # renvoie une notification de test
    python3 robot/robot.py run          # tourne en continu (laisser la fenêtre ouverte)
    python3 robot/robot.py run --once   # un seul passage, puis s'arrête
    python3 robot/robot.py status       # les signaux du jour

Notifications : ntfy (https://ntfy.sh), une application gratuite pour Android
et iPhone. Le robot publie sur un canal au nom aléatoire, gardé dans
trader/robot.json ; abonnez-vous à ce nom dans l'application.

Données : les barres de 5 minutes gratuites de Yahoo (non officielles, avec
parfois du retard). Ce ne sont pas des cotations en temps réel.
"""

import argparse
import datetime
import importlib.util
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load(folder, name):
    path = os.path.join(ROOT, folder, name + ".py")
    spec = importlib.util.spec_from_file_location("robot_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


entry = _load("trader-entry", "entry")
exitp = _load("trader-exit", "exit")

CONFIG = "trader/robot.json"
STATE = "trader/robot_state.json"
NTFY = "https://ntfy.sh"
DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "GOOGL", "AMD", "NFLX", "AVGO"]
DEFAULTS = {
    "symbols": DEFAULT_SYMBOLS,
    "use_watchlist": False,      # true : prendre les actions de trader/watchlist.json (trader-scanner)
    "watchlist_top": 10,
    "max_signals_per_day": 3,    # au-delà, le robot ne signale plus de nouvelles entrées ce jour-là
    "target_r": 2,
    "flat_by": "15:55",          # heure de New York
    "no_entries_after": "15:30",
    "ntfy_server": NTFY,
    "ntfy_topic": "",
}
STEP = 300          # barres de 5 minutes
GRACE = 20          # secondes après la clôture d'une barre avant de demander les données
STALE = 15          # minutes : un signal plus vieux que ça au premier coup d'œil est trop tard, on l'ignore
NOTE = ("Signal calculé par une règle, pas un conseil financier. Données Yahoo, parfois en retard. "
        "Rien n'est acheté ni vendu automatiquement.")


class RobotError(Exception):
    pass


# ---------------------------------------------------------------- fichiers

def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        raise RobotError("impossible de lire %s : %s" % (path, e))


def write_json(path, doc):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def load_config(path=CONFIG):
    cfg = dict(DEFAULTS)
    cfg.update(read_json(path, {}))
    cfg["symbols"] = [s.strip().upper() for s in cfg.get("symbols") or [] if s.strip()]
    return cfg


def symbols_for(cfg, watchlist="trader/watchlist.json"):
    if cfg.get("use_watchlist"):
        doc = read_json(watchlist, {})
        syms = [h["symbol"] for h in doc.get("hits", []) if h.get("symbol")]
        if syms:
            return syms[: int(cfg.get("watchlist_top") or 10)]
    return cfg["symbols"] or list(DEFAULT_SYMBOLS)


# ---------------------------------------------------------------- notifications

def send(cfg, title, message, priority=3, tags=None, opener=None):
    """Publie sur ntfy (JSON, pour que les accents passent). Renvoie True si c'est parti."""
    topic = cfg.get("ntfy_topic")
    print("\n=== %s ===\n%s\n" % (title, message), flush=True)
    if not topic:
        return False
    body = {"topic": topic, "title": title, "message": message, "priority": priority}
    if tags:
        body["tags"] = tags
    req = urllib.request.Request(cfg.get("ntfy_server") or NTFY, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    for attempt in (1, 2, 3):
        try:
            with (opener or urllib.request.urlopen)(req, timeout=15) as r:
                return 200 <= getattr(r, "status", 200) < 300
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:      # ntfy limite les rafales : on attend et on réessaie
                sleep(10 * attempt)
                continue
            print("(notification non envoyée : %s)" % e, file=sys.stderr)
            return False
        except (urllib.error.URLError, OSError) as e:
            print("(notification non envoyée : %s)" % e, file=sys.stderr)
            return False
    return False


def sleep(seconds):
    time.sleep(seconds)


def fmt(x):
    return ("%.2f" % float(x)).replace(".", ",") + " $"


# ---------------------------------------------------------------- la règle, barre par barre

def new_day(day):
    return {"date": day.isoformat(), "symbols": {}, "signals": 0}


def step_symbol(sym, chart, now_utc, st, cfg, day_state):
    """Fait avancer un symbole d'une étape. Renvoie la liste des alertes (titre, message, priorité, tags)."""
    alerts = []
    phase = st.get("phase", "watching")
    if phase in ("done", "skipped"):
        return alerts
    res = entry.evaluate(chart, now_utc, cfg={"no_entries_before": "09:45",
                                               "no_entries_after": cfg.get("no_entries_after", "15:30")})
    bars = res.get("_bars") or []
    local = entry.to_eastern(now_utc)

    if phase == "watching":
        if res["status"] == "expired":
            st["phase"] = "done"
            return alerts
        if res["status"] != "triggered":
            st["seen"] = True
            return alerts
        if day_state["signals"] >= int(cfg.get("max_signals_per_day") or 3):
            st.update(phase="skipped", why="limite de %s signaux par jour atteinte" % cfg.get("max_signals_per_day"))
            return alerts
        tr, rng = res["trigger"], res["opening_range"]
        if st.get("seen") is None and res.get("minutes_since", 0) > STALE:
            st.update(phase="skipped", why="signal déjà passé à %s quand le robot a démarré" % tr["close_time"])
            return alerts
        try:
            plan = exitp.compute(Decimal(str(tr["price"])), "or_mid", None, "r", Decimal(str(cfg.get("target_r", 2))),
                                 or_high=rng["high"], or_low=rng["low"])
        except exitp.PlanError as e:
            st.update(phase="skipped", why=str(e))
            return alerts
        day_state["signals"] += 1
        st.update(phase="in", entry=float(plan["entry"]), stop=float(plan["stop"]), target=float(plan["target"]),
                  trigger_bar=tr["bar_index"], trigger_time=tr["close_time"])
        last = bars[-1]["c"] if bars else tr["price"]
        late = res.get("minutes_since", 0)
        msg = ("Règle d'entrée : la barre de 5 minutes terminée à %s a clôturé à %s, au-dessus du plus haut des 15 premières minutes (%s).\n"
               "Stop (sortie si ça baisse) : %s\nObjectif (sortie si ça monte) : %s\n"
               "Perte max par action au stop : %s\nSortie au plus tard : %s heure de New York." % (
                   tr["close_time"], fmt(plan["entry"]), fmt(rng["high"]), fmt(plan["stop"]), fmt(plan["target"]),
                   fmt(plan["risk"]), cfg.get("flat_by", "15:55")))
        if late >= 10:
            msg += "\nAttention : signal d'il y a %d minutes, dernier cours %s." % (late, fmt(last))
        alerts.append(("ENTRÉE %s à %s" % (sym, fmt(plan["entry"])), msg + "\n\n" + NOTE, 4, ["chart_with_upwards_trend"]))
        phase = "in"

    if phase == "in":
        after = [b for b in bars if b["slot"] > st["trigger_bar"]]
        for b in after:
            hit_stop, hit_target = b["l"] <= st["stop"], b["h"] >= st["target"]
            if hit_stop or hit_target:
                # les deux dans la même barre : on ne sait pas lequel est venu en premier, on compte le stop
                kind = "stop" if hit_stop else "objectif"
                price = st["stop"] if hit_stop else st["target"]
                st.update(phase="done", exit=kind, exit_price=price, exit_time=entry.hm(b["end"]))
                alerts.append(("SORTIE %s : %s touché (%s)" % (sym, kind, fmt(price)),
                               "La barre de %s a touché %s %s (entrée selon la règle %s).\n\n%s" % (
                                   entry.hm(b["et"]), "le stop" if hit_stop else "l'objectif", fmt(price),
                                   fmt(st["entry"]), NOTE), 5 if hit_stop else 4,
                               ["warning"] if hit_stop else ["dart"]))
                return alerts
        flat = flat_by_time(local.date(), cfg)
        if local.time() >= flat:
            last = bars[-1]["c"] if bars else st["entry"]
            st.update(phase="done", exit="fin de journée", exit_price=last, exit_time=entry.hm(flat))
            alerts.append(("SORTIE %s : fin de journée" % sym,
                           "Il est %s à New York : la règle dit de sortir avant la clôture. Dernier cours %s "
                           "(entrée selon la règle %s).\n\n%s" % (entry.hm(flat), fmt(last), fmt(st["entry"]), NOTE),
                           4, ["alarm_clock"]))
    return alerts


def flat_by_time(day, cfg):
    t = entry.parse_hhmm(cfg.get("flat_by", "15:55"), "flat_by")
    _, close = entry.session(day)
    if close != entry.CLOSE:      # fermeture anticipée à 13:00 : 5 minutes avant
        return (datetime.datetime.combine(day, close) - datetime.timedelta(minutes=5)).time()
    return t


# ---------------------------------------------------------------- un passage, la boucle

def run_once(cfg, now_utc, state_path=STATE, get_chart=None, notify=None, offline=None):
    get_chart = get_chart or (lambda s: entry.get_chart(s, "5m", offline=offline,
                                                        today=entry.to_eastern(now_utc).date()))
    notify = notify or (lambda t, m, p, g: send(cfg, t, m, p, g))
    day = entry.to_eastern(now_utc).date()
    state = read_json(state_path, None)
    if not state or state.get("date") != day.isoformat():
        state = new_day(day)
    sent = 0
    for sym in symbols_for(cfg):
        st = state["symbols"].setdefault(sym, {"phase": "watching"})
        if st.get("phase") in ("done", "skipped"):
            continue
        try:
            chart = get_chart(sym)
        except entry.EntryError as e:
            print("%s : %s" % (sym, e), file=sys.stderr)
            continue
        for title, msg, prio, tags in step_symbol(sym, chart, now_utc, st, cfg, state):
            if sent and not offline:
                time.sleep(2)              # pas de rafale vers ntfy
            notify(title, msg, prio, tags)
            sent += 1
        time.sleep(0 if offline else entry.PAUSE)
    write_json(state_path, state)
    return state, sent


def market_window(now_utc):
    """(ouvert maintenant?, prochaine ouverture en UTC). Utilise le calendrier NYSE de trader-entry."""
    local = entry.to_eastern(now_utc)
    d = local.date()
    for _ in range(10):
        ok, _why = entry.trading_day(d)
        if ok:
            o, c = entry.session(d)
            open_dt = datetime.datetime.combine(d, o)
            close_dt = datetime.datetime.combine(d, c)
            if d == local.date() and local < close_dt + datetime.timedelta(minutes=1):
                return local >= open_dt, entry.eastern_to_utc(open_dt)
            if d > local.date():
                return False, entry.eastern_to_utc(open_dt)
        d += datetime.timedelta(days=1)
    raise RobotError("calendrier NYSE inconnu après %s" % local.date())


def seconds_to_next_bar(now_utc):
    ts = entry.ts_of(now_utc)
    return STEP - (ts % STEP) + GRACE


def cmd_run(a):
    cfg = load_config(a.config)
    if not cfg.get("ntfy_topic"):
        print("Pas de canal ntfy : les alertes s'afficheront seulement ici. Lancez d'abord : python3 robot/robot.py setup")
    syms = symbols_for(cfg)
    print("Robot démarré. Actions surveillées : %s" % ", ".join(syms))
    print(NOTE)
    while True:
        now = entry.utc_now()
        is_open, next_open = market_window(now)
        if not is_open:
            if a.once:
                print("Bourse de New York fermée. Prochaine ouverture : %s (heure de New York)."
                      % entry.to_eastern(next_open).strftime("%d/%m %H:%M"))
                return 1
            wait = max(60, (next_open - now).total_seconds())
            print("Bourse fermée. Je reprends à l'ouverture, %s heure de New York (dans %d h %02d)." % (
                entry.to_eastern(next_open).strftime("%d/%m %H:%M"), wait // 3600, (wait % 3600) // 60), flush=True)
            time.sleep(min(wait, 3600))
            continue
        state, sent = run_once(cfg, now, a.state)
        local = entry.to_eastern(now)
        print("%s NY : %d alerte(s), %d signal(aux) aujourd'hui." % (local.strftime("%H:%M"), sent, state["signals"]),
              flush=True)
        if a.once:
            return 0
        time.sleep(seconds_to_next_bar(entry.utc_now()))


def cmd_setup(a):
    cfg = read_json(a.config, {})
    if not cfg.get("ntfy_topic"):
        cfg["ntfy_topic"] = "trader-robot-" + secrets.token_hex(8)
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)
    write_json(a.config, cfg)
    print("Configuration écrite dans %s." % a.config)
    print("\n1. Installez l'application gratuite « ntfy » sur votre téléphone (App Store ou Google Play).")
    print("2. Dans l'application, touchez « + » et abonnez-vous à ce canal :\n\n      %s\n" % cfg["ntfy_topic"])
    print("   Gardez ce nom pour vous : toute personne qui le connaît peut lire vos alertes.")
    ok = send(load_config(a.config), "Robot trader : test", "Si vous lisez ceci, les alertes arrivent bien.", 3,
              ["white_check_mark"])
    print("Notification de test %s." % ("envoyée" if ok else "NON envoyée (vérifiez votre connexion)"))
    return 0 if ok else 1


def cmd_test(a):
    cfg = load_config(a.config)
    if not cfg.get("ntfy_topic"):
        print("Pas de canal ntfy : lancez d'abord python3 robot/robot.py setup")
        return 1
    return 0 if send(cfg, "Robot trader : test", "Les alertes arrivent bien.", 3, ["white_check_mark"]) else 1


def cmd_status(a):
    state = read_json(a.state, None)
    if not state:
        print("Aucun signal enregistré pour l'instant.")
        return 1
    print("Signaux du %s (%d) :" % (state["date"], state["signals"]))
    for sym, st in sorted(state["symbols"].items()):
        ph = st.get("phase")
        if ph == "in":
            print("  %-6s en cours : entrée %s, stop %s, objectif %s" % (sym, fmt(st["entry"]), fmt(st["stop"]),
                                                                       fmt(st["target"])))
        elif ph == "done" and "exit" in st:
            print("  %-6s terminé : entrée %s, sortie (%s) %s à %s" % (sym, fmt(st["entry"]), st["exit"],
                                                                      fmt(st["exit_price"]), st["exit_time"]))
        elif ph == "skipped":
            print("  %-6s ignoré : %s" % (sym, st.get("why", "")))
        else:
            print("  %-6s %s" % (sym, "en attente" if ph == "watching" else "pas de signal"))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Robot d'alertes : signaux d'entrée et de sortie, sans jamais passer d'ordre.")
    p.add_argument("--config", default=CONFIG)
    p.add_argument("--state", default=STATE)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="crée la configuration et le canal ntfy")
    sub.add_parser("test", help="envoie une notification de test")
    r = sub.add_parser("run", help="surveille le marché en continu")
    r.add_argument("--once", action="store_true", help="un seul passage")
    sub.add_parser("status", help="les signaux du jour")
    a = p.parse_args(argv)
    try:
        return {"setup": cmd_setup, "test": cmd_test, "run": cmd_run, "status": cmd_status}[a.cmd](a)
    except RobotError as e:
        print(str(e), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nRobot arrêté.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
