# Data format

Put the files in one folder and run `python -m copilotready review <folder>`. `users.csv` is required; every other file adds its checks. Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the alternatives below are accepted. Dates as ISO 8601 (`2026-11-05` or `2026-11-05T09:00:00Z`), `dd/mm/yyyy` or `MM/dd/yyyy`; the time zone suffix is ignored. Yes/no columns accept `Yes`, `True`, `1`, and also `Compliant` and `Published`. User principal names and site URLs are compared in lower case, and site URLs without the trailing slash.

`scripts/Export-CopilotReadinessData.ps1` writes `users.csv`, `copilot_usage.csv`, `sites.csv` and, with `-IncludeDlp`, `dlp.csv`. `labels.csv`, `agents.csv`, `training.csv`, `survey.csv` and `adoption_history.csv` are compiled by hand from the sources named below.

## How the review works

| Step | Rule |
|---|---|
| Inactive licence | A Copilot licence whose user has no `Last Activity Date` in the usage report in the last `inactive_days`, or never; licences assigned less than `grace_days` ago are not counted. A licence on a disabled account is always reclaimable |
| Licence pool | `licences_owned` minus the licences assigned, against the users of the next wave without a licence; reclaimable licences count only if they are released |
| Wave status | *live* once the go-live date has passed, *next* when it is within `readiness_window_days`, *later* otherwise. Training, MFA and devices are warnings or critical for live and next waves, information for later ones |
| Sensitive site | A site of a department in `sensitive_departments` or with a label in `sensitive_labels` |
| Scope | An issue reaches the waves with users in the department it belongs to. Critical oversharing and critical agent findings reach every wave: Copilot answers from everything a user can already open |
| Wave verdict | NOT READY with a critical issue that reaches the wave, ATTENTION with warnings only, READY otherwise. The overall verdict is the worst area |

## users.csv

One row per user, from Microsoft Graph (`Get-MgUser` with `AssignedLicenses` and `AssignedPlans`).

| Column | Alternatives | Notes |
|---|---|---|
| UserPrincipalName | upn, username | Required; joins every other file |
| DisplayName | name | |
| Department | dept | Entra ID `department`; adoption, label coverage and scope are by department |
| Country | UsageLocation | |
| JobTitle | title | |
| AccountEnabled | enabled | `False` makes a licence reclaimable |
| Manager | manager upn | For the reclaim list |
| Licenses | SkuPartNumber, skus | `SkuPartNumber` values separated by `;` (`SPE_E3;Microsoft_365_Copilot`). A Copilot licence is any of `copilot_skus` (default `Microsoft_365_Copilot`, `M365_Copilot`, `Microsoft_365_Copilot_EDU`, the string IDs on the Microsoft Learn page *Product names and service plan identifiers for licensing*) |
| CopilotAssigned | copilot licence assigned | Date the Copilot licence was assigned (earliest `assignedDateTime` of its service plans in `assignedPlans`); used for the grace period |
| Wave | rollout wave | The wave id from `settings.json` (`W1`, `W2`…); empty when the user is in no wave |
| MfaRegistered | IsMfaRegistered | From `userRegistrationDetails` (`isMfaRegistered`); empty is unknown and not counted |
| DeviceCompliant | compliance state | `Compliant`, `Noncompliant` or `No device` (Intune `complianceState` of the user's managed devices). No device counts as not compliant |

## copilot_usage.csv

The Microsoft 365 Copilot usage report per user, as Microsoft Graph returns it: `GET /copilot/reports/getMicrosoft365CopilotUsageUserDetail(period='D28')` (v1.0; the same report is exported from the Microsoft 365 admin center, Reports > Usage > Microsoft 365 Copilot). It lists users with a Microsoft 365 Copilot licence. Turn off concealed names in the admin center report settings, or the user principal names come back as hashes.

| Column | Notes |
|---|---|
| User Principal Name | Joins users.csv |
| Last Activity Date | Last Copilot activity in any app; empty if never |
| Microsoft Teams Copilot Last Activity Date, Word Copilot Last Activity Date, Excel Copilot Last Activity Date, PowerPoint Copilot Last Activity Date, Outlook Copilot Last Activity Date, OneNote Copilot Last Activity Date, Loop Copilot Last Activity Date, Copilot Chat Last Activity Date | Adoption by app: users with a date in the last `inactive_days` |
| Report Refresh Date | Read, not used in the rules |

## sites.csv

One row per SharePoint site. `Get-SPOSite` properties, plus three columns from the data access governance report *Site permissions across your organization* (SharePoint admin center, Reports > Data access governance; requires SharePoint Advanced Management).

| Column | Alternatives | Notes |
|---|---|---|
| Url | Site URL | Required |
| Title | Site Name | |
| Template | Site Template | |
| Department | business owner | The department that owns the site. Empty: matched from `site_departments` in settings.json (a text in the URL or title, such as `/sites/hr-`, to a department) |
| OwnerCount | owners | Microsoft 365 group owners, or site collection administrators for sites without a group. 0 is a warning, 1 information |
| Owner | Primary admin email | |
| SensitivityLabel | Site Sensitivity | The container label; empty is no label |
| SharingCapability | ExternalSharing | Shown, not scored |
| EEEU permission count | eeeu | Permissions granted to *Everyone except external users* at any level |
| Anyone link count | anyone | Existing Anyone links |
| Number of users having access | users with access | Shown next to the finding |
| LastContentModifiedDate | last activity | Inactive after `inactive_site_days` |
| RestrictContentOrgWideSearch | restricted content discovery | Restricted Content Discovery: the site is kept out of organisation-wide search and Copilot. An EEEU finding on such a site drops to information |
| RestrictedAccessControl | | Shown in oversharing.csv |

## labels.csv

Files and labelled files per site, for the label coverage per department. Compile it from the Microsoft Purview content explorer (items per sensitivity label and location) and the *File count* of the same SharePoint report.

| Column | Alternatives | Notes |
|---|---|---|
| Url | Site URL | Joins sites.csv |
| Files | File count | |
| LabelledFiles | labelled files | Files with any sensitivity label |

## dlp.csv

`Get-DlpCompliancePolicy` in Security & Compliance PowerShell.

| Column | Notes |
|---|---|
| Name | |
| Mode | `Enable`, `TestWithNotifications`, `TestWithoutNotifications`, `Disable` |
| CopilotLocation | `Yes` when the policy applies to the *Microsoft 365 Copilot and Copilot Chat* location. LAB-02 is raised when no such policy is in `Enable` |

## agents.csv

Copilot Studio and Agent Builder agents, compiled from the Power Platform admin center inventory (Manage > Inventory, filtered to agents, Download) and the agent's details. Column names in the download change between releases, so map them to these; the last two columns are yours.

| Column | Alternatives | Notes |
|---|---|---|
| Name | agent name | Required |
| Owner | created by | User principal name; an owner missing from users.csv or disabled is no owner |
| Environment | | |
| Status | published | `Published` or `Draft` |
| SharedWith | audience | `Organization` (any of `org_wide_values`), a group, `Specific people` or `Owner only` |
| Connectors | knowledge sources | Separated by `;`; compared with `allowed_connectors` |
| Authentication | | Shown |
| LastUsed | last activity date | Empty is never used |
| DecisionsAboutPeople | | `Yes` when the agent supports decisions about people (hiring, performance, access to benefits) |
| AiRegisterEntry | | The id of the entry in your AI register; empty raises AGT-05. A record, not a legal assessment |

## training.csv

| Column | Notes |
|---|---|
| UserPrincipalName | |
| Course | |
| CompletedDate | Empty or later than the reference date is not completed |
| Role | `Champion` marks the department's Copilot champions |

## survey.csv (optional)

| Column | Notes |
|---|---|
| UserPrincipalName | |
| MinutesSavedPerWeek | Self-reported; the median is shown |
| Satisfaction | 1–5; the median is shown |

## adoption_history.csv (optional)

The `adoption.csv` of earlier runs, appended: `date`, `department`, `licensed`, `active_30d` (the other columns are ignored). The latest snapshot before the reference date is the baseline for ADP-02.

## settings.json

| Key | Default | Meaning |
|---|---|---|
| organisation, as_of, currency | | Name, reference date (`2026-11-05 09:00`), currency |
| licence_price_month | 30 | Price of one Copilot licence a month, for the reclaim estimate. Set your own |
| licences_owned | | Licences purchased; without it the pool check is skipped |
| copilot_skus | see above | SkuPartNumbers that count as a Copilot licence |
| inactive_days, grace_days | 30, 14 | Inactive licence; new licences not counted |
| waves | | `[{"id": "W2", "name": "Wave 2", "go_live": "2026-11-19", "planned": 400}]` |
| readiness_window_days | 30 | Waves going live within it are checked as *next* |
| training_target, training_critical | 0.9, 0.75 | Share of the wave trained; under the critical value a next wave is NOT READY |
| mfa_critical | 0.05 | Share of the wave not registered for MFA above which it is critical |
| device_target, device_critical | 0.95, 0.85 | Share of the wave with a compliant device |
| sensitive_departments, sensitive_labels | HR, Finance, Legal; Confidential, Highly Confidential | Make EEEU and Anyone findings critical |
| site_departments | | Text in the site URL or title to department |
| inactive_site_days | 180 | |
| label_target, label_critical | 0.6, 0.3 | Label coverage per department |
| allowed_connectors | | Connectors allowed in agents; empty switches AGT-03 off |
| org_wide_values | Organization, Everyone… | Values of SharedWith that mean the whole organisation |
| agent_unused_days | 60 | |
| adoption_target, adoption_drop, min_champions | 0.6, 0.1, 1 | Active-user rate per department, a drop since the last snapshot, champions per department of 10 or more users in a live or next wave |
| owners | | Owner per area: licences, waves, oversharing, labels, agents, adoption |
