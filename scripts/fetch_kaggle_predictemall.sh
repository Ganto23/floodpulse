#!/usr/bin/env bash
# Downloads Kaggle "Predict'em All" (semioniy/predictemall): 296,021 real Pokémon GO
# spawn sightings, 2016-09-02..08, ~208 columns. ~146 MB zip -> 402 MB CSV.
# Public dataset; Kaggle currently serves it without auth. If that changes, use:
#   pip install kaggle && kaggle datasets download semioniy/predictemall -f 300k.csv
set -euo pipefail
DEST="$(cd "$(dirname "$0")/.." && pwd)/data/raw/kaggle_predictemall"
mkdir -p "$DEST"
if [[ -s "$DEST/300k.csv" ]]; then echo "already present: $DEST/300k.csv"; exit 0; fi
curl -fL --progress-bar -o "$DEST/archive.zip" \
  "https://www.kaggle.com/api/v1/datasets/download/semioniy/predictemall"
unzip -o -q -j "$DEST/archive.zip" "300k.csv" -d "$DEST"
rm "$DEST/archive.zip"
echo "ok: $DEST/300k.csv ($(wc -l < "$DEST/300k.csv") lines)"
