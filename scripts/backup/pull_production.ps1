# Pull a backup of production to this computer over ssh.
#
#   .\scripts\backup\pull_production.ps1 -Server <account>@<host> -What json
#       the collections as JSON into mongodb_collections_local\<yymmdd>
#   .\scripts\backup\pull_production.ps1 -Server <account>@<host> -What archive -Dest D:\backups
#       mongodump archive (gzip) to <Dest>\<yymmdd>\csc_db_<yymmdd>.archive.gz
#   .\scripts\backup\pull_production.ps1 -Server <account>@<host> -What assets -Dest D:\backups
#       the asset folders as <Dest>\<yymmdd>\csc_assets_<yymmdd>.tgz
#
# Needs ~/bin/csc_dump.sh on the server (uberspaceconfig/bin/csc_dump.sh).
# Binary streams go through cmd.exe so PowerShell does not re-encode them.

param(
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][ValidateSet('json', 'archive', 'assets')][string]$What,
    [string]$Dest = ''
)

$ErrorActionPreference = 'Stop'
$day = Get-Date -Format yyMMdd
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')

function Pull([string]$remote, [string]$file) {
    cmd /c "ssh $Server $remote > `"$file`""
    if ($LASTEXITCODE -ne 0) { throw "ssh failed ($LASTEXITCODE): $remote" }
    $size = (Get-Item $file).Length
    if ($size -eq 0) { throw "empty download: $file" }
    Write-Host "$file ($size bytes)"
}

if ($What -eq 'json') {
    $target = Join-Path $repo "mongodb_collections_local\$day"
    if (Test-Path $target) { throw "$target exists already; move it away first" }
    New-Item -ItemType Directory -Force $target | Out-Null
    $tgz = Join-Path $env:TEMP "csc_json_$day.tgz"
    Pull 'bin/csc_dump.sh json' $tgz
    tar xzf $tgz -C $target
    Remove-Item $tgz
    Get-ChildItem $target | Select-Object Name, Length | Format-Table -AutoSize
    exit 0
}

if (-not $Dest) { throw '-Dest is required for archive and assets' }
$folder = Join-Path $Dest $day
New-Item -ItemType Directory -Force $folder | Out-Null

if ($What -eq 'archive') {
    Pull 'bin/csc_dump.sh archive' (Join-Path $folder "csc_db_$day.archive.gz")
} else {
    $file = Join-Path $folder "csc_assets_$day.tgz"
    Pull 'tar czf - -C ~ csc_assets_private html/csc_assets' $file
    tar tzf $file | Select-Object -First 3
}
