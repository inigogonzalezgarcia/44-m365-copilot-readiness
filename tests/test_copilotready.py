import csv
import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from copilotready import cli
from copilotready.checks import CRITICAL, INFO, WARNING, area_status, overall, proposal, review, run_all, summary
from copilotready.model import (Agent, Data, DlpPolicy, History, LabelCoverage, Site, Training, Usage, User, load, load_sites, load_usage,
                                load_users, settings_from_dict)

AS_OF = datetime(2026, 11, 5, 9, 0)
TODAY = AS_OF.date()
WAVES = [{"id": "W1", "name": "Pilot", "go_live": "2026-09-01"}, {"id": "W2", "name": "Wave 2", "go_live": "2026-11-19"},
         {"id": "W3", "name": "Wave 3", "go_live": "2027-01-26"}]


def write(path: Path, header: list[str], rows: list[list]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def user(n, dept="Sales", wave="", copilot=True, assigned=date(2026, 8, 25), enabled=True, mfa=True, device=True) -> User:
    return User(f"u{n}@contoso.example", f"User {n}", dept, "Spain", "Analyst", enabled, "", ["SPE_E3"] + (["Microsoft_365_Copilot"] if copilot else []),
                assigned if copilot else None, wave, mfa, device, copilot)


def used(u: User, days_ago: int | None) -> Usage:
    last = None if days_ago is None else TODAY - timedelta(days=days_ago)
    return Usage(u.upn, last, {"teams": last} if last else {})


def data(users=(), usage=(), sites=(), labels=(), dlp=(), agents=(), training=(), history=(), **raw) -> Data:
    raw.setdefault("waves", WAVES)
    d = Data(settings_from_dict(raw), AS_OF, list(users), {u.upn: u for u in usage}, list(sites), {x.url: x for x in labels}, list(dlp),
             list(agents), list(training), [], list(history))
    d.sources = {"users.csv": len(d.users)} | ({"dlp.csv": len(d.dlp)} if dlp else {})
    return d


def rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def issues(rv, code):
    return [i for i in rv["issues"] if i.code == code]


def trained(users, day=date(2026, 10, 20)):
    return [Training(u.upn, "Copilot essentials", day) for u in users]


class TestLoading(unittest.TestCase):
    def test_users_usage_and_sites_from_real_column_names(self):
        with tempfile.TemporaryDirectory() as t:
            u = write(Path(t) / "users.csv", ["UserPrincipalName", "DisplayName", "Department", "AccountEnabled", "Licenses", "CopilotAssigned", "Wave",
                                              "MfaRegistered", "DeviceCompliant"],
                      [["Ana@Contoso.example", "Ana", "HR", "True", "SPE_E5;Microsoft_365_Copilot", "2026-09-01T10:00:00Z", "W1", "Yes", "Compliant"],
                       ["luis@contoso.example", "Luis", "IT", "False", "SPE_E3", "", "", "No", "No device"]])
            us = write(Path(t) / "copilot_usage.csv", ["Report Refresh Date", "User Principal Name", "Display Name", "Last Activity Date",
                                                       "Copilot Chat Last Activity Date", "Microsoft Teams Copilot Last Activity Date",
                                                       "Word Copilot Last Activity Date", "Report Period"],
                       [["2026-11-03", "ana@contoso.example", "Ana", "2026-11-02", "2026-11-02", "", "2026-10-20", "30"]])
            st = write(Path(t) / "sites.csv", ["Url", "Title", "Template", "OwnerCount", "SensitivityLabel", "SharingCapability", "EEEU permission count",
                                               "Anyone link count", "LastContentModifiedDate", "RestrictContentOrgWideSearch"],
                       [["https://contoso.sharepoint.com/sites/hr-payroll/", "HR Payroll", "GROUP#0", "1", "", "Disabled", "2", "0", "2026-10-01", "False"]])
            users = load_users(u)
            usage = load_usage(us)
            sites = load_sites(st, {"/hr-": "HR"})
        self.assertEqual(users[0].upn, "ana@contoso.example")
        self.assertTrue(users[0].copilot and users[0].mfa and users[0].device)
        self.assertEqual(users[0].copilot_assigned, date(2026, 9, 1))
        self.assertFalse(users[1].enabled or users[1].copilot)
        self.assertIsNone(users[1].device)
        self.assertEqual(usage["ana@contoso.example"].apps, {"chat": date(2026, 11, 2), "word": date(2026, 10, 20)})
        self.assertEqual((sites[0].url, sites[0].department, sites[0].eeeu, sites[0].owners, sites[0].rcd),
                         ("https://contoso.sharepoint.com/sites/hr-payroll", "HR", 2, 1, False))


class TestLicences(unittest.TestCase):
    def test_inactive_never_used_disabled_and_grace(self):
        a, b, c, n, x = user(1), user(2), user(3), user(4, assigned=TODAY - timedelta(days=5)), user(5, enabled=False)
        rv = review(data([a, b, c, n, x], [used(a, 3), used(b, 45)], licence_price_month=30))
        reasons = {r["user"].upn: r["reason"] for r in rv["reclaim"]}
        self.assertEqual(reasons, {"u2@contoso.example": "inactive 45 days", "u3@contoso.example": "never used", "u5@contoso.example": "account disabled"})
        self.assertEqual(issues(rv, "LIC-01")[0].cost, 60)
        self.assertEqual(len(issues(rv, "LIC-02")), 1)

    def test_licence_pool_for_the_next_wave(self):
        live = [user(k, wave="W1") for k in range(4)]
        nxt = [user(10 + k, wave="W2", copilot=False) for k in range(6)]
        idle = user(99)
        base = dict(users=live + nxt + [idle], usage=[used(u, 2) for u in live])
        rv = review(data(**base, licences_owned=8))           # 5 assigned, 3 free, 6 needed: 3 short, 1 to reclaim
        self.assertEqual((rv["pool"]["need"], rv["pool"]["free"], rv["pool"]["shortfall"]), (6, 3, 3))
        self.assertEqual(issues(rv, "LIC-03")[0].severity, CRITICAL)
        rv = review(data(**base, licences_owned=10))
        self.assertEqual(issues(rv, "LIC-03")[0].severity, WARNING)
        self.assertEqual(issues(review(data(**base, licences_owned=20)), "LIC-03"), [])


class TestWaves(unittest.TestCase):
    def test_training_mfa_and_devices_of_the_next_wave(self):
        w2 = [user(k, wave="W2", copilot=False) for k in range(20)]
        w2[0].mfa = w2[3].mfa = False
        w2[1].device = None
        w2[2].device = False
        rv = review(data(w2, training=trained(w2[:14])))       # 70% trained, go-live in 14 days
        self.assertEqual(issues(rv, "WAV-01")[0].severity, CRITICAL)
        self.assertEqual(issues(rv, "WAV-02")[0].severity, CRITICAL)          # 10% over mfa_critical (5%)
        self.assertEqual(issues(rv, "WAV-03")[0].severity, WARNING)           # 90% compliant
        rv = review(data(w2, training=trained(w2[:17]), mfa_critical=0.1))
        self.assertEqual([i.severity for i in issues(rv, "WAV-01") + issues(rv, "WAV-02")], [WARNING, WARNING])

    def test_later_waves_are_information_and_live_waves_need_licences(self):
        w3 = [user(k, wave="W3", copilot=False, mfa=False) for k in range(10)]
        live = [user(20 + k, wave="W1", copilot=k > 0) for k in range(5)]
        rv = review(data(w3 + live, [used(u, 1) for u in live[1:]], training=trained(live)))
        self.assertTrue(all(i.severity == INFO for i in rv["issues"] if "W3" in i.waves))
        self.assertEqual(issues(rv, "WAV-04")[0].item, "u20@contoso.example")
        self.assertEqual([w["status"] for w in rv["waves"]], ["live", "next", "later"])


class TestOversharing(unittest.TestCase):
    def test_eeeu_anyone_owners_labels_and_inactive_sites(self):
        hr = Site("https://x/sites/hr", "HR cases", "", "HR", 1, "", "", "", eeeu=3, users=900, modified=TODAY)
        ops = Site("https://x/sites/ops", "Ops", "", "Operations", 0, "", "General", "", eeeu=1, anyone=2, modified=TODAY - timedelta(days=400))
        fin = Site("https://x/sites/fin", "Finance", "", "Finance", 2, "", "Confidential", "", eeeu=1, rcd=True, modified=TODAY)
        users = [user(1, "HR", "W2", False), user(2, "Operations", "W3", False)]
        rv = review(data(users, sites=[hr, ops, fin]))
        sev = {(i.code, i.item.rsplit("/", 1)[-1]): i.severity for i in rv["issues"] if i.code.startswith("OVS")}
        self.assertEqual(sev[("OVS-01", "hr")], CRITICAL)
        self.assertEqual(sev[("OVS-01", "ops")], WARNING)
        self.assertEqual(sev[("OVS-01", "fin")], INFO)              # Restricted Content Discovery on while it is fixed
        self.assertEqual(sev[("OVS-02", "ops")], WARNING)
        self.assertEqual((sev[("OVS-03", "hr")], sev[("OVS-03", "ops")]), (INFO, WARNING))
        self.assertEqual(sev[("OVS-04", "hr")], WARNING)
        self.assertEqual(sev[("OVS-05", "ops")], WARNING)
        crit = [i for i in issues(rv, "OVS-01") if i.severity == CRITICAL][0]
        self.assertEqual(crit.waves, ("*",))
        self.assertEqual([i for i in issues(rv, "OVS-01") if i.severity == WARNING][0].waves, ("W3",))


class TestLabelsAndAgents(unittest.TestCase):
    def test_label_coverage_and_dlp_for_copilot(self):
        fin = Site("https://x/sites/fin", "Finance", "", "Finance", 2, "", "Confidential", "")
        it = Site("https://x/sites/it", "IT", "", "IT", 2, "", "General", "")
        cov = [LabelCoverage(fin.url, 1000, 200), LabelCoverage(it.url, 1000, 500)]
        rv = review(data([user(1, "Finance", "W2", False)], sites=[fin, it], labels=cov, dlp=[DlpPolicy("Copilot", "TestWithNotifications", True)]))
        self.assertEqual([(i.item, i.severity) for i in issues(rv, "LAB-01")], [("Finance", CRITICAL), ("IT", WARNING)])
        self.assertIn("simulation", issues(rv, "LAB-02")[0].text)
        rv = review(data([user(1)], dlp=[DlpPolicy("Copilot", "Enable", True)]))
        self.assertEqual(issues(rv, "LAB-02"), [])

    def test_agents_owner_audience_connectors_use_and_ai_register(self):
        owner, gone = user(1), user(2, enabled=False)
        ags = [Agent("Finder", gone.upn, "Default", "Published", "Organization", ["SharePoint", "Dropbox"], "Entra", TODAY),
               Agent("Screening", owner.upn, "HR", "Published", "Specific people", ["SharePoint"], "Entra", TODAY, True, ""),
               Agent("Leave", owner.upn, "HR", "Published", "Specific people", ["SharePoint"], "Entra", TODAY, True, "AIR-7"),
               Agent("Old", owner.upn, "IT", "Published", "Specific people", ["SharePoint"], "Entra", TODAY - timedelta(days=90)),
               Agent("Draft", "", "IT", "Draft", "Owner only", ["SharePoint"], "Entra", None)]
        rv = review(data([owner, gone], agents=ags, allowed_connectors=["SharePoint"]))
        got = {(i.code, i.item): i.severity for i in rv["issues"] if i.code.startswith("AGT")}
        self.assertEqual(got, {("AGT-01", "Finder"): CRITICAL, ("AGT-02", "Finder"): WARNING, ("AGT-03", "Finder"): CRITICAL,
                               ("AGT-05", "Screening"): WARNING, ("AGT-04", "Old"): WARNING, ("AGT-01", "Draft"): WARNING})


class TestAdoptionAndVerdict(unittest.TestCase):
    def test_adoption_rate_trend_and_champions(self):
        fin = [user(k, "Finance", "W1") for k in range(10)]
        usage = [used(u, 2) for u in fin[:5]]
        hist = [History(date(2026, 10, 6), "Finance", 10, 8)]
        w2 = [user(100 + k, "Trading", "W2", False) for k in range(12)]
        rv = review(data(fin + w2, usage, training=trained(fin + w2), history=hist))
        self.assertIn("5 of 10", issues(rv, "ADP-01")[0].text)
        self.assertIn("down from 80%", issues(rv, "ADP-02")[0].text)
        self.assertEqual([i.item for i in issues(rv, "ADP-03")], ["Finance", "Trading"])
        row = [r for r in rv["adoption"] if r["department"] == "Finance"][0]
        self.assertAlmostEqual(row["change"], -0.3)
        self.assertEqual(rv["apps"]["teams"], 5)

    def test_wave_verdicts_and_overall(self):
        w2 = [user(k, "IT", "W2", False) for k in range(10)]
        champ = [Training(u.upn, "c", date(2026, 10, 1), True) for u in w2[:1]] + trained(w2[1:])
        d = data(w2, training=champ)
        rv = review(d)
        f = run_all(d, rv)
        self.assertEqual([w["verdict"] for w in rv["waves"]], ["ready", "ready", "ready"])
        self.assertEqual(overall(f), "ready")
        hr = Site("https://x/sites/hr", "HR", "", "HR", 2, "", "General", "", eeeu=1)
        d = data(w2, sites=[hr], training=champ)
        rv = review(d)
        f = run_all(d, rv)
        self.assertEqual([w["verdict"] for w in rv["waves"]], ["not ready"] * 3)
        self.assertEqual(proposal(rv["waves"][1]), "no go until the blockers are fixed")
        self.assertEqual(area_status(f)["Oversharing"], CRITICAL)
        self.assertEqual(overall(f), "not ready")

    def test_settings_override_thresholds(self):
        s = settings_from_dict({"training_target": "80", "inactive_days": "60", "allowed_connectors": ["SharePoint"], "licences_owned": "500",
                                "site_departments": {"/HR-": "HR"}, "owners": {"agents": "Maker team"}})
        self.assertEqual((s.training_target, s.inactive_days, s.allowed_connectors, s.licences_owned), (80.0, 60, ["sharepoint"], 500))
        self.assertEqual(s.site_departments, {"/hr-": "HR"})
        self.assertEqual((s.owner("agents"), s.owner("licences")), ("Maker team", "Microsoft 365 licensing (IT)"))
        a = user(1)
        rv = review(data([a], [used(a, 45)], inactive_days=60))
        self.assertEqual(rv["reclaim"], [])


class TestOutputs(unittest.TestCase):
    def test_demo_end_to_end_is_deterministic(self):
        with tempfile.TemporaryDirectory() as t:
            hashes = []
            for k in range(2):
                out = Path(t) / f"out{k}"
                self.assertEqual(cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)]), 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                hashes.append({n: hashlib.sha1((out / n).read_bytes()).hexdigest() for n in cli.OUTPUTS}
                              | {n.name: hashlib.sha1(n.read_bytes()).hexdigest() for n in (Path(t) / f"data{k}").iterdir()})
            self.assertEqual(hashes[0], hashes[1])
            self.assertEqual(json.loads((Path(t) / "data0" / "settings.json").read_text(encoding="utf-8"))["as_of"], "2026-11-05 09:00")
            self.assertLess(sum(p.stat().st_size for p in (Path(t) / "data0").iterdir()), 1_000_000)
            d = load(Path(t) / "data0")
        rv = review(d)
        f = run_all(d, rv)
        sm = summary(d, rv)
        self.assertEqual(overall(f), "not ready")
        self.assertEqual((sm["users"], sm["licensed"], sm["reclaim"], sm["disabled"], rv["pool"]["shortfall"]), (1800, 174, 37, 3, 14))
        self.assertEqual([w[3] for w in sm["waves"]], ["not ready", "not ready", "not ready"])
        w2 = rv["waves"][1]
        self.assertEqual((w2["users"], w2["trained"], w2["no_mfa"], w2["not_compliant"]), (400, 280, 14, 31))
        crit = {x.code for x in f if x.severity == CRITICAL}
        self.assertEqual(crit, {"WAV-01", "OVS-01", "OVS-02", "LAB-01", "AGT-01", "AGT-03"})
        self.assertIn("HR - Employee Relations", [x for x in f if x.code == "OVS-01" and x.severity == CRITICAL][0].detail)
        self.assertIn("Finance: 24%", [x for x in f if x.code == "LAB-01" and x.severity == CRITICAL][0].detail)
        self.assertIn("Contract Finder", [x for x in f if x.code == "AGT-03" and x.severity == CRITICAL][0].detail)
        self.assertIn("Trading", [x for x in f if x.code == "ADP-03"][0].detail)

    def test_pack_and_csv_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["demo", "--data", str(Path(t) / "d"), "--out", str(Path(t) / "o")]), 0)
            o = Path(t) / "o"
            pack = (o / "readiness-pack.md").read_text(encoding="utf-8")
            html = (o / "report.html").read_text(encoding="utf-8")
            rc = rows(o / "licence-reclaim.csv")
            ov = rows(o / "oversharing.csv")
            wv = rows(o / "waves.csv")
            act = rows(o / "actions.csv")
            ad = rows(o / "adoption.csv")
        for h in ("## Decisions per wave", "## Headlines", "## 1. Wave readiness", "## 2. Licences to reclaim", "## 3. Oversharing to fix before the wave",
                  "## 4. Labels and DLP", "## 5. Agents", "## 6. Adoption", "## Actions", "## Sign-off"):
            self.assertIn(h, pack)
        self.assertEqual(len(rc), 37)
        self.assertEqual(ov[0]["severity"], "critical")
        self.assertEqual([r["wave"] for r in wv], ["W1", "W2", "W3"])
        self.assertTrue(all(r["decision"] == "" for r in wv))
        self.assertTrue(all(a["severity"] in ("critical", "warning") for a in act))
        self.assertEqual(ad[0]["date"], "2026-11-05")
        self.assertIn("Wave readiness", html)
        self.assertNotIn("\r", pack)

    def test_review_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)
            self.assertEqual(cli.main(["review", "--out", str(Path(t) / "o")]), 2)
            write(Path(t) / "users.csv", ["UserPrincipalName"], [])
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)
            write(Path(t) / "users.csv", ["UserPrincipalName", "Department", "Licenses"], [["a@contoso.example", "IT", "Microsoft_365_Copilot"]])
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o"), "--as-of", "2026-11-05"]), 0)


if __name__ == "__main__":
    unittest.main()
