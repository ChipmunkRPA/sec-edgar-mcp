from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class CompanyInfo:
    """Company information model."""

    cik: str
    name: str
    ticker: Optional[str] = None
    sic: Optional[str] = None
    sic_description: Optional[str] = None
    exchange: Optional[str] = None
    state: Optional[str] = None
    fiscal_year_end: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cik": self.cik,
            "name": self.name,
            "ticker": self.ticker,
            "sic": self.sic,
            "sic_description": self.sic_description,
            "exchange": self.exchange,
            "state": self.state,
            "fiscal_year_end": self.fiscal_year_end,
        }


@dataclass
class FilingInfo:
    """Filing information model."""

    accession_number: str
    filing_date: datetime
    form_type: str
    company_name: str
    cik: str
    file_number: Optional[str] = None
    acceptance_datetime: Optional[datetime] = None
    period_of_report: Optional[datetime] = None
    items: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "accession_number": self.accession_number,
            "filing_date": self.filing_date.isoformat() if self.filing_date else None,
            "form_type": self.form_type,
            "company_name": self.company_name,
            "cik": self.cik,
            "file_number": self.file_number,
            "acceptance_datetime": self.acceptance_datetime.isoformat() if self.acceptance_datetime else None,
            "period_of_report": self.period_of_report.isoformat() if self.period_of_report else None,
            "items": self.items,
        }


@dataclass
class TransactionInfo:
    """Transaction information model for insider filings."""

    transaction_date: datetime
    security_title: str
    transaction_type: str
    shares: float
    price_per_share: Optional[float] = None
    total_value: Optional[float] = None
    ownership_type: Optional[str] = None
    owner_name: Optional[str] = None
    owner_title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
            "security_title": self.security_title,
            "transaction_type": self.transaction_type,
            "shares": self.shares,
            "price_per_share": self.price_per_share,
            "total_value": self.total_value,
            "ownership_type": self.ownership_type,
            "owner_name": self.owner_name,
            "owner_title": self.owner_title,
        }
