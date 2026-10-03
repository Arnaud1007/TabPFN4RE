$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$private = Join-Path $root 'data\raw\cook_county\u0-cook-clerk-public-docs-v1-20261003T014926Z'
$manifestPath = Join-Path $PSScriptRoot 'capture_manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$verificationPath = Join-Path $PSScriptRoot 'verification.json'
$verification = Get-Content -LiteralPath $verificationPath -Raw | ConvertFrom-Json

function Get-LowerHash([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ((Get-LowerHash (Join-Path $PSScriptRoot 'plan.md')) -ne '6972f88d0bd15507bcd9800567b2c35e0960edab41d863b358bf71e099223568' -or
    (Get-LowerHash $manifestPath) -ne '07133c72543e73f0da5eba07da1f20317d13cc313a4e1a2a66ae533811d94bf7' -or
    (Get-LowerHash (Join-Path $PSScriptRoot 'environment_lock.txt')) -ne '92d4969aa37973d021c9215c67448b26ac689ca8d6f5b4414c701f126f4ac3e7' -or
    (Get-LowerHash (Join-Path $PSScriptRoot 'verify.log')) -ne '11247c7174614f55ef00f8f665671c7b2cc8cb86b58b08a0c95a0e3f7bdcc50a' -or
    (Get-LowerHash $verificationPath) -ne '2f1ee4f0f95c8317aa14887c8a021225e7daa2603b86cddbfd8797427ad06576' -or
    $manifest.run_id -ne 'u0-cook-clerk-public-docs-v1-20261003T014926Z' -or
    $manifest.protocol -ne 'cook-clerk-public-docs-v1' -or
    $manifest.code_commit -ne 'da87a4d2583d8acf0a5cf09cc9bbeb5f3f9f459a' -or
    $manifest.source_rows_requested -ne 0 -or
    $manifest.paid_actions -ne 0 -or
    $manifest.certified_sale_labels -ne 0 -or
    $manifest.u0_gate -ne 'PENDING' -or
    $manifest.g_us_gate -ne 'PENDING' -or
    -not $manifest.private_acl_verified -or
    @($manifest.results).Count -ne 4) {
    throw 'Cook Clerk public-document manifest differs from the frozen capture'
}
if ($verification.run_id -ne $manifest.run_id -or
    $verification.technical_capture_status -ne 'PASS' -or
    $verification.u0_gate -ne 'PENDING' -or
    $verification.g_us_gate -ne 'PENDING' -or
    $verification.baseline_commit -ne $manifest.code_commit -or
    $verification.environment_lock_sha256 -ne '92d4969aa37973d021c9215c67448b26ac689ca8d6f5b4414c701f126f4ac3e7' -or
    $verification.capture_manifest_sha256 -ne '07133c72543e73f0da5eba07da1f20317d13cc313a4e1a2a66ae533811d94bf7' -or
    $verification.plan_sha256 -ne '6972f88d0bd15507bcd9800567b2c35e0960edab41d863b358bf71e099223568' -or
    $verification.command -ne "& 'runs/u0-cook-clerk-public-docs-v1-20261003T014926Z/verify_artifacts.ps1'" -or
    $verification.exit_code -ne 0 -or
    $verification.duration_seconds -le 0 -or
    $verification.output -ne 'verify.log' -or
    $verification.output_sha256 -ne '11247c7174614f55ef00f8f665671c7b2cc8cb86b58b08a0c95a0e3f7bdcc50a' -or
    $verification.source_rows_requested -ne 0 -or
    $verification.paid_actions -ne 0 -or
    $verification.certified_sale_labels -ne 0) {
    throw 'Cook Clerk technical verification differs from its saved result'
}

$expected = @(
    @{ name = 'search.html'; sha256 = '2010e4bcbd03a9e8cb711626ecd6ecc0b28d440d27d2df2d9fb184cc76c1c9a6'; url = 'https://www.cookcountyclerkil.gov/recordings/search-recordings'; type = 'text/html' },
    @{ name = 'transfer-list.pdf'; sha256 = '1b0423cea3a2ffe42a02ed4eec9ff4e6aa48474254423a88816241c812801819'; url = 'https://www.cookcountyclerkil.gov/publication/transfer-list-license-agreement-summary'; type = 'application/pdf' },
    @{ name = 'fees.html'; sha256 = 'ae5e91da8a09a475801108fc863a3310bdb1c80bdff7f3def41d3f312daae416'; url = 'https://www.cookcountyclerkil.gov/recordings/recording-fees'; type = 'text/html' },
    @{ name = 'faqs.html'; sha256 = '4aa93ab2a32cb2f7b042d6bb27b294e0d9a1c2eeae72575629023c5a2b72e185'; url = 'https://www.cookcountyclerkil.gov/recordings/recording-faqs'; type = 'text/html' }
)

foreach ($index in 0..3) {
    $entry = $manifest.results[$index]
    $item = $expected[$index]
    $path = Join-Path $private $item.name
    if ($entry.name -ne $item.name -or
        $entry.url -ne $item.url -or
        $entry.status_code -ne 200 -or
        -not $entry.content_type.StartsWith($item.type) -or
        $entry.sha256 -ne $item.sha256 -or
        (Get-Item -LiteralPath $path).Length -ne $entry.bytes -or
        $entry.bytes -gt 1048576 -or
        (Get-LowerHash $path) -ne $item.sha256) {
        throw "Cook Clerk document capture differs: $($item.name)"
    }
}

Push-Location $root
try {
    & '.\.venv\Scripts\python.exe' -c "from pathlib import Path; import sys; from scripts.private_review_io import private_path, real_directory, verify_acl; root=Path(sys.argv[1])/'data'/'raw'/'cook_county'; directory=root/'u0-cook-clerk-public-docs-v1-20261003T014926Z'; real_directory(directory,root); verify_acl(directory); [private_path(directory/name,directory,must_exist=True) for name in ('search.html','transfer-list.pdf','fees.html','faqs.html')]" $root
    if ($LASTEXITCODE -ne 0) { throw 'Cook Clerk private directory ACL or path failed' }
}
finally { Pop-Location }
Write-Output 'Four Cook Clerk public documents verified; no rows, paid actions or certified sale labels; U0 and G-US pending'
