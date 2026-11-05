"""The checks of the Microsoft 365 Copilot readiness and adoption review. Six areas: licences (licensed but inactive, licences on disabled
accounts, enough licences for the next wave), waves (training, MFA registration, compliant devices and licences of each wave before its
go-live), oversharing (SharePoint sites shared with "Everyone except external users", Anyone links, sites with no owner or one owner, no
sensitivity label, inactive sites still searchable by Copilot), labels and DLP (label coverage per department, a DLP policy for the Copilot
location), agents (no owner, shared with the whole organisation, connectors not on the allowed list, unused, decisions about people with no
entry in the AI register) and adoption (active-user rate per department and its trend, champions). Every issue says which waves it
affects; a wave is READY, ATTENTION or NOT READY from the issues that reach it."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from .model import APP_LABEL, APPS, Data, _norm

CRITICAL, WARNING, INFO = "critical", "warning", "info"
ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Licences", "Waves", "Oversharing", "Labels and DLP", "Agents", "Adoption")
PREFIX = {"LIC": "Licences", "WAV": "Waves", "OVS": "Oversharing", "LAB": "Labels and DLP", "AGT": "Agents", "ADP": "Adoption"}
VERDICT = {CRITICAL: "not ready", WARNING: "attention", None: "ready"}
ALL = "*"
NO_DEPT = "(no department)"


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    items: list[str] = field(default_factory=list)
    waves: list[str] = field(default_factory=list)
    cost: float = 0


@dataclass
class Issue:
    severity: str
    code: str
    text: str
    item: str = ""
    waves: tuple = ()
    cost: float = 0

    @property
    def area(self) -> str:
        return PREFIX[self.code.split("-")[0]]


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


def _top(items: list[str], k: int = 6, sep: str = ", ") -> str:
    return sep.join(items[:k]) + (f" and {len(items) - k} more" if len(items) > k else "")


def pct(x: float | None, k: int = 0) -> str:
    return "–" if x is None else f"{x:.{k}%}"


def money(x: float | None, cur: str = "EUR", k: int = 0) -> str:
    if x is None:
        return "–"
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(cur.upper())
    v = f"{abs(x):,.{k}f}"
    sign = "-" if x < 0 else ""
    return f"{sign}{sym}{v}" if sym else f"{sign}{v} {cur}"


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


# ---------------------------------------------------------------- review

def wave_status(go_live: date | None, today: date, window: int) -> str:
    if go_live is None:
        return "later"
    if go_live <= today:
        return "live"
    return "next" if (go_live - today).days <= window else "later"


def is_sensitive_site(site, s) -> bool:
    return _norm(site.department) in {_norm(x) for x in s.sensitive_departments} or _norm(site.label) in {_norm(x) for x in s.sensitive_labels}


def review(d: Data) -> dict:
    s, today = d.settings, d.today
    issues: list[Issue] = []
    users = {u.upn: u for u in d.users}
    cutoff = today - timedelta(days=s.inactive_days)
    waves = s.wave_list()
    wave_ids = [w.id for w in waves]
    by_wave = defaultdict(list)
    for u in d.users:
        if u.wave:
            by_wave[u.wave].append(u)
    dept_waves = defaultdict(set)
    for u in d.users:
        if u.wave and u.enabled:
            dept_waves[_norm(u.department)].add(u.wave)

    def scope(dept: str) -> tuple:
        return tuple(w for w in wave_ids if w in dept_waves.get(_norm(dept), set()))

    # ------------------------------------------------ licences
    licensed = [u for u in d.users if u.copilot]
    rows, reclaim = [], []
    for u in licensed:
        us = d.usage.get(u.upn)
        last = us.last if us else None
        new = u.copilot_assigned is not None and (today - u.copilot_assigned).days < s.grace_days
        reason = ""
        if not u.enabled:
            reason = "account disabled"
        elif not new and (last is None or last < cutoff):
            reason = "never used" if last is None else f"inactive {(today - last).days} days"
        rows.append({"user": u, "last": last, "new": new, "reason": reason,
                     "apps": sorted((us.apps if us else {}).items(), key=lambda x: APPS.index(x[0]))})
        if reason:
            reclaim.append({"user": u, "last": last, "reason": reason, "cost": s.licence_price_month})
    reclaim.sort(key=lambda r: (r["reason"] != "account disabled", r["last"] or date.min, r["user"].upn))
    inactive = [r for r in reclaim if r["reason"] != "account disabled"]
    disabled = [r for r in reclaim if r["reason"] == "account disabled"]
    if inactive:
        by_dept = Counter(r["user"].department or NO_DEPT for r in inactive)
        issues.append(Issue(WARNING, "LIC-01", f"{_n(len(inactive), 'licence')} with no Copilot activity in {s.inactive_days} days "
                            f"({sum(r['reason'] == 'never used' for r in inactive)} never used), by department: "
                            + ", ".join(f"{k} {v}" for k, v in sorted(by_dept.items(), key=lambda x: (-x[1], x[0]))),
                            "; ".join(r["user"].upn for r in inactive), tuple(sorted({r["user"].wave for r in inactive if r["user"].wave})),
                            len(inactive) * s.licence_price_month))
    if disabled:
        issues.append(Issue(WARNING, "LIC-02", f"{_n(len(disabled), 'licence')} assigned to disabled accounts: "
                            + _top([r["user"].upn for r in disabled], 8), "; ".join(r["user"].upn for r in disabled), (),
                            len(disabled) * s.licence_price_month))
    # the licence pool for the next wave
    pool = {"owned": s.licences_owned, "assigned": len(licensed), "free": None, "reclaimable": len(reclaim), "wave": None, "need": 0,
            "shortfall": None}
    upcoming = [w for w in waves if wave_status(w.go_live, today, s.readiness_window_days) != "live"]
    if upcoming:
        nxt = upcoming[0]
        need = sum(1 for u in by_wave[nxt.id] if u.enabled and not u.copilot)
        pool.update(wave=nxt.id, need=need)
        if s.licences_owned is not None:
            free = s.licences_owned - len(licensed)
            short = need - free
            pool.update(free=free, shortfall=short)
            if short > 0:
                sev = WARNING if short <= len(reclaim) else CRITICAL
                issues.append(Issue(sev, "LIC-03", f"{nxt.name} needs {need} licences on {nxt.go_live:%d %b %Y}: {free} free of "
                                    f"{s.licences_owned} owned, {short} short; {len(reclaim)} can be reclaimed"
                                    + (" (enough)" if sev == WARNING else f", still {short - len(reclaim)} short"), nxt.id, (nxt.id,)))
    # ------------------------------------------------ waves
    trained = {t.upn: t for t in d.training if t.completed and t.completed <= today}
    champions = {t.upn for t in d.training if t.champion}
    wave_rows = []
    for w in waves:
        st = wave_status(w.go_live, today, s.readiness_window_days)
        members = [u for u in by_wave[w.id] if u.enabled]
        n = len(members)
        done = [u for u in members if u.upn in trained]
        no_mfa = [u for u in members if u.mfa is False]
        mfa_unknown = [u for u in members if u.mfa is None]
        not_compliant = [u for u in members if u.device is not True]
        lic = [u for u in members if u.copilot]
        act = [u for u in members if u.copilot and d.usage.get(u.upn) and d.usage[u.upn].last and d.usage[u.upn].last >= cutoff]
        row = {"wave": w, "status": st, "users": n, "planned": w.planned, "trained": len(done), "training": _ratio(len(done), n),
               "no_mfa": len(no_mfa), "mfa_unknown": len(mfa_unknown), "not_compliant": len(not_compliant),
               "device": _ratio(n - len(not_compliant), n), "licensed": len(lic), "active": len(act), "active_rate": _ratio(len(act), len(lic)),
               "champions": sum(1 for u in members if u.upn in champions), "days": (w.go_live - today).days if w.go_live else None,
               "departments": Counter(u.department or NO_DEPT for u in members)}
        wave_rows.append(row)
        if not n:
            continue
        evaluate = st in ("live", "next")
        tr = row["training"] or 0
        if tr < s.training_target:
            sev = (CRITICAL if st == "next" and tr < s.training_critical else WARNING) if evaluate else INFO
            missing = [u for u in members if u.upn not in trained]
            by_dept = Counter(u.department or NO_DEPT for u in missing)
            issues.append(Issue(sev, "WAV-01", f"{w.name}: {len(done)} of {n} trained ({pct(tr)}, target {pct(s.training_target)})"
                                + (f", go-live in {row['days']} days" if st != "live" else "") + "; missing by department: "
                                + ", ".join(f"{k} {v}" for k, v in sorted(by_dept.items(), key=lambda x: (-x[1], x[0]))),
                                "; ".join(u.upn for u in missing), (w.id,)))
        if no_mfa:
            share = len(no_mfa) / n
            sev = (CRITICAL if share > s.mfa_critical else WARNING) if evaluate else INFO
            issues.append(Issue(sev, "WAV-02", f"{w.name}: {len(no_mfa)} of {n} users not registered for MFA ({pct(share, 1)})",
                                "; ".join(u.upn for u in no_mfa), (w.id,)))
        dv = row["device"] or 0
        if dv < s.device_target:
            sev = (CRITICAL if dv < s.device_critical else WARNING) if evaluate else INFO
            issues.append(Issue(sev, "WAV-03", f"{w.name}: {len(not_compliant)} of {n} users without a compliant device ({pct(1 - dv, 1)}; "
                                f"target {pct(s.device_target)} compliant)", "; ".join(u.upn for u in not_compliant), (w.id,)))
        if st == "live":
            nolic = [u for u in members if not u.copilot]
            if nolic:
                issues.append(Issue(WARNING, "WAV-04", f"{w.name} is live and {_n(len(nolic), 'user')} of the wave have no Copilot licence: "
                                    + _top([u.upn for u in nolic], 6), "; ".join(u.upn for u in nolic), (w.id,)))
    # ------------------------------------------------ oversharing
    site_rows = []
    for st_ in sorted(d.sites, key=lambda x: x.url):
        sens = is_sensitive_site(st_, s)
        sc = scope(st_.department)
        si = []
        where = f"{st_.title or st_.url} ({st_.department or 'no department'})"
        if st_.eeeu:
            sev = INFO if st_.rcd else (CRITICAL if sens else WARNING)
            si.append(Issue(sev, "OVS-01", f"{where}: {_n(st_.eeeu, 'permission')} to Everyone except external users"
                            + (f", {st_.users:,} users have access" if st_.users else "") + ("; Restricted Content Discovery on" if st_.rcd else ""),
                            st_.url, (ALL,) if sev == CRITICAL else sc))
        if st_.anyone:
            sev = CRITICAL if sens and not st_.rcd else WARNING
            si.append(Issue(sev, "OVS-02", f"{where}: {_n(st_.anyone, 'Anyone link')}", st_.url, (ALL,) if sev == CRITICAL else sc))
        if st_.owners is not None and st_.owners < 2:
            sev = WARNING if st_.owners == 0 else INFO
            si.append(Issue(sev, "OVS-03", f"{where}: {'no owner' if st_.owners == 0 else 'one owner'}", st_.url, sc))
        if not st_.label:
            si.append(Issue(WARNING if sens else INFO, "OVS-04", f"{where}: no sensitivity label", st_.url, sc))
        if st_.modified and (today - st_.modified).days >= s.inactive_site_days and not st_.rcd:
            exposed = st_.eeeu or st_.anyone
            si.append(Issue(WARNING if exposed else INFO, "OVS-05", f"{where}: no content change since {st_.modified:%d %b %Y}, still "
                            "searchable by Copilot" + (" and shared broadly" if exposed else ""), st_.url, sc))
        cov = d.labels.get(st_.url)
        site_rows.append({"site": st_, "sensitive": sens, "issues": si, "waves": sc,
                          "coverage": _ratio(cov.labelled, cov.files) if cov else None, "files": cov.files if cov else None})
        issues += si
    # ------------------------------------------------ labels and DLP
    dept_cov = defaultdict(lambda: [0, 0])
    for r in site_rows:
        cov = d.labels.get(r["site"].url)
        if cov and cov.files:
            dept_cov[r["site"].department or NO_DEPT][0] += cov.labelled
            dept_cov[r["site"].department or NO_DEPT][1] += cov.files
    label_rows = []
    for dept in sorted(dept_cov):
        lab, files = dept_cov[dept]
        c = lab / files
        label_rows.append({"department": dept, "files": files, "labelled": lab, "coverage": c, "waves": scope(dept)})
        if c < s.label_target:
            sev = CRITICAL if c < s.label_critical else WARNING
            issues.append(Issue(sev, "LAB-01", f"{dept}: {pct(c)} of {files:,} files labelled (target {pct(s.label_target)})", dept, scope(dept)))
    dlp = {"policies": len(d.dlp), "enforced": [p.name for p in d.dlp if p.copilot and _norm(p.mode) == "enable"],
           "test": [p.name for p in d.dlp if p.copilot and _norm(p.mode).startswith("test")], "provided": bool(d.sources.get("dlp.csv"))}
    if dlp["provided"] and not dlp["enforced"]:
        issues.append(Issue(WARNING, "LAB-02", "No DLP policy enforced on the Microsoft 365 Copilot and Copilot Chat location"
                            + (f" (in simulation: {', '.join(dlp['test'])})" if dlp["test"] else ""), "", (ALL,)))
    # ------------------------------------------------ agents
    allowed = {_norm(x) for x in s.allowed_connectors}
    org_wide = {_norm(x) for x in s.org_wide_values}
    agent_rows = []
    for a in sorted(d.agents, key=lambda x: x.name.lower()):
        ai = []
        wide = a.published and _norm(a.shared) in org_wide
        owner = users.get(a.owner)
        orphan = not a.owner or (bool(users) and (owner is None or not owner.enabled))
        bad = [c for c in a.connectors if allowed and _norm(c) not in allowed]
        if orphan:
            why = "no owner" if not a.owner else (f"owner {a.owner} is disabled" if owner else f"owner {a.owner} not in the directory")
            ai.append(Issue(CRITICAL if wide else WARNING, "AGT-01", f"{a.name}: {why}", a.name, (ALL,) if wide else ()))
        if wide:
            ai.append(Issue(WARNING, "AGT-02", f"{a.name}: published to the whole organisation ({a.environment or 'no environment'})", a.name, ()))
        if bad:
            ai.append(Issue(CRITICAL if wide else WARNING, "AGT-03", f"{a.name}: connectors not on the allowed list: {', '.join(bad)}", a.name,
                            (ALL,) if wide else ()))
        if a.published and (a.last_used is None or (today - a.last_used).days > s.agent_unused_days):
            ai.append(Issue(WARNING, "AGT-04", f"{a.name}: " + ("never used" if a.last_used is None else f"not used since {a.last_used:%d %b %Y}"),
                            a.name, ()))
        if a.people and not a.register.strip():
            ai.append(Issue(WARNING, "AGT-05", f"{a.name}: supports decisions about people with no entry in the AI register", a.name, ()))
        agent_rows.append({"agent": a, "wide": wide, "orphan": orphan, "bad": bad, "issues": ai})
        issues += ai
    # ------------------------------------------------ adoption
    apps = Counter()
    dept = defaultdict(lambda: {"licensed": 0, "active": 0, "active7": 0, "champions": 0, "users": 0, "waves": set()})
    last_week = today - timedelta(days=7)
    for u in d.users:
        if not u.enabled:
            continue
        r = dept[u.department or NO_DEPT]
        r["users"] += 1
        if u.upn in champions:
            r["champions"] += 1
        if u.wave:
            r["waves"].add(u.wave)
        if not u.copilot:
            continue
        r["licensed"] += 1
        us = d.usage.get(u.upn)
        if us and us.last and us.last >= cutoff:
            r["active"] += 1
            if us.last >= last_week:
                r["active7"] += 1
            for ap, dt in us.apps.items():
                if dt >= cutoff:
                    apps[ap] += 1
    prev = {}
    for h in sorted(d.history, key=lambda h: h.day):
        if h.day < today:
            prev[_norm(h.department)] = h
    adoption_rows = []
    for k in sorted(dept):
        r = dept[k]
        rate = _ratio(r["active"], r["licensed"])
        h = prev.get(_norm(k))
        prate = _ratio(h.active, h.licensed) if h else None
        change = rate - prate if rate is not None and prate is not None else None
        adoption_rows.append({"department": k, **{x: r[x] for x in ("users", "licensed", "active", "active7", "champions")}, "rate": rate,
                              "previous": prate, "previous_date": h.day if h else None, "change": change,
                              "waves": tuple(w for w in wave_ids if w in r["waves"])})
        if r["licensed"] >= 5 and rate is not None and rate < s.adoption_target:
            issues.append(Issue(WARNING, "ADP-01", f"{k}: {r['active']} of {r['licensed']} licensed users active in {s.inactive_days} days "
                                f"({pct(rate)}, target {pct(s.adoption_target)})", k, ()))
        if change is not None and change <= -s.adoption_drop:
            issues.append(Issue(WARNING, "ADP-02", f"{k}: active rate {pct(rate)}, down from {pct(prate)} on {h.day:%d %b %Y}", k, ()))
    for w in wave_rows:
        if w["status"] in ("live", "next") and w["users"]:
            for dname, cnt in sorted(w["departments"].items()):
                champs = sum(1 for u in by_wave[w["wave"].id] if u.enabled and (u.department or NO_DEPT) == dname and u.upn in champions)
                if cnt >= 10 and champs < s.min_champions:
                    issues.append(Issue(WARNING, "ADP-03", f"{w['wave'].name}: {dname} ({cnt} users) has no Copilot champion", dname,
                                        (w["wave"].id,)))
    sv = {"responses": len(d.survey), "minutes": median([x.minutes for x in d.survey if x.minutes is not None] or [0]) if d.survey else None,
          "satisfaction": median([x.satisfaction for x in d.survey if x.satisfaction is not None] or [0]) if d.survey else None}
    # ------------------------------------------------ wave verdicts
    for w in wave_rows:
        wid = w["wave"].id
        reach = [i for i in issues if i.severity != INFO and (wid in i.waves or ALL in i.waves)]
        sev = CRITICAL if any(i.severity == CRITICAL for i in reach) else WARNING if reach else None
        w["verdict"] = VERDICT[sev]
        w["blockers"] = [i for i in reach if i.severity == CRITICAL]
        w["warnings"] = [i for i in reach if i.severity == WARNING]
    return {"issues": issues, "licensed": rows, "reclaim": reclaim, "pool": pool, "waves": wave_rows, "sites": site_rows, "labels": label_rows,
            "dlp": dlp, "agents": agent_rows, "adoption": adoption_rows, "apps": apps, "survey": sv}


# ---------------------------------------------------------------- findings

CODES = {
    "LIC-01": ("licences", "licensed but inactive: reclaim or reassign", "Ask each manager in one message: keep (with a reason) or release; "
               "reassign released licences to the next wave.", "group"),
    "LIC-02": ("licences", "licences on disabled accounts", "Remove the licence from the leaver process today; it goes back to the pool.", "group"),
    "LIC-03": ("licences", "licences for the next wave", "Reclaim the inactive licences first, then order the rest before go-live.", "group"),
    "WAV-01": ("waves", "training not done", "Send the wave's managers the list; book the missing sessions before go-live.", "group"),
    "WAV-02": ("waves", "users not registered for MFA", "Registration campaign for the wave; no Copilot licence until MFA is registered.",
               "group"),
    "WAV-03": ("waves", "users without a compliant device", "Fix or replace the devices; Conditional Access will block them anyway.", "group"),
    "WAV-04": ("waves", "users of a live wave without a licence", "Assign from the pool or move them to the next wave.", "group"),
    "OVS-01": ("oversharing", "shared with Everyone except external users",
               "Remove the EEEU permission and grant the right group; turn on Restricted Content Discovery until the site is fixed.", "site"),
    "OVS-02": ("oversharing", "with Anyone links", "Expire or remove the Anyone links; restrict sharing on the site to the organisation.",
               "site"),
    "OVS-03": ("oversharing", "without two owners", "Name a second owner; an unowned site is never reviewed.", "site"),
    "OVS-04": ("oversharing", "without a sensitivity label", "Apply the container label agreed for the department.", "site"),
    "OVS-05": ("oversharing", "inactive and still searchable", "Archive the site or turn on Restricted Content Discovery.", "site"),
    "LAB-01": ("labels", "under the label coverage target", "Default label on the department's libraries and a labelling "
               "sprint with the department's champions.", "department"),
    "LAB-02": ("labels", "DLP for Copilot", "Turn the Copilot location policy from simulation to enforcement after reviewing its matches.",
               "group"),
    "AGT-01": ("agents", "without an owner", "Name an owner in the business or block the agent until one is named.", "agent"),
    "AGT-02": ("agents", "published to the whole organisation", "Confirm the audience with the owner; share with a group instead.",
               "agent"),
    "AGT-03": ("agents", "using connectors not on the allowed list", "Remove the connector or approve it through the data policy; "
               "block the agent meanwhile.", "agent"),
    "AGT-04": ("agents", "unused", "Ask the owner; unpublish and delete if nobody needs it.", "agent"),
    "AGT-05": ("agents", "supporting decisions about people without an AI register entry", "Record the use case in the AI register "
               "and have it reviewed (purpose, data, human oversight) before further use.", "agent"),
    "ADP-01": ("adoption", "under the active-user target", "Department session with the champions; look at which apps they use.",
               "department"),
    "ADP-02": ("adoption", "where use is falling", "Ask the champions what changed; refresh the prompts and use cases.",
               "department"),
    "ADP-03": ("adoption", "without a champion", "Name a champion in each department of the wave before go-live.", "department"),
}


def run_all(d: Data, rv: dict | None = None) -> list[Finding]:
    rv = rv if rv is not None else review(d)
    s = d.settings
    hits = defaultdict(list)
    for i in rv["issues"]:
        hits[i.code].append(i)
    waves = {w["wave"].id: w["wave"].name for w in rv["waves"]}
    out: list[Finding] = []
    for code, (owner, subject, fix, word) in CODES.items():
        for sev in (CRITICAL, WARNING, INFO):
            xs = [i for i in hits.get(code, []) if i.severity == sev]
            if not xs:
                continue
            cost = sum(i.cost for i in xs)
            head = subject if word == "group" else f"{_n(len(xs), word)} {subject}"
            if cost:
                head += f" ({money(cost, s.currency)} a month)"
            head = head[0].upper() + head[1:]
            if sev == INFO:
                head = f"For information ({code}): {head}"
            ws = sorted({w for i in xs for w in i.waves}, key=lambda w: (w != ALL, w))
            items = [x for i in xs for x in i.item.split("; ") if x]
            out.append(Finding(sev, PREFIX[code.split("-")[0]], code, head, _top([i.text for i in xs], 8, "; "),
                               fix if sev != INFO else "No action before the wave; on the agenda of the next review.", s.owner(owner),
                               items, ["all waves" if w == ALL else waves.get(w, w) for w in ws], cost))
    out.sort(key=lambda f: (ORDER[f.severity], AREAS.index(f.area), f.code))
    return out


def summary(d: Data, rv: dict) -> dict:
    s = d.settings
    lic = rv["licensed"]
    active = sum(1 for r in lic if r["user"].enabled and r["last"] and r["last"] >= d.today - timedelta(days=s.inactive_days))
    enabled_lic = sum(1 for r in lic if r["user"].enabled)
    files = sum(r["files"] for r in rv["labels"])
    lab = sum(r["labelled"] for r in rv["labels"])
    sites_flag = [r for r in rv["sites"] if any(i.severity != INFO for i in r["issues"])]
    return dict(
        users=len(d.users), enabled=sum(u.enabled for u in d.users), licensed=len(lic), active=active, active_rate=_ratio(active, enabled_lic),
        reclaim=len(rv["reclaim"]), reclaim_cost=sum(r["cost"] for r in rv["reclaim"]), currency=s.currency,
        inactive=sum(1 for r in rv["reclaim"] if r["reason"] != "account disabled"),
        disabled=sum(1 for r in rv["reclaim"] if r["reason"] == "account disabled"), pool=rv["pool"],
        waves=[(w["wave"].id, w["wave"].name, w["status"], w["verdict"]) for w in rv["waves"]],
        sites=len(d.sites), sites_flagged=len(sites_flag),
        sites_critical=sum(1 for r in rv["sites"] if any(i.severity == CRITICAL for i in r["issues"])),
        eeeu=sum(1 for x in d.sites if x.eeeu), anyone=sum(1 for x in d.sites if x.anyone),
        label_coverage=_ratio(lab, files), agents=len(d.agents), agents_flagged=sum(1 for a in rv["agents"] if a["issues"]),
        dlp_enforced=bool(rv["dlp"]["enforced"]), survey=rv["survey"],
        top_app=max(rv["apps"].items(), key=lambda x: (x[1], x[0]))[0] if rv["apps"] else None,
    )


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {}
    for a in AREAS:
        sev = [f.severity for f in findings if f.area == a and f.severity != INFO]
        st[a] = CRITICAL if CRITICAL in sev else WARNING if sev else "ok"
    return st


def overall(findings: list[Finding]) -> str:
    st = set(area_status(findings).values())
    return VERDICT[CRITICAL] if CRITICAL in st else VERDICT[WARNING] if WARNING in st else VERDICT[None]


def proposal(w: dict) -> str:
    """The proposal for the steering group: go, go with conditions or no go."""
    if w["status"] == "live":
        return "live: fix and keep"
    return {"not ready": "no go until the blockers are fixed", "attention": "go with conditions", "ready": "go"}[w["verdict"]]


__all__ = ["AREAS", "CRITICAL", "WARNING", "INFO", "Finding", "Issue", "review", "run_all", "summary", "area_status", "overall", "APP_LABEL"]
