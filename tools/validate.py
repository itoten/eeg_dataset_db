"""Check the database for format, type, key and evidence consistency.

Usage: python3 tools/validate.py

Exit status is 1 when any error is found; warnings do not fail the run.
"""

import datetime
import re
import subprocess
import sys
import unicodedata

import csvio
import db as dbmod
import derive
import views

SLUG = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
TOKENS = {"unknown", "NA", "none", "conflicting"}
LIVE = ("current", "conflicting")
# Child tables whose rows are referenced by other tables: (table, referencing table, columns)
CHILD_REFS = [("acquisition_setups", "channels", ("setup_id",)),
              ("acquisition_setups", "tasks", ("setup_id",)),
              ("tasks", "task_steps", ("task_id",)),
              ("annotations", "label_counts", ("item", "name"))]
NOTE_COLS = {"datasets": ("notes", "license_note", "terms_note"), "participant_groups": ("other_traits",)}
RELEASE_KINDS = ("release_files", "repository_record", "count_report")

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def norm_name(s):
    # Accents are dropped, letters of any script are kept.
    s = unicodedata.normalize("NFKD", s.casefold())
    return re.sub(r"[\W_]", "", "".join(c for c in s if not unicodedata.combining(c)))


# ---- 1. file format -------------------------------------------------------


def check_format(tables, cols):
    for path in sorted(csvio.SCHEMA_DIR.glob("*.csv")):
        check_file_bytes(path, None)
    for name, info in tables.items():
        path = info["path"]
        if not path.is_file():
            err(f"{name}: missing file {path}")
            continue
        try:
            header, rows = csvio.read_rows(path)
        except ValueError as e:
            err(f"{name}: {e}")
            continue
        want = [c["column"] for c in cols[name]]
        if header != want:
            err(f"{name}: header {header} does not match schema/columns.csv {want}")
        check_file_bytes(path, info["keys"], header, rows)
        for i, row in enumerate(rows, 2):
            for c, v in row.items():
                if v != v.strip() or "\n" in v or "\r" in v:
                    err(f"{name} line {i} column {c}: leading/trailing space or newline")


def check_file_bytes(path, keys, header=None, rows=None):
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        err(f"{path.name}: has a BOM")
    if b"\r" in raw:
        err(f"{path.name}: has CR characters")
    if header is None:
        header, rows = csvio.read_rows(path)
    if csvio.format_rows(header, rows, keys).encode("utf-8") != raw:
        err(f"{path.name}: not in canonical form (run tools/db.py fmt)")


# ---- 2. types -------------------------------------------------------------


def check_value(v, ctype, enums):
    """Return an error string or None for a non-null cell."""
    if ctype in ("text", "path"):
        return None
    if ctype == "slug":
        return None if SLUG.match(v) else "not a slug"
    if ctype == "url":
        return None if re.match(r"^https?://\S+$", v) else "not an http(s) URL"
    if ctype == "date":
        try:
            datetime.date.fromisoformat(v)
            return None if re.match(r"^\d{4}-\d{2}-\d{2}$", v) else "not YYYY-MM-DD"
        except ValueError:
            return "not a date"
    if ctype == "int":
        return None if re.match(r"^\d+$", v) else "not an integer"
    if ctype == "float":
        return None if re.match(r"^\d+(\.\d+)?$", v) else "not a number"
    if ctype == "bool":
        return None if v in ("true", "false") else "not true/false"
    if ctype == "list" or ctype.startswith("enumlist:"):
        items = v.split(";")
        if any(not it or it != it.strip() for it in items):
            return "empty or padded list item"
        if ctype.startswith("enumlist:"):
            name = ctype.split(":", 1)[1]
            bad = [it for it in items if it not in enums[name]]
            if bad:
                return f"not in enum {name}: {bad}"
        return None
    if ctype.startswith("enum:"):
        name = ctype.split(":", 1)[1]
        return None if v in enums[name] else f"not in enum {name}"
    return f"unknown column type {ctype}"


def cell_error(v, ctype, nulls, enums):
    allowed = set(nulls.split(";")) if nulls != "-" else set()
    if v == "":
        return None if "empty" in allowed else "empty cell not allowed"
    if v in TOKENS and v in allowed:
        return None
    return check_value(v, ctype, enums)


def check_types(tables, cols, db, enums):
    for name in tables:
        for i, row in enumerate(db[name][1], 2):
            for c in cols[name]:
                msg = cell_error(row[c["column"]], c["type"], c["nulls"], enums)
                if msg:
                    err(f"{name} line {i} ({row[tables[name]['keys'][0]]}) {c['column']}={row[c['column']]!r}: {msg}")


# ---- 3. keys and foreign keys ---------------------------------------------


def dataset_tables(tables):
    return [t for t, info in tables.items() if info["keys"][0] == "dataset_id" and t != "datasets"]


def check_keys(tables, db):
    for name, info in tables.items():
        seen = set()
        for row in db[name][1]:
            k = tuple(row[c] for c in info["keys"])
            if k in seen:
                err(f"{name}: duplicate key {k}")
            seen.add(k)
    ds = {r["dataset_id"] for r in db["datasets"][1]}
    for t in dataset_tables(tables):
        for r in db[t][1]:
            if r["dataset_id"] not in ds:
                err(f"{t} {tuple(r[k] for k in tables[t]['keys'])}: unknown dataset_id")
    for r in db["evidence"][1]:
        m = re.match(r"^([^/]+)/([a-z_0-9.:]+)/(\d{2})$", r["evidence_id"])
        if not m or m.group(1) != r["dataset_id"] or m.group(2) != r["field"]:
            err(f"evidence {r['evidence_id']}: id does not match dataset_id/field/NN")
    for r in db["relations"][1]:
        if r["other_dataset_id"] not in ds:
            err(f"relations {r['dataset_id']}/{r['relation']}/{r['other_dataset_id']}: unknown other_dataset_id")
    for parent, child, cs in CHILD_REFS:
        have = {(r["dataset_id"],) + tuple(r[c] for c in cs) for r in db[parent][1]}
        for r in db[child][1]:
            k = (r["dataset_id"],) + tuple(r[c] for c in cs)
            if all(k[1:]) and k not in have:
                err(f"{child} {k}: no such row in {parent}")
    providers = {r["provider_id"] for r in db["providers"][1]}
    for d in db["datasets"][1]:
        if d["provider_ids"] in TOKENS or not d["provider_ids"]:
            continue
        for p in d["provider_ids"].split(";"):
            if p not in providers:
                err(f"datasets {d['dataset_id']}: provider_ids {p} is not in providers.csv")
    owners = {}
    names = [(r["dataset_id"], r["dataset_id"]) for r in db["datasets"][1]]
    names += [(r["dataset_id"], r["name"]) for r in db["datasets"][1]]
    names += [(r["dataset_id"], r["alias"]) for r in db["aliases"][1] if r["alias_type"] != "catalogue_id"]
    for d, n in names:
        owners.setdefault(norm_name(n), set()).add(d)
    for n, d in owners.items():
        if len(d) > 1:
            err(f"name {n!r} is shared by datasets {sorted(d)}; use relations distinct_from and distinct names")


# ---- 4. evidence ----------------------------------------------------------


def evidence_targets(tables, cols, db):
    """[(dataset_id, field, cell value)] for every cell of a column with evidence=yes."""
    out = []
    for t, info in tables.items():
        ev_cols = [c["column"] for c in cols[t] if c["evidence"] == "yes"]
        if not ev_cols:
            continue
        keys = info["keys"]
        for r in db[t][1]:
            for c in ev_cols:
                field = c if t == "datasets" else f"{t}:{r[keys[1]]}.{c}"
                out.append((r["dataset_id"], field, r[c]))
    return out


def check_evidence(tables, cols, db):
    targets = evidence_targets(tables, cols, db)
    fields = {(d, f) for d, f, _ in targets}
    sources = {r["source_id"]: r for r in db["sources"][1]}
    ev = {}
    untyped = set()
    for r in db["evidence"][1]:
        ev.setdefault((r["dataset_id"], r["field"]), []).append(r)
        eid, st = r["evidence_id"], r["status"]
        if (r["dataset_id"], r["field"]) not in fields:
            err(f"evidence {eid}: field {r['field']} is not a cell that takes evidence")
        if r["source_id"] and r["source_id"] not in sources:
            err(f"evidence {eid}: unknown source_id {r['source_id']}")
        s = sources.get(r["source_id"], {})
        if st in LIVE:
            if not r["source_id"]:
                err(f"evidence {eid}: a {st} row needs a source")
            elif not s.get("source_type"):
                untyped.add(r["source_id"])
            col = r["field"].rsplit(".", 1)[-1]
            if col.endswith("_release") and s and s["kind"] not in RELEASE_KINDS:
                err(f"evidence {eid}: *_release fields need a source of kind {'/'.join(RELEASE_KINDS)}")
            if col.endswith("_reported") and s.get("source_type") == "implementation":
                err(f"evidence {eid}: *_reported fields cannot use an implementation source")
    for d, field, v in targets:
        rows = [r for r in ev.get((d, field), []) if r["status"] in LIVE]
        if v in ("", "NA"):
            if rows and v == "":
                err(f"evidence {d}/{field}: live rows exist but the cell is empty")
            continue
        cur = [r for r in rows if r["status"] == "current"]
        con = [r for r in rows if r["status"] == "conflicting"]
        if not rows:
            err(f"evidence {d}/{field}: no current or conflicting row for {v!r}")
        elif con:
            if cur:
                err(f"evidence {d}/{field}: current and conflicting rows together")
            if len({r["value"] for r in con}) < 2:
                err(f"evidence {d}/{field}: conflicting rows need at least two different values")
            if v != "conflicting":
                err(f"evidence {d}/{field}: conflicting rows but the cell is {v!r}")
        else:
            vals = {r["value"] for r in cur}
            if len(vals) > 1:
                err(f"evidence {d}/{field}: current rows disagree {sorted(vals)}; make them conflicting or supersede one")
            if v not in vals:
                err(f"evidence {d}/{field}: current value {sorted(vals)} != cell value {v!r}")
    if untyped:
        warn(f"{len(untyped)} sources used by current evidence have no publisher and source_type")


def check_derived(db):
    exp = derive.expected(db)
    for d in db["datasets"][1]:
        for c, want in exp[d["dataset_id"]].items():
            if d[c] != want:
                err(f"datasets {d['dataset_id']} {c}: {d[c]!r} != {want!r} (run tools/derive.py)")


def check_human_checks(tables, db):
    """A person's check is recorded only through a merged verification pull request."""
    for t in tables:
        if "checked_by" not in db[t][0]:
            continue
        for r in db[t][1]:
            if r["checked_by"] == "user" and not re.search(r"pull request #\d+", r["note"]):
                err(f"{t} {r.get('evidence_id') or r['dataset_id']}: checked_by=user needs a note naming 'pull request #<number>'")


def check_note_tags(db):
    ids = {r["source_id"] for r in db["sources"][1]}
    for t, cs in NOTE_COLS.items():
        for d in db[t][1]:
            for c in cs:
                for sent in re.split(r"(?<=[.;])\s+(?=[A-Z0-9])", d[c]):
                    if not sent:
                        continue
                    tags = re.findall(r"\[([a-z0-9_]+)\]", sent)
                    if not tags:
                        err(f"{t} {d['dataset_id']} {c}: sentence without a [source_id] tag: {sent[:50]!r}")
                    for tag in tags:
                        if tag not in ids:
                            err(f"{t} {d['dataset_id']} {c}: tag [{tag}] is not a source")


# ---- 5. sources -----------------------------------------------------------


def check_sources(tables, db):
    sources = {}
    seen = {}
    for r in db["sources"][1]:
        sid = r["source_id"]
        sources[sid] = r
        t, p, k = r["source_type"], r["publisher"], r["kind"]
        for key in ((r["url"], t) if r["url"] else None, ("doi", r["doi"], t) if r["doi"] else None):
            if key is None:
                continue
            if key in seen:
                err(f"sources {sid}: same url/DOI and source_type as {seen[key]}")
            seen[key] = sid
        want = {"primary": "authors", "secondary": "third_party", "implementation": "db_maintainer"}.get(t)
        if t and p != want:
            err(f"sources {sid}: source_type {t} needs publisher {want}, not {p!r}")
        if (t == "implementation") != (k == "count_report"):
            err(f"sources {sid}: an implementation source is a count_report and vice versa")
        if k in ("mirror", "catalogue", "survey") and t not in ("secondary", ""):
            err(f"sources {sid}: a {k} is a secondary source")
        if (t == "") != (p == ""):
            err(f"sources {sid}: source_type and publisher are both set or both empty")
    unknown = sum(1 for r in sources.values() if not r["source_type"])
    if unknown:
        warn(f"{unknown} sources have no publisher and source_type yet (origin not checked)")
    for r in db["dataset_sources"][1]:
        if r["source_id"] not in sources:
            err(f"dataset_sources {r['dataset_id']}/{r['source_id']}: unknown source_id")
    for t in dataset_tables(tables):
        if t in ("dataset_sources", "evidence") or "source_id" not in db[t][0]:
            continue
        for r in db[t][1]:
            if r["source_id"] and r["source_id"] not in sources:
                err(f"{t} {tuple(r[k] for k in tables[t]['keys'])}: unknown source_id {r['source_id']}")


def check_traceability(tables, db):
    """Every dataset has a source with a URL, and every source a row cites is linked to its dataset."""
    srcs = {r["source_id"]: r for r in db["sources"][1]}
    linked = {}
    for r in db["dataset_sources"][1]:
        linked.setdefault(r["dataset_id"], set()).add(r["source_id"])
    for d in db["datasets"][1]:
        if not any(srcs.get(s, {}).get("url") for s in linked.get(d["dataset_id"], ())):
            err(f"datasets {d['dataset_id']}: no linked source with a URL; a dataset nobody can trace to a document does not belong in the DB")
    for t in dataset_tables(tables):
        if t == "dataset_sources" or "source_id" not in db[t][0]:
            continue
        for r in db[t][1]:
            if t == "evidence" and r["status"] not in LIVE:
                continue
            if r["source_id"] and r["source_id"] not in linked.get(r["dataset_id"], ()):
                err(f"{t} {tuple(r[k] for k in tables[t]['keys'])}: source {r['source_id']} is not linked to the dataset in dataset_sources.csv")


# ---- 6. repository --------------------------------------------------------


LOCAL_PATH = re.compile(r"(?<![\w.])(/home/\w+/|/Users/\w+/|/mnt/\w+|[~]/|[A-Za-z]:\\Users\\)")


def check_no_local_paths():
    """Written for a future public release: tracked files must not hold machine-specific paths."""
    files = subprocess.run(["git", "-C", str(csvio.ROOT), "ls-files"], capture_output=True,
                           text=True, check=True).stdout.split()
    for name in files:
        try:
            text = (csvio.ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = LOCAL_PATH.search(line)
            if m:
                err(f"{name}:{i}: machine-specific path {m.group(0)!r} (use an environment variable name or a relative path)")


def check_views(db):
    for path, text in views.build(db).items():
        f = csvio.ROOT / path
        if not f.exists() or f.read_bytes().decode("utf-8") != text:
            err(f"{path} is out of date: run python3 tools/views.py")


def main():
    tables = csvio.tables()
    cols = csvio.columns()
    enums = csvio.enums()
    check_format(tables, cols)
    if errors:
        report()
    db = dbmod.load()
    check_types(tables, cols, db, enums)
    check_keys(tables, db)
    check_evidence(tables, cols, db)
    check_sources(tables, db)
    check_derived(db)
    check_human_checks(tables, db)
    check_traceability(tables, db)
    check_note_tags(db)
    check_views(db)
    check_no_local_paths()
    report()


def report():
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
