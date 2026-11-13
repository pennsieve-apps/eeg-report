"""
What the report knows about the scalp EEG apps: their order in the workflows, a title, a paragraph
on what each does (for an epileptologist), a methods sentence, and which of their summary.json
per-recording numbers are the headline numbers.

Everything else about a step (its figures and captions, warnings, numbers) is read from its own
summary.json and provenance.json; an app that is not listed here is rendered generically.

Headline columns are (label, key, kind); kind is how the number is written: `int`, `num` (four
significant digits), `rate` (two decimals), `pct` (a 0-1 fraction as a percentage), `dur` (seconds
as a duration), `text`. Columns whose key no recording has are left out, so an app that renames a
key loses one column, not the section; when none of them is present the section falls back to the
generic table.
"""
from __future__ import annotations

WORKFLOWS = {
    "Scalp EEG Interictal Biomarkers": ["eeg-prep", "eeg-spectral", "eeg-connectivity", "eeg-sleep", "eeg-spikes"],
    "Scalp EEG Seizure Detection & Monitoring": ["eeg-prep", "eeg-seizures", "eeg-sleep", "eeg-spikes"],
}

ORDER = ["eeg-prep", "eeg-seizures", "eeg-spikes", "eeg-spectral", "eeg-sleep", "eeg-connectivity"]

# Input port of each app (conventions.md, Ports).
PORT = {"eeg-seizures": "seizures", "eeg-spikes": "spikes", "eeg-spectral": "spectral", "eeg-sleep": "sleep",
        "eeg-connectivity": "connectivity"}

RESEARCH = ("Research output, to be reviewed by a clinician against the EEG; not a clinical EEG "
            "interpretation.")

APPS: dict[str, dict] = {
    "eeg-prep": {
        "title": "Data quality (preprocessing)",
        "short": "QC",
        "about": (
            "eeg-prep read each recording, kept the EEG channels with their 10-20 names, found bad channels "
            "(pyprep, after the PREP pipeline), filtered (notch at the mains frequency, high-pass), re-referenced, "
            "removed artifact components with ICA and ICLabel (eye, muscle, heart, line and channel noise) and "
            "marked bad segments (very high amplitude, flat signal, muscle bursts). Every later step leaves the bad "
            "segments out (seizure detection keeps them: ictal activity can exceed the amplitude limit). A recording "
            "with several bad channels, a large share of bad segments or many removed components deserves a look "
            "at its own QC figure before its results are interpreted."),
        "methods": (
            "Recordings were preprocessed with eeg-prep: EEG channels kept and named in the 10-20 system, bad "
            "channels detected with pyprep's NoisyChannels (deviation, correlation, high-frequency noise, RANSAC), "
            "notch and high-pass filtering, re-referencing, ICA with ICLabel classification of artifact components, "
            "and amplitude, flat-signal and muscle bad-segment detection"),
        "headline": [],  # its own QC table (model.qc_section)
    },
    "eeg-seizures": {
        "title": "Seizure detection (candidates for review)",
        "short": "Seizures",
        "about": (
            "eeg-seizures marks candidate seizures with a line-length detector (Esteller et al. 2001) on the 10-20 "
            "channels, writes them in the SzCORE event format and, where seizures are annotated, scores them with "
            "SzCORE's event- and sample-based rules (Dan et al. 2024). Detections are candidates for an expert to "
            "review, not a diagnosis. Sensitivity says how many annotated seizures were found; false detections per "
            "day say how much review the candidates cost: the two are always shown together."),
        "methods": (
            "Candidate seizures were detected with eeg-seizures (per-channel line length, normalised to a rolling "
            "baseline, combined across channels and thresholded with hysteresis) and scored against the annotated "
            "seizures with the SzCORE framework's event- and sample-based scoring (timescoring)"),
        "headline": [
            ("Hours", "duration_h", "num"),
            ("Montage", "montage", "text"),
            ("Annotated seizures", "n_annotated_seizures", "int"),
            ("Candidates", "n_detections", "int"),
            ("Annotated seizures detected", "seizures_detected", "int"),
            ("False detections", "false_detections", "int"),
            ("Sensitivity (event)", "event_sensitivity", "pct"),
            ("Precision (event)", "event_precision", "pct"),
            ("F1 (event)", "event_f1", "num"),
            ("False detections / day", "event_fp_per_day", "rate"),
            ("F1 (sample)", "sample_f1", "num"),
        ],
    },
    "eeg-spikes": {
        "title": "Interictal spikes",
        "short": "Spikes",
        "about": (
            "eeg-spikes detects interictal epileptiform discharges (spikes) on the longitudinal bipolar montage with "
            "detectors developed and validated on intracranial EEG (Janca et al. 2015; Barkmeier et al. 2012), "
            "merges spikes within 50 ms across channels into one event with its leading channel, and gives rates per "
            "channel, the side with more detected events (laterality index) and, when a hypnogram is linked, rates per sleep stage. Rates and "
            "lateralisation are research outputs to review against the EEG; automatic detectors also count sharp "
            "transients and artifacts that a reader would not call spikes. The laterality index says on which side "
            "more events were detected; it is not a localisation of the epileptogenic zone."),
        "methods": (
            "Interictal spikes were detected with eeg-spikes on the longitudinal bipolar montage (epycom detectors "
            "developed on intracranial EEG), merged across channels into events, and summarised as rates, laterality "
            "index (left − right) / (left + right) and rates per sleep stage"),
        "headline": [
            ("Minutes analysed", "minutes_analysed", "num"),
            ("Montage", "montage", "text"),
            ("Spike events", "n_events", "int"),
            ("Events / min", "events_per_min", "rate"),
            ("Top channel", "top_channel", "text"),
            ("Top channel rate / min", "top_channel_rate_per_min", "rate"),
            ("Left events", "n_left", "int"),
            ("Right events", "n_right", "int"),
            ("Midline events", "n_midline", "int"),
            ("Laterality index (side with more detected events)", "laterality_index", "num"),
            ("Annotated side", "@lateralisation", "text"),  # from recordings.csv, when the source has it
            ("Region with most detected events", "dominant_region", "text"),
            ("NREM / wake rate", "nrem_wake_ratio", "num"),
        ],
        "by_stage": "events_per_min_by_stage",
    },
    "eeg-spectral": {
        "title": "Spectral biomarkers",
        "short": "Spectral",
        "about": (
            "eeg-spectral computes power spectra of the artifact-free EEG outside seizures: band power, the "
            "aperiodic (1/f) exponent with specparam (Donoghue et al. 2020), the posterior dominant rhythm (PDR; "
            "Lodder & van Putten 2011) with its left-right asymmetry, the revised Brain Symmetry Index (rBSI; 0 = "
            "symmetric, van Putten 2007) and slowing ratios. Without an eyes-closed annotation the PDR is measured "
            "on all artifact-free EEG, which may include drowsiness or sleep."),
        "methods": (
            "Spectral biomarkers were computed with eeg-spectral: Welch spectra (4 s Hamming windows, 50 % overlap) "
            "on artifact-free windows, band powers, aperiodic exponent with specparam, posterior dominant rhythm, "
            "revised Brain Symmetry Index and slowing ratios"),
        "headline": [
            ("Analysed", "seconds_analysed", "dur"),
            ("Montage", "montage", "text"),
            ("PDR (Hz)", "pdr_hz", "rate"),
            ("PDR amplitude (µV)", "pdr_amplitude_uv", "num"),
            ("PDR asymmetry", "pdr_asymmetry", "num"),
            ("PDR reactivity", "pdr_reactivity", "num"),
            ("PDR measured on", "pdr_basis", "text"),
            ("rBSI", "rbsi", "num"),
            ("rBSI signed (L−R)", "rbsi_signed", "num"),
            ("Aperiodic exponent (median)", "aperiodic_exponent_median", "num"),
            ("Theta/alpha (median)", "theta_alpha_ratio_median", "num"),
            ("Posterior relative alpha", "relpow_alpha_posterior", "num"),
            ("Channels with fit r² < 0.9", "low_r_squared_channels", "int"),
        ],
    },
    "eeg-sleep": {
        "title": "Sleep",
        "short": "Sleep",
        "about": (
            "eeg-sleep stages 30-s epochs automatically with YASA (Vallat & Walker 2021) on one central EEG channel "
            "(EEG only: eeg-prep does not keep EOG and EMG, which lowers the accuracy compared with full "
            "polysomnography), gives sleep statistics, and detects spindles and slow waves in N2/N3. Recordings "
            "shorter than an hour are skipped. The hypnogram is a research output, not a clinical sleep scoring: "
            "review it against the EEG, in particular in children under five and in low-confidence stretches."),
        "methods": (
            "Sleep was staged with eeg-sleep (YASA, EEG-only, 30-s epochs), with sleep statistics and spindle and "
            "slow-wave detection on N2/N3"),
        "headline": [
            ("Hours", "duration_h", "num"),
            ("TST (min)", "TST_min", "num"),
            ("Sleep efficiency (%)", "SE_pct", "num"),
            ("Sleep onset latency (min)", "SOL_min", "num"),
            ("WASO (min)", "WASO_min", "num"),
            ("N1 (%)", "N1_pct", "num"),
            ("N2 (%)", "N2_pct", "num"),
            ("N3 (%)", "N3_pct", "num"),
            ("REM (%)", "REM_pct", "num"),
            ("Mean staging confidence (%)", "confidence_mean_pct", "num"),
            ("Spindles", "n_spindles", "int"),
            ("Spindle density, central (/min of N2/N3)", "spindle_density_central", "num"),
            ("Slow-wave density, frontal (/min of N2/N3)", "sw_density_frontal", "num"),
        ],
    },
    "eeg-connectivity": {
        "title": "Functional connectivity",
        "short": "Connectivity",
        "about": (
            "eeg-connectivity computes sensor-level functional connectivity per frequency band (weighted phase lag "
            "index, imaginary coherence, orthogonalised amplitude envelope correlation), graph measures, and the "
            "hemispheric asymmetry of connectivity: (left − right) / (left + right) of the mean connectivity within "
            "each hemisphere. The asymmetry is a sensor-level proxy of the network asymmetry studied for "
            "lateralising temporal lobe epilepsy (Verhoeven et al. 2018); it has not been validated for "
            "lateralisation. On bipolar-only recordings neighbouring derivations share electrodes, so values are not "
            "comparable with referential recordings."),
        "methods": (
            "Functional connectivity was computed with eeg-connectivity (mne-connectivity) on 4-s artifact-free "
            "epochs, with graph measures (networkx) at a proportional threshold and hemispheric means and asymmetry"),
        "headline": [
            ("Analysed", "seconds_analysed", "dur"),
            ("Montage", "montage", "text"),
            ("Epochs used", "epochs_used", "int"),
        ],
        "measures": ["wpli", "imcoh", "aec", "envcorr", "coh", "pli", "plv"],
        "measure_names": {"wpli": "wPLI", "imcoh": "imaginary coherence", "aec": "envelope correlation",
                          "envcorr": "envelope correlation", "coh": "coherence", "pli": "PLI", "plv": "PLV"},
    },
}

# One row per recording across the steps: what an epileptologist looks at first.
# (label, app, key, kind)
GLANCE = [
    ("Bad segments (%)", "eeg-prep", "bad_segment_pct", "num"),
    ("Bad channels", "eeg-prep", "n_bad_channels", "int"),
    ("Annotated seizures", "eeg-seizures", "n_annotated_seizures", "int"),
    ("Seizures detected", "eeg-seizures", "seizures_detected", "int"),
    ("False detections", "eeg-seizures", "false_detections", "int"),
    ("Spike events / min", "eeg-spikes", "events_per_min", "rate"),
    ("Spike laterality index (side with more detected events)", "eeg-spikes", "laterality_index", "num"),
    ("PDR (Hz)", "eeg-spectral", "pdr_hz", "rate"),
    ("rBSI", "eeg-spectral", "rbsi", "num"),
    ("Aperiodic exponent", "eeg-spectral", "aperiodic_exponent_median", "num"),
    ("TST (min)", "eeg-sleep", "TST_min", "num"),
    ("N3 (%)", "eeg-sleep", "N3_pct", "num"),
    ("wPLI alpha asymmetry", "eeg-connectivity", "wpli_alpha_asymmetry", "num"),
]

# Known datasets: who made them, their licence (as conventions.md and the data README give them),
# and the works their authors ask to be cited with them.
DATASETS = {
    "10.13026/5d4a-j060": {"credit": "Paolo Detti and colleagues, University of Siena", "licence": "",
                           "with": ["10.3390/pr8070846", "10.1161/01.cir.101.23.e215"]},
    "10.5281/zenodo.10640762": {"credit": "BIDS conversion by Jonathan Dan and colleagues, EPFL", "licence": "CC BY 4.0",
                                "with": ["10.13026/5d4a-j060", "10.3390/pr8070846", "10.1161/01.cir.101.23.e215"]},
    "10.13026/c2k01r": {"credit": "Ali Shoeb and John Guttag, MIT, with Children's Hospital Boston",
                        "licence": "ODC-By 1.0", "with": ["10.1161/01.cir.101.23.e215"]},
    "10.5281/zenodo.10259996": {"credit": "BIDS conversion by Jonathan Dan and colleagues, EPFL", "licence": "",
                                "with": ["10.13026/c2k01r", "10.1161/01.cir.101.23.e215"]},
    "10.18112/openneuro.ds003555.v1.0.1": {"credit": "Dorottya Cserpan, Johannes Sarnthein and colleagues, "
                                                     "University Hospital Zurich", "licence": "CC0",
                                           "with": ["10.1093/braincomms/fcab052"]},
}
# Dataset names in eeg-prep's dataset_description.json SourceDatasets that imply a DOI.
DATASET_NAMES = [("bids siena", "10.5281/zenodo.10640762"), ("siena scalp eeg", "10.13026/5d4a-j060"),
                 ("bids chb-mit", "10.5281/zenodo.10259996"), ("chb-mit", "10.13026/c2k01r")]
# Recording ids that identify a demo dataset when nothing else names it (loose CHB-MIT EDFs).
DATASET_IDS = [(r"^sub-chb\d{2}_", "10.13026/c2k01r")]
