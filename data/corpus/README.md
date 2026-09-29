# Sample corpus (synthetic)

Everything under this folder is **synthetic demo documentation** written for this project.
"Aurora Networks" and "Helix Radio" are fictional vendors; commands, alarm codes and URLs
(`*.example`) are invented so the system can be demonstrated without redistributing real
vendor manuals.

## Layout convention

```
data/corpus/<vendor>/<product>/<version>/<document>.<md|html|txt|pdf>
```

The folder path supplies the three mandatory metadata fields — **vendor**, **product**,
**version** — so every chunk can be hard-filtered by release at query time.

Optional per-document metadata:

| Format | Where metadata lives |
| --- | --- |
| `.md`, `.txt` | YAML front matter between `---` lines at the top |
| `.html` | `<title>` and `<meta name="doc_type" / "url">` tags |
| `.pdf` | sidecar file `<name>.pdf.meta.yaml` |

Supported `doc_type` values: `runbook`, `config_guide`, `vendor_manual`, `release_notes`.
If `doc_type` is missing it is inferred from the file name.

This README is ignored by the ingestion pipeline.
