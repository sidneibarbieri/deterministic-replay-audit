#!/usr/bin/env bash
# Create a local .env template without writing secrets.

set -euo pipefail

if [ -f .env ]; then
  backup=".env.backup.$(date +%Y%m%d_%H%M%S)"
  cp .env "$backup"
  echo "Existing .env backed up to $backup"
fi

cat > .env <<'ENV'
# ActionAudit local configuration. Do not commit this file.

# SEC EDGAR is free and only requires contact identification.
SEC_USER_AGENT="ActionAudit Reviewer user@example.com"

# Optional free API keys. Leave blank unless you want live provider checks.
FRED_API_KEY=
OPENFIGI_API_KEY=
ALPHAVANTAGE_API_KEY=
FINNHUB_API_KEY=
PATENTSVIEW_API_KEY=
OPENALEX_MAILTO=
MASSIVE_API_KEY=

# Optional alias supported by the app.
FMP_API_KEY=
FINANCIALMODELINGPREP_API_KEY=
ENV

echo "Created .env. Restart the API after editing provider keys."
