<#
.SYNOPSIS
  Full pipeline: preflight -> build_scene -> export_scs -> render_preview -> convert -> package [-> deploy].
.DESCRIPTION
  Reads config/tools.local.json, stops at the first nonzero exit code, tees all output to
  logs/pipeline-<timestamp>.log. A render is NOT proof the mod works; only the in-game test is.
.EXAMPLE
  powershell -File scripts/run_pipeline.ps1 -Profile surface
  powershell -File scripts/run_pipeline.ps1 -Profile gaming -Deploy
  powershell -File scripts/run_pipeline.ps1 -AllowTodo      # dry run while TODO markers remain
#>
param(
    [ValidateSet('surface', 'gaming')][string]$Profile = 'surface',
    [switch]$Deploy,
    [switch]$SkipRender,
    [switch]$AllowTodo
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$cfgPath = Join-Path $Root 'config/tools.local.json'
if (-not (Test-Path $cfgPath)) { throw "config/tools.local.json missing; copy config/tools.example.json" }
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$blender = if ([System.IO.Path]::IsPathRooted($cfg.blender_exe)) { $cfg.blender_exe } else { Join-Path $Root $cfg.blender_exe }

New-Item -ItemType Directory -Force -Path (Join-Path $Root 'logs'), (Join-Path $Root 'renders') | Out-Null
$Log = Join-Path $Root ("logs/pipeline-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

function Invoke-Step([string]$Name, [string]$Exe, [string[]]$StepArgs) {
    $banner = "=== [$Name] $Exe $($StepArgs -join ' ')"
    Write-Host $banner
    $banner | Add-Content -Path $Log
    # Native stderr must not become a terminating error (Windows PowerShell 5.1); exit code decides.
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $Exe @StepArgs 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $Log -Append
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    "=== [$Name] exit code $code" | Tee-Object -FilePath $Log -Append | Write-Host
    if ($code -ne 0) { throw "step '$Name' failed with exit code $code (see $Log)" }
}

$py = 'python'
$lastStage = if ($Deploy) { 'deploy' } else { 'package' }
$bl = @('--background', '--factory-startup', '--python-exit-code', '1')

try {
    Invoke-Step 'preflight' $py @('scripts/preflight.py', '--stage', $lastStage)
    Invoke-Step 'build_scene' $blender ($bl + @('--python', 'scripts/build_scene.py', '--',
        '--config', 'config/v1.json', '--output', 'build/v1.blend'))
    Invoke-Step 'export_scs' $blender @('--background', 'build/v1.blend', '--python-exit-code', '1',
        '--python', 'scripts/export_scs.py', '--', '--config', 'config/v1.json',
        '--materials', 'config/scs_materials.json', '--output', 'build/mid')
    if (-not $SkipRender) {
        Invoke-Step 'render_preview' $blender @('--background', 'build/v1.blend', '--python-exit-code', '1',
            '--python', 'scripts/render_preview.py', '--', '--config', 'config/v1.json',
            '--profile', $Profile, '--output', "renders/v1-$Profile.png")
    }
    Invoke-Step 'convert' $py @('scripts/convert.py')
    $pkgArgs = @('scripts/package.py'); if ($AllowTodo) { $pkgArgs += '--allow-todo' }
    Invoke-Step 'package' $py $pkgArgs
    if ($Deploy) { Invoke-Step 'deploy' $py @('scripts/deploy.py') }
    Write-Host "PIPELINE OK (log: $Log)"
}
catch {
    Write-Host "PIPELINE FAILED: $_" -ForegroundColor Red
    exit 1
}
