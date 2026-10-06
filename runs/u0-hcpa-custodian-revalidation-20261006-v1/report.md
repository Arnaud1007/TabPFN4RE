# U0 HCPA custodian recipient revalidation

**Run ID:** `u0-hcpa-custodian-revalidation-20261006-v1`  
**Checked:** 6 October 2026  
**Requirement:** US05 source qualification  
**Status:** recipient revalidated; inquiry ready to import; not sent

## Result

The current [official HCPA records-custodian notice](https://www.hcpafl.org/Portals/HCPAFL/RecordsCustodianforHCPA_Marilyn.pdf?ver=2023-04-29-105106-420) names Marilyn Martinez and directs records requests to `martinezm@hcpafl.org`. The [official directors page](https://www.hcpafl.org/Links/HCPA-Directors) independently lists her as Director of Administrative Services and Records Custodian. HCPA's [official feedback page](https://hcpafl.org/Contact-Us/Email-Us-Feedback) lists `custserv@hcpafl.org` for general questions, concerns or comments.

The approved inquiry body was preserved. Its recipient and provenance were updated in `data/requests/hcpa_all_sales_inquiry_draft.md`, and `data/requests/hcpa_all_sales_inquiry.eml` now provides a plain-text ready-to-import artifact. It intentionally omits `From` and `Reply-To`; the owner's authenticated mail client must populate those fields before delivery. The former `shepherdw@hcpafl.org` recipient is superseded for this inquiry.

## Delivery boundary

No authenticated mail account or mail window is available in this workspace. The inquiry remains unsent, and no delivery or response is claimed. The source's sale-date meaning, first-publication history, repeated-consideration semantics and commercial-use rights therefore remain unresolved. HCPA data remains ineligible for certified model training.

## Evidence boundary

`source_evidence.json` records only official public contact facts and local artifact paths. It contains no property rows, sender identity, credential or secret. Official pages are dynamic; the recipient must be revalidated again if the inquiry is sent later.
