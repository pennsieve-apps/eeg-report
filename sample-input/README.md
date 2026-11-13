# Sample input

eeg-report reads the outputs of the other scalp EEG apps, not raw EEG. To get real input:

1. Stage the demo data (`workflow-scalp-eeg/scripts/fetch-sample-data.sh`): the BIDS Siena Scalp EEG Database
   (Zenodo 10.5281/zenodo.10640762, from PhysioNet 10.13026/5d4a-j060), CHB-MIT subject chb01 (PhysioNet
   10.13026/C2K01R) and OpenNeuro ds003555 v1.0.1.
2. Run eeg-prep on it, then any of eeg-seizures, eeg-spikes, eeg-spectral, eeg-sleep, eeg-connectivity on
   eeg-prep's `eeg` output. Their outputs land in `workflow-scalp-eeg/data/work/<demo>/<app>/`.
3. `make demo DEMO=siena` mounts whatever is there into the report's ports and writes
   `data/work/siena/eeg-report/{report,tables}/eeg-report/`.

Without the demo data, `make fixture` writes a small synthetic set of every app's outputs to
`data/fixture/linked/` (one folder per port) and `data/fixture/flat/` (merged), and `make run` renders it.
