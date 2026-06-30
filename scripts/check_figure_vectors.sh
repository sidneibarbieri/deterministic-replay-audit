#!/usr/bin/env bash
# Verify that generated paper figures remain vector PDFs with embedded fonts.
set -euo pipefail

cd "$(dirname "$0")/.."

for tool in pdfimages pdffonts; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "ERROR: ${tool} is required for figure vector QA." >&2
        echo "Install poppler utilities and rerun this check." >&2
        exit 1
    fi
done

status=0

for pdf in paper/figures/*.pdf; do
    echo "== ${pdf} =="

    image_rows=$(pdfimages -list "${pdf}" | awk 'NR > 2 && NF {count++} END {print count + 0}')
    if [ "${image_rows}" -ne 0 ]; then
        echo "ERROR: ${pdf} contains ${image_rows} embedded raster image(s)." >&2
        pdfimages -list "${pdf}" >&2
        status=1
    fi

    non_embedded_fonts=$(pdffonts "${pdf}" | awk 'NR > 2 && NF && $(NF - 4) != "yes" {print}')
    if [ -n "${non_embedded_fonts}" ]; then
        echo "ERROR: ${pdf} has non-embedded fonts:" >&2
        echo "${non_embedded_fonts}" >&2
        status=1
    fi
done

if [ "${status}" -ne 0 ]; then
    exit "${status}"
fi

echo "figure vector audit OK: no embedded raster images; fonts are embedded."
