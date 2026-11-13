#!/usr/bin/env python3
"""
Build the report's bundled citation table, processor/references.json.

Two sources, in this order:

1. The CITATION.cff files of the sibling scalp EEG apps (eeg-prep, eeg-spectral, eeg-spikes,
   eeg-seizures, eeg-sleep, eeg-connectivity) and this repo's own. Each has been checked against
   Crossref / DataCite / PubMed by workflow-scalp-eeg/scripts/verify-citations.py, so their author
   lists, titles, journals and PMIDs are already-verified records.
2. Every other DOI the steps cite (the `citations` of each provenance.json under the demo outputs,
   `--data`, plus scripts/extra_dois.txt): fetched from the registry itself (Crossref, or DataCite
   for Zenodo / PhysioNet / OpenNeuro / figshare DOIs) and, for articles, its PMID from PubMed.
   Every field is copied from the registry response; nothing is typed by hand.

The report resolves each step's provenance `citations` against this table; a DOI that is not in
it is shown DOI-only with a note, never filled in at run time (the app has no network).

Run it whenever a sibling's CITATION.cff or citations change, then commit the result:

    python scripts/build_citations.py                       # siblings next to this repo
    python scripts/build_citations.py --root ~/code/pennsieve --data ../workflow-scalp-eeg/data/work

Needs: pyyaml. Network for step 2 (results cached in $TMPDIR/eeg-report-citations).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent.parent
SIBLINGS = ["eeg-prep", "eeg-spectral", "eeg-spikes", "eeg-seizures", "eeg-sleep", "eeg-connectivity"]
OUT = HERE / "processor" / "references.json"
EXTRA = HERE / "scripts" / "extra_dois.txt"
UA = "pennsieve-eeg-report-citations/1.0 (mailto:support@pennsieve.io)"
CACHE = Path(os.environ.get("TMPDIR", "/tmp")) / "eeg-report-citations"
DATACITE_PREFIXES = ("10.5281/", "10.13026/", "10.18112/", "10.6084/", "10.48550/", "10.26275/", "10.48324/")


# ----------------------------------------------------------------------------- CITATION.cff

def _authors(ref: dict) -> list[dict]:
    out = []
    for a in ref.get("authors") or []:
        if a.get("name"):
            out.append({"name": str(a["name"])})
        else:
            out.append({k: str(v) for k, v in (("family", a.get("family-names")), ("given", a.get("given-names")),
                                               ("particle", a.get("name-particle"))) if v})
    return out


def _pmid(ref: dict) -> str:
    for ident in ref.get("identifiers") or []:
        desc = str(ident.get("description", "")).lower()
        val = str(ident.get("value", ""))
        if ident.get("type") == "other" and val.isdigit() and ("pubmed" in desc or "pmid" in desc or not desc):
            return val
    return ""


def _record(ref: dict) -> dict:
    journal = ref.get("journal") or (ref.get("conference") or {}).get("name") or ""
    publisher = ref.get("publisher")
    if isinstance(publisher, dict):
        publisher = publisher.get("name")
    start, end = ref.get("start"), ref.get("end")
    pages = f"{start}-{end}" if start and end else str(start or "")
    return {
        "doi": str(ref.get("doi") or ""),
        "type": ref.get("type") or "generic",
        "title": str(ref.get("title") or "").strip(),
        "authors": _authors(ref),
        "journal": str(journal or ""),
        "publisher": str(publisher or ""),
        "year": ref.get("year") or (str(ref.get("date-released") or "")[:4] or None),
        "volume": str(ref.get("volume") or ""),
        "issue": str(ref.get("issue") or ""),
        "pages": pages,
        "pmid": _pmid(ref),
        "url": str(ref.get("url") or ""),
        "repository": str(ref.get("repository-code") or ""),
        "source": "CITATION.cff",
    }


def _score(r: dict) -> int:
    return sum(1 for k in ("journal", "volume", "pages", "pmid", "year", "issue") if r.get(k)) + len(r["authors"])


# ----------------------------------------------------------------------------- registries

def _get(url: str) -> dict | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    if key.exists():
        return json.loads(key.read_text())
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            key.write_text(json.dumps(data))
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            time.sleep(2 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(2 * (attempt + 1))
    return None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def _pubmed(doi: str) -> str:
    q = urllib.parse.quote(f"{doi}[doi]")
    got = _get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={q}&retmode=json")
    ids = ((got or {}).get("esearchresult") or {}).get("idlist") or []
    if len(ids) != 1:
        return ""
    summ = _get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids[0]}&retmode=json")
    rec = ((summ or {}).get("result") or {}).get(ids[0]) or {}
    for aid in rec.get("articleids") or []:
        if aid.get("idtype") == "doi" and aid.get("value", "").lower() == doi.lower():
            return ids[0]
    return ""


def crossref(doi: str) -> dict | None:
    got = _get("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/:;()._-"))
    m = (got or {}).get("message")
    if not m:
        return None
    authors = []
    for a in m.get("author") or []:
        if a.get("family"):
            authors.append({k: _clean(v) for k, v in (("family", a.get("family")), ("given", a.get("given"))) if v})
        elif a.get("name"):
            authors.append({"name": _clean(a["name"])})
    year = None
    for k in ("published-print", "published-online", "issued", "published"):
        parts = ((m.get(k) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            year = int(parts[0])
            break
    kind = {"journal-article": "article", "proceedings-article": "conference-paper", "posted-content": "article",
            "book-chapter": "book-chapter", "dataset": "data"}.get(m.get("type"), "article")
    return {"doi": m.get("DOI") or doi, "type": kind, "title": _clean((m.get("title") or [""])[0]),
            "authors": authors, "journal": _clean((m.get("container-title") or [""])[0]),
            "publisher": _clean(m.get("publisher") or ""), "year": year, "volume": str(m.get("volume") or ""),
            "issue": str(m.get("issue") or ""), "pages": str(m.get("page") or m.get("article-number") or ""),
            "pmid": _pubmed(doi), "url": "", "repository": "", "source": "Crossref"}


def datacite(doi: str) -> dict | None:
    got = _get("https://api.datacite.org/dois/" + urllib.parse.quote(doi, safe=""))
    a = ((got or {}).get("data") or {}).get("attributes")
    if not a:
        return None
    authors = []
    for c in a.get("creators") or []:
        if c.get("familyName"):
            authors.append({k: _clean(v) for k, v in (("family", c.get("familyName")), ("given", c.get("givenName"))) if v})
        elif c.get("name"):
            authors.append({"name": _clean(c["name"])})
    rtype = ((a.get("types") or {}).get("resourceTypeGeneral") or "").lower()
    kind = {"dataset": "data", "software": "software"}.get(rtype, "article" if rtype in ("text", "preprint") else "data")
    pub = a.get("publisher")
    if isinstance(pub, dict):
        pub = pub.get("name")
    return {"doi": a.get("doi") or doi, "type": kind, "title": _clean((a.get("titles") or [{}])[0].get("title", "")),
            "authors": authors, "journal": "", "publisher": _clean(pub or ""),
            "year": a.get("publicationYear"), "volume": "", "issue": "", "pages": "", "pmid": "", "url": "",
            "repository": "", "source": "DataCite"}


def fetch(doi: str) -> dict | None:
    first, second = (datacite, crossref) if doi.lower().startswith(DATACITE_PREFIXES) else (crossref, datacite)
    return first(doi) or second(doi)


# ----------------------------------------------------------------------------- main

def cited_dois(data: Path | None) -> list[str]:
    out: list[str] = []
    if EXTRA.exists():
        for line in EXTRA.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out.append(line)
    if data and data.is_dir():
        for p in sorted(data.rglob("provenance.json")):
            try:
                prov = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            cites = prov.get("citations") if isinstance(prov, dict) else None
            if isinstance(cites, list):
                out.extend(str(c) for c in cites if isinstance(c, str))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=HERE.parent, help="folder holding the sibling repos")
    ap.add_argument("--data", type=Path, default=HERE.parent / "workflow-scalp-eeg" / "data" / "work",
                    help="demo outputs whose provenance.json citations are fetched too")
    args = ap.parse_args()

    by_doi: dict[str, dict] = {}
    software: dict[str, list[dict]] = {}
    apps: dict[str, dict] = {}
    problems: list[str] = []
    sources = [(name, args.root / name / "CITATION.cff") for name in SIBLINGS] + [("eeg-report", HERE / "CITATION.cff")]
    for app, path in sources:
        if not path.exists():
            problems.append(f"{app}: no CITATION.cff at {path}")
            continue
        cff = yaml.safe_load(path.read_text(encoding="utf-8"))
        apps[app] = {"title": cff.get("title") or app, "repository": cff.get("repository-code") or "",
                     "license": cff.get("license") or ""}
        for ref in cff.get("references") or []:
            rec = _record(ref)
            doi = rec["doi"].lower()
            if doi:
                old = by_doi.get(doi)
                if old is None:
                    rec["cited_by"] = [app]
                    by_doi[doi] = rec
                else:
                    old["cited_by"].append(app)
                    if old["title"].lower().rstrip(".") != rec["title"].lower().rstrip("."):
                        problems.append(f"{doi}: title differs between {old['cited_by'][0]} and {app}")
                    if _score(rec) > _score(old):
                        rec["cited_by"] = old["cited_by"]
                        by_doi[doi] = rec
            if rec["type"] == "software":
                entry = {"title": rec["title"], "url": rec["repository"] or rec["url"] or
                         (f"https://doi.org/{rec['doi']}" if rec["doi"] else ""), "doi": rec["doi"]}
                if entry not in software.setdefault(app, []):
                    software[app].append(entry)

    fetched, failed = 0, []
    for doi in dict.fromkeys(d.strip().lower().removeprefix("https://doi.org/").removeprefix("doi:") for d in cited_dois(args.data)):
        if not doi or doi in by_doi:
            continue
        rec = fetch(doi)
        if rec is None or not rec["title"]:
            failed.append(doi)
            continue
        rec["cited_by"] = ["registry"]
        by_doi[doi] = rec
        fetched += 1

    table = {"_about": "Built by scripts/build_citations.py from the sibling apps' verified CITATION.cff files, "
                       "and from Crossref/DataCite/PubMed for the other DOIs the steps cite. Do not edit by hand.",
             "apps": apps, "software": software,
             "references": dict(sorted(by_doi.items()))}
    OUT.write_text(json.dumps(table, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE)}: {len(by_doi)} DOIs ({fetched} fetched from the registries) "
          f"from {len(apps)} CITATION.cff files")
    for p in problems:
        print("WARNING:", p, file=sys.stderr)
    for d in failed:
        print("WARNING: not found in Crossref or DataCite (left out, shown DOI-only):", d, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
