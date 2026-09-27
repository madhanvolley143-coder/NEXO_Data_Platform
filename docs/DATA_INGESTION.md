# NEXO Data Platform - Cloud Data Ingestion Architecture

This document describes the data ingestion engine, storage architecture, manifest management, integrity validation, and **document immutability & versioning** foundation for the **NEXO Data Platform**.

---

## 1. End-to-End Ingestion Pipeline

```mermaid
flowchart TD
    A[Official Government Source] --> B[Source Registry / URL Intake]
    B --> C[Document Collector / Ingestor]
    C --> D[Compute SHA-256 Checksum]
    D --> E{URL Previously Ingested?}
    E -- Yes: Identical SHA-256 --> F[Audit Duplicate in Manifest\nPreserve Original\nZero Re-upload]
    E -- Yes: Different SHA-256 --> G[Detect Source Update\nDeprecate Prior Active Flag\nCreate Version N+1 Linked to Old SHA-256]
    E -- No: New Document --> H[Register Version 1]
    G --> I[Format & Magic-Byte Detection]
    H --> I
    I --> J{Requires OCR?}
    J -- Yes (Images, Scans) --> K[Flag requires_ocr = True]
    J -- No (Text/PDF/DOCX) --> L[Flag requires_ocr = False]
    K --> M[Metadata Validation & Storage Pre-check]
    L --> M
    M --> N[Append Manifest Record (JSON/JSONL)]
    N --> O[Immutable Supabase Storage (CAS via SHA-256)]
    O --> P[Prepare PostgreSQL Records\n(documents, versions, sync_logs)]
    P --> Q[Future Embeddings & Multilingual RAG]
```

---

## 2. Document Immutability Principles

Official government gazettes, notifications, guidelines, and circulars represent statutory records. Once ingested, an original government document must **NEVER be modified, overwritten, or physically deleted**.

### Immutability Rules
1. **Zero-Overwrite Guarantee**: Once an asset is placed at a storage path, any attempt to overwrite or mutate it raises an `ImmutableDocumentViolationError`.
2. **Content-Addressable Storage (CAS)**:
   - Storage paths incorporate the SHA-256 hash:
     ```
     {domain_slug}/{source_id}/{sha256}.{extension}
     ```
   - If even one byte of a document changes, it naturally hashes to a distinct SHA-256 and receives a new physical path. The prior document remains untouched at its original path.
3. **Duplicate Detection & Audit (Identical SHA-256)**:
   - If the scraper encounters the same URL and content hash, it records a duplicate check event in the manifest (`duplicate_check_count += 1`, `last_verified_at = now()`).
   - No redundant physical copy is created or uploaded.
4. **Official Revisions & Version Lineage (Updated SHA-256)**:
   - When an official source updates a document at an existing URL:
     - Old document remains preserved permanently (`is_current = false`).
     - New document is assigned `version = previous_version + 1`.
     - `previous_sha256` explicitly links to the prior version's hash.
     - New document is stored at its own distinct path.
5. **No Physical Deletion**: The ingestion engine contains no delete or upsert endpoints.

---

## 3. Supabase Storage Architecture

* **Bucket Name**: `nexo-government-documents`
* **Access Policy**: Private by default; accessible via authenticated API or signed URLs.
* **Deterministic Storage Path Structure**:
  ```
  {domain_slug}/{source_id}/{sha256}.{extension}
  ```
  Example:
  ```
  agriculture_rural_sustainability/pm-kisan/a3b1c2d3e4f5...7890.pdf
  ```

### Storage Directory Mapping (7 Core Domains)

| Domain | Storage Directory Slug |
| :--- | :--- |
| **Government Schemes** | `government_schemes/` |
| **Cooperative Governance** | `cooperative_governance/` |
| **Agriculture and Rural Sustainability** | `agriculture_rural_sustainability/` |
| **FoodTech / Cold-chain / Rural Logistics** | `foodtech_coldchain/` |
| **Rural Development and Financial Assistance** | `rural_development_finance/` |
| **Legal Assistance / Grievance Redressal** | `legal_assistance/` |
| **Multilingual government information** | `multilingual/` |

---

## 4. Supported Formats & MIME Matrix

| Format | MIME Type | Extension | OCR Default | Detection Mechanism |
| :--- | :--- | :--- | :--- | :--- |
| **PDF** | `application/pdf` | `.pdf` | Conditional (Heuristic) | Header `%PDF-` |
| **HTML** | `text/html` | `.html` | False | `<!DOCTYPE html` or `<html` |
| **Word DOCX** | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `.docx` | False | `PK\x03\x04` + `word/` |
| **CSV** | `text/csv` | `.csv` | False | Comma-delimited rows |
| **JSON** | `application/json` | `.json` | False | Standard JSON parser / heuristics |
| **XML** | `application/xml` | `.xml` | False | `<?xml` or root tags |
| **Plain Text** | `text/plain` | `.txt` | False | Clean UTF-8 / ASCII text |
| **JPEG Image**| `image/jpeg` | `.jpg` | **True** | Header `\xff\xd8\xff` |
| **PNG Image** | `image/png` | `.png` | **True** | Header `\x89PNG\r\n\x1a\n` |
| **TIFF Image**| `image/tiff` | `.tiff`| **True** | Header `II*\x00` or `MM\x00*` |
| **WebP Image**| `image/webp` | `.webp`| **True** | Header `RIFF....WEBP` |

---

## 5. Manifest System Specification

The manifest tracks every ingested asset, providing an audit trail prior to database and cloud storage execution.

### Manifest Record Schema
* `source_url` (str): Official government origin link.
* `source_id` (str, optional): Foreign key or slug of the source portal.
* `title` (str): Official title of the document.
* `target_domain` (str): One of the 7 official NEXO domains.
* `language` (str): Language code (ISO 639-1 / BCP 47), default `en`.
* `mime_type` (str): Detected MIME type.
* `file_size` (int): Byte count.
* `sha256` (str): 64-character lowercase hexadecimal hash.
* `requires_ocr` (bool): Boolean flag indicating raster/scanned content.
* `scraped_at` (str): UTC ISO 8601 timestamp.
* `storage_path` (str): Deterministic bucket path.
* `processing_status` (str): `staged`, `duplicate_preserved`, `uploaded`, `failed`.
* `version` (int): Revision number (1, 2, 3...).
* `previous_sha256` (str, optional): SHA-256 of superseded version.
* `previous_storage_path` (str, optional): Bucket path of superseded version.
* `is_current` (bool): Whether this is the active current version.
* `duplicate_check_count` (int): Number of times identical content was re-verified.
* `last_verified_at` (str, optional): Timestamp of most recent duplicate verification.

Manifest files are stored under `data/manifests/` and support both `.json` (array) and `.jsonl` (line-delimited) formats.

---

## 6. Local Staging Folder Layout

```
data/
├── raw/          # Temporary cache for freshly scraped raw files
├── processed/    # Normalized documents staged for cloud upload
├── manifests/    # JSON and JSONL operational manifests
├── ocr/          # Documents flagged requires_ocr=true awaiting OCR extraction
└── failed/       # Documents that failed validation, decoding, or corrupt check
```

---

## 7. Python Usage Example: Versioning & Deduplication

```python
from app.ingestion import DocumentIngestor, ManifestManager

# Initialize manifest manager
manifest = ManifestManager("data/manifests/daily_manifest.jsonl")
ingestor = DocumentIngestor(manifest_manager=manifest)

url = "https://agricoop.nic.in/guidelines/pm-kisan.pdf"

# 1. Ingest initial document (Version 1)
res_v1 = ingestor.ingest_bytes(
    content=b"%PDF-1.4 PM-KISAN 2023 Guidelines...",
    source_url=url,
    target_domain="Agriculture and Rural Sustainability",
    title="PM-KISAN Guidelines",
)
print(f"V1: version={res_v1.version}, sha256={res_v1.sha256[:10]}, status={res_v1.processing_status}")

# 2. Rescrape identical document (Duplicate Detection)
res_dup = ingestor.ingest_bytes(
    content=b"%PDF-1.4 PM-KISAN 2023 Guidelines...",
    source_url=url,
    target_domain="Agriculture and Rural Sustainability",
    title="PM-KISAN Guidelines Re-check",
)
print(f"Duplicate check: is_duplicate={res_dup.is_duplicate}, status={res_dup.processing_status}")

# 3. Government publishes revised amendment (Version 2)
res_v2 = ingestor.ingest_bytes(
    content=b"%PDF-1.4 PM-KISAN 2024 Revised Amendment with higher allocation...",
    source_url=url,
    target_domain="Agriculture and Rural Sustainability",
    title="PM-KISAN Guidelines 2024",
)
print(f"V2: version={res_v2.version}, previous_sha256={res_v2.manifest_record.previous_sha256[:10]}")

# 4. Query complete audit trail
lineage = manifest.get_lineage_by_url(url)
for entry in lineage:
    print(f"Version {entry.version}: current={entry.is_current}, sha256={entry.sha256[:10]}, path={entry.storage_path}")
```
