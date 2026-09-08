# Manifest of preregistration timestamps

This directory contains OTS timestamp sidecars for preregistration documents.
The timestamp hash is the source hash recorded by the timestamp service; a
different current hash means that the document received a later editorial
redaction or update. The original private measurement inputs are not part of
this repository and are described only as restricted source material.

Public preregistrations remain reproducible from their checked-in source files.
Restricted corpora, raw prompts, private archives and participant material are
excluded until licensing and privacy review permits redistribution. This file
does not list private archive names, local paths or hashes of restricted data.

| Sidecar group | Public source status |
|---|---|
| Preregistration documents for corpus, survey and protocol work | Source document is checked in; verify its current SHA-256 before use. |
| Timestamps whose source was a restricted measurement run | Timestamp retained as historical evidence; source remains private. |

To inspect a public source and reproduce its current digest:

```text
python -c "import hashlib,pathlib; p=pathlib.Path('research/<source>.md'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
