# Rollout review

How to use the review before each Copilot wave and once a month after it. The tool only reads exports; permissions, labels, licences and agents are changed in the admin centres, by their owners, through the usual change process.

## The cycle

| When | What | From the outputs |
|---|---|---|
| Go-live minus 3 weeks | Export and run the review; send each owner their lines | `readiness-pack.md`, `oversharing.csv`, `licence-reclaim.csv` |
| Go-live minus 2 weeks | Copilot steering group: go, go with conditions, or no go per wave (below) | The pack, *Decisions per wave* |
| Go-live minus 1 week | Run again; confirm the conditions are met; assign the licences | `waves.csv` |
| Go-live | Licences assigned, welcome message, first champions' session | – |
| Monthly after go-live | Run, append `adoption.csv` to `adoption_history.csv`, reclaim, review agents | `adoption.csv`, `agents.csv` |

```powershell
.\scripts\Export-CopilotReadinessData.ps1 -OutputFolder .\data -SharePointAdminUrl https://contoso-admin.sharepoint.com `
    -WaveGroup @{ W1 = '<group id>'; W2 = '<group id>'; W3 = '<group id>' } -PermissionsReport .\downloads\SitePermissions.csv -IncludeDlp
```

```bash
python -m copilotready review data/
```

## Steering group agenda (45 minutes)

| Minutes | Topic | From the pack | Who |
|---|---|---|---|
| 5 | Verdict per wave and what changed since last time | Decisions per wave, Headlines | Rollout lead |
| 10 | Oversharing: the critical sites and who fixes them by when | 3 | SharePoint admin, site owners, information protection |
| 5 | Labels and DLP for Copilot | 4 | Information protection |
| 5 | Agents: owners, audience, connectors, AI register | 5 | Power Platform admin, data protection |
| 10 | Wave readiness: training, MFA, devices, licences, champions | 1, 2 | Rollout lead, workplace, licensing |
| 5 | Adoption and the survey | 6 | Adoption and change lead |
| 5 | Decision per wave, actions, owners and dates | Decisions per wave, Actions | Sponsor |

## Go or no go per wave

- **Go**: READY. Assign the licences on the go-live date.
- **Go with conditions**: ATTENTION. Write the conditions and their owner in the *Decision* column (for example: "go if the MFA campaign closes the 14 gaps by the 17th; users not registered get the licence when they are"). Check them at minus one week.
- **No go**: NOT READY. A critical issue reaches the wave. Either fix it before go-live or contain it (Restricted Content Discovery on the site, the agent blocked) and record that the containment is temporary, with a date.
- A wave never starts with an HR, Finance or Legal site shared with Everyone except external users and not contained, and never with less than three quarters of its people trained.

## Fixing oversharing before the wave

1. Start with the critical sites in `oversharing.csv` (sensitive department or confidential label, with EEEU permissions or Anyone links).
2. If the fix will take more than a few days, turn on **Restricted Content Discovery** for the site now (SharePoint admin center > Active sites > Settings > *Restrict content from Microsoft Copilot*). It keeps the site out of organisation-wide search and Copilot without changing permissions; it is a stopgap, not the fix.
3. With the site owner: remove the *Everyone except external users* permission and grant the group that needs access; remove or expire the Anyone links and restrict sharing on the site; apply the container label agreed for the department.
4. Sites with no owner: find the business owner (department head, last active member) and name two owners. If nobody claims it, archive it.
5. Inactive sites still searchable: archive, or restrict until someone decides.
6. Run the review again; the site leaves the list when the permissions report is refreshed (it can take up to 48 hours).

## Reclaiming licences

1. Send each manager, in one message, their people from `licence-reclaim.csv`: *keep* (with a reason: on leave, starts using next week), *release*, or *coach* (keep it one more month with a session with the champion).
2. Licences on disabled accounts are released straight away and the leaver process is fixed so it removes them.
3. Released licences go to the next wave before any new purchase; the pack shows the pool against the wave's needs.
4. The cost is an estimate at the price in `settings.json`; use your contract price.

## Recording decisions

- In the pack: the *Decision* column of each wave and of the oversharing and agent tables, and *Decisions of the steering group* under Notes.
- In `actions.csv`: owner, due date, decision (do, defer with a reason, accept the risk with a reason and a date) and done. Import it into the tracker the team uses.
- In `waves.csv`: the decision per wave, kept with the exports of that review.
- An accepted risk needs a sponsor's name and an expiry date; next review it is on the list again.

## Communication and training (ADKAR)

| Step | Before the wave | What to measure in the review |
|---|---|---|
| Awareness | Sponsor's message: why Copilot, for whom, when, and what it does not change (it sees only what you can already open) | – |
| Desire | Department sessions led by the champions with use cases from the pilot; managers name what they want to save time on | Champions per department (ADP-03) |
| Knowledge | Copilot essentials (90 minutes) before the licence; prompts library; what not to paste | Training completion (WAV-01) |
| Ability | Office hours in the first two weeks; the champion sits with the team | Active-user rate per department and app (ADP-01) |
| Reinforcement | Monthly tips; share real time saved; reclaim unused licences | Trend (ADP-02), survey, reclaim list (LIC-01) |

Keep each review's folder (exports, pack, CSVs). The next pack starts from what was decided in this one.
