# Project operations

This public note records operational boundaries without account details,
private contact data, credentials, signing material or personal action history.

| Area | Publicly verifiable state | Boundary |
|---|---|---|
| PyPI Trusted Publishing | The release workflow uses GitHub OIDC and validates artifacts before upload. | External publisher configuration is managed by the package service. |
| Catalogs | Public catalog pages and their content are checked by dated snapshots. | An open request is not a published listing. |
| Restricted research data | Only license and access status are recorded. | Restricted datasets stay excluded until terms permit reproducible use. |
| Human evaluation | Automated and model-based checks are labelled with their limits. | Private participant data is not stored here. |

Current distribution evidence is in research/DISTRIBUTION-JOURNAL.md and the
release gates. This public tree is intended to exclude secrets, private keys
and raw private correspondence; verify any new material before committing it.
