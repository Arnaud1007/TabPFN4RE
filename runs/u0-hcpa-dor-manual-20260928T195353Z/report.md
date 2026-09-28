# U0 HCPA DOR Code Manual check

Run ID: `u0-hcpa-dor-manual-20260928T195353Z`. Status: source-documentation
increment; U0 and G-US remain pending. Requirements addressed: US02, US05,
US07 and US24. No HCPA sale rows were relabelled, joined or modelled.

The [official HCPA download page](https://downloads.hcpafl.org/) lists
`_DOR_Code_Manual.docx` with a 2021 update date. The file was downloaded
through the publisher's file selection and retained at Git-ignored
`data/raw/hcpa/_DOR_Code_Manual.docx`. Its SHA-256 is
`cc10939078fd60ba41abdb555b6c34e3e2a3dc2a35bcf4f713114992b52599fe`.
Python's `zipfile.testzip()` found no corrupt DOCX member. Text extracted
from `word/document.xml` was checked for the 0100, 0400 and 0800 entries and
the manual's scope caveat. The source card records additional examples.

The county manual calls 0100 detached single-family residential, 0400
condominium and 0800 multifamily under ten units. It also says it is only a
supplement and directs readers to `parcel_dor_names.dbf` for the definitive
current code list. That DBF has not been inspected. A code on a parcel does
not establish one eligible home, single-property sale consideration or the
code's historical availability on an All Sales row. The present download
listing and DOCX metadata do not establish first publication at old valuation
origins. The earlier parcel-archive readme establishes that area and room
counts total all buildings on a parcel. Those fields remain outside the
certified feature set.

The current source-card versions are frozen under `source_cards/` in this
run; [manifest.json](manifest.json) hashes them, this report and the ignored
raw manual. The source-document integrity and text checks passed. No package
or model code changed, so the prior 277-test engineering gate remains the
latest code verification. The HCPA 200-record manual review remains at zero
complete rubrics. Source-specific reuse rights, true close-date semantics,
publication history and transaction scope are unresolved.
