"""Command line: `demo` writes the fictional Fabrikam Energy exports to sample_data/ and builds the outputs; `review` runs on your own exports."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import report, simulate
from .checks import money, overall, pct, review, run_all, summary
from .model import load, parse_dt

OUTPUTS = ("report.html", "readiness-pack.md", "licence-reclaim.csv", "oversharing.csv", "agents.csv", "adoption.csv", "waves.csv", "actions.csv",
           "findings.csv")


def run(data: Path, out: Path, title: str | None = None, as_of: datetime | None = None) -> dict:
    d = load(data, as_of)
    rv = review(d)
    findings = run_all(d, rv)
    title = title or f"{d.settings.organisation} · Microsoft 365 Copilot readiness, {d.today:%d %B %Y}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, rv, findings, title), encoding="utf-8")
    (out / "readiness-pack.md").write_text(report.pack_md(d, rv, findings, title), encoding="utf-8")
    report.write_reclaim(d, rv, out / "licence-reclaim.csv")
    report.write_oversharing(d, rv, out / "oversharing.csv")
    report.write_agents(d, rv, out / "agents.csv")
    report.write_adoption(d, rv, out / "adoption.csv")
    report.write_waves(d, rv, out / "waves.csv")
    report.write_actions(findings, out / "actions.csv")
    report.write_findings(findings, out / "findings.csv")
    sm = summary(d, rv)
    sm.update(overall=overall(findings), critical=sum(f.severity == "critical" for f in findings), warning=sum(f.severity == "warning" for f in findings))
    return sm


def _when(value: str) -> datetime:
    d = parse_dt(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD or 'YYYY-MM-DD HH:MM'): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="copilotready", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional exports to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own exports")
    rv.add_argument("data", type=Path, nargs="?", help="folder with users.csv and the other exports")
    rv.add_argument("--data", dest="data_opt", type=Path, help="same as the positional folder")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", help="title of the report and the pack")
    rv.add_argument("--as-of", type=_when, help="reference date (default: settings.json, or now)")
    a = p.parse_args(argv)
    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, f"{simulate.ORG} · Microsoft 365 Copilot readiness before wave 2 (review of 5 November 2026)")
    else:
        folder = a.data or a.data_opt
        if not folder:
            print("error: give the folder with the exports", file=sys.stderr)
            return 2
        try:
            sm = run(folder, a.out, a.title, a.as_of)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    c = sm["currency"]
    waves = ", ".join(f"{name} {verdict.upper()}" for _, name, _, verdict in sm["waves"]) or "no waves in settings.json"
    print(f"{sm['overall'].upper()} · {waves} · {sm['licensed']} Copilot licences, {sm['active']} active in 30 days ({pct(sm['active_rate'])}) · "
          f"{sm['reclaim']} to reclaim ({money(sm['reclaim_cost'], c)} a month) · {sm['sites_flagged']} of {sm['sites']} sites to fix "
          f"({sm['sites_critical']} critical) · label coverage {pct(sm['label_coverage'])} · {sm['agents_flagged']} of {sm['agents']} agents "
          f"flagged · {sm['critical']} critical, {sm['warning']} warnings")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
