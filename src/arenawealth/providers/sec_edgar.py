"""SEC EDGAR API provider.

Primary source for regulatory filings (10-K, 10-Q, 8-K).
Free, official, no API key required.
Requires User-Agent header per SEC policy.
"""

import os
from typing import Any

import httpx

from arenawealth.providers.base import QuoteError


class SECEDGARError(QuoteError):
    """SEC EDGAR specific error."""

    pass

class SECEDGARProvider:
    """SEC EDGAR API implementation.

    Primary source for 10-K, 10-Q, 8-K filings.
    Free, no API key, requires User-Agent identification.

    Usage:
        provider = SECEDGARProvider()
        filings = provider.get_company_filings("AAPL")
    """

    BASE_URL = "https://www.sec.gov/Archives/edgar"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions"
    COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts"

    def __init__(self, user_agent: str | None = None) -> None:
        """Initialize with User-Agent.

        Per SEC policy, must identify with email in User-Agent.

        Args:
            user_agent: User-Agent string with contact email.
                       Falls back to SEC_USER_AGENT env var.

        Raises:
            SECEDGARError: If no User-Agent provided.
        """
        self._user_agent = user_agent or os.getenv("SEC_USER_AGENT")
        if not self._user_agent:
            raise SECEDGARError(
                "SEC_USER_AGENT required (e.g., 'Reviewer reviewer@example.com')"
            )

        headers = {
            "User-Agent": self._user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        }

        self._client = httpx.Client(
            timeout=30.0,
            headers=headers,
        )

    def get_company_filings(self, ticker: str) -> dict[str, Any]:
        """Fetch company filing metadata.

        Args:
            ticker: Stock symbol.

        Returns:
            Filing metadata including recent and all filings.

        Raises:
            SECEDGARError: If request fails.
        """
        cik = self._get_cik(ticker)
        url = f"{self.SUBMISSIONS_URL}/CIK{cik}.json"

        response = self._client.get(url)

        if response.status_code == 404:
            raise SECEDGARError(f"CIK not found for ticker: {ticker}")

        response.raise_for_status()
        return response.json()

    def get_company_facts(self, ticker: str) -> dict[str, Any]:
        """Fetch XBRL company facts.

        Structured financial data extracted from filings.

        Args:
            ticker: Stock symbol.

        Returns:
            XBRL facts including financial statement line items.
        """
        cik = self._get_cik(ticker)
        url = f"{self.COMPANY_FACTS_URL}/CIK{cik}.json"

        response = self._client.get(url)
        response.raise_for_status()

        return response.json()

    def get_filing_content(self, accession_number: str) -> str:
        """Fetch full text of a filing.

        Args:
            accession_number: SEC accession number (e.g., "0000320193-23-000064").

        Returns:
            Filing text content.
        """
        # Convert accession number to file path
        acc_no_dashes = accession_number.replace("-", "")
        cik = acc_no_dashes[:10]

        url = (
            f"{self.BASE_URL}/edgar/data/{cik}/"
            f"{accession_number}/{acc_no_dashes}.txt"
        )

        response = self._client.get(url)
        response.raise_for_status()

        return response.text

    def _get_cik(self, ticker: str) -> str:
        """Convert ticker to CIK with padding.

        Args:
            ticker: Stock symbol.

        Returns:
            Zero-padded 10-digit CIK.
        """
        # Company CIKs would typically be loaded from a mapping file
        # This is a simplified version
        cik_map = {
            "AAPL": "0000320193",
            "MSFT": "0000789019",
            "GOOGL": "0001652044",
            "AMZN": "0001018724",
            "NVDA": "0001013480",
        }

        cik = cik_map.get(ticker.upper())
        if not cik:
            raise SECEDGARError(f"CIK mapping not found for: {ticker}")

        return cik.zfill(10)

    def close(self) -> None:
        """Close HTTP client."""
        self._client.close()
