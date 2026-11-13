"""
Synthetic inputs for the report: an eeg-prep derivative (eeg port: dataset_description.json,
recordings.csv, participants.tsv, provenance.json, a tiny EDF+ with its sidecars) and, for every
app of the scalp EEG workflows, its top folder with provenance.json, summary.json (recordings,
figures with captions, tables, warnings), small PNG figures and CSV tables shaped as
conventions.md describes. Also used by app.yml `review.generate`.

Three recordings: two referential (average reference) of subject 01, one bipolar-only of subject
02 (CHB-MIT style) with an annotated `lateralisation` column. Deliberate quirks the tests rely on:
eeg-spikes declares a `licence_notice` and a summary `notice`; eeg-sleep skipped one recording
(too short); eeg-connectivity is bipolar on one recording and warns; one eeg-spectral figure path
is relative to the port folder (`eeg-spectral/figures/...`).

    python -m tests.make_fixture OUT [--layout linked|flat|both]

linked: OUT/linked/<port>/... (eeg, qc/eeg-prep, seizures/eeg-seizures, spikes/eeg-spikes,
spectral/eeg-spectral, sleep/eeg-sleep, connectivity/eeg-connectivity); flat: everything side by
side at OUT/flat/ (the derivative's files at the root, each app's folder next to them).
"""
from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path

RECS = [
    {"recording_id": "sub-01_task-eeg_run-01", "subject": "01", "run": "01", "montage": "average", "kind": "routine",
     "duration_s": 1200, "n_channels": 19, "n_good": 18, "n_seizures": 1, "age": "34", "sex": "f",
     "lateralisation": "left"},
    {"recording_id": "sub-01_task-eeg_run-02", "subject": "01", "run": "02", "montage": "average", "kind": "long-term",
     "duration_s": 9000, "n_channels": 19, "n_good": 19, "n_seizures": 2, "age": "34", "sex": "f",
     "lateralisation": "left"},
    {"recording_id": "sub-02_task-eeg_run-01", "subject": "02", "run": "01", "montage": "bipolar-longitudinal",
     "kind": "routine", "duration_s": 3600, "n_channels": 18, "n_good": 18, "n_seizures": 0, "age": "9", "sex": "m",
     "lateralisation": "right"},
]
IDS = [r["recording_id"] for r in RECS]
CHANNELS = ["Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8", "T7", "C3", "Cz", "C4", "T8", "P7", "P3", "Pz", "P4", "P8",
            "O1", "O2"]
STARTED = "2026-11-12T12:00:00Z"
FINISHED = "2026-11-12T12:01:00Z"

CITES = {
    "eeg-prep": ["10.3389/fnins.2013.00267", "10.3389/fninf.2015.00016", "10.1016/j.neuroimage.2019.05.026",
                 "10.21105/joss.04484"],
    "eeg-seizures": ["10.1111/epi.18113", "10.1109/IEMBS.2001.1020545", "10.3389/fnins.2013.00267"],
    "eeg-spikes": ["10.1007/s10548-014-0379-1", "10.1016/j.clinph.2011.09.023", "10.1111/j.1528-1157.1998.tb01329.x"],
    "eeg-spectral": ["10.1038/s41593-020-00744-x", "10.1016/j.jneumeth.2011.06.008", "10.1016/j.clinph.2007.07.019"],
    "eeg-sleep": ["10.7554/eLife.70092", "10.3389/fnins.2013.00267"],
    "eeg-connectivity": ["10.1016/j.neuroimage.2009.10.003", "10.1016/j.nicl.2017.09.021", "10.5281/zenodo.10278399"],
}
SPIKES_NOTICE = ("Spikes are detected with detectors developed and validated on intracranial EEG (Janca et al. 2015; "
                 "Barkmeier et al. 2012), run here on scalp EEG. Rates and lateralisation are research outputs to be "
                 "reviewed against the EEG, not clinical findings.")
# A licence notice with a link and a DOI, and a string that must never become a link.
LICENCE = ("Test terms: example weights for non-commercial research only; see https://example.org/terms and cite "
           "10.1016/j.clinph.2011.09.023. Not a link: javascript:alert(1).")


# ----------------------------------------------------------------------------- writers

def wjson(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")


def wcsv(path: Path, header: list[str], rows: list[list], delimiter: str = ",") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def png(path: Path, title: str, w: int = 480, h: int = 260) -> None:
    """A small PNG drawn with the standard library only (the review generator image has no
    Pillow): a framed panel with a zig-zag trace, its shade derived from the title."""
    import zlib

    path.parent.mkdir(parents=True, exist_ok=True)
    shade = 200 + sum(title.encode()) % 50
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            border = x < 3 or y < 3 or x >= w - 3 or y >= h - 3
            trace = abs(y - (h // 2 + ((x // 10) % 2 * 2 - 1) * (x % 10) * 4)) < 2
            row += bytes((31, 78, 140) if border else (200, 80, 40) if trace else (shade, shade, 252))
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def edf(path: Path, n_ch: int = 3, sfreq: int = 64, seconds: int = 2) -> None:
    """A tiny valid EDF+ file (the report never opens it; it is there so the derivative looks real)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ns = n_ch
    hdr = ("0".ljust(8) + "X X X X".ljust(80) + "Startdate 01-JAN-2020 X X X".ljust(80) + "01.01.20" + "00.00.00"
           + str(256 + 256 * ns).ljust(8) + "EDF+C".ljust(44) + str(seconds).ljust(8) + "1".ljust(8) + str(ns).ljust(4))
    fields = [[c.ljust(16) for c in CHANNELS[:ns]], ["".ljust(80)] * ns, ["uV".ljust(8)] * ns, ["-100".ljust(8)] * ns,
              ["100".ljust(8)] * ns, ["-32768".ljust(8)] * ns, ["32767".ljust(8)] * ns, ["".ljust(80)] * ns,
              [str(sfreq).ljust(8)] * ns, ["".ljust(32)] * ns]
    hdr += "".join("".join(f) for f in fields)
    data = b"".join(struct.pack("<" + "h" * sfreq, *([0] * sfreq)) for _ in range(seconds * ns))
    path.write_bytes(hdr.encode("ascii") + data)


def prov(app: str, recordings: dict, params: dict, **extra) -> dict:
    p = {"app": app, "version": "0.1.0", "variant": None, "tools": {"python": "3.12.16", "mne": "1.13.2"},
         "parameters": params, "inputs": ["eeg/recordings.csv"], "started": STARTED, "finished": FINISHED,
         "wall_seconds": 12.5, "peak_rss_mb": 300.0, "threads": {"requested": 0, "used": 2, "why": "test"},
         "recordings": recordings, "citations": CITES.get(app, []), "licence_notice": None}
    p.update(extra)
    return p


def ok(**kw) -> dict:
    return {"status": "ok", "seconds": 1.0, **kw}


# ----------------------------------------------------------------------------- the apps

def eeg_prep(eeg: Path, qc: Path) -> None:
    wjson(eeg / "dataset_description.json", {
        "Name": "eeg-prep derivative", "BIDSVersion": "1.10.0", "DatasetType": "derivative",
        "GeneratedBy": [{"Name": "eeg-prep", "Version": "0.1.0"}], "SourceDatasets": [{"URL": "n/a"}]})
    cols = ["recording_id", "subject", "session", "task", "run", "path", "sfreq", "n_channels", "n_good", "duration_s",
            "montage", "reference", "kind", "start_time", "labels_source", "n_seizures", "source_format", "age", "sex",
            "lateralisation"]
    rows = []
    for r in RECS:
        stem = r["recording_id"]
        rel = f"sub-{r['subject']}/eeg/{stem}_desc-preproc_eeg.edf"
        rows.append([stem, r["subject"], "", "eeg", r["run"], rel, 256, r["n_channels"], r["n_good"], r["duration_s"],
                     r["montage"], "average" if r["montage"] == "average" else "", r["kind"],
                     "2020-01-01T22:00:00", "events.tsv" if r["n_seizures"] else "",
                     r["n_seizures"] if r["n_seizures"] else "", "edf", r["age"], r["sex"], r["lateralisation"]])
        edf(eeg / rel)
        base = eeg / f"sub-{r['subject']}" / "eeg" / f"{stem}_desc-preproc"
        wcsv(Path(str(base) + "_channels.tsv"), ["name", "type", "units", "status"],
             [[c, "EEG", "µV", "good"] for c in CHANNELS[:3]], delimiter="\t")
        wcsv(Path(str(base) + "_events.tsv"), ["onset", "duration", "trial_type", "source", "channels"],
             [[100, 60, "seizure", "annotation", ""]], delimiter="\t")
    wcsv(eeg / "recordings.csv", cols, rows)
    wcsv(eeg / "participants.tsv", ["participant_id", "age", "sex"], [["sub-01", 34, "f"], ["sub-02", 9, "m"]],
         delimiter="\t")
    prov_recs = {
        IDS[0]: ok(montage="average", bad_channels=["T7"], ica={"components": 17, "removed": ["IC00 eye blink",
                                                                                              "IC03 muscle artifact"],
                                                                "variance_removed_fraction": 0.31},
                   bad_segment_seconds=60.0, dropped={"ECG": "not EEG"}),
        IDS[1]: ok(montage="average", bad_channels=[], ica={"components": 18, "removed": ["IC01 eye blink"],
                                                            "variance_removed_fraction": 0.12},
                   bad_segment_seconds=450.0, dropped={}),
        IDS[2]: ok(montage="bipolar-longitudinal", bad_channels=[], ica=None, bad_segment_seconds=36.0, dropped={}),
    }
    p = prov("eeg-prep", prov_recs, {"REFERENCE": "average", "ARTIFACTS": "iclabel"})
    wjson(eeg / "provenance.json", p)

    top = qc / "eeg-prep"
    qrows = [[IDS[0], "channel", c, c + "-Avg", "EEG", "bad" if c == "T7" else "good",
              "high-frequency noise (z > 5)" if c == "T7" else "", "", "", "", ""] for c in CHANNELS]
    qrows += [[IDS[0], "dropped", "ECG", "ECG", "ECG", "dropped", "not EEG", "", "", "", ""],
              [IDS[0], "ica_component", "IC00", "", "ICA", "removed", "eye blink 0.99", "eye blink", "0.99", "", ""],
              [IDS[0], "ica_component", "IC01", "", "ICA", "kept", "brain 0.9", "brain", "0.9", "", ""],
              [IDS[0], "ica_component", "IC03", "", "ICA", "removed", "muscle 0.85", "muscle artifact", "0.85", "", ""],
              [IDS[1], "ica_component", "IC01", "", "ICA", "removed", "eye blink 0.95", "eye blink", "0.95", "", ""]]
    qrows += [[rid, "bad_segments", "total", "", "segments", "", "x", "", "", "", ""] for rid in IDS]
    wcsv(top / "qc.csv", ["recording_id", "item", "name", "original_name", "type", "status", "reason",
                          "iclabel_label", "iclabel_probability", "robust_sd_uv", "line_noise_ratio"], qrows)
    figs = [{"path": "overview_qc.png", "caption": "Data quality of every recording (test)."}]
    png(top / "overview_qc.png", "QC overview")
    for rid in IDS:
        png(top / f"{rid}_qc.png", f"{rid}: QC")
        figs.append({"path": f"{rid}_qc.png", "caption": f"{rid}: data quality after preprocessing (test caption)."})
    summ_recs = {
        IDS[0]: {"duration_s": 1200.0, "n_channels": 19, "n_good": 18, "n_bad_channels": 1, "montage": "average",
                 "n_ica_components": 17, "n_ica_removed": 2, "ica_variance_removed_pct": 31.0, "bad_segment_pct": 5.0,
                 "n_seizures": 1},
        IDS[1]: {"duration_s": 9000.0, "n_channels": 19, "n_good": 19, "n_bad_channels": 0, "montage": "average",
                 "n_ica_components": 18, "n_ica_removed": 1, "ica_variance_removed_pct": 12.0, "bad_segment_pct": 5.0,
                 "n_seizures": 2},
        IDS[2]: {"duration_s": 3600.0, "n_channels": 18, "n_good": 18, "n_bad_channels": 0,
                 "montage": "bipolar-longitudinal", "n_ica_components": 0, "n_ica_removed": 0,
                 "ica_variance_removed_pct": 0.0, "bad_segment_pct": 1.0, "n_seizures": 0},
    }
    wjson(top / "summary.json", {"app": "eeg-prep", "version": "0.1.0", "recordings": summ_recs, "figures": figs,
                                 "tables": [{"path": "qc.csv", "caption": "QC per channel and component."}],
                                 "warnings": [f"{IDS[2]}: bipolar-only recording: ICA skipped"]})
    wjson(top / "provenance.json", p)


def eeg_seizures(top: Path) -> None:
    recs = {
        IDS[0]: {"duration_h": 0.333, "montage": "average", "n_channels": 19, "n_detections": 2, "detections_per_day": 144.0,
                 "n_annotated_seizures": 1, "event_sensitivity": 1.0, "event_precision": 0.5, "event_f1": 0.667,
                 "event_fp_per_day": 72.0, "seizures_detected": 1, "false_detections": 1, "sample_f1": 0.81},
        IDS[1]: {"duration_h": 2.5, "montage": "average", "n_channels": 19, "n_detections": 1, "detections_per_day": 9.6,
                 "n_annotated_seizures": 2, "event_sensitivity": 0.5, "event_precision": 1.0, "event_f1": 0.667,
                 "event_fp_per_day": 0.0, "seizures_detected": 1, "false_detections": 0, "sample_f1": 0.4},
        IDS[2]: {"duration_h": 1.0, "montage": "bipolar-longitudinal", "n_channels": 18, "n_detections": 0,
                 "detections_per_day": 0.0, "n_annotated_seizures": 0, "event_sensitivity": None,
                 "event_precision": None, "event_f1": None, "event_fp_per_day": 0.0, "seizures_detected": 0,
                 "false_detections": 0, "sample_f1": None},
    }
    pooled = {"event": {"pooled": {"sensitivity": 0.6667, "precision": 0.6667, "f1": 0.6667, "fp_per_day": 6.0,
                                   "tp": 2.0, "fp": 1.0, "n_reference": 3.0, "hours": 3.833},
                        "subject_mean": {"sensitivity": 0.75, "precision": 0.75, "f1": 0.667, "fp_per_day": 36.0,
                                         "n_subjects": 1.0}},
              "sample": {"pooled": {"sensitivity": 0.55, "precision": 0.6, "f1": 0.57, "fp_per_day": 300.0,
                                    "tp": 110.0, "fp": 70.0, "n_reference": 200.0, "hours": 3.833}}}
    wcsv(top / "seizures.csv", ["recording_id", "onset_s", "duration_s", "confidence", "channels", "detector"],
         [[IDS[0], 95, 70, 0.8, "T7,F7", "linelength"], [IDS[0], 800, 20, 0.6, "Fp1", "linelength"],
          [IDS[1], 4000, 50, 0.9, "T7", "linelength"]])
    wcsv(top / "scores.csv", ["recording_id", "scope", "metric", "value"],
         [["pooled", "event", m, v] for m, v in (("sensitivity", 0.6667), ("precision", 0.6667), ("f1", 0.6667),
                                                 ("fp_per_day", 6.0))])
    wcsv(top / "probability.csv", ["recording_id", "time_s", "probability"], [[IDS[0], t, 0.1] for t in range(5)])
    for rid in IDS:
        wcsv(top / "szcore" / f"{rid}.tsv", ["onset", "duration", "eventType", "confidence", "channels", "dateTime",
                                              "recordingDuration"], [[95, 70, "sz", 0.8, "n/a", "2020-01-01 22:01:35", 1200]],
             delimiter="\t")
    png(top / "figures" / "overview_detections.png", "Detections overview")
    png(top / "figures" / "scores_per_recording.png", "Scores per recording")
    wjson(top / "summary.json", {
        "app": "eeg-seizures", "version": "0.1.0", "detector": "linelength",
        "note": "Detections are research outputs: candidates for an expert to review, not a diagnosis.",
        "recordings": recs, "pooled": pooled,
        "figures": [{"path": "figures/overview_detections.png", "caption": "Annotated seizures and candidates (test)."},
                    {"path": "figures/scores_per_recording.png", "caption": "Scores per recording (test)."}],
        "tables": [{"path": "seizures.csv", "caption": "Candidates."}, {"path": "scores.csv", "caption": "Scores."},
                   {"path": "probability.csv", "caption": "Probability."}],
        "warnings": []})
    wjson(top / "provenance.json", prov("eeg-seizures", {r: ok() for r in IDS}, {"DETECTOR": "linelength"}))


def eeg_spikes(top: Path) -> None:
    recs = {
        IDS[0]: {"minutes_analysed": 18.5, "n_channels": 18, "montage": "bipolar", "n_spikes": 120, "n_events": 80,
                 "events_per_min": 4.324, "top_channel": "F7-T7", "top_channel_rate_per_min": 2.1,
                 "laterality_index": 0.6, "n_left": 56, "n_right": 14, "n_midline": 10,
                 "most_frequent_leader_region": "left temporal", "most_frequent_leading_channel": "F7-T7",
                 "events_per_min_by_stage": {"W": 3.1, "N2": 5.5}},
        IDS[1]: {"minutes_analysed": 140.0, "n_channels": 18, "montage": "bipolar", "n_spikes": 900, "n_events": 600,
                 "events_per_min": 4.286, "top_channel": "T7-P7", "top_channel_rate_per_min": 1.9,
                 "laterality_index": 0.42, "n_left": 380, "n_right": 155, "n_midline": 65,
                 "most_frequent_leader_region": "left temporal", "events_per_min_by_stage": {"W": 2.0, "N2": 4.0, "N3": 7.25, "R": 1.5},
                 "nrem_wake_ratio": 2.6},
        IDS[2]: {"minutes_analysed": 59.0, "n_channels": 18, "montage": "bipolar", "n_spikes": 30, "n_events": 25,
                 "events_per_min": 0.424, "top_channel": "F8-T8", "top_channel_rate_per_min": 0.2,
                 "laterality_index": -0.5, "n_left": 5, "n_right": 15, "n_midline": 5,
                 "most_frequent_leader_region": "right temporal"},
    }
    wcsv(top / "spikes.csv", ["recording_id", "channel", "time_s", "amplitude_uv", "duration_ms", "detector",
                              "sleep_stage"], [[IDS[0], "F7-T7", 12.5, 120, 60, "janca", "W"]])
    wcsv(top / "spike_rates.csv", ["recording_id", "channel", "n_spikes", "minutes", "rate_per_min", "detector"],
         [[IDS[0], "F7-T7", 39, 18.5, 2.1, "janca"]])
    wcsv(top / "spike_events.csv", ["recording_id", "event_id", "time_s", "n_channels", "channels", "leading_channel",
                                    "hemisphere"], [[IDS[0], 1, 12.5, 2, "F7-T7,T7-P7", "F7-T7", "L"]])
    wcsv(top / "lateralisation.csv", ["recording_id", "n_left", "n_right", "n_midline", "laterality_index",
                                      "dominant_region"], [[IDS[0], 56, 14, 10, 0.6, "left temporal"]])
    wcsv(top / "rates_by_stage.csv", ["recording_id", "channel", "stage", "n_spikes", "minutes", "rate_per_min"],
         [[IDS[1], "T7-P7", "N3", 50, 20, 2.5]])
    figs = [{"path": "figures/laterality_index.png", "caption": "Laterality index per recording (test)."}]
    png(top / "figures" / "laterality_index.png", "Laterality index")
    for rid in IDS:
        png(top / "figures" / f"{rid}_spike_rates.png", f"{rid}: spike rates")
        figs.append({"path": f"figures/{rid}_spike_rates.png", "caption": f"{rid}: spike rate per channel (test)."})
    wjson(top / "summary.json", {
        "app": "eeg-spikes", "version": "0.1.0", "recordings": recs, "figures": figs, "notice": SPIKES_NOTICE,
        "tables": [{"path": "spike_rates.csv", "caption": "Rates."}, {"path": "spike_events.csv", "caption": "Events."},
                   {"path": "lateralisation.csv", "caption": "Laterality."}, {"path": "spikes.csv", "caption": "Spikes."},
                   {"path": "rates_by_stage.csv", "caption": "Rates by stage."}],
        "warnings": []})
    wjson(top / "provenance.json", prov("eeg-spikes", {r: ok() for r in IDS}, {"DETECTOR": "janca"},
                                        licence_notice=LICENCE))


def eeg_spectral(top: Path, label: str = "") -> None:
    recs = {
        IDS[0]: {"montage": "average", "n_channels": 19, "seconds_analysed": 1100.0, "pdr_hz": 9.75,
                 "pdr_amplitude_uv": 22.5, "pdr_asymmetry": 0.05, "pdr_reactivity": None, "pdr_basis": "all",
                 "rbsi": 0.083, "rbsi_signed": 0.061, "aperiodic_exponent_median": 1.21, "theta_alpha_ratio_median": 0.9,
                 "relpow_alpha_posterior": 0.31, "low_r_squared_channels": 1, "pdr_estimates_disagree": True},
        IDS[1]: {"montage": "average", "n_channels": 19, "seconds_analysed": 8500.0, "pdr_hz": 8.5,
                 "pdr_amplitude_uv": 18.0, "pdr_asymmetry": 0.2, "pdr_reactivity": None, "pdr_basis": "all",
                 "rbsi": 0.12, "rbsi_signed": 0.1, "aperiodic_exponent_median": 1.45, "theta_alpha_ratio_median": 1.2,
                 "relpow_alpha_posterior": 0.22, "low_r_squared_channels": 0},
        IDS[2]: {"montage": "bipolar-longitudinal", "n_channels": 18, "seconds_analysed": 3400.0, "pdr_hz": None,
                 "pdr_amplitude_uv": None, "pdr_asymmetry": None, "pdr_reactivity": None, "pdr_basis": "all",
                 "rbsi": 0.06, "rbsi_signed": -0.02, "aperiodic_exponent_median": 1.6, "theta_alpha_ratio_median": 2.0,
                 "relpow_alpha_posterior": 0.12, "low_r_squared_channels": 3},
    }
    for name, header in (("bandpower.csv", ["recording_id", "channel", "band", "abs_power", "rel_power", "log_power"]),
                         ("aperiodic.csv", ["recording_id", "channel", "exponent", "offset", "knee", "r_squared",
                                            "error", "n_peaks"]),
                         ("pdr.csv", ["recording_id", "pdr_hz", "pdr_amplitude_uv", "pdr_left_hz", "pdr_right_hz",
                                      "asymmetry", "reactivity", "n_eyes_closed_s", "method"]),
                         ("asymmetry.csv", ["recording_id", "pair", "band", "bsi"])):
        rows = [[IDS[0]] + ["1"] * (len(header) - 1)]
        if name == "pdr.csv":
            rows.append([IDS[2], "", "", "", "", "", "", "0", "specparam peak 6-14 Hz, O1/O2; no clear peak"])
        wcsv(top / name, header, rows)
    figs = []
    for i, rid in enumerate(IDS):
        png(top / "figures" / f"{rid}_psd.png", f"{rid}: PSD")
        # The first figure path is written relative to the port folder, as some apps do.
        figs.append({"path": ("eeg-spectral/" if i == 0 else "") + f"figures/{rid}_psd.png",
                     "caption": f"{rid}: mean power spectrum per region (test)."})
    wjson(top / "summary.json", {
        "app": "eeg-spectral", "version": "0.1.0", "recordings": recs, "figures": figs,
        "notice": "Spectral biomarkers are research outputs, to be reviewed by a clinician.",
        "tables": [{"path": n, "caption": n} for n in ("bandpower.csv", "aperiodic.csv", "pdr.csv", "asymmetry.csv")],
        "warnings": [f"{rid}: PDR on all artifact-free windows (no eyes-closed annotation): review" for rid in IDS]
        + [f"{IDS[2]}: bipolar-only recording: no PDR"]})
    wjson(top / "provenance.json", prov("eeg-spectral", {r: ok() for r in IDS}, {"LABEL": label}))


def eeg_sleep(top: Path) -> None:
    recs = {
        IDS[1]: {"duration_h": 2.5, "epochs": 300.0, "TST_min": 120.0, "SE_pct": 80.0, "SOL_min": 12.0, "WASO_min": 18.0,
                 "N1_pct": 5.0, "N2_pct": 50.0, "N3_pct": 25.0, "REM_pct": 20.0, "confidence_mean_pct": 72.0,
                 "n_spindles": 300.0, "spindle_density_central": 2.5, "sw_density_frontal": 6.0},
        IDS[2]: {"duration_h": 1.0, "epochs": 120.0, "TST_min": 40.0, "SE_pct": 66.7, "SOL_min": 10.0, "WASO_min": 10.0,
                 "N1_pct": 10.0, "N2_pct": 60.0, "N3_pct": 20.0, "REM_pct": 10.0, "confidence_mean_pct": 61.0,
                 "n_spindles": 50.0, "spindle_density_central": 1.25, "sw_density_frontal": 3.0},
    }
    wcsv(top / "hypnogram.csv", ["recording_id", "epoch", "start_s", "duration_s", "stage", "confidence", "channel"],
         [[IDS[1], i, i * 30, 30, "N2", 0.8, "C4"] for i in range(4)])
    wcsv(top / "sleep_stats.csv", ["recording_id", "metric", "value"], [[IDS[1], "TST", 120]])
    png(top / "figures" / f"{IDS[1]}_hypnogram.png", "hypnogram")
    wjson(top / "summary.json", {
        "app": "eeg-sleep", "version": "0.1.0", "recordings": recs,
        "notice": "Sleep stages are scored automatically from EEG only: research output, not a clinical sleep scoring.",
        "figures": [{"path": f"figures/{IDS[1]}_hypnogram.png", "caption": "Hypnogram (test)."}],
        "tables": [{"path": "hypnogram.csv", "caption": "Hypnogram."}, {"path": "sleep_stats.csv", "caption": "Stats."}],
        "warnings": [f"{IDS[2]}: mean staging confidence 61% (< 70%): review the hypnogram"]})
    wjson(top / "provenance.json", prov("eeg-sleep", {
        IDS[0]: {"status": "skipped", "error": "20.0 min < MIN_SLEEP_MINUTES 60"}, IDS[1]: ok(), IDS[2]: ok()},
        {"MIN_SLEEP_MINUTES": "60"}))


def eeg_connectivity(top: Path) -> None:
    recs = {}
    for i, rid in enumerate(IDS):
        r = {"montage": RECS[i]["montage"], "n_channels": 19, "seconds_analysed": 1000.0 + i, "epochs_used": 250}
        for m in ("wpli", "imcoh"):
            for b in ("delta", "theta", "alpha", "beta"):
                r[f"{m}_{b}_mean"] = 0.1 + 0.01 * i
                r[f"{m}_{b}_asymmetry"] = (0.05 if i < 2 else -0.04)
                r[f"{m}_{b}_small_worldness"] = 1.1
        recs[rid] = r
    wcsv(top / "connectivity.csv", ["recording_id", "channel_a", "channel_b", "band", "measure", "value"],
         [[IDS[0], "Fp1", "Fp2", "alpha", "wpli", 0.2]])
    wcsv(top / "hemisphere.csv", ["recording_id", "band", "measure", "left", "right", "interhemispheric", "asymmetry"],
         [[IDS[0], "alpha", "wpli", 0.2, 0.18, 0.1, 0.05]])
    png(top / "figures" / "asymmetry_overview.png", "asymmetry overview")
    wjson(top / "summary.json", {
        "app": "eeg-connectivity", "version": "0.1.0", "recordings": recs,
        "figures": [{"path": "figures/asymmetry_overview.png", "caption": "Hemispheric asymmetry (test)."}],
        "tables": [{"path": "connectivity.csv", "caption": "Edges."}, {"path": "hemisphere.csv", "caption": "Hemispheres."}],
        "notice": "Connectivity and network measures are research outputs.",
        "warnings": [f"{IDS[2]}: bipolar-only recording: connectivity between bipolar derivations"]})
    wjson(top / "provenance.json", prov("eeg-connectivity", {r: ok() for r in IDS}, {"DENSITY": "0.2"}))


APPS = {"eeg-seizures": ("seizures", eeg_seizures), "eeg-spikes": ("spikes", eeg_spikes),
        "eeg-spectral": ("spectral", eeg_spectral), "eeg-sleep": ("sleep", eeg_sleep),
        "eeg-connectivity": ("connectivity", eeg_connectivity)}


def write(root: Path, layout: str = "linked", apps: list[str] | None = None) -> Path:
    """Write one layout under root; returns the input folder."""
    apps = list(APPS) if apps is None else apps
    if layout == "linked":
        base = root / "linked"
        eeg_prep(base / "eeg", base / "qc")
        for app in apps:
            port, fn = APPS[app]
            fn(base / port / app)
    else:
        base = root / "flat"
        eeg_prep(base, base)
        for app in apps:
            APPS[app][1](base / app)
    return base


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--layout", choices=["linked", "flat", "both"], default="linked")
    args = ap.parse_args()
    for layout in (("linked", "flat") if args.layout == "both" else (args.layout,)):
        print("wrote", write(args.out, layout))


if __name__ == "__main__":
    main()
