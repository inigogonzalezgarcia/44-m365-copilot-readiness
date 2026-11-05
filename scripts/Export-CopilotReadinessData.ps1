<#
.SYNOPSIS
    Read-only export of the tenant data that copilotready reads: users with licences, wave, MFA registration and device compliance; the
    Microsoft 365 Copilot usage report; the SharePoint sites with their sharing and Copilot restrictions; and, optionally, the DLP policies.

.DESCRIPTION
    Only read operations: Get-* cmdlets and GET requests. Nothing is created, changed, assigned, removed or shared, and no secret is written
    to disk. The script does not generate SharePoint reports either: it reads one you already downloaded (-PermissionsReport).

    Modules and roles:
      - Microsoft Graph PowerShell SDK (Microsoft.Graph.Authentication, .Users, .Groups, .Identity.DirectoryManagement, .Reports,
        .DeviceManagement), signed in with Connect-MgGraph and the delegated scopes User.Read.All, GroupMember.Read.All,
        Organization.Read.All, Reports.Read.All, AuditLog.Read.All and DeviceManagementManagedDevices.Read.All. Reading the usage report
        also needs a role such as Reports Reader.
      - SharePoint Online Management Shell (Microsoft.Online.SharePoint.PowerShell), signed in with Connect-SPOService as a SharePoint
        administrator.
      - With -IncludeDlp: Exchange Online PowerShell (ExchangeOnlineManagement), signed in to Security & Compliance PowerShell with
        Connect-IPPSSession.

    Files:
      - users.csv          Get-MgUser -All (UserPrincipalName, DisplayName, Department, Country, JobTitle, AccountEnabled, AssignedLicenses,
                           AssignedPlans). Licences as SkuPartNumber through Get-MgSubscribedSku. CopilotAssigned is the earliest
                           assignedDateTime of the Microsoft 365 Copilot service plans in AssignedPlans. Manager (Get-MgUserManager) for
                           licensed users only. Wave from the members of one Entra ID group per wave (-WaveGroup, Get-MgGroupMember).
                           MfaRegistered from Get-MgReportAuthenticationMethodUserRegistrationDetail (IsMfaRegistered). DeviceCompliant from
                           Get-MgDeviceManagementManagedDevice (ComplianceState of every Intune-managed device of the user: Compliant if all
                           are compliant, Noncompliant if any is not, "No device" if the user has none).
      - copilot_usage.csv  GET https://graph.microsoft.com/v1.0/copilot/reports/getMicrosoft365CopilotUsageUserDetail(period='D28') through
                           Invoke-MgGraphRequest; the CSV as returned (Report Refresh Date, User Principal Name, Last Activity Date and the
                           last activity date per app). Turn off "Display concealed user, group, and site names in all reports" in the
                           Microsoft 365 admin center (Settings > Org settings > Reports) or the names come back hashed and nothing joins.
      - sites.csv          Get-SPOSite -Limit All, then Get-SPOSite -Identity per site for Title, Template, Owner, SensitivityLabel,
                           SharingCapability, LastContentModifiedDate, RestrictContentOrgWideSearch (Restricted Content Discovery) and
                           RestrictedAccessControl. OwnerCount from Get-MgGroupOwner for group-connected sites, otherwise the site
                           collection administrators from Get-SPOUser (IsSiteAdmin). With -PermissionsReport, the EEEU permission count, Anyone
                           link count and Number of users having access of the data access governance report "Site permissions across your
                           organization" (a CSV you download from the SharePoint admin center, Reports > Data access governance; it needs
                           SharePoint Advanced Management), joined by Site URL.
      - dlp.csv            With -IncludeDlp: Get-DlpCompliancePolicy (Name, Mode). CopilotLocation is Yes when the policy's locations
                           include the Microsoft 365 Copilot location (470f2276-e011-4e9d-a6ec-20768be3a4b0).

    Not exported by this script (see docs/data-format.md): labels.csv (files and labelled files per site, from Microsoft Purview and the
    File count of the same SharePoint report), agents.csv (the Power Platform admin center inventory, Manage > Inventory > Download, filtered
    to agents), training.csv (your learning platform), survey.csv, adoption_history.csv and settings.json.

.PARAMETER OutputFolder
    Where the CSV files are written (default .\data).

.PARAMETER SharePointAdminUrl
    The SharePoint admin center URL, for example https://contoso-admin.sharepoint.com. Without it, sites.csv is not exported.

.PARAMETER WaveGroup
    One Entra ID group per wave, as a hashtable of wave id to group object id: @{ W1 = '<id>'; W2 = '<id>' }. The wave ids must match
    the ones in settings.json.

.PARAMETER PermissionsReport
    Path of the downloaded "Site permissions across your organization" report (CSV), to add EEEU permissions, Anyone links and users with
    access to sites.csv.

.PARAMETER Period
    Period of the usage report: D7, D28, D90 or D180 (default D28). The last activity dates do not depend on it.

.PARAMETER IncludeDlp
    Also export the DLP policies (needs Connect-IPPSSession).

.EXAMPLE
    .\scripts\Export-CopilotReadinessData.ps1 -OutputFolder .\data -SharePointAdminUrl https://contoso-admin.sharepoint.com `
        -WaveGroup @{ W1 = '11111111-1111-1111-1111-111111111111'; W2 = '22222222-2222-2222-2222-222222222222' } `
        -PermissionsReport .\downloads\SitePermissionsReport.csv -IncludeDlp

.EXAMPLE
    .\scripts\Export-CopilotReadinessData.ps1 -OutputFolder .\data
    Users and usage only.
#>
[CmdletBinding()]
param(
    [string] $OutputFolder = '.\data',
    [string] $SharePointAdminUrl,
    [hashtable] $WaveGroup = @{},
    [string] $PermissionsReport,
    [ValidateSet('D7', 'D28', 'D90', 'D180')] [string] $Period = 'D28',
    [switch] $IncludeDlp
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null

# Service plans of the Microsoft 365 Copilot licence (Microsoft_365_Copilot): Productivity Apps, Teams, Graph-grounded chat
$CopilotPlans = @('a62f8878-de10-42f3-b68f-6149a25ceb97', 'b95945de-b3bd-46db-8437-f2beb6ea2347', '3f30311c-6b1e-48a4-ab79-725b469da960')
$CopilotDlpLocation = '470f2276-e011-4e9d-a6ec-20768be3a4b0'

function Write-Csv([object[]] $Rows, [string] $Name) {
    $path = Join-Path $OutputFolder $Name
    @($Rows) | Export-Csv -Path $path -NoTypeInformation -Encoding utf8
    Write-Host ("{0,7} rows -> {1}" -f @($Rows).Count, $path)
}

function Format-Date($Value) {
    if (-not $Value) { return '' }
    return ([datetime] $Value).ToUniversalTime().ToString('yyyy-MM-dd')
}

# ------------------------------------------------------------------ Microsoft Graph
if (-not (Get-MgContext)) {
    Connect-MgGraph -NoWelcome -Scopes 'User.Read.All', 'GroupMember.Read.All', 'Organization.Read.All', 'Reports.Read.All', 'AuditLog.Read.All',
        'DeviceManagementManagedDevices.Read.All'
}

$skus = @{}
foreach ($s in Get-MgSubscribedSku -All) { $skus[[string] $s.SkuId] = $s.SkuPartNumber }

$waveOf = @{}
foreach ($w in $WaveGroup.Keys) {
    foreach ($m in Get-MgGroupMember -GroupId $WaveGroup[$w] -All) { $waveOf[[string] $m.Id] = $w }
}

$mfa = @{}
foreach ($r in Get-MgReportAuthenticationMethodUserRegistrationDetail -All) { $mfa[[string] $r.Id] = [bool] $r.IsMfaRegistered }

$devices = @{}
foreach ($dv in Get-MgDeviceManagementManagedDevice -All) {
    if (-not $dv.UserPrincipalName) { continue }
    $k = $dv.UserPrincipalName.ToLower()
    if (-not $devices.ContainsKey($k)) { $devices[$k] = @() }
    $devices[$k] += [string] $dv.ComplianceState
}

$users = foreach ($u in Get-MgUser -All -Property 'Id,UserPrincipalName,DisplayName,Department,Country,JobTitle,AccountEnabled,AssignedLicenses,AssignedPlans') {
    $lic = @($u.AssignedLicenses | ForEach-Object { $skus[[string] $_.SkuId] } | Where-Object { $_ })
    $plans = @($u.AssignedPlans | Where-Object { $CopilotPlans -contains [string] $_.ServicePlanId -and $_.CapabilityStatus -eq 'Enabled' })
    $assigned = if ($plans) { Format-Date (($plans | Sort-Object AssignedDateTime | Select-Object -First 1).AssignedDateTime) } else { '' }
    $manager = ''
    if ($plans) {
        $m = Get-MgUserManager -UserId $u.Id -ErrorAction SilentlyContinue
        if ($m) { $manager = $m.AdditionalProperties['userPrincipalName'] }
    }
    $states = $devices[$u.UserPrincipalName.ToLower()]
    $device = if (-not $states) { 'No device' } elseif (@($states | Where-Object { $_ -ne 'compliant' }).Count -eq 0) { 'Compliant' } else { 'Noncompliant' }
    [pscustomobject]@{
        UserPrincipalName = $u.UserPrincipalName
        DisplayName       = $u.DisplayName
        Department        = $u.Department
        Country           = $u.Country
        JobTitle          = $u.JobTitle
        AccountEnabled    = $u.AccountEnabled
        Manager           = $manager
        Licenses          = ($lic -join ';')
        CopilotAssigned   = $assigned
        Wave              = $waveOf[[string] $u.Id]
        MfaRegistered     = if ($mfa.ContainsKey([string] $u.Id)) { if ($mfa[[string] $u.Id]) { 'Yes' } else { 'No' } } else { '' }
        DeviceCompliant   = $device
    }
}
Write-Csv $users 'users.csv'

$usagePath = Join-Path $OutputFolder 'copilot_usage.csv'
Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/copilot/reports/getMicrosoft365CopilotUsageUserDetail(period='$Period')" `
    -OutputFilePath $usagePath
Write-Host ("{0,7} rows -> {1}" -f ((Get-Content $usagePath | Measure-Object).Count - 1), $usagePath)

# ------------------------------------------------------------------ SharePoint Online
if ($SharePointAdminUrl) {
    Connect-SPOService -Url $SharePointAdminUrl
    $perm = @{}
    if ($PermissionsReport) {
        foreach ($r in Import-Csv $PermissionsReport) { $perm[$r.'Site URL'.TrimEnd('/').ToLower()] = $r }
    }
    $sites = foreach ($s in Get-SPOSite -Limit All) {
        $x = Get-SPOSite -Identity $s.Url
        $owners = if ($x.GroupId -and [string] $x.GroupId -ne '00000000-0000-0000-0000-000000000000') {
            @(Get-MgGroupOwner -GroupId $x.GroupId -All).Count
        } else {
            @(Get-SPOUser -Site $x.Url -Limit All | Where-Object { $_.IsSiteAdmin }).Count
        }
        $p = $perm[$x.Url.TrimEnd('/').ToLower()]
        [pscustomobject]@{
            Url                             = $x.Url
            Title                           = $x.Title
            Template                        = $x.Template
            Department                      = ''
            OwnerCount                      = $owners
            Owner                           = $x.Owner
            SensitivityLabel                = $x.SensitivityLabel
            SharingCapability               = $x.SharingCapability
            'EEEU permission count'         = if ($p) { $p.'EEEU permission count' } else { '' }
            'Anyone link count'             = if ($p) { $p.'Anyone link count' } else { '' }
            'Number of users having access' = if ($p) { $p.'Number of users having access' } else { '' }
            LastContentModifiedDate         = Format-Date $x.LastContentModifiedDate
            RestrictContentOrgWideSearch    = $x.RestrictContentOrgWideSearch
            RestrictedAccessControl         = $x.RestrictedAccessControl
        }
    }
    Write-Csv $sites 'sites.csv'
}

# ------------------------------------------------------------------ Microsoft Purview DLP
if ($IncludeDlp) {
    $dlp = foreach ($p in Get-DlpCompliancePolicy) {
        [pscustomobject]@{
            Name            = $p.Name
            Mode            = $p.Mode
            CopilotLocation = if (($p | ConvertTo-Json -Depth 6 -WarningAction SilentlyContinue) -match $CopilotDlpLocation) { 'Yes' } else { 'No' }
        }
    }
    Write-Csv $dlp 'dlp.csv'
}

Write-Host 'Done. Add labels.csv, agents.csv, training.csv (and survey.csv) by hand; see docs/data-format.md.'
