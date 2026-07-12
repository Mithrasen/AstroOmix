# Data notes — what the archive actually contains

Findings from probing the live NASA archive. Several contradict the original
project brief; they are recorded here so they are not rediscovered the hard way.

## The API moved

`GLOpenAPI` at `visualization.genelab.nasa.gov` no longer exists — that host now
serves only a web app. The live service is the **OSDR Biological Data API v2**:

    https://visualization.osdr.nasa.gov/biodata/api/v2

There is **no `file.datatype=unnormalized counts` query parameter**. The API
serves metadata and file *listings*; counts are a file you resolve by name and
download. `src/data/loaders.py` does that.

## OSD and GLDS numbers are different series

They are not interchangeable. OSD-576 contains GLDS-570; OSD-577 contains
GLDS-571. Always address datasets by **OSD** accession.

## Rodent A/B module — viable

| Accession | Tissue | Counts | Split |
|---|---|---|---|
| OSD-104 | soleus | 56,832 genes × 12 samples | 6 flight / 6 ground |
| OSD-105 | tibialis anterior | 56,832 genes × 12 samples | 6 flight / 6 ground |
| OSD-488 | — | **none** | **unusable** |

**OSD-488 is not an RNA-seq dataset.** It is SERCA function work — Western blot
and spectrofluorimetric assays, 5 files, no counts matrix. It cannot serve the
A/B module and has been dropped.

Note the counts are RSEM *expected counts*, so they are floats, not integers.
DESeq2 requires integers — round at the DE step, do not assume `int` dtype.

## Human Inspiration4 module — the timeline is the constraint

OSD-569–575 is Inspiration4, but **none of it publishes a bulk unnormalized
counts matrix** through the file-listing route. Real I4 counts do exist, inside
OSD-569's long-read RNA-seq `.xlsx` (61,852 genes × 4 crew × 4 timepoints).

The decisive fact is which timepoints each modality has:

| Modality | Timepoints | Recovery? |
|---|---|---|
| RNA-seq (OSD-569) | L-92, L-44, L-3, **R+1** | **no** — stops 1 day post-return |
| CBC clinical (OSD-569) | L-92, L-44, L-3, R+1, **R+45, R+82, R+194** | yes |

The "months of recovery" timepoints exist **only in the blood-count panel, not
in the transcriptomics**. The RNA-seq has three pre-flight draws and exactly one
post-return draw, so a recovery *trajectory* cannot be fit to it — Prophet,
ARIMA and LightGBM all need a post-flight curve that isn't there.

Hence the split:

* **Forecasting** runs on the **CBC panel** (7 timepoints, 4 crew, 20 analytes).
* **Differential expression** runs on the **I4 RNA-seq** (pre vs. post, R+1).

### The xlsx has repeated column headers

Each sheet holds several side-by-side blocks under a three-row header —
quantifier (`featureCounts`, `salmon`), then crew, then timepoint — plus a
trailing DESeq2 stats block. **The crew/timepoint headers repeat verbatim across
blocks.** Selecting on crew/timepoint alone silently returns 32 columns that mix
two different quantifications. `fetch_i4_counts` selects one block by name.

## Mission-day axis

OSDR labels samples against two anchors: `L-` is days before *launch*, `R+` is
days after *return*. Mixing them naively puts `R+1` on day 1 and erases the
flight. I4 flew 3 days (2021-09-16 → 09-18), so on the `mission_day` axis used
by `src/data/timepoints.py` (launch = day 0), `R+1` is **day 4**.

## Excluded, deliberately

Per-astronaut BMD and VO2max are **not public at usable resolution**. They are
not to be stubbed, faked, or approximated.

## TLS note (local machines)

Some dev machines run antivirus that intercepts HTTPS (e.g. Avast re-signs certs
with `CN=Avast Web/Mail Shield Root`), which `certifi` does not trust. We call
`truststore.inject_into_ssl()` to verify against the OS trust store. Certificate
verification stays **on** — never `verify=False`.
