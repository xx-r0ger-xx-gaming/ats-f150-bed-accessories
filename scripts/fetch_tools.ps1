<#
.SYNOPSIS
  Download and verify the pinned toolchain into tools/ (gitignored).
.DESCRIPTION
  Blender 3.6.23 portable, SCS Blender Tools v2.4.1, SCS Conversion Tools 2.21, SCS Game Archive
  Extractor 1.55. Downloads happen into tools/_dl and are sha256-checked before extraction.
  The Conversion Tools and Extractor hashes were recorded by us on 2026-10-14 (SCS publishes none),
  so they pin "the file we tested", not an SCS-signed value.
#>
param([switch]$Force)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root 'tools'
$Dl = Join-Path $Tools '_dl'
New-Item -ItemType Directory -Force -Path $Dl | Out-Null

$items = @(
    @{ Name = 'Blender 3.6.23'; File = 'blender-3.6.23-windows-x64.zip'
       Url = 'https://mirrors.ocf.berkeley.edu/blender/release/Blender3.6/blender-3.6.23-windows-x64.zip'
       Sha = 'e3296eba7eab32c2e5182459ec7614af32224eee2bd32c9d0a08ffd751c54f3b'
       Check = 'blender-3.6.23-windows-x64/blender.exe'; Extract = $Tools },
    @{ Name = 'SCS Blender Tools v2.4.1'; File = 'SCS_Blender_Tools.zip'
       Url = 'https://github.com/SCSSoftware/BlenderTools/releases/download/v2.4.1/scs_blender_tools_addon.zip'
       Sha = 'c38df76fbdb4f703fdd72493eda30bdac32b56e50052ec8b3c5f5767ee226649'
       Check = 'SCS_Blender_Tools.zip'; Extract = $null },
    @{ Name = 'SCS Conversion Tools 2.21'; File = 'conversion_tools_2_21.zip'
       Url = 'https://download.eurotrucksimulator2.com/conversion_tools_2_21.zip'
       Sha = 'c9622cc0fe7719942bc1b7918a8745f48ef603f30a32b052259de83909f4bb75'
       Check = 'conversion_tools/convert.cmd'; Extract = (Join-Path $Tools 'conversion_tools') },
    @{ Name = 'SCS Game Archive Extractor 1.55'; File = 'scs_extractor_1_55.zip'
       Url = 'https://download.eurotrucksimulator2.com/scs_extractor_1_55.zip'
       Sha = '45385795fa830b975bd5c80a2076e17fa8398d8d23d679325e3b89b528b0229c'
       Check = 'scs_extractor.exe'; Extract = $Tools }
)

foreach ($i in $items) {
    $target = Join-Path $Tools $i.Check
    if ((Test-Path $target) -and -not $Force) { Write-Host "[skip] $($i.Name) already present"; continue }
    $zip = Join-Path $Dl $i.File
    if (-not (Test-Path $zip) -or $Force) {
        Write-Host "[get ] $($i.Name)"
        Invoke-WebRequest -Uri $i.Url -OutFile $zip -UseBasicParsing
    }
    $actual = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
    if ($actual -ne $i.Sha) { Remove-Item $zip; throw "SHA256 mismatch for $($i.File): got $actual expected $($i.Sha)" }
    Write-Host "[ok  ] sha256 verified $($i.File)"
    if ($i.Extract) {
        New-Item -ItemType Directory -Force -Path $i.Extract | Out-Null
        Expand-Archive -Path $zip -DestinationPath $i.Extract -Force
    } else {
        Copy-Item $zip (Join-Path $Tools $i.File) -Force
    }
    if (-not (Test-Path $target)) { throw "expected file missing after extract: $target" }
}
Write-Host "Toolchain ready in $Tools. Next: python scripts/preflight.py --stage convert"
