#!/bin/sh
# Run the image on a demo's real step outputs, as the platform would (read-only root, any uid,
# no network, HOME/TMPDIR under /tmp, 2 GB), and write data/work/<demo>/eeg-report/{report,tables}.
#
#   scripts/run_demo.sh siena            (or chbmit, ds003555)
#
# Each step found under data/work/<demo>/ is mounted at its port folder; steps not there yet are
# left out (the report renders whatever is linked). Prints the cgroup peak memory at the end.
set -eu
DEMO=${1:?usage: run_demo.sh <demo>}
DATA=${DATA:-$(cd "$(dirname "$0")/../../workflow-scalp-eeg/data/work" && pwd)}
W="$DATA/$DEMO"
OUT=${OUT:-$W/eeg-report}
IMAGE=${IMAGE:-eeg-report:dev}
mkdir -p "$OUT"
set -- --rm --platform linux/amd64 --read-only --user 65534:65534 --tmpfs /tmp:mode=1777 --network none \
  --memory 2g -e HOME=/tmp/w/home -e TMPDIR=/tmp/w/tmp -e INPUT_DIR=/tmp/s/input -e OUTPUT_DIR=/tmp/s/output \
  -v "$OUT":/tmp/s/output
[ -d "$W/eeg-prep/eeg" ] && set -- "$@" -v "$W/eeg-prep/eeg":/tmp/s/input/eeg:ro
[ -d "$W/eeg-prep/qc" ] && set -- "$@" -v "$W/eeg-prep/qc":/tmp/s/input/qc:ro
for pair in seizures:eeg-seizures spikes:eeg-spikes spectral:eeg-spectral sleep:eeg-sleep connectivity:eeg-connectivity; do
  port=${pair%%:*}; app=${pair#*:}
  [ -d "$W/$app" ] || continue
  # The demo folder is either the port (holding <app>/) or the app's top folder itself.
  if [ -d "$W/$app/$app" ]; then set -- "$@" -v "$W/$app":/tmp/s/input/$port:ro
  else set -- "$@" -v "$W/$app":/tmp/s/input/$port/$app:ro; fi
done
docker run "$@" --entrypoint sh "$IMAGE" -c 'python3 -m processor.main; rc=$?; echo "cgroup memory.peak $(cat /sys/fs/cgroup/memory.peak 2>/dev/null) bytes"; exit $rc'
