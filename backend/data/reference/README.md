# Reference data

Static reference files, committed to the repo on purpose. These are versioned
inputs to the analysis, not cached responses — they must not be fetched live at
request time, or the same query could return different answers on different days.

| File | Source | Downloaded |
|---|---|---|
| `HOM_MouseHumanSequence.rpt` | https://www.informatics.jax.org/downloads/reports/HOM_MouseHumanSequence.rpt | 2026-07-13 |
| `MGI_Gene_Model_Coord.rpt` | https://www.informatics.jax.org/downloads/reports/MGI_Gene_Model_Coord.rpt | 2026-07-13 |

Both from MGI (Mouse Genome Informatics, The Jackson Laboratory). Files are
committed **unmodified**, exactly as served.

## Why two files

`HOM_MouseHumanSequence.rpt` is the mouse–human homology table, but it identifies
genes by **Symbol / EntrezGene ID / MGI ID / HGNC ID — it has no Ensembl column.**
Our rodent differential-expression results are keyed by `ENSMUSG` IDs, so a second
file is needed to bridge Ensembl → MGI:

`MGI_Gene_Model_Coord.rpt` provides `MGI accession id` ↔ `Ensembl gene id`.

## Parsing gotcha (both files)

`MGI_Gene_Model_Coord.rpt` declares **15 header fields but every data row has 16**
(a trailing tab). Naive `pd.read_csv(..., sep='\t')` silently promotes the MGI ID
into the DataFrame index and shifts every column name one position to the left —
so `'11. Ensembl gene id'` ends up holding chromosome numbers. The result is a
mapping that parses without error and matches nothing. `orthology.py` reads this
file **positionally** for that reason.

`HOM_MouseHumanSequence.rpt` also contains duplicate rows for the same gene within
a homology class (e.g. `Try5` appears twice in class 51818048). Cardinality must be
computed over **distinct genes**, not row counts, or those duplicates masquerade as
extra orthologs.
