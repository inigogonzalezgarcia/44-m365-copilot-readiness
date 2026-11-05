"""Loading: the Entra ID users with their licences, wave, MFA registration and device compliance; the Microsoft 365 Copilot usage report
(getMicrosoft365CopilotUsageUserDetail); the SharePoint sites with their sharing, owners, sensitivity label and Copilot restrictions; the
label coverage per site and the DLP policies (Microsoft Purview); the Copilot Studio and Agent Builder agents (Power Platform inventory);
the training records and, optionally, a survey and the adoption history. Forgiving column names, into plain dataclasses."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

USER_ALIASES = {
    "upn": ["UserPrincipalName", "user principal name", "upn", "username", "user name"],
    "name": ["DisplayName", "display name", "name"],
    "department": ["Department", "dept"],
    "country": ["Country", "UsageLocation", "usage location"],
    "title": ["JobTitle", "job title", "title"],
    "enabled": ["AccountEnabled", "account enabled", "enabled"],
    "manager": ["Manager", "manager upn"],
    "licences": ["Licenses", "licences", "assigned licenses", "skus", "SkuPartNumber"],
    "copilot_assigned": ["CopilotAssigned", "copilot assigned", "copilot licence assigned", "copilot license assigned"],
    "wave": ["Wave", "rollout wave", "copilot wave"],
    "mfa": ["MfaRegistered", "IsMfaRegistered", "mfa registered", "mfa"],
    "device": ["DeviceCompliant", "device compliant", "compliant device", "compliance state"],
}
USAGE_ALIASES = {
    "upn": ["User Principal Name", "UserPrincipalName", "upn"],
    "refresh": ["Report Refresh Date"],
    "last": ["Last Activity Date", "Last activity date (UTC)"],
    "teams": ["Microsoft Teams Copilot Last Activity Date"],
    "word": ["Word Copilot Last Activity Date"],
    "excel": ["Excel Copilot Last Activity Date"],
    "powerpoint": ["PowerPoint Copilot Last Activity Date"],
    "outlook": ["Outlook Copilot Last Activity Date"],
    "onenote": ["OneNote Copilot Last Activity Date"],
    "loop": ["Loop Copilot Last Activity Date"],
    "chat": ["Copilot Chat Last Activity Date", "Copilot Chat (work) Last Activity Date"],
}
APPS = ("teams", "word", "excel", "powerpoint", "outlook", "onenote", "loop", "chat")
APP_LABEL = {"teams": "Teams", "word": "Word", "excel": "Excel", "powerpoint": "PowerPoint", "outlook": "Outlook", "onenote": "OneNote",
             "loop": "Loop", "chat": "Copilot Chat"}
SITE_ALIASES = {
    "url": ["Url", "Site URL", "site url"],
    "title": ["Title", "Site Name", "site name"],
    "template": ["Template", "Site Template", "site template"],
    "department": ["Department", "business owner", "dept"],
    "owners": ["OwnerCount", "owner count", "owners"],
    "admin": ["Owner", "Primary admin email", "primary admin", "primary admin email"],
    "label": ["SensitivityLabel", "Site Sensitivity", "sensitivity label", "label"],
    "sharing": ["SharingCapability", "sharing capability", "ExternalSharing", "external sharing"],
    "eeeu": ["EEEU permission count", "eeeu permissions", "eeeu"],
    "anyone": ["Anyone link count", "anyone links", "anyone"],
    "users": ["Number of users having access", "users with access", "users having access"],
    "modified": ["LastContentModifiedDate", "last content modified date", "last activity", "last modified"],
    "rcd": ["RestrictContentOrgWideSearch", "restricted content discovery", "rcd"],
    "rac": ["RestrictedAccessControl", "restricted access control", "rac"],
}
LABEL_ALIASES = {
    "url": ["Url", "Site URL", "site url", "location"],
    "files": ["Files", "File count", "file count", "items"],
    "labelled": ["LabelledFiles", "labelled files", "labeled files", "files with a label"],
}
DLP_ALIASES = {
    "name": ["Name", "policy", "policy name"],
    "mode": ["Mode", "state"],
    "copilot": ["CopilotLocation", "copilot location", "copilot"],
}
AGENT_ALIASES = {
    "name": ["Name", "agent name", "display name"],
    "owner": ["Owner", "owner upn", "created by", "creator"],
    "environment": ["Environment", "environment name"],
    "status": ["Status", "published", "state", "publish status"],
    "shared": ["SharedWith", "shared with", "sharing", "audience"],
    "connectors": ["Connectors", "connector", "data sources", "knowledge sources"],
    "auth": ["Authentication", "authentication", "auth"],
    "last_used": ["LastUsed", "last used", "last activity date", "last activity date (utc)"],
    "people": ["DecisionsAboutPeople", "decisions about people", "affects people"],
    "register": ["AiRegisterEntry", "ai register entry", "register entry", "ai register"],
}
TRAINING_ALIASES = {
    "upn": ["UserPrincipalName", "user principal name", "upn", "email"],
    "course": ["Course", "module"],
    "completed": ["CompletedDate", "completed date", "completed", "completion date"],
    "role": ["Role", "champion"],
}
SURVEY_ALIASES = {
    "upn": ["UserPrincipalName", "user principal name", "upn", "email"],
    "minutes": ["MinutesSavedPerWeek", "minutes saved per week", "minutes saved"],
    "satisfaction": ["Satisfaction", "score", "rating"],
}
HISTORY_ALIASES = {
    "date": ["Date", "as of", "snapshot"],
    "department": ["Department", "dept"],
    "licensed": ["Licensed", "licensed users"],
    "active": ["Active30d", "active 30d", "active_30d", "active users"],
}
YES = {"yes", "y", "true", "1", "on", "si", "compliant", "enabled", "published"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M", "%m/%d/%Y")
DEFAULT_OWNERS = {"licences": "Microsoft 365 licensing (IT)", "waves": "Copilot rollout lead", "oversharing": "SharePoint administrator",
                  "labels": "Information protection lead", "agents": "Power Platform administrator", "adoption": "Adoption and change lead"}
COPILOT_SKUS = ["Microsoft_365_Copilot", "M365_Copilot", "Microsoft_365_Copilot_EDU"]


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip()
    if not s or _norm(s) in {"n a", "na", "none", "null", "never"}:
        return None
    s = re.sub(r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})$", "", s)
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def parse_d(v) -> date | None:
    x = parse_dt(v)
    return x.date() if x else None


def yes(v) -> bool:
    return _norm(v) in YES


def tri(v) -> bool | None:
    """yes / no / unknown (empty)."""
    n = _norm(v)
    if not n:
        return None
    return n in YES


def num(v) -> float | None:
    s = str(v or "").strip().replace("%", "").replace("€", "").replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    s = s.replace(",", "")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def split_list(v) -> list[str]:
    return [x.strip() for x in re.split(r"[;|,]", str(v or "")) if x.strip()]


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header = fh.readline()
        fh.seek(0)
        delim = max(",;\t", key=header.count)
        reader = csv.DictReader(fh, delimiter=delim)
        return list(reader.fieldnames or []), list(reader)


def _map(fields: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    heads = {_norm(h): h for h in fields}
    cols = {}
    for k, names in aliases.items():
        for n in names + [k.replace("_", " ")]:
            if _norm(n) in heads and heads[_norm(n)] not in cols.values():
                cols[k] = heads[_norm(n)]
                break
    return cols


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    fields, raw = _read(path)
    cols = _map(fields, aliases)
    return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in raw]


def _upn(v) -> str:
    return str(v or "").strip().lower()


@dataclass
class User:
    upn: str
    name: str = ""
    department: str = ""
    country: str = ""
    title: str = ""
    enabled: bool = True
    manager: str = ""
    licences: list = field(default_factory=list)
    copilot_assigned: date | None = None
    wave: str = ""
    mfa: bool | None = None
    device: bool | None = None
    copilot: bool = False


@dataclass
class Usage:
    upn: str
    last: date | None = None
    apps: dict = field(default_factory=dict)      # app -> last activity date
    refresh: date | None = None


@dataclass
class Site:
    url: str
    title: str = ""
    template: str = ""
    department: str = ""
    owners: int | None = None
    admin: str = ""
    label: str = ""
    sharing: str = ""
    eeeu: int = 0
    anyone: int = 0
    users: int | None = None
    modified: date | None = None
    rcd: bool = False
    rac: bool = False


@dataclass
class LabelCoverage:
    url: str
    files: int = 0
    labelled: int = 0


@dataclass
class DlpPolicy:
    name: str
    mode: str = ""
    copilot: bool = False


@dataclass
class Agent:
    name: str
    owner: str = ""
    environment: str = ""
    status: str = ""
    shared: str = ""
    connectors: list = field(default_factory=list)
    auth: str = ""
    last_used: date | None = None
    people: bool = False
    register: str = ""

    @property
    def published(self) -> bool:
        return _norm(self.status) in {"published", "yes", "true", "1", "active"}


@dataclass
class Training:
    upn: str
    course: str = ""
    completed: date | None = None
    champion: bool = False


@dataclass
class Survey:
    upn: str
    minutes: float | None = None
    satisfaction: float | None = None


@dataclass
class History:
    day: date
    department: str
    licensed: int
    active: int


@dataclass
class Wave:
    id: str
    name: str = ""
    go_live: date | None = None
    planned: int | None = None


@dataclass
class Settings:
    organisation: str = "Microsoft 365 Copilot readiness review"
    as_of: datetime | None = None
    currency: str = "EUR"
    licence_price_month: float = 30.0
    licences_owned: int | None = None
    copilot_skus: list = field(default_factory=lambda: [s.lower() for s in COPILOT_SKUS])
    inactive_days: int = 30
    grace_days: int = 14
    readiness_window_days: int = 30
    training_target: float = 0.9
    training_critical: float = 0.75
    mfa_critical: float = 0.05
    device_target: float = 0.95
    device_critical: float = 0.85
    sensitive_departments: list = field(default_factory=lambda: ["hr", "human resources", "finance", "legal"])
    sensitive_labels: list = field(default_factory=lambda: ["confidential", "highly confidential"])
    inactive_site_days: int = 180
    label_target: float = 0.6
    label_critical: float = 0.3
    allowed_connectors: list = field(default_factory=list)
    agent_unused_days: int = 60
    org_wide_values: list = field(default_factory=lambda: ["organization", "organisation", "everyone", "entire organization", "all users", "tenant"])
    adoption_target: float = 0.6
    adoption_drop: float = 0.1
    min_champions: int = 1
    waves: list = field(default_factory=list)
    site_departments: dict = field(default_factory=dict)
    owners: dict = field(default_factory=lambda: dict(DEFAULT_OWNERS))

    def owner(self, area: str) -> str:
        return self.owners.get(area) or DEFAULT_OWNERS.get(area, "Copilot rollout lead")

    def wave_list(self) -> list[Wave]:
        out = []
        for w in self.waves:
            out.append(Wave(str(w.get("id", "")), str(w.get("name", "") or w.get("id", "")), parse_d(w.get("go_live")),
                            int(num(w.get("planned")) or 0) or None))
        return sorted(out, key=lambda w: (w.go_live or date.max, w.id))


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k) or v is None:
            continue
        cur = getattr(s, k)
        if k == "as_of":
            s.as_of = parse_dt(v)
        elif k == "waves":
            s.waves = [dict(x) for x in v]
        elif k == "licences_owned":
            s.licences_owned = int(num(v) or 0)
        elif isinstance(cur, dict):
            if k == "site_departments":
                s.site_departments = {str(a).lower(): str(b) for a, b in v.items()}
            else:
                cur.update({str(a): b for a, b in v.items()})
        elif isinstance(cur, list):
            setattr(s, k, [str(x).lower() for x in v])
        elif isinstance(cur, bool):
            setattr(s, k, bool(v))
        elif isinstance(cur, int):
            setattr(s, k, int(num(v) or 0))
        elif isinstance(cur, float):
            setattr(s, k, float(num(v) or 0))
        else:
            setattr(s, k, v)
    return s


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    users: list[User] = field(default_factory=list)
    usage: dict = field(default_factory=dict)          # upn -> Usage
    sites: list[Site] = field(default_factory=list)
    labels: dict = field(default_factory=dict)         # url -> LabelCoverage
    dlp: list[DlpPolicy] = field(default_factory=list)
    agents: list[Agent] = field(default_factory=list)
    training: list[Training] = field(default_factory=list)
    survey: list[Survey] = field(default_factory=list)
    history: list[History] = field(default_factory=list)
    sources: dict = field(default_factory=dict)

    @property
    def today(self) -> date:
        return self.as_of.date()


# ---------------------------------------------------------------- loaders

def load_users(path: Path, skus: list[str] | None = None) -> list[User]:
    skus = [s.lower() for s in (skus or COPILOT_SKUS)]
    out = []
    for r in _rows(path, USER_ALIASES):
        if not r.get("upn"):
            continue
        lic = split_list(r.get("licences"))
        en = tri(r.get("enabled"))
        dev = r.get("device", "")
        out.append(User(_upn(r["upn"]), r.get("name", ""), r.get("department", ""), r.get("country", ""), r.get("title", ""),
                        True if en is None else en, _upn(r.get("manager")), lic, parse_d(r.get("copilot_assigned")), r.get("wave", ""),
                        tri(r.get("mfa")), None if not dev or _norm(dev) in {"no device", "unknown"} else tri(dev),
                        any(x.lower() in skus for x in lic)))
    return out


def load_usage(path: Path) -> dict:
    out = {}
    for r in _rows(path, USAGE_ALIASES):
        if not r.get("upn"):
            continue
        out[_upn(r["upn"])] = Usage(_upn(r["upn"]), parse_d(r.get("last")), {a: parse_d(r.get(a)) for a in APPS if parse_d(r.get(a))},
                                    parse_d(r.get("refresh")))
    return out


def site_department(url: str, title: str, mapping: dict) -> str:
    low = f"{url} {title}".lower()
    for k in sorted(mapping, key=lambda x: (-len(x), x)):
        if k in low:
            return mapping[k]
    return ""


def load_sites(path: Path, mapping: dict | None = None) -> list[Site]:
    out = []
    for r in _rows(path, SITE_ALIASES):
        if not r.get("url"):
            continue
        url = r["url"].rstrip("/").lower()
        dept = r.get("department") or site_department(url, r.get("title", ""), mapping or {})
        own = num(r.get("owners"))
        users = num(r.get("users"))
        out.append(Site(url, r.get("title", ""), r.get("template", ""), dept, None if own is None else int(own), _upn(r.get("admin")),
                        r.get("label", ""), r.get("sharing", ""), int(num(r.get("eeeu")) or 0), int(num(r.get("anyone")) or 0),
                        None if users is None else int(users), parse_d(r.get("modified")), yes(r.get("rcd")), yes(r.get("rac"))))
    return out


def load_labels(path: Path) -> dict:
    return {r["url"].rstrip("/").lower(): LabelCoverage(r["url"].rstrip("/").lower(), int(num(r.get("files")) or 0), int(num(r.get("labelled")) or 0))
            for r in _rows(path, LABEL_ALIASES) if r.get("url")}


def load_dlp(path: Path) -> list[DlpPolicy]:
    return [DlpPolicy(r["name"], r.get("mode", ""), yes(r.get("copilot"))) for r in _rows(path, DLP_ALIASES) if r.get("name")]


def load_agents(path: Path) -> list[Agent]:
    return [Agent(r["name"], _upn(r.get("owner")), r.get("environment", ""), r.get("status", ""), r.get("shared", ""),
                  split_list(r.get("connectors")), r.get("auth", ""), parse_d(r.get("last_used")), yes(r.get("people")), r.get("register", ""))
            for r in _rows(path, AGENT_ALIASES) if r.get("name")]


def load_training(path: Path) -> list[Training]:
    return [Training(_upn(r["upn"]), r.get("course", ""), parse_d(r.get("completed")), _norm(r.get("role")) in {"champion", "yes", "true", "1"})
            for r in _rows(path, TRAINING_ALIASES) if r.get("upn")]


def load_survey(path: Path) -> list[Survey]:
    return [Survey(_upn(r["upn"]), num(r.get("minutes")), num(r.get("satisfaction"))) for r in _rows(path, SURVEY_ALIASES) if r.get("upn")]


def load_history(path: Path) -> list[History]:
    out = []
    for r in _rows(path, HISTORY_ALIASES):
        d = parse_d(r.get("date"))
        if d and r.get("department"):
            out.append(History(d, r["department"], int(num(r.get("licensed")) or 0), int(num(r.get("active")) or 0)))
    return out


FILES = {
    "users.csv": "Entra ID users with licences, Copilot licence date, wave, MFA registration and device compliance (Microsoft Graph)",
    "copilot_usage.csv": "Microsoft 365 Copilot usage report per user (getMicrosoft365CopilotUsageUserDetail)",
    "sites.csv": "SharePoint sites with owners, sensitivity label, sharing, EEEU permissions, Anyone links and Copilot restrictions",
    "labels.csv": "Files and labelled files per site (Microsoft Purview)",
    "dlp.csv": "DLP policies and whether they cover the Microsoft 365 Copilot location (Get-DlpCompliancePolicy)",
    "agents.csv": "Copilot Studio and Agent Builder agents (Power Platform inventory)",
    "training.csv": "Copilot training completions and champions",
    "survey.csv": "Survey: minutes saved per week and satisfaction (optional)",
    "adoption_history.csv": "Earlier adoption snapshots per department (optional; the adoption.csv of earlier runs)",
}


def _find(folder: Path, name: str) -> Path | None:
    p = folder / name
    if p.exists():
        return p
    stem = name.rsplit(".", 1)[0]
    alts = sorted(folder.glob(f"{stem}*.csv"))
    return alts[0] if alts else None


def load(folder: Path, as_of: datetime | None = None) -> Data:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"no folder {folder}")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    when = as_of or s.as_of or datetime.now().replace(second=0, microsecond=0)
    paths = {n: _find(folder, n) for n in FILES}
    if not paths["users.csv"]:
        raise FileNotFoundError(f"{folder}: need users.csv ({FILES['users.csv']})")
    d = Data(s, when)
    d.users = load_users(paths["users.csv"], s.copilot_skus)
    if not d.users:
        raise ValueError(f"{paths['users.csv']}: no users (check the UserPrincipalName column)")
    loaders = {"copilot_usage.csv": ("usage", load_usage), "sites.csv": ("sites", lambda p: load_sites(p, s.site_departments)),
               "labels.csv": ("labels", load_labels), "dlp.csv": ("dlp", load_dlp), "agents.csv": ("agents", load_agents),
               "training.csv": ("training", load_training), "survey.csv": ("survey", load_survey),
               "adoption_history.csv": ("history", load_history)}
    for n, (attr, fn) in loaders.items():
        if paths[n]:
            setattr(d, attr, fn(paths[n]))
    d.sources = {"users.csv": len(d.users)} | {n: len(getattr(d, attr)) for n, (attr, _) in loaders.items() if paths[n]}
    return d


__all__ = ["Data", "Settings", "User", "Usage", "Site", "LabelCoverage", "DlpPolicy", "Agent", "Training", "Survey", "History", "Wave", "load",
           "APPS", "APP_LABEL"]
