# U0 HCPA 2025 parcel archive inventory

Run ID: `u0-hcpa-2025-vintage-20260928T203518Z`. Requirements addressed:
US05 and US24. Status: source-file integrity and DBF header verified; U0 and
G-US remain pending. No parcel rows were ingested, joined, modelled or used
for historical features.

The [official HCPA archive listing](https://downloads.hcpafl.org/?subfolder=_shapefile_archives)
shows `2025_10_parcels.zip` as 97 MB and last updated 7 November 2025 at
06:12. It was downloaded via the publisher's file selection to ignored
`data/raw/hcpa/2025_10_parcels.zip`. The exact file is 102,118,177 bytes,
SHA-256 `2c575a9d7f47a0a3d20527f3c2c5bfa88cb9fbdb9f27dfe3fce59d3edec8260c`.
ZIP integrity passed across nine members.

Its sole DBF, `2025_10_parcel.dbf`, is 559,387,918 uncompressed bytes,
SHA-256 `60adc780260f7405da0a711723dbc156b97b7f39bb71d5ac5e1530796a7fb514`,
CRC32 `49a63ebf`. The dBASE III header declares 527,723 parcel records and
47 fields. The inspected field descriptors include `PIN` C(29), `FOLIO`
C(10), `STRAP` C(22), `DOR_C` C(4), `HEAT_AR` N(19,5), `tUNITS`/`tBLDGS` N(15,2),
`S_DATE` D(8) and `S_AMT` N(19,5). The ZIP does not contain a code-name DBF.
The observed 2025 format differs from the inspected 2026 current parcel ZIP,
so a cross-vintage schema migration and identifier audit are required.

The [source card](../../data/source_cards/hillsborough_hcpa_2025_parcels.yaml)
records the original file, observed fields and limitations. The ZIP member
timestamp and header date are 12 September 2025. They do not prove first
public availability. The listing's last-updated field is also insufficient
to certify an earlier prediction origin. Parcel room/area fields cover all
buildings, and parcel identity is not dwelling or sale identity. Commercial
AVM and redistribution rights remain unresolved.

[test_gate.json](test_gate.json) records exact hash, ZIP and DBF-header checks.
No new model code was introduced by this archive inventory. The separate
frozen 200-sale audit remains unaccepted. A later, predeclared linkage
experiment can compare the 2025 parcel schema with All Sales identifiers;
it must report missing/ambiguous matches and cannot infer historical
availability or price eligibility from a match.
