$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

$verification = @'
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from scripts import review_cook_sales_sample as review, private_review_io as private

run = Path('runs/u0-cook-system-fields-v1-20261003T030715Z')
raw_root = review.RAW_ROOT
directory = raw_root / 'system-fields-v1-20261003T030715Z'
private.real_directory(raw_root, raw_root.parent)
private.verify_acl(raw_root)
private.real_directory(directory, raw_root)
private.verify_acl(directory)
rows = review._capture_rows()
manifest_bytes = private.private_path(directory / 'manifest.json', directory, must_exist=True).read_bytes()
response_bytes = private.private_path(directory / 'response.json', directory, must_exist=True).read_bytes()
public = json.loads((run / 'aggregate.json').read_text(encoding='utf-8'))
manifest = json.loads(manifest_bytes)

def require(condition, message):
    if not condition:
        raise ValueError(message)

require(sha256((run / 'plan.md').read_bytes()).hexdigest() == '82bfdf50280ed2f86717fada903fae8e7184c21992f093225d6d395e42d6e509', 'Frozen plan differs')
require(sha256(manifest_bytes).hexdigest() == 'eba8d7a28f7f50bb241d1591c16470a9ac35f9347ccd28b8d0da80be77f1c598', 'Private probe manifest differs')
require(sha256(response_bytes).hexdigest() == '888ac8fdadcca884ad2cd619814bb22a85ee0410931fa715755104ace0048e71', 'Private probe response differs')
require(manifest['plan_sha256'] == public['plan_sha256'], 'Plan reference differs')
require(manifest['capture_manifest_sha256'] == review.CAPTURE_SHA256 == public['capture_manifest_sha256'], 'Source capture differs')
require(manifest['source_metadata_sha256'] == review.SOURCE_METADATA_SHA256 == public['source_metadata_sha256'], 'Source metadata differs')
require(manifest['http_status'] == public['http_status'] == 200, 'Probe HTTP status differs')
require(manifest['response_bytes'] == public['response_bytes'] == len(response_bytes), 'Probe response size differs')
require(manifest['response_sha256'] == public['response_sha256'], 'Probe response hash differs')
require(manifest['response_row_count'] == public['response_row_count'] == 1, 'Probe row count differs')
require(manifest['identity_match'] is public['identity_match'] is True, 'Probe identity flag differs')
require(public['first_public_availability_established'] is False and public['historical_asof_eligible'] is False and public['certified_sale_labels'] == 0, 'Unsupported qualification claim')

url = urlsplit(manifest['request_url'])
query = parse_qs(url.query, strict_parsing=True)
expected_where = "row_id='" + rows[0]['row_id'].replace("'", "''") + "'"
require(url.scheme == 'https' and url.hostname == 'datacatalog.cookcountyil.gov' and url.path == '/resource/wvhk-k5uv.json', 'Probe URL differs')
require(query == {'$select': [':id,:created_at,:updated_at,row_id'], '$where': [expected_where], '$limit': ['1']}, 'Probe query differs')

response = json.loads(response_bytes)
require(isinstance(response, list) and len(response) == 1 and isinstance(response[0], dict), 'Probe shape differs')
observed = response[0]
fields = [':created_at', ':id', ':updated_at', 'row_id']
require(sorted(observed) == fields == manifest['response_fields'] == public['response_fields'], 'Probe fields differ')
require(observed['row_id'] == rows[0]['row_id'] and isinstance(observed[':id'], str) and observed[':id'], 'Probe identity differs')
for field in (':created_at', ':updated_at'):
    stamp = datetime.fromisoformat(observed[field].replace('Z', '+00:00'))
    require(stamp.utcoffset() is not None, 'Probe timestamp lacks timezone')
require(sha256(manifest_bytes).hexdigest() == public['private_manifest_sha256'], 'Public manifest hash differs')
print('Cook system-field probe verified; timestamps exposed, availability unproven, zero certified labels')
'@

Push-Location $projectRoot
try {
    $verification | & $python -
    if ($LASTEXITCODE -ne 0) { throw 'Cook system-field private replay failed' }
}
finally { Pop-Location }
