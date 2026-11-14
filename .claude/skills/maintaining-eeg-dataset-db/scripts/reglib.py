"""Stage and save DB changes: datasets, child rows, evidence, sources.

Import it from a short registration script and run that script once with the system Python.
Nothing is written until save(); save() recomputes the derived columns and rewrites the CSVs
through tools/db.py.

    import sys
    sys.path.insert(0, "<skill dir>/scripts")
    from reglib import Batch

    B = Batch(today="2026-01-31")
    R = B.dataset("mydataset", name_source=None)     # new or existing row
    page = R.source("mydataset_page", "https://example.org/page", "distribution_page", "authors")
    R.link(page, "distribution")
    R.ev("name", "My Dataset", page, "title")
    R.child("acquisition_setups", "main")
    R.ev("acquisition_setups:main.sampling_rate_hz", "500", page, "Methods")
    R.add_row("channels", setup_id="main", channel_name="Fp1", channel_type="eeg", source_id=page)
    B.save()

Evidence fields are a datasets column, or <table>:<row id>.<column> for a child row.
"""

import sys
from pathlib import Path


def _find_root():
    for p in Path(__file__).resolve().parents:
        if (p / "tools" / "validate.py").is_file() and (p / "data" / "datasets.csv").is_file():
            return p
    raise SystemExit("reglib: could not find the DB root")


ROOT = _find_root()
sys.path.insert(0, str(ROOT / "tools"))
import csvio  # noqa: E402
import db as dbmod  # noqa: E402
import derive  # noqa: E402

STYPE = {"authors": "primary", "third_party": "secondary", "recipe_author": "implementation"}


class Batch:
    """Changes for any number of datasets, saved together."""

    def __init__(self, today):
        self.today = today
        self.db = dbmod.load()
        self.tables = csvio.tables()
        self.touched = set()
        self._ev_index = {}
        for e in self.db["evidence"][1]:
            self._ev_index.setdefault((e["dataset_id"], e["field"]), []).append(e)

    def dataset(self, dataset_id):
        return Reg(self, dataset_id)

    def source(self, source_id, url, kind, publisher, title="", doi="", describes_version="", note="",
               identity_basis="", archive_url=""):
        """Add a source (or return the existing one with the same id, or the same url and type)."""
        stype = STYPE[publisher]
        sh, sr = self.db["sources"]
        for r in sr:
            if r["source_id"] == source_id:
                if url and r["url"] != url:
                    raise SystemExit(f"source: {source_id} exists with another url {r['url']!r}")
                return source_id
            if url and r["url"] == url and r["source_type"] == stype:
                return r["source_id"]
        sr.append({**{k: "" for k in sh}, "source_id": source_id, "url": url, "doi": doi, "title": title,
                   "kind": kind, "publisher": publisher, "source_type": stype,
                   "describes_version": describes_version, "identity_basis": identity_basis,
                   "checked_on": self.today, "archive_url": archive_url, "note": note})
        return source_id

    def provider(self, provider_id, name, source_id, provider_type="", country="", url="", locator="", by="claude"):
        ph, pr = self.db["providers"]
        if any(r["provider_id"] == provider_id for r in pr):
            return provider_id
        pr.append({**{k: "" for k in ph}, "provider_id": provider_id, "name": name, "provider_type": provider_type,
                   "country": country, "url": url, "source_id": source_id, "locator": locator,
                   "checked_on": self.today, "checked_by": by})
        return provider_id

    def save(self):
        for d in self.db["datasets"][1]:
            if d["dataset_id"] in self.touched:
                d["last_updated_on"] = self.today
        derive.apply(self.db)
        dbmod.save(self.db)
        print(f"saved {len(self.touched)} dataset(s); now run tools/views.py and tools/validate.py")


class Reg:
    """Changes for one dataset_id within a Batch."""

    def __init__(self, batch, dataset_id):
        self.B = batch
        self.db = batch.db
        self.D = dataset_id
        self.today = batch.today
        self.row = dbmod.find(self.db, "datasets", (dataset_id,))
        if self.row is None:
            h, rows = self.db["datasets"]
            self.row = {c: "" for c in h}
            self.row["dataset_id"] = dataset_id
            rows.append(self.row)
        batch.touched.add(dataset_id)

    # sources ------------------------------------------------------------------------------

    def source(self, *a, **k):
        return self.B.source(*a, **k)

    def link(self, source_id, role):
        """Say that this source introduces the dataset (paper / distribution / mirror / catalogue / readme / other)."""
        lr = self.db["dataset_sources"][1]
        if not any(r["dataset_id"] == self.D and r["source_id"] == source_id and r["role"] == role for r in lr):
            lr.append({"dataset_id": self.D, "source_id": source_id, "role": role})

    def _linked(self, source_id):
        if not any(r["source_id"] == source_id for r in self.db["sources"][1]):
            raise SystemExit(f"no source {source_id!r}: add it with source() first")
        if not any(r["dataset_id"] == self.D and r["source_id"] == source_id for r in self.db["dataset_sources"][1]):
            self.link(source_id, "other")

    # child rows ---------------------------------------------------------------------------

    def child(self, table, row_id, **cells):
        """Create (or return) the child row <table>:<row_id> of a table with evidence columns."""
        keys = self.B.tables[table]["keys"]
        h, rows = self.db[table]
        for r in rows:
            if r["dataset_id"] == self.D and r[keys[1]] == row_id:
                r.update(cells)
                return r
        r = {c: "" for c in h}
        r.update({"dataset_id": self.D, keys[1]: row_id, **cells})
        rows.append(r)
        return r

    def add_row(self, table, by="claude", **cells):
        """A row of a table with a row-level source (channels, task_steps, annotations, ...)."""
        if "source_id" in cells and cells["source_id"]:
            self._linked(cells["source_id"])
        h, rows = self.db[table]
        r = {c: "" for c in h}
        r.update({"dataset_id": self.D, **cells})
        if "checked_on" in h:
            r["checked_on"] = r["checked_on"] or self.today
        if "checked_by" in h:
            r["checked_by"] = r["checked_by"] or by
        rows.append(r)
        return r

    # evidence -----------------------------------------------------------------------------

    def _cell_row(self, field):
        if ":" not in field:
            return self.row, field
        table, rest = field.split(":", 1)
        row_id, col = rest.rsplit(".", 1)
        keys = self.B.tables[table]["keys"]
        for r in self.db[table][1]:
            if r["dataset_id"] == self.D and r[keys[1]] == row_id:
                return r, col
        raise SystemExit(f"no row {table}:{row_id} for {self.D}: call child() first")

    def _rows(self, field):
        return self.B._ev_index.get((self.D, field), [])

    def _append(self, field, value, source_id, loc, by, note, status):
        n = max([int(e["evidence_id"].rsplit("/", 1)[1]) for e in self._rows(field)] or [0]) + 1
        eid = f"{self.D}/{field}/{n:02d}"
        h, rows = self.db["evidence"]
        e = {c: "" for c in h}
        e.update(evidence_id=eid, dataset_id=self.D, field=field, value=value, source_id=source_id,
                 locator=loc, checked_on=self.today, checked_by=by, status=status, note=note.strip())
        rows.append(e)
        self.B._ev_index.setdefault((self.D, field), []).append(e)
        return eid

    def ev(self, field, value, source_id, loc="", by="claude", note=""):
        """Add a current evidence row and set the cell. Current rows with another value are superseded."""
        self._linked(source_id)
        r, col = self._cell_row(field)
        if any(o["status"] == "conflicting" for o in self._rows(field)):
            raise SystemExit(f"ev: {field} is conflicting; use conflicting()")
        same = [o for o in self._rows(field) if o["status"] == "current" and o["value"] == value and o["source_id"] == source_id]
        if same:
            return same[0]["evidence_id"]
        eid = self._append(field, value, source_id, loc, by, note, "current")
        for o in self._rows(field):
            if o["status"] == "current" and o["value"] != value:
                o.update(status="superseded", note=((o["note"] + "; ") if o["note"] else "") + f"superseded by {eid}")
        r[col] = value
        return eid

    def conflicting(self, field, value, source_id, loc="", by="claude", note=""):
        """Add a source that disagrees with the others; the cell becomes conflicting."""
        self._linked(source_id)
        r, col = self._cell_row(field)
        for o in self._rows(field):
            if o["status"] == "current" and o["value"] != value:
                o["status"] = "conflicting"
        cur = [o for o in self._rows(field) if o["status"] == "current"]
        if cur and all(o["value"] == value for o in cur):
            return self.ev(field, value, source_id, loc, by, note)
        eid = self._append(field, value, source_id, loc, by, note, "conflicting")
        r[col] = "conflicting"
        return eid

    def set(self, **cells):
        """Cells that take no evidence row (notes, license_note, terms_note)."""
        unknown = [c for c in cells if c not in self.row]
        if unknown:
            raise SystemExit(f"set: no such datasets column(s): {unknown}")
        self.row.update(cells)

    def alias(self, alias, alias_type, source_id="", note=""):
        ar = self.db["aliases"][1]
        if not any(r["dataset_id"] == self.D and r["alias"] == alias for r in ar):
            ar.append({"dataset_id": self.D, "alias": alias, "alias_type": alias_type, "source_id": source_id, "note": note})

    def relation(self, relation, other_dataset_id, source_id="", note=""):
        self.db["relations"][1].append({"dataset_id": self.D, "relation": relation,
                                        "other_dataset_id": other_dataset_id, "source_id": source_id, "note": note})
