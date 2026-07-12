"""Loaders for NASA OSDR (formerly GeneLab) RNA-seq data.

Notes on the API, learned by probing it directly:

* GLOpenAPI at `visualization.genelab.nasa.gov` is gone. The live service is the
  OSDR Biological Data API v2 at `visualization.osdr.nasa.gov/biodata/api/v2`.
* There is no `file.datatype=unnormalized counts` query parameter. The API serves
  metadata and file *listings*; the counts themselves are a file you download.
  So we list a dataset's files and resolve the counts file by name.
* OSD and GLDS accession numbers are NOT the same series. OSD-576 contains
  GLDS-570. Always address datasets by their OSD accession.
* TLS on some machines is intercepted by antivirus (e.g. Avast), which re-signs
  certificates with a root that `certifi` does not carry. We use `truststore` to
  verify against the OS trust store instead. Verification stays ON; we never
  pass verify=False.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import requests
import truststore

from src.data.timepoints import to_mission_day

truststore.inject_into_ssl()

API = "https://visualization.osdr.nasa.gov/biodata/api/v2"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"

# Quantifier preference when a dataset ships several counts files. RSEM with rRNA
# removed is the most processed; plain STAR is the most widely available.
QUANTIFIER_PREFERENCE = ("RSEM_Unnormalized_Counts_rRNArm", "RSEM_Unnormalized_Counts",
                         "STAR_Unnormalized_Counts", "FeatureCounts_Unnormalized_Counts")


class NoCountsFileError(LookupError):
    """The dataset exists but publishes no unnormalized counts matrix."""


def _cache_path(kind: str, accession: str, params: dict) -> Path:
    """Cache key = accession + a hash of the query params, so a changed query
    cannot silently return a stale file."""
    digest = hashlib.sha256(
        json.dumps(params, sort_keys=True).encode()
    ).hexdigest()[:12]
    return CACHE_DIR / f"{accession}__{kind}__{digest}"


def _get(url: str, params: dict | None = None, timeout: int = 120) -> requests.Response:
    response = requests.get(url, params=params or {}, timeout=timeout)
    response.raise_for_status()
    return response


def list_files(accession: str, refresh: bool = False) -> dict:
    """Return the file manifest for an OSD accession, cached on disk."""
    cache = _cache_path("files", accession, {}).with_suffix(".json")
    if cache.is_file() and not refresh:
        return json.loads(cache.read_text())

    payload = _get(f"{API}/dataset/{accession}/files/").json()
    files = payload[accession]["files"]

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(files))
    return files


def resolve_counts_file(accession: str, refresh: bool = False) -> tuple[str, str]:
    """Return (filename, url) of the preferred unnormalized counts file.

    Raises NoCountsFileError if the dataset publishes none — several OSDR
    datasets (assay-only, metagenomics, single-cell) genuinely do not.
    """
    files = list_files(accession, refresh=refresh)
    candidates = [n for n in files if "unnormalized_counts" in n.lower()]
    if not candidates:
        raise NoCountsFileError(
            f"{accession} publishes no unnormalized counts file "
            f"({len(files)} files listed). It may not be a bulk RNA-seq dataset."
        )

    for quantifier in QUANTIFIER_PREFERENCE:
        for name in candidates:
            if quantifier.lower() in name.lower():
                return name, files[name]["URL"]
    name = sorted(candidates)[0]
    return name, files[name]["URL"]


def fetch_counts(accession: str, refresh: bool = False) -> pd.DataFrame:
    """Return the unnormalized counts matrix for an OSD accession.

    Genes are the index; columns are samples. The raw CSV is cached on disk, so
    a second call does no network I/O.
    """
    name, url = resolve_counts_file(accession, refresh=refresh)
    cache = _cache_path("counts", accession, {"file": name}).with_suffix(".csv")

    if not cache.is_file() or refresh:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(_get(url, timeout=600).content)

    counts = pd.read_csv(cache, index_col=0)
    counts.index.name = "gene"
    return counts


# --- Inspiration4 -----------------------------------------------------------
#
# The I4 datasets do not expose counts through the file-listing route above, so
# these two are addressed by name. See docs/DATA_NOTES.md for why.

I4_ACCESSION = "OSD-569"
I4_CBC_FILE = "LSDS-7_Complete_Blood_Count_CBC_TRANSFORMED.csv"
I4_RNA_FILE = ("GLDS-561_long-readRNAseq_Direct_RNA_seq_Gene_Expression_"
               "Processed.xlsx")
_GEODE = "https://osdr.nasa.gov/geode-py/ws/studies/{acc}/download"


def _fetch_named_file(accession: str, filename: str, refresh: bool = False) -> Path:
    """Download a named file from a dataset, returning its cached path."""
    cache = _cache_path("file", accession, {"file": filename})
    cache = cache.with_suffix(Path(filename).suffix)
    if not cache.is_file() or refresh:
        cache.parent.mkdir(parents=True, exist_ok=True)
        response = _get(_GEODE.format(acc=accession),
                        params={"source": "datamanager", "file": filename},
                        timeout=900)
        cache.write_bytes(response.content)
    return cache


def fetch_i4_cbc(refresh: bool = False) -> pd.DataFrame:
    """Return the I4 complete-blood-count panel in tidy long form.

    One row per (crew, timepoint, analyte). This is the forecasting target: it
    is the only I4 modality with post-return recovery timepoints (R+45, R+82,
    R+194) — the RNA-seq stops at R+1.

    Columns: crew, timepoint, mission_day, analyte, unit, value, ref_min, ref_max
    """
    path = _fetch_named_file(I4_ACCESSION, I4_CBC_FILE, refresh=refresh)
    wide = pd.read_csv(path)

    ids = wide["Sample Name"].str.extract(
        r"^(?P<crew>C\d+)_whole-blood_(?P<timepoint>[LR][+-]\d+)_cbc$"
    )
    if ids.isna().any().any():
        bad = wide.loc[ids.isna().any(axis=1), "Sample Name"].tolist()
        raise ValueError(f"Unparseable CBC sample names: {bad}")

    # Column names look like `absolute_basophils_value_cells_per_microliter`,
    # with matching `_range_min_` / `_range_max_` siblings.
    pattern = re.compile(r"^(?P<analyte>.+?)_(?P<kind>value|range_min|range_max)_(?P<unit>.+)$")
    records = []
    for column in wide.columns:
        match = pattern.match(column)
        if match:
            records.append((column, match["analyte"], match["kind"], match["unit"]))

    frames = {}
    for column, analyte, kind, unit in records:
        frames.setdefault((analyte, unit), {})[kind] = wide[column]

    rows = []
    for (analyte, unit), kinds in frames.items():
        block = pd.DataFrame({
            "crew": ids["crew"],
            "timepoint": ids["timepoint"],
            "analyte": analyte,
            "unit": unit,
            "value": kinds.get("value"),
            "ref_min": kinds.get("range_min"),
            "ref_max": kinds.get("range_max"),
        })
        rows.append(block)

    tidy = pd.concat(rows, ignore_index=True)
    tidy["mission_day"] = tidy["timepoint"].map(to_mission_day)
    tidy = tidy[["crew", "timepoint", "mission_day", "analyte", "unit",
                 "value", "ref_min", "ref_max"]]
    return tidy.sort_values(["analyte", "crew", "mission_day"]).reset_index(drop=True)


def fetch_i4_counts(sheet: str = "I4-FP1", quantifier: str = "featureCounts",
                    refresh: bool = False) -> pd.DataFrame:
    """Return the I4 long-read RNA-seq counts matrix (genes x crew/timepoint).

    Used for pre-vs-post differential expression, NOT for trajectory
    forecasting: there is only one post-return timepoint (R+1).

    Each sheet holds SEVERAL side-by-side blocks under a three-row header —
    quantifier ('featureCounts', 'salmon'), then crew, then timepoint — plus a
    trailing block of DESeq2 stats. The crew/timepoint headers repeat verbatim
    across blocks, so selecting on those alone yields duplicate columns and
    silently mixes two quantifications. We pick one block by `quantifier`.
    """
    path = _fetch_named_file(I4_ACCESSION, I4_RNA_FILE, refresh=refresh)
    raw = pd.read_excel(path, sheet_name=sheet, header=None)

    quantifier_row, crew_row, timepoint_row, first_data_row = 6, 7, 8, 9
    blocks = raw.iloc[quantifier_row].ffill()

    selected = [
        i for i in range(1, raw.shape[1])
        if str(blocks.iloc[i]) == quantifier
        and str(raw.iloc[crew_row, i]).startswith("C")
        and str(raw.iloc[timepoint_row, i])[:1] in ("L", "R")
    ]
    if not selected:
        available = sorted({str(v) for v in blocks.dropna()})
        raise LookupError(
            f"No '{quantifier}' block in sheet {sheet!r}. Available: {available}"
        )

    columns = pd.MultiIndex.from_tuples(
        [(str(raw.iloc[crew_row, i]), str(raw.iloc[timepoint_row, i]))
         for i in selected],
        names=["crew", "timepoint"],
    )
    if columns.duplicated().any():
        raise ValueError(f"Duplicate (crew, timepoint) columns in {sheet!r}")

    counts = raw.iloc[first_data_row:, selected].apply(pd.to_numeric, errors="coerce")
    counts.columns = columns
    counts.index = raw.iloc[first_data_row:, 0].rename("gene")
    return counts.dropna(how="all")
