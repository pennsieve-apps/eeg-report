"""
eeg-report: one report (HTML + PDF) of whatever scalp EEG steps are linked in, plus a tables folder.

Reads INPUT_DIR recursively: eeg-prep's derivative (recordings.csv, dataset_description.json),
eeg-prep's qc output and each analysis step's top folder (provenance.json + summary.json), in any
layout (one folder per port, side by side, or merged at the root). Writes

  OUTPUT_DIR/report/eeg-report/  index.html, report.pdf, figures/<step>/..., summary.json, provenance.json
  OUTPUT_DIR/tables/eeg-report/  recordings.csv, overview.csv, headline.csv, qc.csv, seizure_scores.csv,
                                 <step>/<every table the step wrote>, provenance.json

Exit codes: 0 ok, 1 nothing to report on (no step output and no recordings.csv) or the PDF could
not be written (everything else is written first), 2 bad parameters.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import resource
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("eeg-report")
APP = "eeg-report"
OWN_CITATIONS: list[str] = []  # the report adds no method of its own


class ParameterError(ValueError):
    pass


def version() -> str:
    for p in (Path(__file__).resolve().parent.parent / "VERSION", Path("/processor/VERSION")):
        if p.exists():
            return p.read_text().strip()
    return "0.0.0"


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v == "":
        return default
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    raise ParameterError(f"{name} must be true or false, got {v!r}")


def parameters() -> dict[str, Any]:
    raw = os.environ.get("MAX_FIGURES", "").strip() or "40"
    try:
        max_figures = int(raw)
    except ValueError:
        raise ParameterError(f"MAX_FIGURES must be an integer, got {raw!r}") from None
    if max_figures < 0:
        raise ParameterError("MAX_FIGURES must be >= 0")
    dois = os.environ.get("DATASET_DOIS", "").strip()
    from processor.citations import valid

    bad = [d for d in re.split(r"[\s,;]+", dois) if d and not valid(d)]
    if bad:
        raise ParameterError(f"DATASET_DOIS must be DOIs (10.<registrant>/<suffix>), got {', '.join(map(repr, bad))}")
    title = os.environ.get("REPORT_TITLE", "").strip()
    if len(title) > 200:
        raise ParameterError("REPORT_TITLE is longer than 200 characters")
    return {"REPORT_TITLE": title, "MAX_FIGURES": max_figures, "DATASET_DOIS": dois,
            "WRITE_PDF": _bool("WRITE_PDF", True)}


def _scratch() -> None:
    """HOME and TMPDIR may name folders that don't exist yet (Lambda): make them. Caches that must
    be written (fontconfig for the PDF) go under TMPDIR, never into the image or HOME."""
    for var in ("TMPDIR", "HOME"):
        d = os.environ.get(var)
        if d:
            try:
                Path(d).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
    tmp = Path(tempfile.gettempdir())
    os.environ.setdefault("XDG_CACHE_HOME", str(tmp / "cache"))
    Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)


def _peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1024 * 1024) if sys.platform == "darwin" else r / 1024, 1)


def _tool_versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as v

    out = {"python": sys.version.split()[0]}
    for pkg in ("jinja2", "weasyprint", "pillow", "pydyf"):
        try:
            out[pkg] = v(pkg)
        except PackageNotFoundError:
            pass
    return out


def _write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])


def _scalar(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def copy_figures(model: dict[str, Any], out: Path) -> None:
    from processor.render import image_size

    n = 0
    for sec in model["sections"]:
        for f in sec["figures"] + sec["omitted"]:
            dst = out / f["dest"]
            f["out_path"] = str(dst)
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f["src_path"], dst)
                size = image_size(dst)
            except OSError as exc:
                log.warning("cannot copy figure %s: %s", f["src_path"], exc)
                size = None
            f["ok"] = size is not None
            f["w"], f["h"] = size if size else (0, 0)
            if not f["ok"]:
                msg = f"figure {f['rel']} could not be read as an image"
                sec["warnings"].append(msg)
                model["issues"].append({"step": sec["label"], "problem": msg})
        for f in sec["figures"]:
            n += 1
            f["number"] = n


def write_tables(model: dict[str, Any], found: Any, out: Path) -> list[str]:
    from processor.model import resolve

    written: list[str] = []
    out.mkdir(parents=True, exist_ok=True)
    # recordings.csv: every derivative's rows, all columns.
    cols: list[str] = []
    rows: dict[str, dict[str, str]] = {}
    for d in found.derivatives:
        for r in d.recordings:
            for k in r:
                if k not in cols:
                    cols.append(k)
            if r.get("recording_id") and r["recording_id"] not in rows:
                rows[r["recording_id"]] = r
    if rows:
        _write_csv(out / "recordings.csv", cols, [[r.get(c, "") for c in cols] for r in rows.values()])
        written.append("recordings.csv")
    g = model["glance"]
    if g["rows"]:
        _write_csv(out / "overview.csv", ["recording_id"] + [f"{app}:{key}" for _, app, key, _ in g["cols"]],
                   [[r["recording_id"]] + r["raw"] for r in g["rows"]])
        written.append("overview.csv")
    long_rows = []
    for sec in model["sections"]:
        for rid, rec in sec["recs"].items():
            for k, v in rec.items():
                if _scalar(v) and v not in (None, "") and k != "recording_id":
                    long_rows.append([rid, sec["label"], k, v])
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        if _scalar(v2) and v2 not in (None, ""):
                            long_rows.append([rid, sec["label"], f"{k}.{k2}", v2])
    if long_rows:
        _write_csv(out / "headline.csv", ["recording_id", "step", "metric", "value"], long_rows)
        written.append("headline.csv")
    for sec in model["sections"]:
        if sec.get("qc") and sec["qc"]["rows"]:
            keys = ["recording_id", "duration", "montage", "channels", "bad_channels", "n_bad_channels", "ica",
                    "ica_classes", "ica_var", "bad_segment_pct", "seizures", "dropped"]
            _write_csv(out / "qc_summary.csv", keys, [[r.get(k) for k in keys] for r in sec["qc"]["rows"]])
            written.append("qc_summary.csv")
        if sec.get("scores"):
            _write_csv(out / "seizure_scores.csv" if "/" not in sec["label"] else
                       out / f"seizure_scores_{sec['label'].split('/', 1)[1].replace('/', '_')}.csv",
                       sec["scores"]["header"], sec["scores"]["rows"])
            written.append("seizure_scores.csv")
    # Copies of every table each step wrote, under <step label>/.
    for sec in model["sections"]:
        step = sec["step"]
        for t in sec["tables"]:
            for rel in t["files"]:
                src = resolve(step, rel)
                if src is None:
                    continue
                dst = out / sec["label"] / rel
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
                    written.append(f"{sec['label']}/{rel}")
                except OSError as exc:
                    log.warning("cannot copy table %s: %s", src, exc)
    return written


def run(input_dir: Path, output_dir: Path, params: dict[str, Any]) -> int:
    _scratch()
    from processor import model as M
    from processor import render
    from processor.inputs import find

    t0 = time.time()
    started = datetime.now(timezone.utc)
    found = find(input_dir)
    for d in found.derivatives:
        log.info("eeg-prep derivative %-40s recordings=%d", d.rel, len(d.recordings))
    for s in found.steps:
        log.info("step %-22s %-45s recordings=%d figures=%d", s.label, s.rel,
                 len(M.recordings_of(s)), len(s.summary.get("figures") or []))
    if not found.steps and not found.derivatives:
        log.error("nothing to report on under %s: no step output (<app>/provenance.json + summary.json) and no "
                  "eeg-prep recordings.csv", input_dir)
        return 1

    model = M.build(found, params, version())
    model["generated"] = started.strftime("%Y-%m-%d %H:%M UTC")
    rep = output_dir / "report" / APP
    tab = output_dir / "tables" / APP
    rep.mkdir(parents=True, exist_ok=True)
    copy_figures(model, rep)
    written = write_tables(model, found, tab)
    model["warnings_total"] = sum(len(s["warnings"]) for s in model["sections"])
    (rep / "index.html").write_text(render.html(model), encoding="utf-8")
    log.info("wrote index.html (%d sections, %d figures shown, %d recordings), %d tables",
             len(model["sections"]), sum(len(s["figures"]) for s in model["sections"]), len(model["recordings"]),
             len(written))

    pdf_error = ""
    if params["WRITE_PDF"]:
        try:
            t1 = time.time()
            render.write_pdf(model, rep / "report.pdf")
            log.info("wrote report.pdf (%.1f MB, %.0f s)", (rep / "report.pdf").stat().st_size / 1e6, time.time() - t1)
        except Exception as exc:  # noqa: BLE001
            pdf_error = f"{type(exc).__name__}: {exc}"[:500]
            log.exception("report.pdf could not be written: %s", pdf_error)
            (rep / "report.pdf").unlink(missing_ok=True)

    finished = datetime.now(timezone.utc)
    summary = {
        "app": APP, "version": version(),
        "recordings": {r["recording_id"]: {"steps": r["steps"]} for r in model["recordings"]},
        "steps": [s["label"] for s in model["sections"]],
        "workflows": model["workflows"],
        "n_figures": sum(len(s["figures"]) for s in model["sections"]),
        "n_references": len(model["references"]),
        "n_unknown_dois": sum(1 for r in model["references"] if not r["known"]),
        "figures": [],
        "tables": [],
        "tables_output": written,  # files written to the tables output (OUTPUT_DIR/tables/eeg-report/)
        "warnings": [f"{s['label']}: {w}" for s in model["sections"] for w in s["warnings"]]
        + ([f"eeg-report: report.pdf could not be written ({pdf_error})"] if pdf_error else []),
        "notice": "Research output, not a clinical interpretation: every number and detection is to be reviewed "
                  "by a clinician against the EEG.",
    }
    (rep / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    inputs = [str(Path(d.rel) / "recordings.csv") for d in found.derivatives] + \
             [str(Path(s.rel) / "provenance.json") for s in found.steps]
    provenance = {
        "app": APP, "version": version(), "variant": None, "tools": _tool_versions(), "parameters": params,
        "inputs": inputs,
        "started": started.isoformat().replace("+00:00", "Z"), "finished": finished.isoformat().replace("+00:00", "Z"),
        "wall_seconds": round(time.time() - t0, 2), "peak_rss_mb": _peak_rss_mb(),
        "threads": {"requested": 0, "used": 1, "why": "single-threaded: reads small JSON/CSV/PNG files"},
        "recordings": {r["recording_id"]: {"status": "ok", "seconds": 0.0, "montage": r["montage"]}
                       for r in model["recordings"]},
        "citations": OWN_CITATIONS, "licence_notice": None,
    }
    for folder in (rep, tab):
        (folder / "provenance.json").write_text(json.dumps(provenance, indent=1, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
    log.info("done: %d steps, %d recordings, %d references (%d DOI-only), %d warnings, %d input notes, %.1f s, "
             "peak %.0f MB", len(model["sections"]), len(model["recordings"]), len(model["references"]),
             summary["n_unknown_dois"], model["warnings_total"], len(model["issues"]), provenance["wall_seconds"],
             provenance["peak_rss_mb"])
    if pdf_error:
        log.error("failing the step: report.pdf could not be written (index.html and the tables are complete)")
        return 1
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    for noisy in ("weasyprint", "fontTools", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    input_dir = Path(os.environ.get("INPUT_DIR") or "/data/input")
    output_dir = Path(os.environ.get("OUTPUT_DIR") or "/data/output")
    try:
        params = parameters()
    except ParameterError as exc:
        log.error("bad parameter: %s", exc)
        return 2
    if not input_dir.is_dir():
        log.error("INPUT_DIR %s does not exist", input_dir)
        return 1
    log.info("eeg-report %s: INPUT_DIR=%s OUTPUT_DIR=%s %s", version(), input_dir, output_dir,
             " ".join(f"{k}={v!r}" for k, v in params.items()))
    return run(input_dir, output_dir, params)


if __name__ == "__main__":
    sys.exit(main())
