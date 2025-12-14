param(
  [string]$WorkDir = (Join-Path (Get-Location) "output"),
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

Write-Host "[info] WorkDir: $WorkDir"

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$repoRoot = Get-Location
$venvDir = Join-Path $WorkDir ".venv"
$snapshot = Join-Path $WorkDir "snapshot.json"
$indexHtml = Join-Path $WorkDir "index.html"
$imageWebp = Join-Path $WorkDir "gameinfo.webp"

$template = Join-Path $repoRoot "epic-freebies.html.template"
$requirements = Join-Path $repoRoot "requirements.txt"
$fetchScript = Join-Path $repoRoot "fetch_freebies.py"
$renderScript = Join-Path $repoRoot "render_html.py"
$imageScript = Join-Path $repoRoot "generate_image.py"

if (!(Test-Path $template)) { throw "Missing template: $template" }
if (!(Test-Path $requirements)) { throw "Missing requirements: $requirements" }
if (!(Test-Path $fetchScript)) { throw "Missing script: $fetchScript" }
if (!(Test-Path $renderScript)) { throw "Missing script: $renderScript" }
if (!(Test-Path $imageScript)) { throw "Missing script: $imageScript" }

Write-Host "[step] Create venv: $venvDir"
& $Python -m venv $venvDir

$venvPy = Join-Path $venvDir "Scripts\python.exe"
if (!(Test-Path $venvPy)) { throw "Venv python missing: $venvPy" }

Write-Host "[step] Upgrade pip"
& $venvPy -m pip install --upgrade pip | Out-Host

Write-Host "[step] Install dependencies"
& $venvPy -m pip install -r $requirements | Out-Host

Write-Host "[step] Install Playwright chromium"
& $venvPy -m playwright install chromium | Out-Host

Write-Host "[step] Fetch snapshot"
Push-Location $WorkDir
try {
  & $venvPy $fetchScript $snapshot | Out-Host
  if (!(Test-Path $snapshot)) { throw "snapshot.json not generated" }

  Write-Host "[step] Render HTML"
  & $venvPy $renderScript $snapshot $template $indexHtml | Out-Host
  if (!(Test-Path $indexHtml)) { throw "index.html not generated" }

  Write-Host "[step] Generate share image"
  & $venvPy $imageScript $indexHtml $imageWebp 1200 | Out-Host
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "[done] snapshot: $snapshot"
Write-Host "[done] html:     $indexHtml"
Write-Host "[done] image:    $imageWebp"


