#!/bin/bash
# Build the six interiors until every cross-volume page reference is stable.
#
# Build order: references go both ways between volumes (vol. 1 cites the
# Twelve Virtues in vol. 5, vol. 5 cites vol. 1, ...), so one volume cannot
# be finished before the others.  Each pass compiles vol1..vol6 in order;
# every volume reads the other volumes' .aux files (zref-xr) from the
# previous pass.  Inserted references can move page breaks, so passes are
# repeated until no .aux file changes (normally 3 passes).
set -euo pipefail
PAPER=${PAPER:-royal}
VOLS=${VOLS:-"1 2 3 4 5 6"}
MAXPASS=${MAXPASS:-6}
OUT=build/tex
mkdir -p "$OUT"
export TEXINPUTS=.:print//:

compile() {
  local v=$1
  if ! lualatex -interaction=nonstopmode -halt-on-error -output-directory="$OUT" \
      -jobname="vol$v" "\def\PaperName{$PAPER}\def\VolNum{$v}\input{print/volume.tex}" \
      > "$OUT/vol$v.stdout" 2>&1; then
    echo "lualatex failed for vol$v, see $OUT/vol$v.log" >&2
    grep -E '^!' -A6 "$OUT/vol$v.log" >&2 || true
    exit 1
  fi
}

sums() { for v in $VOLS; do md5sum "$OUT/vol$v.aux" 2>/dev/null || echo none; done; }

prev=""
for pass in $(seq 1 "$MAXPASS"); do
  for v in $VOLS; do compile "$v"; done
  cur=$(sums)
  rerun=$(grep -l 'Rerun to get\|Label(s) may have changed' $(for v in $VOLS; do echo "$OUT/vol$v.log"; done) || true)
  echo "pass $pass done${rerun:+ (rerun requested: $rerun)}"
  if [ "$cur" = "$prev" ] && [ -z "$rerun" ]; then
    echo "cross references stable after $pass passes"
    undef=$(grep -h 'Reference .* undefined' $(for v in $VOLS; do echo "$OUT/vol$v.log"; done) || true)
    if [ -n "$undef" ]; then
      echo "undefined references:" >&2; echo "$undef" >&2; exit 1
    fi
    exit 0
  fi
  prev=$cur
done
echo "cross references did not converge after $MAXPASS passes" >&2
exit 1
