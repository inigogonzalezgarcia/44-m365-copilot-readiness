"""Fictional demo: Fabrikam Energy, a made-up energy company with 1,800 people in Spain, Portugal and the United Kingdom, rolling out
Microsoft 365 Copilot in three waves: a pilot of 120 people live since 1 September, wave 2 of 400 going live on 19 November and wave 3 of
600 in January. Reviewed on Thursday 5 November 2026, two weeks before wave 2, in euros. Every person, site, agent and number is made up;
the licence price is a round figure set in settings.json, not a quote. The problems are placed on purpose among the everyday ones."""
from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

ORG = "Fabrikam Energy"
SEED = 44
TODAY = date(2026, 11, 5)
REFRESH = date(2026, 11, 3)
DOMAIN = "fabrikamenergy.example"
TENANT = "https://fabrikamenergy.sharepoint.com/sites/"
WAVES = [{"id": "W1", "name": "Pilot", "go_live": "2026-09-01", "planned": 120},
         {"id": "W2", "name": "Wave 2", "go_live": "2026-11-19", "planned": 400},
         {"id": "W3", "name": "Wave 3", "go_live": "2027-01-26", "planned": 600}]

SETTINGS = {
    "organisation": ORG,
    "as_of": "2026-11-05 09:00",
    "currency": "EUR",
    "licence_price_month": 30,
    "licences_owned": 520,
    "copilot_skus": ["Microsoft_365_Copilot", "M365_Copilot"],
    "inactive_days": 30,
    "grace_days": 14,
    "readiness_window_days": 30,
    "training_target": 0.9,
    "training_critical": 0.75,
    "mfa_critical": 0.05,
    "device_target": 0.95,
    "device_critical": 0.85,
    "sensitive_departments": ["HR", "Finance", "Legal"],
    "sensitive_labels": ["Confidential", "Highly Confidential"],
    "inactive_site_days": 180,
    "label_target": 0.6,
    "label_critical": 0.3,
    "allowed_connectors": ["SharePoint", "OneDrive for Business", "Office 365 Outlook", "Office 365 Users", "Microsoft Teams", "Dataverse",
                           "Approvals", "ServiceNow", "Excel Online (Business)"],
    "agent_unused_days": 60,
    "adoption_target": 0.6,
    "adoption_drop": 0.1,
    "min_champions": 1,
    "waves": WAVES,
    "owners": {"licences": "M365 licensing (Raúl Ortega)", "waves": "Copilot rollout lead (Nuria Campos)",
               "oversharing": "SharePoint admin (Diego Martín)", "labels": "Information protection (Clara Rey)",
               "agents": "Power Platform admin (Iker Salas)", "adoption": "Adoption and change (Nuria Campos)"},
}

# department: total, pilot, wave 2, wave 3
DEPTS = [("IT", 95, 40, 0, 30), ("Executive", 25, 20, 0, 0), ("Finance", 110, 20, 80, 0), ("Sales and Marketing", 140, 40, 0, 60),
         ("HR", 65, 0, 60, 0), ("Legal", 30, 0, 30, 0), ("Customer Service", 230, 0, 150, 0), ("Procurement", 60, 0, 50, 0),
         ("Trading", 45, 0, 30, 0), ("Engineering", 330, 0, 0, 250), ("Operations", 380, 0, 0, 160), ("Health and Safety", 60, 0, 0, 50),
         ("Field Services", 230, 0, 0, 50)]
TITLES = {"IT": ["Systems engineer", "Service desk analyst", "Network engineer", "IT manager"],
          "Executive": ["Director", "Executive assistant", "Chief of staff"],
          "Finance": ["Financial analyst", "Accountant", "Controller", "Treasury analyst"],
          "Sales and Marketing": ["Account manager", "Marketing specialist", "Sales manager"],
          "HR": ["HR business partner", "Recruiter", "Payroll specialist"], "Legal": ["Lawyer", "Paralegal", "Compliance officer"],
          "Customer Service": ["Customer agent", "Team lead", "Billing specialist"], "Procurement": ["Buyer", "Category manager"],
          "Trading": ["Energy trader", "Risk analyst", "Scheduler"], "Engineering": ["Engineer", "Project engineer", "Design lead"],
          "Operations": ["Plant operator", "Shift supervisor", "Maintenance planner"], "Health and Safety": ["HSE advisor", "HSE manager"],
          "Field Services": ["Field technician", "Field supervisor"]}
FIRST = ["Ana", "Luis", "Marta", "Javier", "Lucía", "Pablo", "Elena", "Sergio", "Carmen", "David", "Laura", "Jorge", "Sara", "Álvaro",
         "Paula", "Diego", "Irene", "Rubén", "Nerea", "Hugo", "Inés", "Óscar", "Alba", "Adrián", "Rocío", "Marcos", "Beatriz", "Iván", "Claudia",
         "Raquel", "João", "Rita", "Tiago", "Mariana", "Emma", "Oliver", "Grace", "Thomas", "Amelia", "Harry"]
LAST = ["García", "López", "Martín", "Sánchez", "Pérez", "Gómez", "Ruiz", "Díaz", "Moreno", "Muñoz", "Álvarez", "Romero", "Navarro",
        "Torres", "Domínguez", "Vázquez", "Ramos", "Gil", "Serrano", "Blanco", "Molina", "Castro", "Ortiz", "Rubio", "Marín", "Sanz",
        "Iglesias", "Medina", "Silva", "Costa", "Ferreira", "Santos", "Carvalho", "Walker", "Hughes", "Evans", "Bennett", "Clarke"]
ASCII = str.maketrans("áéíóúüñçãõâêôÁÉÍÓÚÑ", "aeiouuncaoaeoAEIOUN")

# pilot users with no Copilot activity in 30 days (of which never used) per department
PILOT_INACTIVE = {"Finance": (9, 2), "Sales and Marketing": (9, 2), "IT": (5, 1), "Executive": (7, 0)}
PILOT_LEAVERS = 3                 # Sales and Marketing, disabled with the licence still assigned
EARLY = {"IT": 9, "Executive": 5}   # licensed outside the waves since June
EARLY_INACTIVE = 4
W2_EARLY = {"Finance": 10, "HR": 8, "Customer Service": 12, "Procurement": 5, "Legal": 5}     # wave 2 champions and managers licensed on 28 Oct
W2_UNTRAINED = {"Customer Service": 70, "Procurement": 20, "Trading": 12, "Finance": 10, "HR": 4, "Legal": 4}
W2_NO_MFA, W2_NONCOMPLIANT = 14, 31
CHAMPION_DEPTS = {"W1": ["IT", "Executive", "Finance", "Sales and Marketing"], "W2": ["Finance", "HR", "Legal", "Customer Service", "Procurement"],
                  "W3": ["Engineering"]}
APP_P = [("teams", 0.8), ("word", 0.55), ("excel", 0.35), ("powerpoint", 0.3), ("outlook", 0.7), ("onenote", 0.08), ("loop", 0.05),
         ("chat", 0.75)]


def _d(x: date | None) -> str:
    return x.isoformat() if x else ""


def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def people(rnd: random.Random) -> list[dict]:
    out, seen = [], set()
    for dept, total, w1, w2, w3 in DEPTS:
        for k in range(total):
            f, l = rnd.choice(FIRST), rnd.choice(LAST)
            base = f"{f}.{l}".lower().translate(ASCII)
            upn = f"{base}@{DOMAIN}"
            n = 2
            while upn in seen:
                upn = f"{base}{n}@{DOMAIN}"
                n += 1
            seen.add(upn)
            wave = "W1" if k < w1 else "W2" if k < w1 + w2 else "W3" if k < w1 + w2 + w3 else ""
            country = "Portugal" if dept in ("Customer Service", "Field Services") and rnd.random() < 0.3 else \
                "United Kingdom" if dept == "Trading" else "Spain"
            out.append({"upn": upn, "name": f"{f} {l}", "dept": dept, "country": country, "title": rnd.choice(TITLES[dept]), "enabled": True,
                        "wave": wave, "mfa": True, "device": True, "copilot": None, "last": None, "apps": {}, "trained": None, "champion": False,
                        "idx": k})
    return out


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(SEED)
    P = people(rnd)
    by_dept = {}
    for p in P:
        by_dept.setdefault(p["dept"], []).append(p)
    managers = {d: ps[-1]["upn"] for d, ps in by_dept.items()}
    # licences
    for p in P:
        if p["wave"] == "W1":
            p["copilot"] = date(2026, 8, 25) + timedelta(days=rnd.randint(0, 7))
    for dept, n in EARLY.items():
        free = [p for p in by_dept[dept] if not p["wave"]]
        for p in free[:n]:
            p["copilot"] = date(2026, 6, 15)
    for dept, n in W2_EARLY.items():
        for p in [p for p in by_dept[dept] if p["wave"] == "W2"][:n]:
            p["copilot"] = date(2026, 10, 28)
    sales_pilot = [p for p in by_dept["Sales and Marketing"] if p["wave"] == "W1"]
    for p in sales_pilot[-PILOT_LEAVERS:]:
        p["enabled"] = False
    # usage
    for p in P:
        if not p["copilot"] or not p["enabled"]:
            continue
        p["last"] = TODAY - timedelta(days=rnd.randint(2, 20))
    for dept, (n, never) in PILOT_INACTIVE.items():
        pilots = [p for p in by_dept[dept] if p["wave"] == "W1" and p["enabled"]]
        for j, p in enumerate(pilots[:n]):
            p["last"] = None if j < never else TODAY - timedelta(days=rnd.randint(34, 70))
    early = [p for p in P if p["copilot"] == date(2026, 6, 15)]
    for p in early[:EARLY_INACTIVE]:
        p["last"] = TODAY - timedelta(days=rnd.randint(40, 110))
    for p in P:
        if p["copilot"] == date(2026, 10, 28) and rnd.random() < 0.4:
            p["last"] = None
    for p in P:
        if p["last"]:
            for app, prob in APP_P:
                if rnd.random() < prob:
                    p["apps"][app] = p["last"] - timedelta(days=rnd.choice([0, 0, 1, 3, 6, 12]))
            if not p["apps"]:
                p["apps"]["chat"] = p["last"]
            p["last"] = max(p["apps"].values())
    # training, champions, MFA and devices
    for p in P:
        if p["wave"] == "W1" and p["enabled"]:
            p["trained"] = date(2026, 8, 20) + timedelta(days=rnd.randint(0, 10))
    w2 = [p for p in P if p["wave"] == "W2"]
    missing = set()
    for dept, n in W2_UNTRAINED.items():
        missing |= {p["upn"] for p in [p for p in w2 if p["dept"] == dept][-n:]}
    for p in w2:
        if p["upn"] not in missing:
            p["trained"] = date(2026, 10, 12) + timedelta(days=rnd.randint(0, 22))
    w3 = [p for p in P if p["wave"] == "W3"]
    for p in w3[:30]:
        p["trained"] = date(2026, 10, 30)
    for wave, depts in CHAMPION_DEPTS.items():
        for dept in depts:
            cand = [p for p in P if p["wave"] == wave and p["dept"] == dept and p["enabled"]]
            for p in cand[:2]:
                p["champion"] = True
                p["trained"] = p["trained"] or date(2026, 10, 1)
    rest = [p for p in P if p["wave"] != "W2"]
    for p in rnd.sample(w2, W2_NO_MFA):
        p["mfa"] = False
    for p in rnd.sample(w2, W2_NONCOMPLIANT):
        p["device"] = False if rnd.random() < 0.7 else None
    for p in rest:
        if p["wave"] == "W1":
            continue
        if rnd.random() < 0.06:
            p["mfa"] = False
        if rnd.random() < 0.1:
            p["device"] = False if rnd.random() < 0.6 else None
    for p in rnd.sample([p for p in P if p["wave"] == "W1" and p["enabled"]], 3):
        p["device"] = False
    # ---------------------------------------------------------- users.csv and copilot_usage.csv
    yn = {True: "Yes", False: "No", None: ""}
    _w(folder / "users.csv", ["UserPrincipalName", "DisplayName", "Department", "Country", "JobTitle", "AccountEnabled", "Manager", "Licenses",
                              "CopilotAssigned", "Wave", "MfaRegistered", "DeviceCompliant"],
       [[p["upn"], p["name"], p["dept"], p["country"], p["title"], "True" if p["enabled"] else "False", managers[p["dept"]] if p["upn"] !=
         managers[p["dept"]] else "", ";".join(["SPE_E5" if p["dept"] in ("IT", "Executive", "Legal", "Trading") else "SPE_E3"]
                                               + (["Microsoft_365_Copilot"] if p["copilot"] else [])),
         _d(p["copilot"]), p["wave"], yn[p["mfa"]], {True: "Compliant", False: "Noncompliant", None: "No device"}[p["device"]]] for p in P])
    _w(folder / "copilot_usage.csv", ["Report Refresh Date", "User Principal Name", "Display Name", "Last Activity Date", "Copilot Chat Last Activity Date",
                                      "Microsoft Teams Copilot Last Activity Date", "Word Copilot Last Activity Date", "Excel Copilot Last Activity Date",
                                      "PowerPoint Copilot Last Activity Date", "Outlook Copilot Last Activity Date",
                                      "OneNote Copilot Last Activity Date", "Loop Copilot Last Activity Date", "Report Period"],
       [[_d(REFRESH), p["upn"], p["name"], _d(p["last"]), _d(p["apps"].get("chat")), _d(p["apps"].get("teams")), _d(p["apps"].get("word")),
         _d(p["apps"].get("excel")), _d(p["apps"].get("powerpoint")), _d(p["apps"].get("outlook")), _d(p["apps"].get("onenote")),
         _d(p["apps"].get("loop")), "30"] for p in P if p["copilot"]])
    # ---------------------------------------------------------- training.csv and survey.csv
    _w(folder / "training.csv", ["UserPrincipalName", "Course", "CompletedDate", "Role"],
       [[p["upn"], "Copilot essentials (90 min)", _d(p["trained"]), "Champion" if p["champion"] else ""] for p in P if p["trained"] or p["champion"]])
    resp = [p for p in P if p["wave"] == "W1" and p["enabled"]]
    resp = rnd.sample(resp, 84)
    _w(folder / "survey.csv", ["UserPrincipalName", "MinutesSavedPerWeek", "Satisfaction"],
       [[p["upn"], (rnd.choice([0, 10, 15]) if p["last"] is None or p["last"] < TODAY - timedelta(days=30) else rnd.choice([20, 30, 45, 45, 60, 60, 90, 120])),
         (rnd.choice([2, 3]) if p["last"] is None or p["last"] < TODAY - timedelta(days=30) else rnd.choice([3, 4, 4, 4, 5, 5]))]
        for p in sorted(resp, key=lambda x: x["upn"])])
    # ---------------------------------------------------------- adoption_history.csv (the adoption.csv of the October review)
    prev = {"IT": (49, 42), "Executive": (25, 21), "Finance": (20, 13), "Sales and Marketing": (40, 30)}
    _w(folder / "adoption_history.csv", ["Date", "Department", "Licensed", "Active30d"],
       [["2026-10-06", k, a, b] for k, (a, b) in prev.items()])
    # ---------------------------------------------------------- sites.csv and labels.csv
    sites, labels = sites_and_labels(rnd, by_dept)
    _w(folder / "sites.csv", ["Url", "Title", "Template", "Department", "OwnerCount", "Owner", "SensitivityLabel", "SharingCapability",
                              "EEEU permission count", "Anyone link count", "Number of users having access", "LastContentModifiedDate",
                              "RestrictContentOrgWideSearch", "RestrictedAccessControl"], sites)
    _w(folder / "labels.csv", ["Url", "Files", "LabelledFiles"], labels)
    # ---------------------------------------------------------- dlp.csv and agents.csv
    _w(folder / "dlp.csv", ["Name", "Mode", "CopilotLocation"],
       [["Copilot - exclude Highly Confidential", "TestWithNotifications", "Yes"], ["Financial data - Exchange and SharePoint", "Enable", "No"],
        ["Personal data (GDPR) - all locations", "Enable", "No"], ["Card numbers - Teams chats", "Enable", "No"]])
    _w(folder / "agents.csv", ["Name", "Owner", "Environment", "Status", "SharedWith", "Connectors", "Authentication", "LastUsed",
                               "DecisionsAboutPeople", "AiRegisterEntry"], agents(by_dept))
    (folder / "settings.json").write_text(json.dumps(SETTINGS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return folder


SITE_PLAN = {
    "IT": ["Service Desk", "Infrastructure", "Architecture", "Security Operations", "Projects", "Change Board"],
    "Executive": ["Leadership Team", "Board Papers"],
    "Finance": ["Accounts Payable", "Budget 2027", "Treasury", "Month-End Close", "Audit 2026", "Tax"],
    "Sales and Marketing": ["Campaigns", "Price Lists", "Brand Assets", "Key Accounts", "Events"],
    "HR": ["Employee Relations", "Payroll and Benefits", "Recruitment 2025", "Learning", "Policies"],
    "Legal": ["Contracts", "Litigation 2023 (closed)", "Regulatory"],
    "Customer Service": ["Knowledge Base", "Billing Disputes", "Team Rotas", "Quality"],
    "Procurement": ["Tenders", "Supplier Onboarding", "Framework Agreements"],
    "Trading": ["Desk Procedures", "Risk Reports", "Market Data"],
    "Engineering": ["Standards Library", "Wind Projects", "Solar Projects", "Grid Connections", "Design Reviews", "CAD Archive 2022"],
    "Operations": ["Shift Handover", "Plant Procedures", "Maintenance Planning", "Outages", "Spares"],
    "Health and Safety": ["Incident Reports", "Risk Assessments", "Toolbox Talks"],
    "Field Services": ["Work Orders", "Vehicle Fleet", "Field Photos 2023"],
}
# title: (eeeu, anyone, owners, label, months since last change, rcd, coverage)
SPECIAL = {
    "HR - Employee Relations": (4, 0, 1, "General", 0, False, 0.42),
    "HR - Payroll and Benefits": (2, 0, 2, "Confidential", 0, False, 0.61),
    "HR - Recruitment 2025": (0, 3, 1, "", 2, False, 0.30),
    "Legal - Litigation 2023 (closed)": (1, 0, 0, "Confidential", 14, False, 0.80),
    "Finance - Budget 2027": (1, 0, 2, "Confidential", 0, True, 0.35),
    "Finance - Accounts Payable": (0, 0, 2, "", 0, False, 0.12),
    "Finance - Treasury": (0, 0, 1, "", 0, False, 0.18),
    "Finance - Month-End Close": (0, 0, 2, "", 0, False, 0.20),
    "Operations - Shift Handover": (3, 0, 2, "General", 0, False, 0.70),
    "Engineering - Standards Library": (2, 0, 2, "General", 1, False, 0.75),
    "Sales and Marketing - Price Lists": (0, 6, 2, "General", 0, False, 0.66),
    "Engineering - CAD Archive 2022": (0, 0, 0, "", 26, False, 0.70),
    "Field Services - Field Photos 2023": (1, 0, 0, "", 20, False, 0.30),
    "IT - Change Board": (0, 0, 0, "General", 3, False, 0.80),
    "Customer Service - Team Rotas": (0, 0, 0, "", 1, False, 0.62),
}


def sites_and_labels(rnd: random.Random, by_dept: dict) -> tuple[list, list]:
    sites, labels = [], []
    one_owner = 0
    for dept, names in SITE_PLAN.items():
        for nm in names:
            title = f"{dept} - {nm}"
            slug = (dept.split()[0][:5] + "-" + nm).lower().translate(ASCII)
            slug = "".join(ch if ch.isalnum() else "-" for ch in slug).strip("-").replace("--", "-")
            url = TENANT + slug
            if title in SPECIAL:
                eeeu, anyone, owners, label, months, rcd, cov = SPECIAL[title]
            else:
                eeeu, anyone, rcd = 0, 0, False
                owners = 2 + rnd.randint(0, 2)
                if one_owner < 9 and rnd.random() < 0.18:
                    owners, one_owner = 1, one_owner + 1
                label = "Confidential" if dept in ("HR", "Finance", "Legal", "Executive") else rnd.choice(["General", "General", "Internal"])
                months = rnd.choice([0, 0, 0, 1, 2, 3])
                cov = {"Finance": 0.25, "HR": 0.55, "Field Services": 0.42}.get(dept, rnd.uniform(0.63, 0.86))
            modified = TODAY - timedelta(days=months * 30 + rnd.randint(1, 20))
            members = len(by_dept[dept])
            users = 1650 if eeeu else (members + rnd.randint(5, 40) if not anyone else members + rnd.randint(40, 120))
            template = "GROUP#0" if rnd.random() < 0.7 else "SITEPAGEPUBLISHING#0"
            admin = by_dept[dept][rnd.randrange(len(by_dept[dept]))]["upn"] if owners else ""
            sites.append([url, title, template, dept, owners, admin, label, "ExternalUserSharingOnly" if anyone or dept == "Procurement" else "Disabled",
                          eeeu, anyone, users, modified.isoformat(), "True" if rcd else "False", "False"])
            files = rnd.randint(300, 6000)
            labels.append([url, files, round(files * cov)])
    return sites, labels


def agents(by_dept: dict) -> list[list]:
    first = {d: ps[0]["upn"] for d, ps in by_dept.items()}
    leaver = [p for p in by_dept["Sales and Marketing"] if p["wave"] == "W1"][-1]["upn"]
    rows = [
        ["Contract Finder", leaver, "Fabrikam (default)", "Published", "Organization", "SharePoint; Dropbox", "Microsoft Entra ID", "2026-11-02",
         "No", ""],
        ["Candidate Screening Assistant", first["HR"], "HR Production", "Published", "Specific people", "SharePoint; Office 365 Outlook",
         "Microsoft Entra ID", "2026-10-30", "Yes", ""],
        ["Leave Request Checker", first["HR"], "HR Production", "Published", "Specific people", "SharePoint; Approvals", "Microsoft Entra ID",
         "2026-11-03", "Yes", "AIR-007"],
        ["IT Helpdesk Agent", first["IT"], "IT Production", "Published", "Organization", "SharePoint; ServiceNow", "Microsoft Entra ID",
         "2026-11-04", "No", ""],
        ["Travel Policy Q&A", first["Finance"], "Fabrikam (default)", "Published", "Organization", "SharePoint", "Microsoft Entra ID", "2026-11-01",
         "No", ""],
        ["Pilot FAQ", first["IT"], "Fabrikam (default)", "Published", "Specific people", "SharePoint", "Microsoft Entra ID", "2026-07-10", "No", ""],
        ["Tender Drafting Helper", first["Procurement"], "Procurement", "Published", "Specific people", "SharePoint; Salesforce",
         "Microsoft Entra ID", "2026-10-29", "No", ""],
        ["Price List Lookup", first["Sales and Marketing"], "Fabrikam (default)", "Published", "Specific people", "SharePoint",
         "Microsoft Entra ID", "", "No", ""],
        ["Shift Handover Summariser", first["Operations"], "Operations", "Published", "Specific people", "SharePoint; Microsoft Teams",
         "Microsoft Entra ID", "2026-11-04", "No", ""],
        ["Safety Incident Triage", first["Health and Safety"], "Operations", "Draft", "Owner only", "SharePoint; Dataverse",
         "Microsoft Entra ID", "", "No", ""],
        ["Budget Variance Explainer", first["Finance"], "Finance", "Draft", "Owner only", "SharePoint; Excel Online (Business)",
         "Microsoft Entra ID", "", "No", ""],
        ["Onboarding Buddy", first["HR"], "HR Production", "Published", "Organization", "SharePoint; Office 365 Users", "Microsoft Entra ID",
         "2026-11-03", "No", ""],
    ]
    return rows


__all__ = ["write", "ORG", "SETTINGS"]
