"""csv_parser.py

Parses CSV/Excel files and raw text into campaign recipient lists.
Supports auto-detection of delimiters, column aliases, and phone number normalization.
"""

import csv
import io
import re
from typing import Any, Dict, List, Optional, Tuple


# --------------- Phone Number Normalization --------------- #

def normalize_phone_number(value: Optional[str]) -> Optional[str]:
    """Normalize a phone number to +91XXXXXXXXXX format."""
    if not value:
        return None
    # Strip whitespace, dashes, dots, parentheses
    cleaned = re.sub(r"[\s\-\.\(\)]+", "", str(value).strip())

    # Remove leading quotes
    cleaned = cleaned.strip("'\"")

    # If it starts with +, keep as-is but validate
    if cleaned.startswith("+"):
        digits = re.sub(r"[^\d]", "", cleaned[1:])
        if len(digits) >= 10:
            return f"+{digits}"
        return None

    # Remove leading 0 (for 0-prefixed numbers)
    if cleaned.startswith("0"):
        cleaned = cleaned[1:]

    # Extract just digits
    digits = re.sub(r"[^\d]", "", cleaned)

    # 10-digit Indian mobile number
    if len(digits) == 10:
        return f"+91{digits}"
    # Already has country code
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    # Other valid international numbers
    if len(digits) >= 10:
        return f"+{digits}"

    return None


def looks_like_phone_number(value: Optional[str]) -> bool:
    """Check if a string looks like a phone number."""
    if not value:
        return False
    digits = re.sub(r"[^\d]", "", str(value))
    return 7 <= len(digits) <= 15


# --------------- Column Detection --------------- #

HEADER_ALIASES = {
    "serial_number": ["serialnumber", "serial", "srno", "sno", "sl", "slno", "sequence", "#"],
    "name": ["name", "fullname", "recipientname", "contactname", "person", "customer"],
    "phone_number": [
        "number", "phonenumber", "phone", "mobile", "mobilenumber",
        "contactnumber", "tel", "telephone", "cell", "cellphone",
    ],
    "detail": [
        "detail", "details", "notes", "context", "description",
        "recipientdetail", "recipientdetails", "info", "remarks",
    ],
}


def _normalize_header(header: str) -> str:
    """Normalize a header string for matching."""
    return re.sub(r"[^a-z0-9]", "", header.strip().lower())


def _detect_header_map(headers: List[str]) -> Dict[str, int]:
    """Map canonical field names to column indices."""
    normalized = [_normalize_header(h) for h in headers]
    result = {}

    for field, aliases in HEADER_ALIASES.items():
        for i, nh in enumerate(normalized):
            if nh in aliases:
                result[field] = i
                break

    return result


# --------------- CSV Parsing --------------- #

def _detect_delimiter(text: str) -> str:
    """Auto-detect CSV delimiter."""
    lines = text.strip().split("\n")[:5]
    if not lines:
        return ","

    for delim in [",", "\t", ";", "|"]:
        counts = [line.count(delim) for line in lines]
        if all(c > 0 for c in counts) and len(set(counts)) <= 2:
            return delim

    return ","


def parse_csv_text(text: str) -> Dict[str, Any]:
    """
    Parse CSV/delimited text into recipient records.

    Returns:
        {
            "recipients": [{"phone_number": ..., "name": ..., "detail": ...}],
            "summary": {"total": N, "valid": N, "invalid": N},
            "warnings": [...],
            "detected_columns": [...],
            "mode": "numbers" | "structured"
        }
    """
    text = text.strip()
    if not text:
        return {
            "recipients": [],
            "summary": {"total": 0, "valid": 0, "invalid": 0},
            "warnings": [],
            "detected_columns": [],
            "mode": "empty",
        }

    warnings = []
    lines = text.split("\n")

    # Check if it's just a list of phone numbers (one per line)
    stripped_lines = [l.strip() for l in lines if l.strip()]
    if all(looks_like_phone_number(l) for l in stripped_lines[:5]):
        recipients = []
        invalid = 0
        for i, line in enumerate(stripped_lines):
            normalized = normalize_phone_number(line)
            if normalized:
                recipients.append({
                    "phone_number": normalized,
                    "name": "",
                    "detail": "",
                })
            else:
                invalid += 1
                warnings.append(f"Row {i + 1}: Invalid phone number '{line}'")

        return {
            "recipients": recipients,
            "summary": {"total": len(stripped_lines), "valid": len(recipients), "invalid": invalid},
            "warnings": warnings,
            "detected_columns": ["phone_number"],
            "mode": "numbers",
        }

    # Structured CSV
    delimiter = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)

    if len(rows) < 2:
        # Single row — might be all phone numbers
        if len(rows) == 1 and len(rows[0]) == 1:
            normalized = normalize_phone_number(rows[0][0])
            if normalized:
                return {
                    "recipients": [{"phone_number": normalized, "name": "", "detail": ""}],
                    "summary": {"total": 1, "valid": 1, "invalid": 0},
                    "warnings": [],
                    "detected_columns": ["phone_number"],
                    "mode": "numbers",
                }
        return {
            "recipients": [],
            "summary": {"total": 0, "valid": 0, "invalid": 0},
            "warnings": ["File appears to be empty or has only headers"],
            "detected_columns": [],
            "mode": "empty",
        }

    # First row = headers
    headers = rows[0]
    header_map = _detect_header_map(headers)
    detected_columns = list(header_map.keys())

    # If no phone column detected, try to find one by scanning data
    if "phone_number" not in header_map:
        for col_idx in range(len(headers)):
            sample_values = [rows[r][col_idx] for r in range(1, min(4, len(rows))) if col_idx < len(rows[r])]
            if any(looks_like_phone_number(v) for v in sample_values):
                header_map["phone_number"] = col_idx
                detected_columns.append("phone_number")
                warnings.append(f"Auto-detected column {col_idx + 1} ('{headers[col_idx]}') as phone number")
                break

    if "phone_number" not in header_map:
        return {
            "recipients": [],
            "summary": {"total": len(rows) - 1, "valid": 0, "invalid": len(rows) - 1},
            "warnings": ["Could not detect a phone number column. Please ensure a column named 'Phone', 'Number', or 'Mobile' exists."],
            "detected_columns": detected_columns,
            "mode": "structured",
        }

    recipients = []
    invalid = 0

    for row_idx, row in enumerate(rows[1:], start=2):
        phone_col = header_map.get("phone_number")
        if phone_col is None or phone_col >= len(row):
            invalid += 1
            continue

        phone = normalize_phone_number(row[phone_col])
        if not phone:
            invalid += 1
            warnings.append(f"Row {row_idx}: Invalid phone number '{row[phone_col] if phone_col < len(row) else ''}'")
            continue

        name_col = header_map.get("name")
        detail_col = header_map.get("detail")

        recipients.append({
            "phone_number": phone,
            "name": row[name_col].strip() if name_col is not None and name_col < len(row) else "",
            "detail": row[detail_col].strip() if detail_col is not None and detail_col < len(row) else "",
        })

    return {
        "recipients": recipients,
        "summary": {"total": len(rows) - 1, "valid": len(recipients), "invalid": invalid},
        "warnings": warnings,
        "detected_columns": detected_columns,
        "mode": "structured",
    }


def parse_excel_bytes(file_bytes: bytes) -> Dict[str, Any]:
    """Parse an Excel (.xlsx) file into recipient records."""
    try:
        import openpyxl
    except ImportError:
        return {
            "recipients": [],
            "summary": {"total": 0, "valid": 0, "invalid": 0},
            "warnings": ["openpyxl not installed. Install with: pip install openpyxl"],
            "detected_columns": [],
            "mode": "empty",
        }

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
    ws = wb.active

    # Convert to CSV text and reuse parser
    lines = []
    for row in ws.iter_rows(values_only=True):
        cells = [str(cell) if cell is not None else "" for cell in row]
        lines.append(",".join(cells))
    wb.close()

    return parse_csv_text("\n".join(lines))
