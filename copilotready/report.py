"""Outputs: report.html (verdict, tiles, the waves with their verdicts, licences, oversharing, labels and DLP, agents, adoption and all
findings), readiness-pack.md (the pack for the Copilot steering group, with a decision column per wave), and the CSVs: licence-reclaim,
oversharing, agents, adoption, waves, actions and findings."""
from __future__ import annotations

import csv
import html
from pathlib import Path

from .checks import (AREAS, CRITICAL, INFO, NO_DEPT, VERDICT, WARNING, Finding, _n, area_status, money, overall, pct, proposal, summary)
from .model import APP_LABEL, APPS, FILES, Data

e = html.escape
TODO = "**[TO COMPLETE]**"


# ---------------------------------------------------------------- csv

def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _f(x, k=2) -> str:
    return "" if x is None else f"{x:.{k}f}"


def _d(x) -> str:
    return x.isoformat() if x else ""


def _worst(issues) -> str:
    sev = {i.severity for i in issues}
    return CRITICAL if CRITICAL in sev else WARNING if WARNING in sev else INFO if sev else ""


def _codes(issues) -> str:
    return "; ".join(dict.fromkeys(i.code for i in issues))


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "area", "code", "subject", "detail", "next_step", "owner", "waves", "monthly_cost", "items"],
       [[f.severity, f.area, f.code, f.subject, f.detail, f.fix, f.owner, "; ".join(f.waves), _f(f.cost), "; ".join(f.items)] for f in findings])


def write_actions(findings: list[Finding], path: Path) -> None:
    _w(path, ["ref", "action", "next_step", "owner", "severity", "waves", "monthly_cost", "due", "decision", "done"],
       [[f.code, f.subject, f.fix, f.owner, f.severity, "; ".join(f.waves), _f(f.cost), "", "", ""] for f in findings if f.severity != INFO])


def write_reclaim(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["user_principal_name", "display_name", "department", "wave", "account_enabled", "licence_assigned", "last_activity", "days_inactive",
              "reason", "monthly_cost", "manager", "decision"],
       [[r["user"].upn, r["user"].name, r["user"].department, r["user"].wave, "yes" if r["user"].enabled else "no", _d(r["user"].copilot_assigned),
         _d(r["last"]), "" if r["last"] is None else (d.today - r["last"]).days, r["reason"], _f(r["cost"]), r["user"].manager, ""]
        for r in rv["reclaim"]])


def site_action(r: dict) -> str:
    codes = {i.code for i in r["issues"] if i.severity != INFO}
    st = r["site"]
    acts = []
    if "OVS-01" in codes:
        acts.append("remove Everyone except external users" + ("" if st.rcd else "; Restricted Content Discovery until fixed"))
    if "OVS-02" in codes:
        acts.append("remove Anyone links")
    if "OVS-03" in codes:
        acts.append("name two owners")
    if "OVS-04" in codes:
        acts.append("apply the sensitivity label")
    if "OVS-05" in codes:
        acts.append("archive or restrict")
    return "; ".join(acts)


def write_oversharing(d: Data, rv: dict, path: Path) -> None:
    rows = sorted(rv["sites"], key=lambda r: ({CRITICAL: 0, WARNING: 1, INFO: 2, "": 3}[_worst(r["issues"])], r["site"].url))
    _w(path, ["url", "title", "department", "waves", "sensitive", "owners", "sensitivity_label", "sharing_capability", "eeeu_permissions",
              "anyone_links", "users_with_access", "last_content_modified", "restricted_content_discovery", "restricted_access_control",
              "label_coverage", "severity", "codes", "action"],
       [[r["site"].url, r["site"].title, r["site"].department, "; ".join(r["waves"]), "yes" if r["sensitive"] else "no",
         "" if r["site"].owners is None else r["site"].owners, r["site"].label, r["site"].sharing, r["site"].eeeu, r["site"].anyone,
         "" if r["site"].users is None else r["site"].users, _d(r["site"].modified), "yes" if r["site"].rcd else "no",
         "yes" if r["site"].rac else "no", _f(r["coverage"], 3), _worst(r["issues"]), _codes(r["issues"]), site_action(r)] for r in rows])


def agent_action(r: dict) -> str:
    codes = {i.code for i in r["issues"]}
    acts = []
    if "AGT-01" in codes:
        acts.append("name an owner or block")
    if "AGT-03" in codes:
        acts.append("remove the connector or approve it")
    if "AGT-02" in codes:
        acts.append("share with a group")
    if "AGT-05" in codes:
        acts.append("record it in the AI register")
    if "AGT-04" in codes:
        acts.append("unpublish if unused")
    return "; ".join(acts)


def write_agents(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["name", "owner", "environment", "status", "shared_with", "connectors", "connectors_not_allowed", "authentication", "last_used",
              "decisions_about_people", "ai_register_entry", "severity", "codes", "action"],
       [[r["agent"].name, r["agent"].owner, r["agent"].environment, r["agent"].status, r["agent"].shared, "; ".join(r["agent"].connectors),
         "; ".join(r["bad"]), r["agent"].auth, _d(r["agent"].last_used), "yes" if r["agent"].people else "no", r["agent"].register,
         _worst(r["issues"]), _codes(r["issues"]), agent_action(r)] for r in rv["agents"]])


def write_adoption(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["date", "department", "users", "licensed", "active_30d", "active_7d", "active_rate", "previous_rate", "previous_date", "change",
              "champions", "waves"],
       [[d.today.isoformat(), r["department"], r["users"], r["licensed"], r["active"], r["active7"], _f(r["rate"], 3), _f(r["previous"], 3),
         _d(r["previous_date"]), _f(r["change"], 3), r["champions"], "; ".join(r["waves"])] for r in rv["adoption"]])


def write_waves(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["wave", "name", "go_live", "status", "days_to_go_live", "users", "planned", "licensed", "trained", "training_rate", "no_mfa",
              "mfa_unknown", "no_compliant_device", "device_rate", "champions", "active_30d", "active_rate", "verdict", "proposal", "blockers",
              "warnings", "decision"],
       [[w["wave"].id, w["wave"].name, _d(w["wave"].go_live), w["status"], "" if w["days"] is None else w["days"], w["users"],
         "" if w["planned"] is None else w["planned"], w["licensed"], w["trained"], _f(w["training"], 3), w["no_mfa"], w["mfa_unknown"],
         w["not_compliant"], _f(w["device"], 3), w["champions"], w["active"], _f(w["active_rate"], 3), w["verdict"], proposal(w),
         "; ".join(dict.fromkeys(i.code for i in w["blockers"])), "; ".join(dict.fromkeys(i.code for i in w["warnings"])), ""]
        for w in rv["waves"]])


# ---------------------------------------------------------------- the pack

def _md(x) -> str:
    return str(x).replace("|", "/")


def _status_word(st: str) -> str:
    return "READY" if st == "ok" else VERDICT[st].upper()


def pack_md(d: Data, rv: dict, findings: list[Finding], title: str) -> str:
    s, sm, st = d.settings, summary(d, rv), area_status(findings)
    cur = sm["currency"]
    M = lambda x, k=0: money(x, cur, k)  # noqa: E731
    pool = rv["pool"]
    out = [f"# {title}", "",
           f"> Generated by copilotready on {d.as_of:%a %d %b %Y} from the exports listed under *Scope and evidence*. Read-only: nothing was "
           f"changed in the tenant. Licence costs are estimates at {M(s.licence_price_month, 2)} per licence a month; sections marked {TODO} are "
           "for the meeting.", "",
           f"**Overall: {overall(findings).upper()}**", "",
           "## Decisions per wave", "",
           "| Wave | Go-live | Status | Users | Trained | MFA gaps | No compliant device | Verdict | Proposal | Decision |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for w in rv["waves"]:
        out.append(f"| {_md(w['wave'].name)} | {w['wave'].go_live:%d %b %Y} | {w['status']} | {w['users']} | {pct(w['training'])} | {w['no_mfa']} | "
                   f"{w['not_compliant']} | **{w['verdict'].upper()}** | {proposal(w)} | {TODO} |" if w["wave"].go_live else
                   f"| {_md(w['wave'].name)} | – | {w['status']} | {w['users']} | {pct(w['training'])} | {w['no_mfa']} | {w['not_compliant']} | "
                   f"**{w['verdict'].upper()}** | {proposal(w)} | {TODO} |")
    for w in rv["waves"]:
        if w["blockers"] or w["warnings"]:
            out += ["", f"**{_md(w['wave'].name)}**: " + (f"blockers: {'; '.join(dict.fromkeys(i.code for i in w['blockers']))}. " if w["blockers"]
                                                        else "no blockers. ")
                    + (f"To watch: {'; '.join(dict.fromkeys(i.code for i in w['warnings']))}." if w["warnings"] else "")]
    out += ["", "| Area | Status | To act on |", "|---|---|---|"]
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        out.append(f"| {a} | {_status_word(st[a])} | {n} |")
    sv = sm["survey"]
    out += ["", "## Headlines", "",
            f"- {sm['licensed']} Copilot licences assigned" + (f" of {pool['owned']} owned" if pool["owned"] is not None else "")
            + f"; **{sm['active']} active in the last {s.inactive_days} days** ({pct(sm['active_rate'])} of the enabled licensed users).",
            f"- **{sm['reclaim']} licences to reclaim or reassign** ({sm['inactive']} inactive, {sm['disabled']} on disabled accounts): "
            f"{M(sm['reclaim_cost'])} a month, {M(sm['reclaim_cost'] * 12)} a year (estimate).",
            ]
    if pool["wave"]:
        nxt = next(w for w in rv["waves"] if w["wave"].id == pool["wave"])
        line = f"- {nxt['wave'].name} needs {pool['need']} more licences"
        if pool["free"] is not None:
            line += f"; {pool['free']} free in the pool" + (f", {pool['shortfall']} short before reclaiming" if pool["shortfall"] > 0 else "")
        out.append(line + ".")
    out += [f"- SharePoint: {sm['sites_flagged']} of {sm['sites']} sites to fix before the next wave, {sm['sites_critical']} critical; "
            f"{sm['eeeu']} with permissions to Everyone except external users, {sm['anyone']} with Anyone links.",
            f"- Label coverage {pct(sm['label_coverage'])} of the files in the sites reviewed; DLP for the Copilot location "
            + ("enforced." if sm["dlp_enforced"] else "not enforced."),
            f"- Agents: {sm['agents_flagged']} of {sm['agents']} with findings.",
            (f"- Survey ({sv['responses']} answers): median {sv['minutes']:g} minutes saved a week, satisfaction {sv['satisfaction']:g} of 5 "
             "(self-reported)." if sv["responses"] else "- No survey answers."),
            "", "## Scope and evidence", "", f"- Organisation: {s.organisation}", f"- Reference date: {d.as_of:%a %d %b %Y %H:%M}",
            f"- Inactive means no Copilot activity in {s.inactive_days} days; licences assigned less than {s.grace_days} days ago are not counted",
            "", "| Source | File | Records |", "|---|---|---|"]
    out += [f"| {FILES.get(k, k)} | `{k}` | {v:,} |" for k, v in d.sources.items()]
    # 1 waves
    out += ["", "## 1. Wave readiness", "",
            "| Wave | Departments | Licensed | Champions | Active (live waves) |", "|---|---|---|---|---|"]
    for w in rv["waves"]:
        deps = ", ".join(f"{k} {v}" for k, v in sorted(w["departments"].items(), key=lambda x: (-x[1], x[0])))
        out.append(f"| {_md(w['wave'].name)} | {_md(deps)} | {w['licensed']} | {w['champions']} | "
                   f"{(str(w['active']) + ' (' + pct(w['active_rate']) + ')') if w['status'] == 'live' else '–'} |")
    # 2 licences
    out += ["", "## 2. Licences to reclaim", "", "| Reason | Users | Monthly cost (estimate) |", "|---|---|---|"]
    reasons = {}
    for r in rv["reclaim"]:
        key = "account disabled" if r["reason"] == "account disabled" else "never used" if r["reason"] == "never used" else \
            f"inactive {s.inactive_days}+ days"
        reasons[key] = reasons.get(key, 0) + 1
    out += [f"| {k} | {v} | {M(v * s.licence_price_month)} |" for k, v in sorted(reasons.items())]
    out += [f"| **Total** | **{sm['reclaim']}** | **{M(sm['reclaim_cost'])}** |", "",
            "Every user is in `licence-reclaim.csv` with the manager and a decision column: release, keep (with a reason) or coach."]
    # 3 oversharing
    out += ["", "## 3. Oversharing to fix before the wave", "",
            "| Site | Department | EEEU | Anyone links | Owners | Label | Users with access | Action | Decision |", "|---|---|---|---|---|---|---|---|---|"]
    flagged = [r for r in rv["sites"] if any(i.severity != INFO for i in r["issues"])]
    flagged.sort(key=lambda r: (_worst(r["issues"]) != CRITICAL, r["site"].url))
    for r in flagged:
        x = r["site"]
        out.append(f"| {_md(x.title or x.url)}{' **(critical)**' if _worst(r['issues']) == CRITICAL else ''} | {_md(x.department or '–')} | {x.eeeu} | "
                   f"{x.anyone} | {'–' if x.owners is None else x.owners} | {_md(x.label or 'none')} | "
                   f"{'–' if x.users is None else format(x.users, ',')} | {_md(site_action(r))} | |")
    if not flagged:
        out.append("| None | | | | | | | | |")
    # 4 labels
    out += ["", "## 4. Labels and DLP", "", "| Department | Files | Labelled | Coverage |", "|---|---|---|---|"]
    out += [f"| {_md(r['department'])} | {r['files']:,} | {r['labelled']:,} | {pct(r['coverage'])}"
            f"{' (under target)' if r['coverage'] < s.label_target else ''} |" for r in rv["labels"]]
    dl = rv["dlp"]
    out += ["", (f"DLP for the Microsoft 365 Copilot and Copilot Chat location: enforced by {', '.join(dl['enforced'])}." if dl["enforced"] else
                 "DLP for the Microsoft 365 Copilot and Copilot Chat location: not enforced"
                 + (f" (in simulation: {', '.join(dl['test'])})." if dl["test"] else ".")) if dl["provided"] else "No dlp.csv provided."]
    # 5 agents
    out += ["", "## 5. Agents", "", "| Agent | Owner | Shared with | Connectors | Last used | Findings | Decision |", "|---|---|---|---|---|---|---|"]
    for r in rv["agents"]:
        if not r["issues"]:
            continue
        a = r["agent"]
        out.append(f"| {_md(a.name)} | {_md(a.owner or '(none)')} | {_md(a.shared or '–')} | {_md(', '.join(a.connectors))} | "
                   f"{_d(a.last_used) or 'never'} | {_codes(r['issues'])} | {TODO if _worst(r['issues']) == CRITICAL else ''} |")
    # 6 adoption
    out += ["", "## 6. Adoption", "", "| Department | Licensed | Active 30 d | Rate | Previous | Change | Champions |", "|---|---|---|---|---|---|---|"]
    for r in rv["adoption"]:
        if not r["licensed"]:
            continue
        out.append(f"| {_md(r['department'])} | {r['licensed']} | {r['active']} | {pct(r['rate'])} | {pct(r['previous'])} | "
                   f"{'–' if r['change'] is None else format(r['change'] * 100, '+.0f') + ' pts'} | {r['champions']} |")
    lic_active = sm["active"] or 0
    out += ["", "Active users by app in the last 30 days: " + (", ".join(f"{APP_LABEL[a]} {rv['apps'][a]} ({pct(rv['apps'][a] / lic_active)})"
                                                                    for a in APPS if rv["apps"].get(a)) if lic_active else "none") + "."]
    out += ["", "## Findings", ""]
    for f in findings:
        if f.severity == INFO:
            continue
        out += [f"### {f.code} · {f.subject} ({f.severity})", "", _md(f.detail), "",
                f"Waves: {', '.join(f.waves) or 'none'}. Next step: {f.fix} Owner: {f.owner}.", ""]
    out += ["## Actions", "", "| Ref | Action | Owner | Waves | Due | Decision |", "|---|---|---|---|---|---|"]
    out += [f"| {f.code} | {_md(f.subject)} | {f.owner} | {', '.join(f.waves) or '–'} | {TODO if f.severity == CRITICAL else ''} | |"
            for f in findings if f.severity != INFO]
    out += ["", "## Notes", "",
            "- A wave is NOT READY when a critical issue reaches it, ATTENTION with warnings only, READY otherwise. Critical oversharing "
            "(Everyone except external users or Anyone links on an HR, Finance or Legal site, or a site with a confidential label) and agents "
            "published to the whole organisation with no owner or with a connector not allowed reach every wave: Copilot answers from "
            "everything a user can already open.",
            f"- Training, MFA and devices are checked for waves live or going live in the next {s.readiness_window_days} days; later waves are "
            "listed for information.",
            "- Restricted Content Discovery hides a site from organisation-wide search and Copilot while it is fixed; it does not change "
            "permissions.",
            "- The AI register column records whether an agent that supports decisions about people has an entry; it is not a legal "
            "assessment under the EU AI Act.",
            f"- Decisions of the steering group: {TODO}", "",
            "## Sign-off", "", f"- Prepared by (Copilot rollout lead): {TODO}",
            f"- Reviewed with (security, SharePoint, information protection, HR, works council if applicable): {TODO}", f"- Date: {TODO}", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb;--bar:#3d6fb6;--bar2:#c9d6ea}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0;--bar:#6f9be0;--bar2:#2e3d55}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}h3{font-size:15px;margin:18px 0 8px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:24px}
.overall{display:inline-block;margin-top:14px;padding:6px 14px;border-radius:99px;font-weight:700;border:2px solid currentColor}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
.waves{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.wave{background:var(--card);border:1px solid var(--line);border-top:5px solid var(--ok);border-radius:10px;padding:12px 16px}
.wave.not-ready{border-top-color:var(--bad)}.wave.attention{border-top-color:var(--warn)}.wave h3{margin:0 0 2px}.wave ul{margin:8px 0 0;padding-left:18px;font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical{color:var(--bad)}.warning{color:var(--warn)}.info{color:var(--info)}.ok{color:var(--ok)}
.area.critical,.area.warning,.area.ok{color:inherit}
.pill.ready{color:var(--ok)}.pill.attention{color:var(--warn)}.pill.not-ready{color:var(--bad)}.pill.live{color:var(--info)}
td.subj{min-width:190px}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);min-width:200px;max-width:380px}td.sm{font-size:13px}
.brk{overflow-wrap:anywhere;word-break:break-word}
.bar{position:relative;height:14px;min-width:140px;background:var(--bar2);border-radius:3px}.bar i{position:absolute;left:0;top:0;bottom:0;background:var(--bar);border-radius:3px}
.bar i.low{background:var(--warn)}.bar s{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink)}
footer{margin-top:40px;font-size:13px}
"""


def _pill(cls: str, text: str) -> str:
    return f"<span class='pill {cls}'>{e(text)}</span>"


def _vpill(v: str) -> str:
    return _pill(v.replace(" ", "-"), v.upper())


def _table(head: list[str], rows: list[str]) -> str:
    return "<div class='wrap'><table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" + "".join(rows) + "</table></div>"


def _sect(h: list, n: int, title: str, area: str | None, st: dict, note: str) -> None:
    pill = _vpill("ready" if st[area] == "ok" else VERDICT[st[area]]) if area else ""
    h.append(f"<h2>{n}. {e(title)} {pill}</h2><p class='muted'>{e(note)}</p>")


def _area_table(findings: list[Finding], prefix: str) -> str:
    xs = [f for f in findings if f.code.startswith(prefix)]
    if not xs:
        return "<p class='muted'>Nothing to report.</p>"
    return _table(["Severity", "Finding", "Detail", "Next step"],
                  [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='subj'><b>{e(f.code)}</b> {e(f.subject)}</td>"
                   f"<td class='sm brk'>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td></tr>" for f in xs])


def _bar(value: float | None, mark: float | None = None) -> str:
    if value is None:
        return "–"
    w = max(0.0, min(100.0, value * 100))
    m = "" if mark is None else f"<s style='left:{min(100.0, mark * 100):.1f}%'></s>"
    return f"<div class='bar'><i class='{'low' if mark is not None and value < mark else ''}' style='width:{w:.1f}%'></i>{m}</div>"


def render_html(d: Data, rv: dict, findings: list[Finding], title: str) -> str:
    s, sm, st = d.settings, summary(d, rv), area_status(findings)
    cur = sm["currency"]
    M = lambda x, k=0: money(x, cur, k)  # noqa: E731
    ov = overall(findings)
    pool = rv["pool"]
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>{e(s.organisation)} · as of {d.as_of:%a %d %b %Y} · licence costs in {e(cur)} per month "
         "(estimates)</p>",
         f"<span class='overall {'critical' if ov == 'not ready' else 'warning' if ov == 'attention' else 'ok'}'>Overall: {e(ov.upper())}</span>"
         "<div class='tiles'>"]
    nxt = next((w for w in rv["waves"] if w["wave"].id == pool["wave"]), None)
    tiles = [("Copilot licences", str(sm["licensed"]), f"of {pool['owned']} owned" if pool["owned"] is not None else "assigned"),
             ("Active in 30 days", pct(sm["active_rate"]), f"{sm['active']} users"),
             ("To reclaim", str(sm["reclaim"]), f"{M(sm['reclaim_cost'])} a month"),
             ("Next wave", nxt["wave"].name if nxt else "–", f"{nxt['verdict'].upper()} · in {nxt['days']} days" if nxt and nxt["days"] is not None
              else ""),
             ("Sites to fix", str(sm["sites_flagged"]), f"{sm['sites_critical']} critical · of {sm['sites']}"),
             ("Label coverage", pct(sm["label_coverage"]), f"target {pct(s.label_target)}"),
             ("Agents flagged", str(sm["agents_flagged"]), f"of {sm['agents']} agents"),
             ("Minutes saved", f"{sm['survey']['minutes']:g}" if sm["survey"]["responses"] else "–",
              f"a week, median of {sm['survey']['responses']} answers" if sm["survey"]["responses"] else "no survey")]
    h += [f"<div class='tile'><span class='muted'>{e(x)}</span><b>{e(y)}</b><span class='muted'>{e(z)}</span></div>" for x, y, z in tiles]
    h.append("</div><h2>Waves</h2><div class='waves'>")
    for w in rv["waves"]:
        cls = w["verdict"].replace(" ", "-")
        when = f"{w['wave'].go_live:%d %b %Y}" if w["wave"].go_live else "no date"
        rs = [f"<li class='critical'>{e(i.text)}</li>" for i in w["blockers"][:4]] + [f"<li>{e(i.text)}</li>" for i in w["warnings"][:3]]
        more = len(w["blockers"]) + len(w["warnings"]) - len(rs)
        h.append(f"<div class='wave {cls}'><h3>{e(w['wave'].name)} {_vpill(w['verdict'])}</h3><span class='muted'>{e(w['status'])} · go-live "
                 f"{when} · {w['users']} users · trained {pct(w['training'])} · proposal: {e(proposal(w))}</span><ul>{''.join(rs)}"
                 f"{f'<li class=muted>and {more} more</li>' if more > 0 else ''}</ul></div>")
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for ar in AREAS:
        n = sum(f.area == ar and f.severity != INFO for f in findings)
        h.append(f"<div class='area {st[ar]}'><span class='lbl'>{e(ar)}</span>"
                 f"{_pill(st[ar].replace('ok', 'ready').replace('critical', 'not-ready').replace('warning', 'attention'), _status_word(st[ar]))}"
                 f"<span class='cnt'>{n} to act on</span></div>")
    h.append("</div>")
    crit = [f for f in findings if f.severity == CRITICAL]
    if crit:
        h.append("<h2>Fix first</h2>")
        h.append(_table(["Subject", "What", "Next step", "Owner"],
                        [f"<tr><td class='subj'><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)} · {e(f.code)} · {e(', '.join(f.waves))}</span></td>"
                         f"<td class='sm brk'>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in crit]))
    # 1 waves
    _sect(h, 1, "Wave readiness", "Waves", st, f"Training, MFA registration, a compliant device and a licence for every user of a wave live or "
          f"going live in the next {s.readiness_window_days} days. waves.csv has every number.")
    h.append(_table(["Wave", "Go-live", "Users", "Trained", "MFA gaps", "Compliant device", "Licensed", "Champions", "Verdict"],
                    [f"<tr><td><b>{e(w['wave'].name)}</b><br><span class='muted'>{e(w['status'])}</span></td><td class='nw'>"
                     f"{_d(w['wave'].go_live) or '–'}</td><td class='num'>{w['users']}</td><td>{_bar(w['training'], s.training_target)}"
                     f"<span class='muted'>{pct(w['training'])}</span></td><td class='num'>{w['no_mfa']}</td><td>{_bar(w['device'], s.device_target)}"
                     f"<span class='muted'>{pct(w['device'])}</span></td><td class='num'>{w['licensed']}</td><td class='num'>{w['champions']}</td>"
                     f"<td>{_vpill(w['verdict'])}</td></tr>" for w in rv["waves"]]))
    h.append("<p></p>" + _area_table(findings, "WAV"))
    # 2 licences
    _sect(h, 2, "Licences", "Licences", st, f"Licensed users with no Copilot activity in {s.inactive_days} days (licences assigned less than "
          f"{s.grace_days} days ago are not counted) and licences on disabled accounts, at {M(s.licence_price_month, 2)} a month each. "
          "licence-reclaim.csv has every user with the manager.")
    if nxt and pool["free"] is not None:
        h.append(f"<p>{e(nxt['wave'].name)} needs <b>{pool['need']}</b> more licences: {pool['free']} free in the pool, "
                 f"{max(0, pool['shortfall'])} short, {pool['reclaimable']} can be reclaimed.</p>")
    h.append(_area_table(findings, "LIC"))
    # 3 oversharing
    _sect(h, 3, "Oversharing", "Oversharing", st, "Copilot answers from everything a user can already open. Sites shared with Everyone except "
          "external users or with Anyone links, sites without two owners or a sensitivity label, and inactive sites still searchable. "
          "oversharing.csv has every site.")
    flagged = sorted([r for r in rv["sites"] if any(i.severity != INFO for i in r["issues"])],
                     key=lambda r: (_worst(r["issues"]) != CRITICAL, r["site"].url))
    h.append(_table(["Site", "EEEU", "Anyone", "Owners", "Label", "Users", "Action"],
                    [f"<tr><td class='sm'><b>{e(r['site'].title or r['site'].url)}</b><br><span class='muted'>{e(r['site'].department or '–')}"
                     f"{' · sensitive' if r['sensitive'] else ''}{' · RCD on' if r['site'].rcd else ''}</span></td>"
                     f"<td class='num {'critical' if r['site'].eeeu and r['sensitive'] and not r['site'].rcd else ''}'>{r['site'].eeeu}</td>"
                     f"<td class='num'>{r['site'].anyone}</td><td class='num'>{'–' if r['site'].owners is None else r['site'].owners}</td>"
                     f"<td class='sm'>{e(r['site'].label or 'none')}</td><td class='num'>{'–' if r['site'].users is None else format(r['site'].users, ',')}"
                     f"</td><td class='fix'>{e(site_action(r))}</td></tr>" for r in flagged]) if flagged else "<p class='muted'>None.</p>")
    h.append("<p></p>" + _area_table(findings, "OVS"))
    # 4 labels
    _sect(h, 4, "Labels and DLP", "Labels and DLP", st, f"Share of files with a sensitivity label per department (target {pct(s.label_target)}, "
          "the mark), and whether a DLP policy is enforced on the Microsoft 365 Copilot and Copilot Chat location.")
    h.append(_table(["Department", "Files", "Coverage", ""],
                    [f"<tr><td>{e(r['department'])}</td><td class='num'>{r['files']:,}</td><td class='num'>{pct(r['coverage'])}</td>"
                     f"<td>{_bar(r['coverage'], s.label_target)}</td></tr>" for r in rv["labels"]]))
    h.append("<p></p>" + _area_table(findings, "LAB"))
    # 5 agents
    _sect(h, 5, "Agents", "Agents", st, "Copilot Studio and Agent Builder agents: owner, audience, connectors against the allowed list, use, and "
          "an AI register entry for agents that support decisions about people. agents.csv has every agent.")
    h.append(_table(["Agent", "Owner", "Shared with", "Connectors", "Last used", "Action"],
                    [f"<tr><td class='sm'><b>{e(r['agent'].name)}</b><br><span class='muted'>{e(r['agent'].status)} · {e(r['agent'].environment)}</span>"
                     f"</td><td class='sm brk'>{e(r['agent'].owner or '(none)')}</td><td class='sm'>{e(r['agent'].shared)}</td><td class='sm'>"
                     f"{e(', '.join(r['agent'].connectors))}</td><td class='nw sm'>{_d(r['agent'].last_used) or 'never'}</td>"
                     f"<td class='fix {_worst(r['issues'])}'>{e(agent_action(r) or '–')}</td></tr>" for r in rv["agents"]]))
    h.append("<p></p>" + _area_table(findings, "AGT"))
    # 6 adoption
    _sect(h, 6, "Adoption", "Adoption", st, f"Licensed users active in the last {s.inactive_days} days per department (target "
          f"{pct(s.adoption_target)}, the mark), the change since the last snapshot in adoption_history.csv, and champions.")
    h.append(_table(["Department", "Licensed", "Active", "Rate", "", "Change", "Champions"],
                    [f"<tr><td>{e(r['department'])}</td><td class='num'>{r['licensed']}</td><td class='num'>{r['active']}</td>"
                     f"<td class='num'>{pct(r['rate'])}</td><td>{_bar(r['rate'], s.adoption_target)}</td><td class='num'>"
                     f"{'–' if r['change'] is None else format(r['change'] * 100, '+.0f') + ' pts'}</td><td class='num'>{r['champions']}</td></tr>"
                     for r in rv["adoption"] if r["licensed"]]))
    act = sm["active"] or 0
    if act:
        h.append("<h3>By app, last 30 days</h3>")
        h.append(_table(["App", "Active users", "Share of active", ""],
                        [f"<tr><td>{e(APP_LABEL[a])}</td><td class='num'>{rv['apps'][a]}</td><td class='num'>{pct(rv['apps'][a] / act)}</td>"
                         f"<td>{_bar(rv['apps'][a] / act)}</td></tr>" for a in APPS if rv["apps"].get(a)]))
    h.append("<p></p>" + _area_table(findings, "ADP"))
    h.append("<h2>All findings</h2>")
    h.append(_table(["Severity", "Area", "Subject", "Detail", "Waves", "Owner"],
                    [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td>"
                     f"<td class='sm brk'>{e(f.detail)}</td><td class='sm'>{e(', '.join(f.waves) or '–')}</td><td class='nw'>{e(f.owner)}</td></tr>"
                     for f in findings]))
    h.append("<footer class='muted'>Generated by copilotready. Fictional demo data unless you ran it on your own exports. The pack for the "
             "steering group is readiness-pack.md.</footer></main></body></html>")
    return "".join(h)


__all__ = ["render_html", "pack_md", "NO_DEPT", "_n"]
