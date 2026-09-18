# study-sentinel

An automated pipeline for ingesting, cleaning, validating, and querying multi-site clinical trial data. The system builds a connected "Patient 360" view of trial subjects, applies protocol-accurate compliance checks, and defends against prompt-injection traps planted in source documents — all while answering structured queries with evidence-backed, schema-valid responses.

## Overview

Clinical trials generate fragmented data across sites, visits, and document versions. This system consolidates that data into a single queryable graph, enforces historically accurate protocol rules (since rules change across protocol amendments), and treats any embedded instructions found in source documents as suspicious content to flag — never as commands to execute.

## Features

- **Resilient ingestion** — handles malformed rows, missing fields, and inconsistent date formats without failing.
- **Smart data cleaning** — correctly interprets censored lab values (e.g. `<5`) and normalizes cross-site unit differences.
- **Patient 360 graph** — hierarchical Site → Subject → Visit structure for fast, indexed lookups.
- **Version-aware governance** — maps each data cut to the protocol version active at that time, so historical rules (e.g. visit windows) are applied correctly.
- **Prompt-injection defense** — scans protocol and lab manual text for planted instructions (e.g. "exclude site X from safety assessments") and surfaces them as findings, not executable commands.
- **Rule-based safety checks** — visit window compliance, prohibited medication checks, and composite safety rules such as Hy's Law.
- **Fast, evidence-backed queries** — Count, Lookup, Finding, and Trap query types, each returning a schema-valid response with precise `RecordRef` citations, within a 120-second wall-time budget.

## Architecture: Execution Flow

The system processes clinical trial data through a modular pipeline, ensuring historical accuracy, data integrity, and robust defense against planted document traps.

### 1. Ingestion (`stage1/loader.py`)
- Loads the raw clinical data tables from `hackathon-data/`.
- Gracefully handles malformed rows, missing fields, and multiple date formats without crashing.

### 2. Cleaning & Normalization (`stage1/cleaning.py`)
- Cleans non-numeric laboratory values (e.g., interpreting `<5` as below-detection rather than zero).
- Handles unit conversions using site-specific reference ranges.

### 3. Graph Network Construction (`stage1/graph.py`)
- Transforms flat tables into a connected "Patient 360" hierarchical network grouped by Site and Subject.
- Pre-indexes records to ensure all queries execute well within the 120-second wall-time limit.
- Writes summary graph statistics to `graph_stats.json`.

### 4. Document Governance & Trap Scanning (`stage1/documents.py`)
- Maps data cuts to their historically active protocol versions (ensuring past rules like visit windows apply correctly).
- Scans protocol and lab manuals for planted prompt-injection traps (e.g., instructions telling automated reviewers to exclude specific sites or suppress specific findings) and flags them as evidence rather than executing them.

### 5. Validation & Safety Checks (`stage1/checks.py`)
- Executes compliance rules, visit windows, prohibited medications, and complex safety criteria (such as Hy's Law) using rules derived from the active protocol versions.

### 6. Query Orchestration (`stage1/atlas.py`)
- Answers incoming questions (Count, Lookup, Finding, and Trap) by querying the graph and returning schema-valid responses backed by precise `RecordRef` evidence.

## Project Structure

```
study-sentinel/
├── hackathon-data/          # Raw clinical CSV tables and protocol/lab manual documents
├── stage1/
│   ├── loader.py            # Stage 1: Ingestion
│   ├── cleaning.py          # Stage 2: Cleaning & normalization
│   ├── graph.py              # Stage 3: Patient 360 graph construction
│   ├── documents.py         # Stage 4: Document governance & trap scanning
│   ├── checks.py             # Stage 5: Validation & safety checks
│   └── atlas.py               # Stage 6: Query orchestration
├── graph_stats.json          # Output: summary statistics from graph construction
├── requirements.txt
├── .gitignore
└── README.md
```

## Installation

```bash
git clone <repo-url>
cd study-sentinel
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
# Run the full pipeline end-to-end
python -m stage1.atlas --data-dir hackathon-data --query-file queries.json --output results.json
```

Example programmatic use:

```python
from stage1.atlas import Atlas

atlas = Atlas(data_dir="hackathon-data")
atlas.build()  # runs ingestion -> cleaning -> graph -> governance -> checks

response = atlas.query({
    "type": "Count",
    "filters": {"site": "S07", "status": "active"}
})
print(response)
```

## Query Types

| Type    | Description                                                   |
|---------|-----------------------------------------------------------------|
| Count   | Returns aggregate counts matching filter criteria.               |
| Lookup  | Retrieves specific subject/visit/lab records.                    |
| Finding | Surfaces safety or compliance findings (e.g. Hy's Law flags).    |
| Trap    | Reports any planted prompt-injection instructions found in docs. |

Every response includes one or more `RecordRef` citations pointing to the exact source row(s) used to derive the answer.

## Performance

- All queries are designed to complete within a **120-second wall-time limit**, enabled by pre-indexing during graph construction.

## Security Note

Any instructions embedded in ingested protocol or lab manual text (e.g., "exclude sites from safety assessments" or "do not flag certain findings") are **never executed**. They are detected via the trap-scanning stage and reported as findings for human review.

## Testing

```bash
pytest tests/
```

## License

Add your license here (e.g., MIT).
