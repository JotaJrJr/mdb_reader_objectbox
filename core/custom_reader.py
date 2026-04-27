"""Reader for custom binary container files (.mdb extension, non-Jet format).

These files use a proprietary format where JSON blobs are stored with a uint32
length prefix. Magic signature 0xBEEFC0DE appears at offset 0x10.

When an ObjectBox schema file (objectbox-model.json) is provided, a second
FlatBuffers-based scan extracts all entity tables with proper field names.

LMDB page format (64-bit):
  Page header: pgno(8) + pad(2) + flags(2) + lower(2) + upper(2) = 16 bytes
  Leaf page node: mn_lo(2) + mn_hi(2) + mn_flags(2) + mn_ksize(2) + key + data
  Overflow page: header(16) + raw data (continues on successive pages)

FlatBuffers Dart convention:
  soffset at table start is POSITIVE; vtable_pos = table_pos - soffset
  (C++ stores NEGATIVE soffset; vtable_pos = table_pos + soffset)
"""
import json
import os
import re
import struct
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

# ── LMDB constants ────────────────────────────────────────────────────────────
_LMDB_PAGE_SIZE = 4096
_LMDB_PAGE_HDR = 16          # bytes of page header
_LMDB_P_BRANCH = 0x01
_LMDB_P_LEAF = 0x02
_LMDB_P_OVERFLOW = 0x04
_LMDB_P_META = 0x08
_LMDB_N_BIGDATA = 0x01       # node flag: value stored on overflow page(s)
_LMDB_N_SUBDATA = 0x02       # node flag: sub-database entry (skip these)


MAGIC = b"\xde\xc0\xef\xbe"
MAGIC_OFFSET = 0x10


def is_custom_format(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            f.seek(MAGIC_OFFSET)
            return f.read(4) == MAGIC
    except OSError:
        return False


def _extract_json_blobs(data: bytes) -> List[Tuple[int, Any]]:
    """Scan binary data for length-prefixed JSON blobs.
    Returns a list of (end_offset, decoded_obj) tuples.
    """
    results = []
    pos = 0
    size = len(data)
    while pos < size - 8:
        if data[pos] in (0x5B, 0x7B):  # '[' or '{'
            if pos >= 4:
                length = struct.unpack_from("<I", data, pos - 4)[0]
                if 10 <= length <= 5_000_000:
                    end = pos + length
                    if end <= size:
                        try:
                            txt = data[pos:end].decode("utf-8")
                            obj = json.loads(txt)
                            results.append((end, obj))
                            pos = end
                            continue
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            pass
        pos += 1
    return results


def _schema_key(record: dict) -> frozenset:
    return frozenset(record.keys())


def _flatten_record(record: Any, parent_type: str = "") -> dict:
    """Unwrap {data, type} envelope into flat record."""
    if isinstance(record, dict) and set(record.keys()) == {"data", "type"}:
        d = record["data"]
        rec_type = record["type"]
        if isinstance(d, dict):
            return {"_type": rec_type, **d}
        return {"_type": rec_type, "_data": json.dumps(d, ensure_ascii=False)}
    return record


class CustomTable:
    def __init__(self, name: str, rows: List[dict]):
        self.name = name
        self.rows = rows

    @property
    def columns(self) -> List[str]:
        if not self.rows:
            return []
        # Collect all keys across rows to handle sparse data
        seen: Dict[str, int] = {}
        for row in self.rows:
            for k in row.keys():
                if k not in seen:
                    seen[k] = 0
                seen[k] += 1
        return list(seen.keys())

    @property
    def row_count(self) -> int:
        return len(self.rows)


def _extract_resposta_records(data: bytes, json_by_end_pos: Dict[int, Any]) -> List[dict]:
    """Extract RespostaPesquisaModel records: JSON blob + 3 UUID reference fields."""
    uuid_re = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    records = []
    pos = 0
    size = len(data)
    while pos < size - 50:
        # Check if we are at the end of a JSON blob that we've already decoded
        # Many records are [JSON][0...][LengthPrefix][UUID]
        if data[pos] in (0x7D, 0x5D):  # '}' or ']'
            blob_end = pos + 1
            base_record = json_by_end_pos.get(blob_end)
            
            j = blob_end
            null_count = 0
            while j < size and data[j] == 0 and null_count < 16:
                null_count += 1
                j += 1
                
            # If we find the UUID length prefix (0x24) after the JSON blob
            if j + 40 <= size and data[j : j + 4] == b"\x24\x00\x00\x00":
                j += 4
                m = uuid_re.match(data[j : j + 36])
                if m:
                    uuids = [m.group(0).decode()]
                    k = j + 36
                    # Look for up to 2 more UUIDs
                    for _ in range(2):
                        nc = 0
                        while k < size and data[k] == 0 and nc < 16:
                            nc += 1
                            k += 1
                        if k + 40 <= size and data[k : k + 4] == b"\x24\x00\x00\x00":
                            k += 4
                            m2 = uuid_re.match(data[k : k + 36])
                            if m2:
                                uuids.append(m2.group(0).decode())
                                k += 36
                                continue
                        break
                    
                    if len(uuids) >= 1:
                        rec = {}
                        if isinstance(base_record, dict):
                            rec.update(base_record)
                        
                        rec.update({
                            "roteiro_external_id": uuids[0] if len(uuids) > 0 else None,
                            "pesquisa_external_id": uuids[1] if len(uuids) > 1 else None,
                            "external_id": uuids[2] if len(uuids) > 2 else None,
                        })
                        records.append(rec)
                        pos = k
                        continue
        pos += 1
    return records


# ── FlatBuffers entity extraction (uses objectbox-model.json schema) ─────────

def load_ob_schema(schema_path: str) -> Optional[dict]:
    """Load and return an objectbox-model.json schema, or None on failure."""
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _read_fb_field(data: bytes, fabs: int, type_code: int) -> Any:
    """Read a single FlatBuffers field at absolute byte offset fabs."""
    size = len(data)
    try:
        if type_code == 1:  # bool (1 byte)
            return bool(data[fabs]) if fabs < size else None
        if type_code in (6, 10, 11):  # int64 / date-ms / ToOne relation
            if fabs + 8 > size:
                return None
            v = struct.unpack_from("<q", data, fabs)[0]
            return v if v != 0 else None
        if type_code == 8:  # double
            if fabs + 8 > size:
                return None
            return struct.unpack_from("<d", data, fabs)[0]
        if type_code in (9, 30):  # string / byte-vector
            if fabs + 4 > size:
                return None
            rel = struct.unpack_from("<I", data, fabs)[0]
            if rel == 0:
                return None
            sp = fabs + rel
            if sp + 4 > size:
                return None
            sl = struct.unpack_from("<I", data, sp)[0]
            if sl == 0:
                return ""
            if sl > 500_000 or sp + 4 + sl > size:
                return None
            raw_val = data[sp + 4 : sp + 4 + sl]
            try:
                return raw_val.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
                # If it's not valid UTF-8, it's likely binary data (like a date or encrypted blob)
                return f"<binary:{raw_val.hex()[:16]}...>"
    except (struct.error, IndexError):
        return None
    return None


def _parse_fb_record(data: bytes, obj_pos: int, props: List[Tuple]) -> Optional[dict]:
    """Parse FlatBuffers object at obj_pos.

    props: sorted list of (prop_id: int, name: str, type_code: int)

    Supports both conventions:
      Dart/positive soffset: vtable_pos = obj_pos - soff  (ObjectBox Flutter)
      C++/negative soffset:  vtable_pos = obj_pos + soff
    Returns a dict or None if the position doesn't look valid.
    """
    size = len(data)
    if obj_pos + 4 > size:
        return None

    soff = struct.unpack_from("<i", data, obj_pos)[0]
    if soff == 0:
        return None
    vt_pos = obj_pos - soff if soff > 0 else obj_pos + soff

    if vt_pos < 0 or vt_pos + 4 > size:
        return None

    vts = struct.unpack_from("<H", data, vt_pos)[0]
    if vts < 4 or vts > 2000:
        return None

    num_fields = (vts - 4) // 2
    result: dict = {}

    for prop_id, name, type_code in props:
        fi = prop_id - 1  # vtable is 0-indexed; ObjectBox prop IDs are 1-based
        if fi >= num_fields:
            result[name] = None
            continue
        fo_addr = vt_pos + 4 + fi * 2
        if fo_addr + 2 > size:
            result[name] = None
            continue
        field_off = struct.unpack_from("<H", data, fo_addr)[0]
        if field_off == 0:
            result[name] = None
            continue
        result[name] = _read_fb_field(data, obj_pos + field_off, type_code)

    return result


def _validate_fb_record(record: dict, props: List[Tuple],
                         lmdb_key: bytes = b"") -> bool:
    """Return True if the parsed record looks like a genuine ObjectBox entity.

    Validation rules:
    • If an int64 ID field is present and non-null, it must be a positive int
      in a plausible range.  If it is absent (ObjectBox sometimes omits the ID
      from the FlatBuffers payload and stores it only as the LMDB key), we
      attempt to fill it from the LMDB key.
    • At least one non-ID field must be non-null (guards against empty parses).
    """
    # Locate the entity's ID field: lowest-prop_id property with type 6 (Long)
    id_name: Optional[str] = None
    for pid, name, tc in props:  # props is sorted by prop_id
        if tc == 6:
            id_name = name
            break

    if id_name is not None:
        id_val = record.get(id_name)
        if id_val is None and len(lmdb_key) == 8:
            # ObjectBox stores the ID as an 8-byte big-endian key; inject it.
            try:
                eid = struct.unpack(">Q", lmdb_key)[0]
                if 0 < eid <= 100_000_000:
                    record[id_name] = eid
                    id_val = eid
            except struct.error:
                pass
        if id_val is not None:
            if not isinstance(id_val, int) or id_val <= 0 or id_val > 100_000_000:
                return False

    # Require at least one non-null value besides the ID field
    non_id_non_null = sum(
        1 for k, v in record.items() if k != id_name and v is not None
    )
    return non_id_non_null > 0


def _lmdb_overflow_value(data: bytes, start_pgno: int, data_size: int) -> bytes:
    """Read data_size bytes from an LMDB overflow page chain starting at start_pgno."""
    parts: List[bytes] = []
    remaining = data_size
    pgno = start_pgno
    total = len(data)
    while remaining > 0:
        base = pgno * _LMDB_PAGE_SIZE
        if base + _LMDB_PAGE_HDR > total:
            break
        page = data[base: base + _LMDB_PAGE_SIZE]
        flags = struct.unpack_from("<H", page, 10)[0]
        if not (flags & _LMDB_P_OVERFLOW):
            break
        chunk = min(remaining, _LMDB_PAGE_SIZE - _LMDB_PAGE_HDR)
        parts.append(page[_LMDB_PAGE_HDR: _LMDB_PAGE_HDR + chunk])
        remaining -= chunk
        pgno += 1
    return b"".join(parts)


def _lmdb_leaf_entries(data: bytes) -> List[Tuple[int, bytes, bytes]]:
    """Iterate every LMDB leaf page and yield (page_idx, key_bytes, value_bytes) triples.

    page_idx lets callers group entries by page.  All entries on the same LMDB
    leaf page belong to the same entity's sub-database, which is the basis for
    per-page entity identification (majority-vote disambiguation).

    Sub-database catalogue entries (MDB_N_SUBDATA) are skipped because their
    values are not FlatBuffers records.
    """
    results: List[Tuple[int, bytes, bytes]] = []
    total = len(data)
    n_pages = total // _LMDB_PAGE_SIZE

    for pi in range(n_pages):
        base = pi * _LMDB_PAGE_SIZE
        page = data[base: base + _LMDB_PAGE_SIZE]
        if len(page) < _LMDB_PAGE_HDR:
            continue

        flags = struct.unpack_from("<H", page, 10)[0]
        if not (flags & _LMDB_P_LEAF):
            continue

        lower = struct.unpack_from("<H", page, 12)[0]
        n_entries = (lower - _LMDB_PAGE_HDR) // 2
        if n_entries <= 0 or n_entries > 2000:
            continue

        for j in range(n_entries):
            ptr_off = _LMDB_PAGE_HDR + j * 2
            if ptr_off + 2 > _LMDB_PAGE_SIZE:
                break
            node_off = struct.unpack_from("<H", page, ptr_off)[0]
            if node_off + 8 > _LMDB_PAGE_SIZE:
                continue
            mn_lo, mn_hi, mn_flags, mn_ksize = struct.unpack_from("<HHHH", page, node_off)

            # Skip sub-database catalogue entries
            if mn_flags & _LMDB_N_SUBDATA:
                continue

            key_start = node_off + 8
            key_end = key_start + mn_ksize
            if key_end > _LMDB_PAGE_SIZE:
                continue
            key = page[key_start:key_end]

            dsize = mn_lo | (mn_hi << 16)
            if dsize == 0:
                continue

            if mn_flags & _LMDB_N_BIGDATA:
                # Value is an 8-byte overflow page number stored inline
                if key_end + 8 > _LMDB_PAGE_SIZE:
                    continue
                ov_pgno = struct.unpack_from("<Q", page, key_end)[0]
                value = _lmdb_overflow_value(data, ov_pgno, dsize)
            else:
                v_start = key_end
                v_end = v_start + dsize
                if v_end > _LMDB_PAGE_SIZE:
                    continue
                value = page[v_start:v_end]

            if value:
                results.append((pi, key, value))

    return results


def _scan_all_entities(data: bytes, schema: dict) -> Dict[str, List[dict]]:
    """Parse LMDB leaf pages and decode FlatBuffers records using objectbox-model schema.

    Strategy:
      1. Build vtable_size → [(entity_name, props)] from schema
      2. Iterate every LMDB leaf entry; for each value:
           a. Read FlatBuffers root_offset (uint32 LE at byte 0)
           b. At obj_pos = root_offset, read soffset (Dart: positive)
           c. vtable_pos = obj_pos - soffset
           d. Match vtable_size against schema candidates
           e. Parse and validate the record
    Returns a dict of entity_name → list of record dicts.
    """
    entities = schema.get("entities", [])

    # Build schema keyed by expected vtable_size.
    #
    # Exact match: vts = 4 + 2 * max_prop_id  (priority 0)
    # Trailing-delete tolerance: vts+2 = 4 + 2*(max_prop_id+1) (priority 1)
    #   Handles databases written with a now-deleted last property. The serialized
    #   vtable has one extra zero-offset slot; fi = prop_id-1 still works.
    #
    # Priority ensures exact-match entities are tried before +2 fallbacks so that
    # two entities sharing the same vtable_size don't steal each other's records.
    _raw: Dict[int, list] = defaultdict(list)  # vts → [(priority, name, props)]
    for entity in entities:
        props: List[Tuple] = []
        for p in entity["properties"]:
            pid = int(p["id"].split(":")[0])
            props.append((pid, p["name"], p.get("type", 9)))
        props.sort()
        if not props:
            continue
        max_prop_id = props[-1][0]
        vts_exact = 4 + 2 * max_prop_id
        _raw[vts_exact].append((0, entity["name"], props))
        _raw[vts_exact + 2].append((1, entity["name"], props))

    # Sort each bucket: priority 0 (exact) before priority 1 (+2), then name for stability
    schema_by_vts: Dict[int, list] = {
        vts: [(name, props) for _, name, props in sorted(entries, key=lambda x: (x[0], x[1]))]
        for vts, entries in _raw.items()
    }

    # ── Per-record entity identification via precision scoring ──────────────
    # For each LMDB leaf entry, identify the best-matching entity schema using
    # field-precision: non-null fields / total schema fields.  The CORRECT schema
    # will have the highest precision because its prop_ids align with the vtable
    # entries actually present in the data (gaps in prop_ids → vtable=0 → null →
    # lower precision for schemas that expect a field there).
    #
    # When two schemas tie (identical field coverage), the first one in the
    # sorted candidates list wins — exact-match entities (priority 0) sort before
    # +2 tolerance entries (priority 1), and within a priority alphabetically.

    results: Dict[str, List[dict]] = defaultdict(list)

    for _page_idx, _key, value in _lmdb_leaf_entries(data):
        vlen = len(value)
        if vlen < 8:
            continue
        root_off = struct.unpack_from("<I", value, 0)[0]
        if root_off + 4 > vlen:
            continue
        obj_pos = root_off
        soff = struct.unpack_from("<i", value, obj_pos)[0]
        if soff <= 0 or soff > vlen:
            continue
        vt_pos = obj_pos - soff
        if vt_pos < 0 or vt_pos + 4 > vlen:
            continue
        actual_vts = struct.unpack_from("<H", value, vt_pos)[0]
        if actual_vts not in schema_by_vts:
            continue

        candidates = schema_by_vts[actual_vts]
        if len(candidates) == 1:
            entity_name, props = candidates[0]
            record = _parse_fb_record(value, obj_pos, props)
            if record is not None and _validate_fb_record(record, props):
                results[entity_name].append(record)
        else:
            best_score = -1.0
            best_entity: str = ""
            best_record: Optional[dict] = None
            for entity_name, props in candidates:
                rec = _parse_fb_record(value, obj_pos, props)
                if rec is None or not _validate_fb_record(rec, props):
                    continue
                score = sum(1 for v in rec.values() if v is not None) / len(props)
                if score > best_score:
                    best_score = score
                    best_entity = entity_name
                    best_record = rec
            if best_record is not None:
                results[best_entity].append(best_record)

    return dict(results)


# ─────────────────────────────────────────────────────────────────────────────

def read_tables(path: str, schema: Optional[dict] = None) -> List[CustomTable]:
    with open(path, "rb") as f:
        data = f.read()

    blobs_with_pos = _extract_json_blobs(data)
    blobs = [b[1] for b in blobs_with_pos]
    json_by_end_pos = {pos: obj for pos, obj in blobs_with_pos}

    # Flatten lists into individual records
    flat: List[Any] = []
    for blob in blobs:
        if isinstance(blob, list):
            flat.extend(blob)
        else:
            flat.append(blob)

    # Separate dicts from other types
    dicts = [r for r in flat if isinstance(r, dict)]

    # Unwrap {data, type} envelopes and single-UUID-key envelopes
    unwrapped = []
    for r in dicts:
        unwrapped.append(_flatten_record(r))

    # Unwrap single-UUID-keyed dicts: {uuid: {campo_tipo, valor, ...}}
    # These are form-field response records; expand to {_field_uuid, campo_tipo, valor, ...}
    expanded = []
    for r in unwrapped:
        keys = list(r.keys())
        if (
            len(keys) == 1
            and isinstance(keys[0], str)
            and len(keys[0]) == 36
            and keys[0][8] == "-"
            and isinstance(r[keys[0]], dict)
        ):
            inner = r[keys[0]]
            expanded.append({"_field_uuid": keys[0], **inner})
        else:
            expanded.append(r)

    # Group by dominant schema (top-level key set)
    by_schema: Dict[frozenset, List[dict]] = defaultdict(list)
    for rec in expanded:
        by_schema[_schema_key(rec)].append(rec)

    # Build tables, merging fragments with the same name
    named: Dict[str, List[dict]] = defaultdict(list)
    for key_schema, rows in sorted(by_schema.items(), key=lambda x: -len(x[1])):
        keys = sorted(key_schema)
        # Field-response records: split by campo_tipo so each type gets its own table
        if "_field_uuid" in key_schema and "campo_tipo" in key_schema:
            by_tipo: Dict[str, List[dict]] = defaultdict(list)
            for r in rows:
                tipo = r.get("campo_tipo") or "sem_tipo"
                by_tipo[tipo].append(r)
            for tipo, tipo_rows in by_tipo.items():
                named[f"respostas_{tipo.lower()}"].extend(tipo_rows)
            continue
        name = _guess_table_name(keys, rows)
        named[name].extend(rows)

    # Extract RespostaPesquisaModel records (JSON resposta + UUID foreign keys)
    resposta_records = _extract_resposta_records(data, json_by_end_pos)
    if resposta_records:
        named["RespostaPesquisaModel"] = resposta_records

    # FlatBuffers entity extraction — overrides/supplements blob-scan tables
    if schema is not None:
        # Ensure ALL entities from schema exist in 'named', even with 0 rows
        for entity in schema.get("entities", []):
            name = entity["name"]
            if name not in named:
                named[name] = []

        fb_entities = _scan_all_entities(data, schema)
        for entity_name, rows in fb_entities.items():
            if rows:
                named[entity_name] = rows

    tables: List[CustomTable] = [
        CustomTable(name, rows)
        for name, rows in sorted(named.items(), key=lambda x: -len(x[1]))
    ]

    return tables


def _guess_table_name(keys: List[str], rows: List[dict]) -> str:
    key_set = set(keys)

    # Unwrapped field-response records: {_field_uuid, campo_tipo, valor, ...}
    if "_field_uuid" in key_set and "campo_tipo" in key_set:
        types = {r.get("campo_tipo") for r in rows if r.get("campo_tipo")}
        if len(types) == 1:
            return f"respostas_{list(types)[0].lower()}"
        return "respostas_campos"

    # Typed envelope records — form field definitions share uuid+label
    if "_type" in key_set and "uuid" in key_set and "label" in key_set:
        return "form_field_definitions"
    if "_type" in key_set:
        types = {r.get("_type") for r in rows if r.get("_type")}
        if len(types) == 1:
            return list(types)[0]
        if types:
            return "mixed_types"

    if key_set == {"uuid"}:
        return "uuid_references"
    if key_set == {"uuid", "is_active"}:
        return "uuid_active_flags"

    if "REGIONAL" in key_set:
        return "survey_summary"
    if "uuid" in key_set and "titulo" in key_set:
        return "form_sections"
    if "uuid" in key_set and "label" in key_set:
        return "form_fields"
    if "uuid" in key_set and "nome" in key_set:
        return "products"
    if "uuid" in key_set and "name" in key_set:
        return "entities"

    # Fallback: first few keys
    preview = "_".join(k for k in keys[:3] if not k.startswith("_"))
    return preview or "table"


def execute_query(tables: List[CustomTable], sql: str) -> Tuple[List[Tuple], List[str]]:
    """Very basic SQL-like query execution using Python lists.

    Supports: SELECT * FROM <table>, SELECT col,... FROM <table> WHERE ...
    """
    import re

    sql_clean = sql.strip().rstrip(";")

    # Parse optional LIMIT / TOP
    limit_val: Optional[int] = None
    limit_m = re.search(r"\bLIMIT\s+(\d+)\b", sql_clean, re.IGNORECASE)
    if limit_m:
        limit_val = int(limit_m.group(1))
        sql_clean = sql_clean[: limit_m.start()].strip()
    top_m = re.match(r"SELECT\s+TOP\s+(\d+)\b", sql_clean, re.IGNORECASE)
    if top_m:
        limit_val = int(top_m.group(1))
        sql_clean = "SELECT " + sql_clean[top_m.end():].strip()

    # SELECT ... FROM <table>  (table may be wrapped in [], ``, or "")
    m = re.match(
        r"SELECT\s+(.+?)\s+FROM\s+(?:\[([^\]]+)\]|`([^`]+)`|\"([^\"]+)\"|(\w[\w\s]*))"
        r"(?:\s+WHERE\s+(.+))?$",
        sql_clean,
        re.IGNORECASE,
    )
    if not m:
        raise ValueError(f"Unsupported query: {sql!r}")

    select_clause = m.group(1).strip()
    table_name = (m.group(2) or m.group(3) or m.group(4) or m.group(5) or "").strip()
    where_clause = m.group(6)

    # Find table (case-insensitive)
    table = next(
        (t for t in tables if t.name.lower() == table_name.lower()), None
    )
    if table is None:
        available = [t.name for t in tables]
        raise ValueError(f"Table {table_name!r} not found. Available: {available}")

    rows = table.rows

    # WHERE: basic key=value support
    if where_clause:
        rows = _apply_where(rows, where_clause)

    # SELECT columns
    if select_clause.upper() == "COUNT(*)":
        return [(len(rows),)], ["COUNT(*)"]

    if select_clause.strip() == "*":
        cols = table.columns
    else:
        cols = [c.strip().strip("`[]\"'") for c in select_clause.split(",")]

    result_rows = []
    for row in rows:
        result_rows.append(tuple(_cell(row.get(c)) for c in cols))

    if limit_val is not None:
        result_rows = result_rows[:limit_val]

    return result_rows, cols


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _apply_where(rows: List[dict], clause: str) -> List[dict]:
    import re

    # Only support simple col = 'val' or col = val
    m = re.match(r"(\w+)\s*=\s*['\"]?([^'\"]+)['\"]?", clause.strip())
    if not m:
        return rows
    col, val = m.group(1), m.group(2).strip().lower()
    return [r for r in rows if str(r.get(col, "")).lower() == val]


def count_records(table: CustomTable) -> int:
    return table.row_count


class CustomConnection:
    """Adapter so the custom reader plugs into the same UI interface as MDBConnection."""

    def __init__(self, path: str, schema: Optional[dict] = None):
        self.path = path
        self._schema = schema
        self._tables: Optional[List[CustomTable]] = None
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._tables = read_tables(self.path, self._schema)
        self._open = True

    def close(self) -> None:
        self._open = False

    def tables(self) -> List[CustomTable]:
        return self._tables or []

    def execute(self, sql: str) -> Tuple[List[Tuple], List[str]]:
        if not self._open:
            raise RuntimeError("Connection is not open.")
        return execute_query(self._tables or [], sql)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()
        return False


class CustomSchemaReader:
    """Produces TableMeta / ColumnMeta objects from a CustomConnection."""

    def __init__(self, conn: CustomConnection):
        self._conn = conn

    def get_all_tables(self):
        from core.schema import ColumnMeta, TableMeta

        result = []
        for t in self._conn.tables():
            cols = [ColumnMeta(name=c, type_name="text", nullable=True) for c in t.columns]
            result.append(TableMeta(name=t.name, columns=cols, row_count=t.row_count))
        return result
