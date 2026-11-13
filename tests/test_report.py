"""The report on the synthetic fixture: every layout, every subset of steps, and broken inputs."""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
from pathlib import Path

import pytest

from processor import main as M
from tests import make_fixture as F

PARAMS = {"REPORT_TITLE": "", "MAX_FIGURES": 40, "DATASET_DOIS": "", "WRITE_PDF": False}


def weasyprint_works() -> bool:
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 - missing Pango on a dev machine
        return False


def run(inp: Path, out: Path, **params) -> tuple[int, str, Path]:
    rc = M.run(inp, out, {**PARAMS, **params})
    rep = out / "report" / "eeg-report"
    page = (rep / "index.html").read_text(encoding="utf-8") if (rep / "index.html").exists() else ""
    return rc, page, rep


def text(page: str) -> str:
    t = re.sub(r"<style.*?</style>", "", page, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


@pytest.fixture()
def linked(tmp_path: Path) -> Path:
    return F.write(tmp_path / "in", "linked")


def test_full_linked_report(linked: Path, tmp_path: Path) -> None:
    rc, page, rep = run(linked, tmp_path / "out")
    assert rc == 0
    t = text(page)
    # Recordings table from recordings.csv, the QC summary, one section per step.
    for rid in F.IDS:
        assert rid in t
    for title in ("Data quality (preprocessing)", "Seizure detection (candidates for review)", "Interictal spikes",
                  "Spectral biomarkers", "Sleep", "Functional connectivity", "References", "How to cite"):
        assert title in t, title
    # Sections in workflow order.
    order = [t.index(x) for x in ("2. Data quality", "3. Seizure detection", "4. Interictal spikes",
                                  "5. Spectral biomarkers", "6. Sleep", "7. Functional connectivity")]
    assert order == sorted(order)
    # QC: bad channel names, ICA classes, bad segment percentage.
    assert "T7" in t and "eye blink, muscle artifact" in t and "1 with at least one bad channel" in t
    # Seizures: sensitivity, precision, F1 and false detections per day side by side, as review candidates.
    assert "Sensitivity Precision F1 False detections / day" in t
    assert "66.7 % 66.7 % 0.6667 6.00" in t
    assert "Candidate seizures per recording (for review)" in t
    # Spikes: the notice box, side-with-more-events wording, never a localisation, annotated side.
    assert F.SPIKES_NOTICE in t
    assert "Laterality index (side with more detected events)" in t
    assert "not a localisation of the epileptogenic zone" in t
    assert "Annotated side" in t and "left temporal" in t
    assert "Spike events per minute by sleep stage" in t
    # Spectral, sleep, connectivity headline numbers.
    assert "PDR (Hz)" in t and "9.75" in t and "rBSI" in t
    assert "TST (min)" in t and "120" in t
    assert "Hemispheric asymmetry (wPLI)" in t and "Hemispheric asymmetry (imaginary coherence)" in t
    # Research labels.
    assert "Research output, not a clinical interpretation" in t
    assert t.count("Research output, to be reviewed by a clinician") >= 5
    # Every figure, with its caption, in order, copied next to the page.
    figs = re.findall(r'<img src="([^"]+)"', page)
    assert len(figs) == 4 + 2 + 4 + 3 + 1 + 1
    for f in figs:
        assert (rep / f).is_file()
    assert "Hypnogram (test)." in t
    # Licence notice at the top and in the step, its link and DOI linked, the javascript: text not.
    top = page[:page.index('id="recordings"')]
    assert "Usage and licence" in top and 'href="https://example.org/terms"' in top
    assert 'href="https://doi.org/10.1016/j.clinph.2011.09.023"' in page
    assert 'href="javascript' not in page
    # References: full entries from the bundled table, no DOI-only.
    assert "Detection of Interictal Epileptiform Discharges Using Signal Envelope Distribution Modelling" in t
    assert "DOI only" not in t
    # Skipped recording listed, warnings shown.
    assert "Not analysed" in t and "MIN_SLEEP_MINUTES" in t
    assert "Warnings (" in t


def test_tables_and_json(linked: Path, tmp_path: Path) -> None:
    rc, _, rep = run(linked, tmp_path / "out")
    assert rc == 0
    tab = tmp_path / "out" / "tables" / "eeg-report"
    for name in ("recordings.csv", "overview.csv", "headline.csv", "qc_summary.csv", "seizure_scores.csv",
                 "provenance.json", "eeg-prep/qc.csv", "eeg-seizures/szcore/sub-01_task-eeg_run-01.tsv",
                 "eeg-spikes/lateralisation.csv", "eeg-sleep/hypnogram.csv", "eeg-connectivity/hemisphere.csv"):
        assert (tab / name).is_file(), name
    rows = list(csv.DictReader(open(tab / "headline.csv", encoding="utf-8")))
    assert {"recording_id", "step", "metric", "value"} == set(rows[0])
    assert any(r["step"] == "eeg-spikes" and r["metric"] == "events_per_min_by_stage.N3" for r in rows)
    summ = json.loads((rep / "summary.json").read_text())
    prov = json.loads((rep / "provenance.json").read_text())
    assert summ["app"] == "eeg-report" and set(summ["recordings"]) == set(F.IDS)
    for key in ("app", "version", "variant", "tools", "parameters", "inputs", "started", "finished", "wall_seconds",
                "peak_rss_mb", "threads", "recordings", "citations", "licence_notice"):
        assert key in prov, key


def test_flat_layout_matches_linked(tmp_path: Path) -> None:
    flat = F.write(tmp_path / "in", "flat")
    rc, page, _ = run(flat, tmp_path / "out")
    assert rc == 0
    t = text(page)
    assert "7. Functional connectivity" in t and "sub-02_task-eeg_run-01" in t
    assert len(re.findall(r"<img ", page)) == 15


def test_symlinked_ports(tmp_path: Path) -> None:
    real = F.write(tmp_path / "real", "linked")
    inp = tmp_path / "in"
    inp.mkdir()
    for p in real.iterdir():
        os.symlink(p, inp / p.name)
    rc, page, _ = run(inp, tmp_path / "out")
    assert rc == 0 and "7. Functional connectivity" in text(page)


@pytest.mark.parametrize("apps", [[], ["eeg-seizures"], ["eeg-spectral", "eeg-connectivity"], ["eeg-sleep", "eeg-spikes"]])
def test_any_subset_of_steps(tmp_path: Path, apps: list[str]) -> None:
    inp = F.write(tmp_path / "in", "linked", apps=apps)
    rc, page, _ = run(inp, tmp_path / "out")
    assert rc == 0
    t = text(page)
    assert "Data quality per recording" in t
    from processor.apps import APPS
    for app in F.APPS:
        present = re.search(r"\d+\. " + re.escape(APPS[app]["title"]), t) is not None
        assert present == (app in apps), app


def test_only_eeg_port(tmp_path: Path) -> None:
    """Only eeg-prep's derivative: recordings and a QC table from its provenance.json."""
    inp = F.write(tmp_path / "in", "linked", apps=[])
    shutil.rmtree(inp / "qc")
    rc, page, _ = run(inp, tmp_path / "out")
    assert rc == 0
    t = text(page)
    assert "Data quality per recording" in t and "T7" in t and "eye blink, muscle artifact" in t


def test_only_a_step_without_eeg_prep(tmp_path: Path) -> None:
    inp = F.write(tmp_path / "in", "linked", apps=["eeg-seizures"])
    shutil.rmtree(inp / "eeg")
    shutil.rmtree(inp / "qc")
    rc, page, _ = run(inp, tmp_path / "out")
    assert rc == 0
    t = text(page)
    assert "listed from the steps' own outputs" in t and "sub-01_task-eeg_run-02" in t


def test_missing_figure_and_corrupt_figure(linked: Path, tmp_path: Path) -> None:
    (linked / "sleep" / "eeg-sleep" / "figures" / f"{F.IDS[1]}_hypnogram.png").unlink()
    (linked / "spikes" / "eeg-spikes" / "figures" / "laterality_index.png").write_bytes(b"not a png")
    rc, page, _ = run(linked, tmp_path / "out")
    assert rc == 0
    t = text(page)
    assert "listed in summary.json are missing" in t
    assert "could not be read as an image" in t
    assert "Notes on the inputs" in t


def test_zero_recordings_step(linked: Path, tmp_path: Path) -> None:
    p = linked / "sleep" / "eeg-sleep" / "summary.json"
    s = json.loads(p.read_text())
    s["recordings"], s["figures"] = {}, []
    p.write_text(json.dumps(s))
    rc, page, _ = run(linked, tmp_path / "out")
    assert rc == 0
    assert "This step reported no recordings" in text(page)


def test_label_subfolders(tmp_path: Path) -> None:
    inp = F.write(tmp_path / "in", "linked", apps=["eeg-seizures"])
    F.eeg_spectral(inp / "spectral" / "eeg-spectral" / "raw", label="raw")
    F.eeg_spectral(inp / "spectral" / "eeg-spectral" / "clean", label="clean")
    rc, page, rep = run(inp, tmp_path / "out")
    assert rc == 0
    t = text(page)
    assert "Spectral biomarkers (clean)" in t and "Spectral biomarkers (raw)" in t
    assert (rep / "figures" / "eeg-spectral_raw").is_dir() and (rep / "figures" / "eeg-spectral_clean").is_dir()
    tab = tmp_path / "out" / "tables" / "eeg-report"
    assert (tab / "eeg-spectral/raw/pdr.csv").is_file() and (tab / "eeg-spectral/clean/pdr.csv").is_file()


def test_unsafe_paths_and_bad_json(linked: Path, tmp_path: Path) -> None:
    p = linked / "spikes" / "eeg-spikes" / "summary.json"
    s = json.loads(p.read_text())
    s["figures"].append({"path": "../../eeg/recordings.csv", "caption": "escape"})
    s["figures"].append({"path": "/etc/passwd", "caption": "absolute"})
    s["figures"].append("not-a-dict-but-a-path.png")
    p.write_text(json.dumps(s))
    (linked / "connectivity" / "eeg-connectivity" / "summary.json").write_text("{not json")
    rc, page, rep = run(linked, tmp_path / "out")
    assert rc == 0
    assert not list(rep.rglob("passwd"))
    t = text(page)
    assert "Functional connectivity" in t  # still a section, from its provenance.json


def test_max_figures_and_dataset_dois(linked: Path, tmp_path: Path) -> None:
    rc, page, rep = run(linked, tmp_path / "out", MAX_FIGURES=1, DATASET_DOIS="10.13026/5d4a-j060")
    assert rc == 0
    t = text(page)
    assert len(re.findall(r"<img ", page)) == 6
    assert "more figures of this step (MAX_FIGURES = 1)" in t
    # Every figure is still copied, the omitted ones linked.
    assert (rep / "figures" / "eeg-spikes" / f"figures__{F.IDS[2]}_spike_rates.png").is_file()
    assert "Siena Scalp EEG Database" in t and "EEG Synchronization Analysis for Seizure Prediction" in t
    assert "PhysioBank, PhysioToolkit, and PhysioNet" in t


def test_previous_report_is_ignored(linked: Path, tmp_path: Path) -> None:
    rc, _, _ = run(linked, tmp_path / "out1")
    shutil.copytree(tmp_path / "out1" / "report", linked / "old-report")
    rc, page, _ = run(linked, tmp_path / "out2")
    assert rc == 0 and "eeg-report 0" not in text(page).split("How to cite")[0]


def test_no_input_and_bad_parameters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "empty").mkdir()
    assert run(tmp_path / "empty", tmp_path / "out")[0] == 1
    monkeypatch.setenv("INPUT_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    for name, value in (("MAX_FIGURES", "many"), ("MAX_FIGURES", "-1"), ("WRITE_PDF", "maybe"),
                        ("DATASET_DOIS", "not-a-doi")):
        monkeypatch.setenv(name, value)
        assert M.main() == 2
        monkeypatch.delenv(name)


@pytest.mark.skipif(not weasyprint_works(), reason="WeasyPrint needs Pango (in the image); run `make test-docker`")
def test_pdf(linked: Path, tmp_path: Path) -> None:
    rc, _, rep = run(linked, tmp_path / "out", WRITE_PDF=True)
    assert rc == 0
    pdf = (rep / "report.pdf").read_bytes()
    assert pdf.startswith(b"%PDF") and len(pdf) > 20_000
