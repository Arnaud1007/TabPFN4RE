$ErrorActionPreference = "Stop"

$expectedFiles = @(
    "data/requests/hcpa_all_sales_inquiry_draft.md",
    "data/source_cards/hillsborough_hcpa_allsales.yaml",
    "decisions/0097-hcpa-root-documentation-boundary.md",
    "next_action.md",
    "requirements.yaml",
    "runs/u0-hcpa-root-documentation-20261005-v1/manifest.json",
    "runs/u0-hcpa-root-documentation-20261005-v1/report.md",
    "runs/u0-hcpa-root-documentation-20261005-v1/test_gate.json",
    "runs/u0-hcpa-root-documentation-20261005-v1/verify_artifacts.ps1"
)

$workingSet = @(
    git diff --name-only HEAD
    git ls-files --others --exclude-standard
) | Where-Object { $_ } | Sort-Object -Unique

$expected = $expectedFiles | Sort-Object -Unique
if ($workingSet.Count -gt 0) {
    $checkpointFiles = $workingSet
} else {
    $checkpointFiles = @(
        git diff-tree --no-commit-id --name-only -r HEAD
    ) | Where-Object { $_ } | Sort-Object -Unique
}
if (Compare-Object $expected $checkpointFiles) {
    throw "Candidate publication set differs from the expected checkpoint files."
}

& py -3.11 -c @"
import json
import yaml
json.load(open('runs/u0-hcpa-root-documentation-20261005-v1/manifest.json', encoding='utf-8'))
yaml.safe_load(open('data/source_cards/hillsborough_hcpa_allsales.yaml', encoding='utf-8'))
yaml.safe_load(open('requirements.yaml', encoding='utf-8'))
"@
if ($LASTEXITCODE -ne 0) {
    throw "JSON or YAML parse failed."
}

$rawHash = (Get-FileHash `
    -LiteralPath "data/raw/hcpa/_Documentation.doc" `
    -Algorithm SHA256).Hash.ToLowerInvariant()
$textHash = (Get-FileHash `
    -LiteralPath "data/raw/hcpa/_Documentation.txt" `
    -Algorithm SHA256).Hash.ToLowerInvariant()
if ($rawHash -ne "207fab6385b9be0a48eab5fe4f0960d0f99ec08d8db83f18474dfa280db37253") {
    throw "Raw document hash mismatch."
}
if ($textHash -ne "b1e6a1adb0bcea2f17fe3b8f83f0158cc18f5701670d95623d91d7c0543db64c") {
    throw "Extracted text hash mismatch."
}

$privatePaths = @(
    "data/raw/hcpa/_Documentation.doc",
    "data/raw/hcpa/_Documentation.txt"
)
$ignored = @(git check-ignore -- $privatePaths)
if ($ignored.Count -ne $privatePaths.Count) {
    throw "A private source file is not ignored."
}
if (git ls-files -- $privatePaths) {
    throw "A private source file is tracked."
}

$patterns = @(
    '(?i)["'']property_id["'']\s*[:=]\s*["''][^"'']+',
    '(?i)["'']street_address["'']\s*[:=]\s*["''][^"'']+',
    '(?i)["'']sale_price(?:_value)?["'']\s*[:=]\s*[0-9]',
    '(?i)["''](?:grantor|grantee|owner)["'']\s*[:=]\s*["''][^"'']+'
)
foreach ($file in $expectedFiles) {
    $content = Get-Content -LiteralPath $file -Raw
    foreach ($pattern in $patterns) {
        if ($content -match $pattern) {
            throw "Potential row-level property data found in $file."
        }
    }
}

Write-Output "artifact_parse=PASS"
Write-Output "private_hashes=PASS"
Write-Output "private_storage=PASS"
Write-Output "candidate_set_privacy=PASS"
