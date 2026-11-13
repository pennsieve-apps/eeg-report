"""
The report as data. Every section of the HTML page and the PDF is built from this model, and
the tables folder is written from it. Nothing here recomputes a result: numbers, captions and
warnings are copied from each step's summary.json, provenance.json and tables; the only text the
report adds is its built-in description of each known app and the research-output labels.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from processor import apps as A
from processor import citations as C
from processor.inputs import Derivative, Found, Step, read_table

SUMMARY_KEYS = {"app", "version", "recordings", "figures", "tables", "warnings"}
NOTICE_KEYS = ("notice", "note")
WARN_VISIBLE = 8
GENERIC_COLS = 12
STAGES = ["W", "N1", "N2", "N3", "R", "REM", "NREM"]
LATERAL_COLS = ("lateralisation", "lateralization", "laterality", "side", "seizure_side")
OK_STATUS = {"ok", "success", "done", "warn", "warning"}
TABLE_SUFFIXES = (".csv", ".tsv")


# ----------------------------------------------------------------------------- formatting

def num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else float(v)
    if isinstance(v, str) and re.fullmatch(r"\s*-?\d+(\.\d+)?([eE][-+]?\d+)?\s*", v):
        return float(v)
    return None


def duration(s: Any) -> str:
    x = num(s)
    if x is None:
        return "–"
    if x < 90:
        return f"{x:.0f} s"
    if x < 5400:
        return f"{x / 60:.1f} min"
    return f"{x / 3600:.1f} h"


def fmt(v: Any, kind: str = "num") -> str:
    """A value as a person reads it: integers exactly, rates to two decimals, other numbers to four
    significant digits, 0-1 fractions as percentages (kind pct), durations (kind dur)."""
    if v is None or v == "":
        return "–"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if kind == "dur":
        return duration(v)
    x = num(v)
    if kind == "text" or x is None:
        if isinstance(v, (list, tuple)):
            return ", ".join(fmt(i, "text") for i in v) if len(v) <= 8 else f"{len(v)} values"
        if isinstance(v, dict):
            return "; ".join(f"{k}: {fmt(val)}" for k, val in v.items())
        if isinstance(v, float):
            return "–"
        return str(v)
    if kind == "pct":
        return f"{x * 100:.0f} %" if abs(x * 100 - round(x * 100)) < 0.05 else f"{x * 100:.1f} %"
    if kind == "int" or (x.is_integer() and not isinstance(v, float) and abs(x) < 1e15):
        return f"{int(round(x)):,}"
    ax = abs(x)
    if ax == 0:
        return "0"
    if kind == "rate":
        return f"{x:,.2f}"
    if ax >= 1000:
        return f"{x:,.0f}"
    if ax >= 0.001:
        return f"{x:.4g}"
    return f"{x:.2e}"


def humanise(key: str) -> str:
    k = key.replace("_", " ").strip()
    return k[:1].upper() + k[1:]


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "step"


LINK = re.compile(r"(https?://[^\s<>\"'\]\[]+)|((?:doi:\s*)?10\.\d{4,9}/[^\s<>\"'\]\[,;]+)", re.I)


def safe_url(url: str) -> str:
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc or re.search(r"[\s<>\"'\\]", url):
        return ""
    return url


def linkify(text: str) -> list[dict[str, str]]:
    """Text split into segments; http(s) URLs and DOIs become links (DOIs to doi.org)."""
    out: list[dict[str, str]] = []
    pos = 0
    for m in LINK.finditer(text):
        token = m.group(0).rstrip(".,;:)")
        url = safe_url(token) if m.group(1) else C.doi_url(re.sub(r"^doi:\s*", "", token, flags=re.I))
        if not url:
            continue
        if m.start() > pos:
            out.append({"text": text[pos:m.start()], "url": ""})
        out.append({"text": token, "url": url})
        pos = m.start() + len(token)
    if pos < len(text):
        out.append({"text": text[pos:], "url": ""})
    return out


def as_list(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v] if v.strip() else []
    return [str(x) for x in v if isinstance(x, (str, int, float)) and str(x).strip()] if isinstance(v, list) else []


# ----------------------------------------------------------------------------- reading a step

def resolve(step: Step, rel: str) -> Path | None:
    """A path from summary.json: relative to the app's top folder (the contract), or to the port
    folder above it (`<app>/...`). Never absolute, never outside the step's folder."""
    p = PurePosixPath(str(rel).replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts:
        return None
    cand = step.folder.joinpath(*p.parts)
    if cand.is_file():
        return cand
    if len(p.parts) > 1 and p.parts[0] in (step.folder.name, step.app):
        cand = step.folder.joinpath(*p.parts[1:])
        if cand.is_file():
            return cand
    return None


def recordings_of(step: Step) -> dict[str, dict[str, Any]]:
    raw = step.summary.get("recordings")
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    if isinstance(raw, list):  # tolerated: a list of {recording_id, ...}
        return {str(r["recording_id"]): r for r in raw if isinstance(r, dict) and r.get("recording_id")}
    return {}


def find_file(step: Step, name: str) -> Path | None:
    """A table by file name anywhere under the step's folder (conventions: find by name)."""
    try:
        for p in sorted(step.folder.rglob(name)):
            if p.is_file():
                return p
    except OSError:
        pass
    return None


def step_tables(step: Step) -> list[Path]:
    out = []
    try:
        for p in sorted(step.folder.rglob("*")):
            if p.suffix.lower() in TABLE_SUFFIXES and p.is_file():
                out.append(p)
    except OSError:
        pass
    return out


# ----------------------------------------------------------------------------- recordings

STANDARD_REC = ["recording_id", "subject", "session", "task", "run", "path", "sfreq", "n_channels", "n_good",
                "duration_s", "montage", "reference", "kind", "start_time", "n_seizures", "source_format", "age", "sex"]


def recordings_table(derivs: list[Derivative], steps: list[Step]) -> tuple[list[dict[str, str]], list[str]]:
    """recordings.csv rows of every linked derivative (first wins per id), then ids that only the
    steps know; and the extra recording-level columns (labels.csv's, e.g. lateralisation)."""
    rows: dict[str, dict[str, str]] = {}
    extra: list[str] = []
    for d in derivs:
        for r in d.recordings:
            rid = r.get("recording_id")
            if rid and rid not in rows:
                rows[rid] = dict(r)
                for k in r:
                    if k not in STANDARD_REC and k not in extra:
                        extra.append(k)
    for s in steps:
        for rid, rec in recordings_of(s).items():
            if rid not in rows:
                rows[rid] = {"recording_id": rid, "montage": str(rec.get("montage") or ""),
                             "_from_steps": "1"}
    return list(rows.values()), extra


def lateral_of(row: dict[str, str]) -> str:
    for c in LATERAL_COLS:
        if row.get(c):
            return row[c]
    return ""


# ----------------------------------------------------------------------------- QC (eeg-prep)

def _ica_classes(labels: list[str]) -> str:
    c = Counter(labels)
    return ", ".join(f"{k} {n}" if n > 1 else k for k, n in c.most_common()) if c else ""


def qc_rows(qc_steps: list[Step], derivs: list[Derivative], rec_rows: dict[str, dict[str, str]]) -> tuple[list[dict], dict]:
    """One QC row per recording, from eeg-prep's qc summary.json + qc.csv, else from the
    derivative's provenance.json. Returns (rows, totals)."""
    per: dict[str, dict[str, Any]] = {}
    for s in qc_steps:
        for rid, r in recordings_of(s).items():
            per.setdefault(rid, {}).update({k: v for k, v in r.items()})
        qcp = find_file(s, "qc.csv")
        if qcp:
            for row in read_table(qcp):
                rid = row.get("recording_id", "")
                if not rid:
                    continue
                d = per.setdefault(rid, {})
                item, status = row.get("item", ""), row.get("status", "")
                if item == "channel" and status == "bad":
                    d.setdefault("_bad", []).append(row.get("name", ""))
                elif item in ("channel", "dropped") and status in ("dropped", "removed", "excluded"):
                    d.setdefault("_dropped", []).append(row.get("name", ""))
                elif item in ("ica_component", "component") and status == "removed":
                    d.setdefault("_ica", []).append(row.get("iclabel_label") or row.get("reason") or "artifact")
    for dv in derivs:
        prov_recs = dv.provenance.get("recordings") if isinstance(dv.provenance.get("recordings"), dict) else {}
        for rid, p in prov_recs.items():
            if not isinstance(p, dict) or p.get("status") not in (None, "ok"):
                continue
            d = per.setdefault(rid, {})
            if "_bad" not in d and isinstance(p.get("bad_channels"), list):
                d["_bad"] = [str(x) for x in p["bad_channels"]]
            ica = p.get("ica") if isinstance(p.get("ica"), dict) else None
            if ica and "_ica" not in d and isinstance(ica.get("removed"), list):
                d["_ica"] = [re.sub(r"^IC\d+\s+", "", str(x)) for x in ica["removed"]]
                d.setdefault("n_ica_components", ica.get("components"))
                if ica.get("variance_removed_fraction") is not None and "ica_variance_removed_pct" not in d:
                    vf = num(ica.get("variance_removed_fraction"))
                    d["ica_variance_removed_pct"] = round(vf * 100, 1) if vf is not None else None
            if "bad_segment_pct" not in d and num(p.get("bad_segment_seconds")) is not None:
                dur = num(rec_rows.get(rid, {}).get("duration_s"))
                if dur:
                    d["bad_segment_pct"] = round(100 * num(p["bad_segment_seconds"]) / dur, 2)
            if "_dropped" not in d and isinstance(p.get("dropped"), dict):
                d["_dropped"] = list(p["dropped"].keys())
    rows = []
    all_ica: list[str] = []
    bad_pcts = []
    for rid in list(rec_rows) + [r for r in per if r not in rec_rows]:
        if rid not in per:
            continue
        d, rr = per[rid], rec_rows.get(rid, {})
        bad = [b for b in d.get("_bad", []) if b]
        ica = d.get("_ica", [])
        all_ica += ica
        n_ch = d.get("n_channels", rr.get("n_channels"))
        n_good = d.get("n_good", rr.get("n_good"))
        n_rem = d.get("n_ica_removed", len(ica) if "_ica" in d else None)
        bp = num(d.get("bad_segment_pct"))
        if bp is not None:
            bad_pcts.append(bp)
        rows.append({
            "recording_id": rid,
            "duration": fmt(d.get("duration_s", rr.get("duration_s")), "dur"),
            "montage": str(d.get("montage") or rr.get("montage") or "–"),
            "channels": f"{fmt(n_good, 'int')} of {fmt(n_ch, 'int')}" if n_ch not in (None, "") else "–",
            "bad_channels": ", ".join(bad) if bad else ("none" if ("_bad" in d or d.get("n_bad_channels") == 0) else "–"),
            "n_bad_channels": d.get("n_bad_channels", len(bad) if "_bad" in d else None),
            "ica": (f"{fmt(n_rem, 'int')} of {fmt(d.get('n_ica_components'), 'int')}"
                    if n_rem is not None and d.get("n_ica_components") not in (None, "") else fmt(n_rem, "int")),
            "ica_classes": _ica_classes(ica),
            "ica_var": fmt(d.get("ica_variance_removed_pct")),
            "bad_pct": fmt(bp),
            "bad_segment_pct": bp,
            "seizures": fmt(d.get("n_seizures", rr.get("n_seizures")), "int"),
            "dropped": ", ".join(x for x in d.get("_dropped", []) if x),
        })
    totals = {
        "n": len(rows),
        "with_bad": sum(1 for r in rows if num(r["n_bad_channels"]) not in (None, 0.0)),
        "bad_channels": sum(int(num(r["n_bad_channels"]) or 0) for r in rows),
        "ica_total": len(all_ica),
        "ica_classes": _ica_classes(all_ica),
        "bad_pct_median": fmt(sorted(bad_pcts)[len(bad_pcts) // 2] if bad_pcts else None),
        "bad_pct_max": fmt(max(bad_pcts) if bad_pcts else None),
        "has_dropped": any(r["dropped"] for r in rows),
    }
    return rows, totals


# ----------------------------------------------------------------------------- per-step pieces

def headline(app: str, recs: dict[str, dict[str, Any]], rec_rows: dict[str, dict[str, str]],
             order: list[str]) -> dict[str, Any] | None:
    spec = A.APPS.get(app, {}).get("headline") or []
    cols = []
    for label, key, kind in spec:
        if key.startswith("@"):
            if any(lateral_of(rec_rows.get(rid, {})) for rid in recs):
                cols.append((label, key, kind))
        elif any(r.get(key) is not None for r in recs.values()):
            cols.append((label, key, kind))
    if not [c for c in cols if c[2] != "text" and not c[1].startswith("@")]:
        cols = generic_cols(recs)
    if not cols or not recs:
        return None
    rows = []
    for rid in order:
        if rid not in recs:
            continue
        r = recs[rid]
        cells = []
        for _, key, kind in cols:
            v = lateral_of(rec_rows.get(rid, {})) if key.startswith("@") else r.get(key)
            cells.append(fmt(v, kind))
        rows.append([rid] + cells)
    return {"header": ["Recording"] + [c[0] for c in cols], "kinds": ["text"] + [c[2] for c in cols], "rows": rows}


def generic_cols(recs: dict[str, dict[str, Any]]) -> list[tuple[str, str, str]]:
    keys: list[str] = []
    for r in recs.values():
        for k, v in r.items():
            if k in keys or k in ("status", "seconds", "warnings", "recording_id"):
                continue
            if isinstance(v, bool) or num(v) is not None and not isinstance(v, str):
                keys.append(k)
    out = [(humanise(k), k, "num") for k in keys[:GENERIC_COLS]]
    if any(isinstance(r.get("montage"), str) for r in recs.values()):
        out.insert(0, ("Montage", "montage", "text"))
    return out


def stage_table(recs: dict[str, dict[str, Any]], key: str, order: list[str]) -> dict[str, Any] | None:
    stages: list[str] = []
    for r in recs.values():
        v = r.get(key)
        if isinstance(v, dict):
            for s in v:
                if s not in stages:
                    stages.append(s)
    if not stages:
        return None
    stages.sort(key=lambda s: STAGES.index(s) if s in STAGES else 99)
    rows = [[rid] + [fmt((recs[rid].get(key) or {}).get(s), "rate") for s in stages]
            for rid in order if rid in recs and isinstance(recs[rid].get(key), dict)]
    return {"name": "Spike events per minute by sleep stage",
            "note": "W wake, N1-N3 non-REM stages, R REM; from the linked hypnogram (eeg-sleep) or annotated sleep. "
                    "Spiking usually increases in deep non-REM sleep (Malow et al. 1998). " + A.RESEARCH,
            "header": ["Recording"] + stages, "kinds": ["text"] + ["rate"] * len(stages), "rows": rows}


CONN_KEY = re.compile(r"^([a-z0-9]+)_([a-z0-9-]+)_(mean|asymmetry|small_worldness)$")


def connectivity_tables(recs: dict[str, dict[str, Any]], order: list[str]) -> list[dict[str, Any]]:
    spec = A.APPS["eeg-connectivity"]
    found: dict[str, dict[str, list[str]]] = {}
    for r in recs.values():
        for k in r:
            m = CONN_KEY.match(k)
            if m:
                bands = found.setdefault(m.group(1), {}).setdefault(m.group(3), [])
                if m.group(2) not in bands:
                    bands.append(m.group(2))
    measures = sorted(found, key=lambda m: spec["measures"].index(m) if m in spec["measures"] else 99)
    out = []
    for i, m in enumerate(measures):
        name = spec["measure_names"].get(m, m)
        for stat in (("asymmetry", "mean") if i == 0 else ("asymmetry",)):
            bands = found[m].get(stat) or []
            if not bands:
                continue
            rows = [[rid] + [fmt(recs[rid].get(f"{m}_{b}_{stat}")) for b in bands] for rid in order if rid in recs]
            note = ("(left − right) / (left + right) of the mean connectivity within each hemisphere; positive = more "
                    "connectivity within the left hemisphere. Not validated for lateralisation." if stat == "asymmetry"
                    else "Mean connectivity over all channel pairs, per band.")
            out.append({"name": f"{'Hemispheric asymmetry' if stat == 'asymmetry' else 'Mean connectivity'} ({name})",
                        "note": note + " " + A.RESEARCH, "header": ["Recording"] + bands,
                        "kinds": ["text"] + ["num"] * len(bands), "rows": rows})
    return out


POOLED_ROWS = [("event", "pooled", "Event-based, pooled over all recordings"),
               ("event", "subject_mean", "Event-based, mean over subjects"),
               ("sample", "pooled", "Sample-based (per second), pooled"),
               ("sample", "subject_mean", "Sample-based (per second), mean over subjects")]


def seizure_scores(step: Step) -> dict[str, Any] | None:
    """Sensitivity, precision, F1 and false detections per day side by side, from summary.json
    `pooled`, else from scores.csv's pooled rows."""
    pooled = step.summary.get("pooled")
    data: dict[tuple[str, str], dict[str, Any]] = {}
    if isinstance(pooled, dict):
        for scope, aggs in pooled.items():
            if isinstance(aggs, dict):
                for agg, vals in aggs.items():
                    if isinstance(vals, dict):
                        data[(scope, agg)] = vals
    if not data:
        p = find_file(step, "scores.csv")
        for row in read_table(p) if p else []:
            if row.get("recording_id") == "pooled" and row.get("scope") and row.get("metric"):
                data.setdefault((row["scope"], "pooled"), {})[row["metric"]] = row.get("value")
    if not data:
        return None
    rows = []
    for scope, agg, label in POOLED_ROWS + [(s, a, f"{s} {a}") for (s, a) in data if (s, a, f"{s} {a}") not in
                                           [(x, y, f"{x} {y}") for x, y, _ in POOLED_ROWS]]:
        v = data.get((scope, agg))
        if not v:
            continue
        n_sub = v.get("n_subjects")
        rows.append([label + (f" ({fmt(n_sub, 'int')} subjects)" if n_sub is not None and agg == "subject_mean" else ""),
                     fmt(v.get("sensitivity"), "pct"), fmt(v.get("precision"), "pct"), fmt(v.get("f1")),
                     fmt(v.get("fp_per_day"), "rate"), fmt(v.get("n_reference"), "int"), fmt(v.get("tp"), "int"),
                     fmt(v.get("fp"), "int"), fmt(v.get("hours"))])
    return {"header": ["Scoring", "Sensitivity", "Precision", "F1", "False detections / day", "Annotated",
                       "True positives", "False positives", "Hours"],
            "kinds": ["text"] + ["num"] * 8, "rows": rows}


def step_warnings(step: Step) -> tuple[list[str], list[dict[str, Any]]]:
    """(warnings, not-analysed groups): the step's warnings, recordings' own warnings, failed
    recordings; skipped recordings grouped by reason."""
    out: list[str] = []
    for w in step.summary.get("warnings") or []:
        text = w if isinstance(w, str) else "; ".join(f"{k}: {v}" for k, v in w.items()) if isinstance(w, dict) else str(w)
        if text not in out:
            out.append(text)
    for w in step.provenance.get("warnings") or [] if isinstance(step.provenance.get("warnings"), list) else []:
        if isinstance(w, str) and w not in out:
            out.append(w)
    for rid, r in recordings_of(step).items():
        for w in as_list(r.get("warnings")):
            msg = f"{rid}: {w}"
            if msg not in out:
                out.append(msg)
    skipped: dict[str, dict[str, list[str]]] = {}
    prov_recs = step.provenance.get("recordings")
    for rid, r in (prov_recs.items() if isinstance(prov_recs, dict) else []):
        if not isinstance(r, dict):
            continue
        status = str(r.get("status") or "").lower()
        reason = str(r.get("error") or r.get("reason") or r.get("note") or "").strip()
        if status in ("failed", "error"):
            msg = f"{rid}: failed" + (f" ({reason})" if reason else "")
            if msg not in out:
                out.append(msg)
        elif status and status not in OK_STATUS:
            text = f"{status}: {reason}" if reason else status
            # Reasons that differ only in their numbers ("43.8 min < 60") are one group.
            key = re.sub(r"\d+(\.\d+)?", "#", text)
            g = skipped.setdefault(key, {"texts": [], "ids": []})
            g["texts"].append(text)
            g["ids"].append(rid)
    groups = [{"reason": g["texts"][0] + (" (and similar)" if len(set(g["texts"])) > 1 else ""), "ids": g["ids"]}
              for g in skipped.values()]
    return out, groups


def licence_of(step: Step) -> dict[str, Any] | None:
    ln = step.provenance.get("licence_notice")
    if not ln:
        return None
    if isinstance(ln, str):
        return {"text": ln.strip(), "dois": [], "url": "", "segments": linkify(ln.strip())}
    if isinstance(ln, dict):
        text = str(ln.get("text") or ln.get("notice") or ln.get("summary") or "").strip()
        dois = [d for d in as_list(ln.get("citations") or ln.get("cite") or ln.get("dois")) if C.valid(d)]
        url = safe_url(str(ln.get("url") or ""))
        if not text and not url:
            return None
        return {"text": text, "dois": dois, "url": url, "segments": linkify(text)}
    return None


def figures_of(step: Step, issues: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[str]]:
    listed = step.summary.get("figures") or []
    figs, missing = [], []
    for f in listed if isinstance(listed, list) else []:
        if isinstance(f, str):
            f = {"path": f}
        if not isinstance(f, dict) or not f.get("path"):
            issues.append({"step": step.label, "problem": f"a figures entry is not {{path, caption}}: {str(f)[:80]}"})
            continue
        caption = str(f.get("caption") or f.get("description") or "").strip()
        path = resolve(step, str(f["path"]))
        if path is None:
            missing.append(str(f["path"]))
            continue
        if not caption:
            issues.append({"step": step.label, "problem": f"figure {f['path']} has no caption"})
        flat = str(f["path"]).replace("\\", "/").strip("/").replace("/", "__")
        figs.append({"src_path": str(path), "rel": str(f["path"]), "caption": caption,
                     "dest": f"figures/{slug(step.label)}/{slug(flat)}"})
    return figs, missing


def tables_of(step: Step) -> list[dict[str, Any]]:
    """The tables the step listed in summary.json, then every other CSV/TSV under its folder; many
    unlisted files in one subfolder (szcore/<recording>.tsv) are one entry. `files` are the
    paths (relative to the step folder) to copy."""
    out = []
    listed = step.summary.get("tables") or []
    seen = set()
    for t in listed if isinstance(listed, list) else []:
        if isinstance(t, str):
            t = {"path": t}
        if not isinstance(t, dict) or not t.get("path"):
            continue
        p = resolve(step, str(t["path"]))
        rel = str(p.relative_to(step.folder)) if p is not None else str(t["path"])
        out.append({"rel": str(t["path"]), "caption": str(t.get("caption") or "").strip(), "exists": p is not None,
                    "files": [rel] if p is not None else []})
        if p is not None:
            seen.add(p.resolve())
    groups: dict[str, list[str]] = {}
    for p in step_tables(step):
        if p.resolve() in seen:
            continue
        seen.add(p.resolve())
        rel = p.relative_to(step.folder)
        groups.setdefault(str(rel.parent), []).append(str(rel))
    for parent, files in groups.items():
        if parent != "." and len(files) > 3:
            out.append({"rel": parent + "/", "caption": f"{len(files)} files", "exists": True, "files": files})
        else:
            out += [{"rel": f, "caption": "", "exists": True, "files": [f]} for f in files]
    return out


def group_warnings(warnings: list[str], ids: set[str]) -> list[str]:
    """Identical per-recording warnings ("<recording_id>: text") said once, with the recordings."""
    by_text: dict[str, list[str]] = {}
    order: list[tuple[str, str]] = []
    for w in warnings:
        rid, sep, rest = w.partition(": ")
        if sep and rid in ids:
            if rest not in by_text:
                by_text[rest] = []
                order.append(("g", rest))
            by_text[rest].append(rid)
        else:
            order.append(("w", w))
    out = []
    for kind, text in order:
        if kind == "w":
            out.append(text)
        elif len(by_text[text]) == 1:
            out.append(f"{by_text[text][0]}: {text}")
        else:
            rids = by_text[text]
            out.append(f"{text} ({len(rids)} recordings: " + ", ".join(rids[:8]) + (", ..." if len(rids) > 8 else "") + ")")
    return out


def notices_of(step: Step) -> list[str]:
    out = []
    for k in NOTICE_KEYS:
        v = step.summary.get(k)
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
    return out


# ----------------------------------------------------------------------------- the model

def sort_key(step: Step) -> tuple[int, str]:
    return (A.ORDER.index(step.app) if step.app in A.ORDER else len(A.ORDER), step.label)


def build(found: Found, params: dict[str, Any], version: str) -> dict[str, Any]:
    steps = sorted(found.steps, key=sort_key)
    derivs = found.derivatives
    issues: list[dict[str, str]] = []
    for s in steps:
        for p in s.problems:
            issues.append({"step": s.label, "problem": p})

    rec_list, extra_cols = recordings_table(derivs, steps)
    rec_rows = {r["recording_id"]: r for r in rec_list}
    order = list(rec_rows)

    # Which steps cover which recording.
    covered: dict[str, list[str]] = {rid: [] for rid in order}
    for s in steps:
        short = A.APPS.get(s.app, {}).get("short", s.app)
        name = short + (f" ({s.label.split('/', 1)[1]})" if "/" in s.label else "")
        for rid in recordings_of(s):
            covered.setdefault(rid, [])
            if name not in covered[rid]:
                covered[rid].append(name)

    recordings = []
    for r in rec_list:
        rid = r["recording_id"]
        recordings.append({
            "recording_id": rid, "subject": r.get("subject", ""), "kind": r.get("kind", ""),
            "duration": fmt(r.get("duration_s"), "dur") if r.get("duration_s") else "–",
            "start": (r.get("start_time") or "").replace("T", " ")[:16],
            "montage": r.get("montage", "") or "–", "reference": r.get("reference", ""),
            "channels": (f"{r.get('n_good')} of {r.get('n_channels')}" if r.get("n_channels") else "–"),
            "sfreq": fmt(r.get("sfreq")) if r.get("sfreq") else "–",
            "seizures": r.get("n_seizures", "") or "–", "age": r.get("age", ""), "sex": r.get("sex", ""),
            "source_format": r.get("source_format", ""),
            "extra": [r.get(c, "") for c in extra_cols], "steps": covered.get(rid, []),
        })

    # Sections.
    sections: list[dict[str, Any]] = []
    qc_steps = [s for s in steps if s.app == "eeg-prep"]
    other = [s for s in steps if s.app != "eeg-prep"]
    qc_rows_, qc_tot = qc_rows(qc_steps, derivs, rec_rows)
    qc_source = qc_steps[0] if qc_steps else None
    if qc_source is None and derivs and derivs[0].provenance.get("app"):
        # Only the eeg port linked: eeg-prep's provenance stands in for the QC step.
        qc_source = Step(app="eeg-prep", folder=derivs[0].folder, rel=derivs[0].rel, provenance=derivs[0].provenance)
        qc_steps_for_section = [qc_source]
    else:
        qc_steps_for_section = qc_steps[:1] if qc_steps else []
    for s in qc_steps[1:]:
        issues.append({"step": s.label, "problem": "a second eeg-prep qc output: its figures are shown, its QC numbers "
                                                    "merged into the QC table"})
        qc_steps_for_section.append(s)

    for s in qc_steps_for_section + other:
        sections.append(build_section(s, rec_rows, order, issues, params))
    if qc_steps_for_section:
        sections[0]["qc"] = {"rows": qc_rows_, "totals": qc_tot}
        for extra in sections[1:len(qc_steps_for_section)]:
            extra["qc_extra"] = True

    for i, sec in enumerate(sections, start=1):
        sec["index"] = i + 1  # section 1 is Recordings
        sec["anchor"] = f"step-{slug(sec['label'])}"

    # Datasets, then references in order of first appearance.
    datasets = find_datasets(derivs, order, params)
    references: list[dict[str, Any]] = []
    index_of: dict[str, int] = {}

    def cite(doi: str) -> int | None:
        d = C.norm(doi)
        if not d:
            return None
        if d not in index_of:
            e = C.entry(d) if C.valid(d) else {"doi": d, "url": "", "known": False, "authors": "", "title": "",
                                                 "where": "", "kind": "unknown", "short": d, "year": ""}
            e["n"] = len(references) + 1
            references.append(e)
            index_of[d] = e["n"]
        return index_of[d]

    for sec in sections:
        sec["refs"] = [n for n in (cite(d) for d in sec["citations"]) if n]
        if sec.get("licence"):
            sec["licence"]["refs"] = [n for n in (cite(d) for d in sec["licence"]["dois"]) if n]
    for ds in datasets:
        ds["n"] = cite(ds["doi"])
        ds["with_refs"] = [n for n in (cite(d) for d in ds["with"]) if n]
        e = C.entry(ds["doi"])
        ds.update({"title": e["title"] or ds.get("name") or ds["doi"], "creators": e["authors"], "year": e["year"],
                   "known": e["known"], "url": e["url"], "short": e["short"]})
        pub = (C.lookup(ds["doi"]) or {}).get("publisher") or ""
        ds["publisher"] = pub
    unknown = [r for r in references if not r["known"]]
    for r in unknown:
        issues.append({"step": "references", "problem": f"DOI {r['doi']} is not in the report's citation table: listed "
                                                         "DOI-only"})

    # At a glance: one row per recording across the steps (first label of each app).
    glance_cols = []
    first_of: dict[str, Step] = {}
    for s in steps:
        first_of.setdefault(s.app, s)
    qc_by_id = {r["recording_id"]: r for r in qc_rows_}
    for label, app, key, kind in A.GLANCE:
        if app == "eeg-prep":
            if any((r["bad_segment_pct"] if key == "bad_segment_pct" else r["n_bad_channels"]) is not None for r in qc_rows_):
                glance_cols.append((label, app, key, kind))
        elif app in first_of and any(r.get(key) is not None for r in recordings_of(first_of[app]).values()):
            glance_cols.append((label, app, key, kind))
    glance_rows = []
    for rid in order:
        cells, raw = [], []
        for label, app, key, kind in glance_cols:
            if app == "eeg-prep":
                q = qc_by_id.get(rid, {})
                v = q.get("bad_segment_pct") if key == "bad_segment_pct" else q.get("n_bad_channels")
            else:
                v = recordings_of(first_of[app]).get(rid, {}).get(key)
            cells.append(fmt(v, kind))
            raw.append(v)
        if any(v is not None for v in raw):
            glance_rows.append({"recording_id": rid, "cells": cells, "raw": raw})
    glance = {"header": ["Recording"] + [c[0] for c in glance_cols], "cols": glance_cols, "rows": glance_rows}

    licences = [{"step": s["title"], "label": s["label"], "anchor": s["anchor"], **s["licence"]}
                for s in sections if s.get("licence")]
    warnings_total = sum(len(s["warnings"]) for s in sections)
    workflows = [name for name, apps in A.WORKFLOWS.items()
                 if any(s.app in apps and s.app != "eeg-prep" for s in steps)
                 and all(s.app in apps or s.app == "eeg-prep" or s.app not in A.ORDER for s in steps)]
    if not workflows:
        workflows = [name for name, apps in A.WORKFLOWS.items() if any(s.app in apps and s.app != "eeg-prep" for s in steps)]
    title = params.get("REPORT_TITLE") or "Scalp EEG report"

    from processor import citations as Cit
    acknowledgements = []
    for sec in sections:
        sw = Cit.software_of(sec["app"])
        if sw and not any(a["app"] == sec["app"] for a in acknowledgements):
            acknowledgements.append({"app": sec["app"], "software": sw})

    apps_cited = []
    for sec in sections:
        info = Cit.app_info(sec["app"])
        key = (sec["app"], sec["version"])
        if key not in [(a["app"], a["version"]) for a in apps_cited]:
            apps_cited.append({"app": sec["app"], "version": sec["version"],
                               "repository": info.get("repository") or (f"https://github.com/pennsieve-apps/{sec['app']}"
                                                                        if sec["app"] in A.ORDER else "")})
    return {
        "title": title, "version": version, "parameters": params, "workflows": workflows,
        "recordings": recordings, "extra_cols": [humanise(c) for c in extra_cols], "extra_keys": extra_cols,
        "has_age": any(r["age"] for r in recordings), "has_sex": any(r["sex"] for r in recordings),
        "has_subject": any(r["subject"] for r in recordings),
        "rec_from_steps": any(r.get("_from_steps") for r in rec_list), "has_derivative": bool(derivs),
        "sections": sections, "glance": glance, "datasets": datasets, "references": references,
        "licences": licences, "warnings_total": warnings_total, "issues": issues,
        "acknowledgements": acknowledgements, "apps_cited": apps_cited,
        "n_figures": sum(len(s["figures"]) for s in sections),
    }


def build_section(s: Step, rec_rows: dict[str, dict[str, str]], order: list[str], issues: list[dict[str, str]],
                  params: dict[str, Any]) -> dict[str, Any]:
    info = A.APPS.get(s.app, {})
    recs = recordings_of(s)
    if s.summary and "recordings" not in s.summary:
        issues.append({"step": s.label, "problem": "summary.json has no `recordings` object"})
    order_here = [r for r in order if r in recs] + [r for r in recs if r not in rec_rows]
    figs, missing = figures_of(s, issues)
    for m in missing:
        issues.append({"step": s.label, "problem": f"figure {m} is listed in summary.json but not in the output"})
    max_f = params.get("MAX_FIGURES", 40)
    warnings, skipped = step_warnings(s)
    warnings = group_warnings(warnings, set(recs) | set(rec_rows) | set(
        (s.provenance.get("recordings") or {}) if isinstance(s.provenance.get("recordings"), dict) else {}))
    if missing:
        warnings.append(f"{len(missing)} figure(s) listed in summary.json are missing from the step's output: "
                        + ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else ""))
    extra_tables = []
    if s.app == "eeg-spikes":
        t = stage_table(recs, info.get("by_stage", "events_per_min_by_stage"), order_here)
        if t:
            extra_tables.append(t)
    if s.app == "eeg-connectivity":
        extra_tables += connectivity_tables(recs, order_here)
    prov = s.provenance
    tools = prov.get("tools") if isinstance(prov.get("tools"), dict) else {}
    params_ = prov.get("parameters") if isinstance(prov.get("parameters"), dict) else {}
    cites = [c for c in as_list(prov.get("citations"))]
    prov_recs = prov.get("recordings") if isinstance(prov.get("recordings"), dict) else {}
    statuses = Counter(str((r or {}).get("status") or "ok") if isinstance(r, dict) else "ok" for r in prov_recs.values())
    title = info.get("title") or humanise(s.app)
    if "/" in s.label:
        title += f" ({s.label.split('/', 1)[1]})"
    return {
        "app": s.app, "label": s.label, "rel": s.rel, "title": title, "known": s.app in A.APPS,
        "version": str(prov.get("version") or s.summary.get("version") or ""), "variant": prov.get("variant") or "",
        "about": info.get("about", ""), "methods": info.get("methods", ""), "research": A.RESEARCH,
        "tables_dir": "eeg-report/" + s.label,
        "notices": notices_of(s), "licence": licence_of(s),
        "warnings": warnings, "warnings_visible": WARN_VISIBLE, "skipped": skipped,
        "n_recordings": len(recs),
        "headline": headline(s.app, recs, rec_rows, order_here) if s.app != "eeg-prep" else None,
        "scores": seizure_scores(s) if s.app == "eeg-seizures" else None,
        "extra_tables": extra_tables,
        "figures": figs[:max_f], "omitted": figs[max_f:], "missing": missing,
        "tables": tables_of(s), "parameters": params_, "tools": tools, "citations": cites,
        "wall_seconds": num(prov.get("wall_seconds")), "peak_rss_mb": num(prov.get("peak_rss_mb")),
        "statuses": dict(statuses), "recs": recs, "step": s,
    }


def find_datasets(derivs: list[Derivative], order: list[str], params: dict[str, Any]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def add(doi: str, how: str, name: str = "") -> None:
        d = C.norm(doi)
        if not C.valid(d) or d in out:
            return
        info = A.DATASETS.get(d, {})
        out[d] = {"doi": d, "how": how, "name": name, "credit": info.get("credit", ""),
                  "licence": info.get("licence", ""), "with": [w for w in info.get("with", [])]}

    for dv in derivs:
        for sd in dv.description.get("SourceDatasets") or []:
            if not isinstance(sd, dict):
                continue
            name = str(sd.get("Name") or "").strip()
            for key, doi in A.DATASET_NAMES:
                if key in name.lower():
                    add(doi, "named in eeg-prep's dataset_description.json", name)
                    break
            if sd.get("DOI"):
                add(str(sd["DOI"]), "eeg-prep's dataset_description.json", name)
    for d in re.split(r"[\s,;]+", params.get("DATASET_DOIS") or ""):
        if d:
            add(d, "DATASET_DOIS parameter")
    if not out:
        for pattern, doi in A.DATASET_IDS:
            if any(re.match(pattern, rid) for rid in order):
                add(doi, "recognised from the recording ids")
    # A dataset's companion works are cited with it but not listed as datasets themselves,
    # unless they are datasets the analysis used directly.
    for ds in out.values():
        ds["with"] = [w for w in ds["with"] if C.norm(w) not in out]
    return list(out.values())
