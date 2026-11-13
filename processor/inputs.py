"""
Find what is linked into the report under INPUT_DIR.

- Steps: every analysis app writes into one top folder named after it, holding provenance.json
  (with an `app` key) and summary.json (conventions.md); an app that ran more than once adds a
  LABEL level (`<app>/<label>/`). They are found by those files, recursively and following
  symlinks (INPUT_DIR entries are symlinks), wherever the ports put them: one folder per port
  (`spectral/eeg-spectral/...`), several links side by side, or everything merged at the root.
  eeg-prep's `qc` port is such a step (`qc/eeg-prep/summary.json`).
- eeg-prep's `eeg` port is a BIDS derivative: `dataset_description.json` and `recordings.csv` at
  its root, with eeg-prep's provenance.json next to them. It is read for the recordings table and
  the source datasets; its sub-*/ folders (the EDF files) are never descended into.
"""
from __future__ import annotations

import csv
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("eeg-report")

MAX_DEPTH = 8
SELF = "eeg-report"


@dataclass
class Step:
    app: str
    folder: Path              # the app's top folder (or its LABEL folder)
    rel: str                  # folder relative to INPUT_DIR, for messages
    provenance: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        """`<app>` or `<app>/<label>` when the app ran more than once (LABEL level)."""
        parts = Path(self.rel).parts
        if self.app in parts:
            i = len(parts) - 1 - list(reversed(parts)).index(self.app)
            rest = parts[i + 1:]
            if rest:
                return "/".join((self.app,) + rest)
        return self.app


@dataclass
class Derivative:
    folder: Path
    rel: str
    recordings: list[dict[str, str]]
    description: dict[str, Any]
    provenance: dict[str, Any]
    participants: list[dict[str, str]]


@dataclass
class Found:
    steps: list[Step]
    derivatives: list[Derivative]


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError) as exc:
        log.warning("cannot read %s: %s", path, exc)
        return None


def read_table(path: Path, delimiter: str | None = None) -> list[dict[str, str]]:
    """A CSV/TSV as a list of rows (empty on any error)."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            delim = delimiter or ("\t" if path.suffix.lower() == ".tsv" else ",")
            return [{(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
                    for row in csv.DictReader(fh, delimiter=delim)]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        log.warning("cannot read %s: %s", path, exc)
        return []


def _is_derivative(files: dict[str, Path], prov: dict[str, Any] | None) -> bool:
    if "recordings.csv" not in files:
        return False
    if "dataset_description.json" in files:
        return True
    return bool(prov and prov.get("app") == "eeg-prep" and "summary.json" not in files)


def find(input_dir: Path) -> Found:
    steps: list[Step] = []
    derivs: list[Derivative] = []
    seen: set[tuple[int, int]] = set()
    stack = [(input_dir, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            st = d.stat()
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            continue
        if (st.st_dev, st.st_ino) in seen:
            continue
        seen.add((st.st_dev, st.st_ino))
        files = {e.name: Path(e.path) for e in entries if _is_file(e)}
        rel = str(d.relative_to(input_dir)) if d != input_dir else "."
        prov = read_json(files["provenance.json"]) if "provenance.json" in files else None
        if _is_derivative(files, prov):
            derivs.append(Derivative(
                folder=d, rel=rel, recordings=read_table(files["recordings.csv"]),
                description=(read_json(files["dataset_description.json"]) or {}) if "dataset_description.json" in files else {},
                provenance=prov or {},
                participants=read_table(files["participants.tsv"]) if "participants.tsv" in files else []))
            # The subject folders hold the EDF files and are not read; other folders may be other
            # steps merged next to the derivative (everything linked at the root of INPUT_DIR).
            if depth < MAX_DEPTH:
                for e in reversed(entries):
                    if _is_dir(e) and not e.name.startswith((".", "sub-")) and e.name != "derivatives":
                        stack.append((Path(e.path), depth + 1))
            continue
        summ = read_json(files["summary.json"]) if "summary.json" in files else None
        app = (prov or {}).get("app") if isinstance((prov or {}).get("app"), str) else None
        if not app and summ and isinstance(summ.get("app"), str):
            app = summ["app"]
        if app:
            if app == SELF:
                continue  # a previous report linked back in
            step = Step(app=app, folder=d, rel=rel, provenance=prov or {}, summary=summ or {})
            if prov is None:
                step.problems.append("no provenance.json in the app's top folder")
            elif summ and isinstance(summ.get("app"), str) and summ["app"] != prov.get("app"):
                step.problems.append(f"provenance.json app is {prov.get('app')!r}, summary.json says {summ['app']!r}")
            if summ is None:
                step.problems.append("no summary.json in the app's top folder: no figures or headline numbers")
            if d.name != app and app not in Path(rel).parts:
                step.problems.append(f"top folder is named {d.name!r}, not after the app")
            steps.append(step)
            continue  # everything below belongs to this step
        if depth < MAX_DEPTH:
            for e in reversed(entries):
                if _is_dir(e) and not e.name.startswith("."):
                    stack.append((Path(e.path), depth + 1))
    steps.sort(key=lambda s: s.rel)
    derivs.sort(key=lambda x: x.rel)
    return Found(steps=steps, derivatives=derivs)


def _is_file(e: os.DirEntry) -> bool:
    try:
        return e.is_file()  # follows symlinks
    except OSError:
        return False


def _is_dir(e: os.DirEntry) -> bool:
    try:
        return e.is_dir()
    except OSError:
        return False
