# eeg-report

This app writes the report at the end of the scalp EEG workflows. **The analyses in it are other people's
methods, packaged as Pennsieve apps; the report credits them**: each step's section names what the step does and
the References list the works each step cites (full author lists from the apps' CITATION.cff files, verified
against Crossref, DataCite and PubMed). The report itself is rendered with
[WeasyPrint](https://github.com/Kozea/WeasyPrint) (created by Simon Sapin, maintained by CourtBouillon),
[Jinja](https://github.com/pallets/jinja) (Pallets) and [Pillow](https://github.com/python-pillow/Pillow)
(Jeffrey A. Clark and contributors). **Pennsieve built the report; it did not develop the methods it reports
on.** The demo reports were made from the Siena Scalp EEG Database (Paolo Detti and colleagues, University of
Siena; BIDS conversion by Jonathan Dan and colleagues, EPFL), the CHB-MIT Scalp EEG Database (Ali Shoeb and John
Guttag, MIT, with Children's Hospital Boston) and OpenNeuro ds003555 (Dorottya Cserpan, Johannes Sarnthein and
colleagues, University Hospital Zurich); see [Citations](#citations).

The last step of both scalp EEG workflows:

- **Scalp EEG Interictal Biomarkers:** `eeg-prep → {eeg-spectral, eeg-connectivity, eeg-sleep → eeg-spikes} → eeg-report`
- **Scalp EEG Seizure Detection & Monitoring:** `eeg-prep → {eeg-seizures, eeg-sleep → eeg-spikes} → eeg-report`

**For an epileptologist or neurologist.** Link the outputs of the steps you ran and you get one report you can
read, keep with the data and send to a colleague: an HTML page that opens offline and the same report as a PDF.
It opens with a box saying what everything in it is: **research output, not a clinical interpretation**. Then:

1. **Recordings**: every recording eeg-prep read (duration, kind, montage, good channels, annotated seizures, age,
   sex, and any recording-level label such as an annotated lateralisation), which steps have results for it, and
   an **at-a-glance** table with one headline number per step per recording.
2. **Data quality**: per recording the bad channels by name, the ICA components removed and what ICLabel called
   them (eye blink, muscle, ...), the share of variance they carried, and the percentage of the recording marked
   as bad segments; plus eeg-prep's QC figures.
3. One section per linked step, in workflow order, each starting with the step's own **method caveat** (its
   summary.json `notice`, in a box) and any **licence notice** (also gathered at the top of the report):
   - **Seizure detection**: event-based and sample-based **sensitivity, precision, F1 and false detections per
     day, side by side** (SzCORE scoring), pooled and per subject, and per recording the candidates, the
     annotated seizures found and the false detections. Always labelled as candidates for review.
   - **Interictal spikes**: event rate, top channel, left/right/midline events and the laterality index, labelled
     as **the side with more detected events** (never as a localisation), next to the annotated side when the
     source data has one; rates per sleep stage when a hypnogram was linked.
   - **Spectral biomarkers**: posterior dominant rhythm (frequency, amplitude, asymmetry, what it was measured
     on), revised Brain Symmetry Index, aperiodic exponent, theta/alpha ratio.
   - **Sleep**: hypnogram statistics (TST, sleep efficiency, latency, WASO, stage percentages, staging
     confidence, spindle and slow-wave densities).
   - **Connectivity**: hemispheric asymmetry per band and measure, mean connectivity.
   - Every figure the step chose, in its order, with **the caption the step wrote** (each says what to look at);
     the step's **warnings** (identical per-recording warnings said once, with the recordings); recordings it
     skipped and why; the tables it wrote; its parameters.
4. Methods (a sentence per step you can adapt), software versions, run times and memory, References,
   Acknowledgements (upstream software and datasets) and how to cite.

**For a researcher.** The report reads only the shared contract of `workflow-scalp-eeg/docs/conventions.md`:
eeg-prep's BIDS derivative (`recordings.csv`, `dataset_description.json`, `provenance.json`; the EDF files are
never opened) and each app's top folder `<app>/` (or `<app>/<LABEL>/`) with `provenance.json` and `summary.json`
(`recordings` keyed by recording id, `figures` `[{path, caption}]`, `tables`, `warnings`, optional `notice`).
Everything is found by file name and content, recursively, following symlinks: ports in their own folders,
everything merged at the input root, or any mix. Figure and table paths are taken relative to the app's top
folder (paths relative to the port folder are accepted too); absolute paths and `..` are never followed. The
known apps get a curated headline table (columns whose keys no recording has are dropped, so a renamed key
loses a column, not the section); any other app, or a known app whose keys all changed, is rendered generically
from its numeric per-recording values. Numbers are copied, never recomputed: integers exactly, rates to two
decimals, other numbers to four significant digits, 0-1 fractions (sensitivity, precision) as percentages.
DOIs in each step's `provenance.citations` are resolved from a citation table bundled at build time
(`processor/references.json`, written by `scripts/build_citations.py` from the sibling apps' verified
CITATION.cff files and, for any other DOI the steps cite, from Crossref/DataCite/PubMed); a DOI not in it is
listed DOI-only, never filled in at run time (the app has no network). Where a step's output departs from the
contract (a figure listed but missing or unreadable, no caption, no summary.json, a top folder not named after
the app) the report still renders what it can and lists the problem under "Notes on the inputs".

## Ports

| Port | Direction | Content |
|---|---|---|
| `eeg` | in (required) | eeg-prep's `eeg` output: `recordings.csv`, `dataset_description.json`, `provenance.json` (the EDF files are not read). |
| `qc` | in (optional) | eeg-prep's `qc` output: `eeg-prep/qc.csv`, `summary.json`, `provenance.json`, figures. Without it the QC table is built from the derivative's provenance.json (no QC figures). |
| `seizures` | in (optional) | eeg-seizures: `eeg-seizures/summary.json` (`recordings`, `pooled` scores), `seizures.csv`, `scores.csv`, `probability.csv`, `szcore/`, figures. |
| `spikes` | in (optional) | eeg-spikes: `eeg-spikes/summary.json`, `spike_rates.csv`, `spike_events.csv`, `lateralisation.csv`, `rates_by_stage.csv`, figures. |
| `spectral` | in (optional) | eeg-spectral: `eeg-spectral/summary.json`, `bandpower.csv`, `aperiodic.csv`, `pdr.csv`, `asymmetry.csv`, ... figures. |
| `sleep` | in (optional) | eeg-sleep: `eeg-sleep/summary.json`, `hypnogram.csv`, `sleep_stats.csv`, `spindles.csv`, `slow_waves.csv`, figures. |
| `connectivity` | in (optional) | eeg-connectivity: `eeg-connectivity/summary.json`, `connectivity.csv`, `node_strength.csv`, `graph.csv`, `hemisphere.csv`, figures. |
| `report` | out | `eeg-report/index.html`, `report.pdf`, `figures/<step>/*.png`, `summary.json`, `provenance.json`. |
| `tables` | out | `eeg-report/`: `recordings.csv`, `overview.csv`, `headline.csv`, `qc_summary.csv`, `seizure_scores.csv`, `<step>/<every table the step wrote>`, `provenance.json`. |

All inputs use `placement: subfolder`; an app linked twice under different `LABEL`s gets two sections
("Spectral biomarkers (raw)", "... (clean)") and separate figure and table folders.

## Parameters

| Name | Default | What it does |
|---|---|---|
| `REPORT_TITLE` | empty | Title. Empty: "Scalp EEG report". |
| `MAX_FIGURES` | `40` | Figures shown per step in the page and the PDF, in the step's order. The rest are copied next to the page and linked from it. `0` shows none. |
| `DATASET_DOIS` | empty | DOIs of the datasets analysed (comma-separated), credited and cited. eeg-prep's `dataset_description.json` `SourceDatasets` are read without this; the demo datasets' companion papers (Detti 2020 and Goldberger 2000 for Siena, Cserpan 2021 for ds003555) are cited with them. |
| `WRITE_PDF` | `true` | Also write `report.pdf`. |

## Outputs

`OUTPUT_DIR/report/eeg-report/`:

- `index.html`: inline CSS, no scripts, nothing loaded from elsewhere (DOIs and repositories are plain links);
  figures are PNG files in `figures/<step>/` next to it, so keep the folder together. Long warning lists show
  the first eight and fold the rest.
- `report.pdf`: the same content on A4 (WeasyPrint, DejaVu fonts), everything unfolded, figures converted to
  JPEG at most 1200 px wide so a report with 210 figures stays near 25 MB; every page footer repeats "research
  output, not a clinical interpretation".
- `summary.json` (recordings with the steps that cover them, counts, warnings) and `provenance.json`
  (conventions.md keys).

`OUTPUT_DIR/tables/eeg-report/`:

- `recordings.csv`: eeg-prep's recordings.csv (all linked derivatives, all columns).
- `overview.csv`: the at-a-glance table as numbers (`recording_id`, `<app>:<key>` ...).
- `headline.csv`: every scalar per-recording value of every step's summary.json, long format
  (`recording_id, step, metric, value`; nested values such as rates per stage as `metric.key`).
- `qc_summary.csv`: the data-quality table. `seizure_scores.csv`: the pooled seizure scores.
- `<step>/...`: a copy of every CSV/TSV each step wrote (eeg-seizures' `szcore/` included), keeping its layout.
- `provenance.json`.

Exit codes: `0` ok; `1` nothing to report on (no step output and no recordings.csv), or the PDF could not be
written (the page, tables and JSON are written first, and the error is logged and listed in summary.json);
`2` bad parameters.

## Runtime

`cpu: 1024`, `memory: 2048` MiB, `computeTypes: [standard]`, `timeoutSeconds: 900`: within the Lambda limits, so
the platform can run it as a Lambda step; it is Lambda-safe (writes only `OUTPUT_DIR` and `TMPDIR`, makes
`HOME`/`TMPDIR` when missing, keeps the fontconfig cache in the image's read-only `/var/cache/fontconfig` and any
run-time cache under `$TMPDIR`, runs as any uid). Measured in the image (linux/amd64 under emulation on an
M-series Mac), read-only root, uid 65534, `--memory 2g`, `--network none`:

| Input | Steps | Recordings | Figures shown | Wall time | Peak RSS | cgroup memory.peak | PDF |
|---|---|---|---|---|---|---|---|
| Siena demo (`scripts/run_demo.sh siena`) | all six | 41 (eeg-sleep: 35, six recordings < 60 min skipped by design) | 214 | 17 s | 265 MB | 622 MB | 25 MB, 173 pages |
| CHB-MIT chb01 demo | all six | 42 (eeg-sleep: 39) | 211 | 16 s | 242 MB | 508 MB | 26 MB, 183 pages |
| ds003555 demo | eeg-prep, eeg-sleep, eeg-spikes, eeg-spectral, eeg-connectivity | 3 | 42 | 3.5 s | 152 MB | – | 4 MB, 36 pages |
| Synthetic fixture | all six | 3 | 15 | 2.4 s | 106 MB | 98 MB | 0.3 MB |

Memory grows with the largest figure and the PDF's layout, not with the EEG: the report never opens an EDF.
Image: 297 MB, 71 MB compressed. Output size is dominated by the copied figures and tables (Siena: 155 MB
report folder with every figure, 95 MB of tables, most of it eeg-seizures' per-second `probability.csv` and
eeg-spikes' `spikes.csv`).

## Limitations

- It reports what the steps wrote. It does not check that a number is right, re-run a statistic or compare
  recordings; a wrong caption or number upstream is a wrong caption or number in the report.
- The at-a-glance table uses the first `LABEL` of an app that is linked more than once.
- Datasets are credited only when eeg-prep's `dataset_description.json` names them, when given in
  `DATASET_DOIS`, or (CHB-MIT) when the recording ids are CHB-MIT's.
- A cited DOI that is not in the bundled table is shown DOI-only; rebuild the table (`make citations`) after a
  sibling app adds a citation.
- Wide tables in the PDF use a small font; the HTML page scrolls them instead.

## Development

```
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
make test        # pytest on the synthetic fixture (tests/make_fixture.py); the PDF test needs Pango
make run         # the image over the fixture, read-only, uid 65534, no network
make demo DEMO=siena
make citations validate verify
```

`tests/make_fixture.py` writes an eeg-prep derivative (with a tiny EDF+) and every app's outputs for three
recordings (two referential, one bipolar-only), in the `linked` (one folder per port) and `flat` (merged)
layouts; it needs only the Python standard library (it is also the release review's input generator). The tests
cover both layouts, symlinked ports, every subset of steps, only the eeg port, a step without eeg-prep, missing
and corrupt figures, a step with zero recordings, the same app under two LABELs, unsafe figure paths, invalid
JSON, a previous report linked back in, and bad parameters.

## Licences

Apache-2.0 (this app). Bundled components and their licences are in [THIRD_PARTY.md](THIRD_PARTY.md): Jinja and
MarkupSafe (BSD-3-Clause), WeasyPrint and its CourtBouillon libraries (BSD-3-Clause), Pillow (MIT-CMU),
fontTools (MIT), Pyphen (code only, used under its MPL 1.1 option; its dictionaries are removed), and the Debian
Pango/HarfBuzz/fontconfig/FreeType/GLib libraries and DejaVu fonts. The figures, numbers and tables in a report
belong to the steps that made them and to the data's licence (Siena BIDS: CC BY 4.0; CHB-MIT: ODC-By 1.0;
ds003555: CC0; Siena on PhysioNet: CC BY 4.0).

## Citations

The report adds no method of its own; cite the works of each step, which the report lists under "How to cite".
For the demo reports, please cite these works if you use this app's demo output. Verified on Crossref/DataCite
and PubMed; full author lists in CITATION.cff.

- Detti P. Siena Scalp EEG Database. PhysioNet 2020. doi:[10.13026/5d4a-j060](https://doi.org/10.13026/5d4a-j060)
- Detti P, Vatti G, Zabalo Manrique de Lara G. EEG Synchronization Analysis for Seizure Prediction: A Study on
  Data of Noninvasive Recordings. Processes 2020;8(7):846. doi:[10.3390/pr8070846](https://doi.org/10.3390/pr8070846)
- Dan J, Detti P. BIDS Siena Scalp EEG Database. EPFL 2024. doi:[10.5281/zenodo.10640762](https://doi.org/10.5281/zenodo.10640762)
- Shoeb A. CHB-MIT Scalp EEG Database. PhysioNet 2010. doi:[10.13026/C2K01R](https://doi.org/10.13026/C2K01R)
- Goldberger AL, Amaral LAN, Glass L, Hausdorff JM, Ivanov PCh, Mark RG, Mietus JE, Moody GB, Peng C-K, Stanley
  HE. PhysioBank, PhysioToolkit, and PhysioNet. Circulation 2000;101(23):e215-e220.
  doi:[10.1161/01.CIR.101.23.e215](https://doi.org/10.1161/01.CIR.101.23.e215), PMID 10851218
- Cserpan D, Boran E, Rosch R, Lo Biundo SP, Ramantani G, Sarnthein J. Dataset of EEG recordings of pediatric
  patients with epilepsy based on the 10-20 system. OpenNeuro 2021.
  doi:[10.18112/openneuro.ds003555.v1.0.1](https://doi.org/10.18112/openneuro.ds003555.v1.0.1)
- Cserpan D, Boran E, Lo Biundo SP, Rosch R, Sarnthein J, Ramantani G. Scalp high-frequency oscillation rates are
  higher in younger children. Brain Communications 2021;3(2):fcab052.
  doi:[10.1093/braincomms/fcab052](https://doi.org/10.1093/braincomms/fcab052), PMID 33870193
- Software: WeasyPrint (Simon Sapin; CourtBouillon), https://github.com/Kozea/WeasyPrint; Jinja (Pallets),
  https://github.com/pallets/jinja; Pillow (Jeffrey A. Clark and contributors),
  https://github.com/python-pillow/Pillow.

## Acknowledgements

The methods in every report are those of the upstream projects each step packages (MNE-Python, pyprep,
mne-icalabel and ICLabel, specparam, epycom, timescoring and SzCORE, YASA, mne-connectivity, networkx; see each
app's README). The demo data come from PhysioNet (Siena, CHB-MIT), the EPFL BIDS conversions of SzCORE, and
OpenNeuro (ds003555).
