from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, date
from ..core.client import EdgarClient
from ..utils.exceptions import FilingNotFoundError
from .types import ToolResponse


class InsiderTools:
    """Tools for insider trading data (Forms 3, 4, 5) - simplified version."""

    def __init__(self):
        self.client = EdgarClient()

    def get_insider_transactions(
        self, identifier: str, form_types: Optional[List[str]] = None, days: int = 90, limit: int = 50
    ) -> ToolResponse:
        """Get insider transactions for a company."""
        try:
            company = self.client.get_company(identifier)

            # Default to all insider forms
            if not form_types:
                form_types = ["3", "4", "5"]

            # Get insider filings
            filings = company.get_filings(form=form_types)

            transactions = []
            count = 0

            for filing in filings:
                if count >= limit:
                    break

                # Check date filter
                filing_date = filing.filing_date

                # Convert to datetime object for comparison
                if isinstance(filing_date, str):
                    filing_date = datetime.fromisoformat(filing_date.replace("Z", "+00:00"))
                elif isinstance(filing_date, date) and not isinstance(filing_date, datetime):
                    # It's a date object, convert to datetime
                    filing_date = datetime.combine(filing_date, datetime.min.time())

                # Ensure we have a datetime object
                if not isinstance(filing_date, datetime):
                    continue

                if (datetime.now() - filing_date).days > days:
                    continue

                try:
                    # Basic transaction info from filing with proper SEC URL
                    transaction_info = {
                        "filing_date": filing.filing_date.isoformat(),
                        "form_type": filing.form,
                        "accession_number": filing.accession_number,
                        "company_name": filing.company,
                        "cik": filing.cik,
                        "url": filing.url,
                        "sec_url": f"https://www.sec.gov/Archives/edgar/data/{filing.cik}/{filing.accession_number.replace('-', '')}/{filing.accession_number}.txt",
                        "data_source": f"SEC EDGAR Filing {filing.accession_number}, extracted directly from insider filing data",
                    }

                    # Try to get more details if available
                    try:
                        ownership = filing.obj()
                        if ownership:
                            # Extract basic ownership info
                            if hasattr(ownership, "owner_name"):
                                transaction_info["owner_name"] = ownership.owner_name
                            if hasattr(ownership, "owner_title"):
                                transaction_info["owner_title"] = ownership.owner_title
                            if hasattr(ownership, "is_director"):
                                transaction_info["is_director"] = ownership.is_director
                            if hasattr(ownership, "is_officer"):
                                transaction_info["is_officer"] = ownership.is_officer
                    except Exception:
                        pass

                    transactions.append(transaction_info)
                    count += 1
                except Exception:
                    continue

            return {
                "success": True,
                "cik": company.cik,
                "name": company.name,
                "transactions": transactions,
                "count": len(transactions),
                "form_types": form_types,
                "days_back": days,
                "filing_reference": {
                    "data_source": "SEC EDGAR Insider Trading Filings (Forms 3, 4, 5)",
                    "disclaimer": "All insider trading data extracted directly from SEC EDGAR filings with exact precision. No estimates or calculations added.",
                    "verification_note": "Each transaction includes direct SEC URL for independent verification",
                    "period_analyzed": f"Last {days} days from {datetime.now().strftime('%Y-%m-%d')}",
                },
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to get insider transactions: {str(e)}"}

    def get_insider_summary(self, identifier: str, days: int = 180) -> ToolResponse:
        """Get summary of insider trading activity."""
        try:
            company = self.client.get_company(identifier)

            # Get all insider filings
            filings = company.get_filings(form=["3", "4", "5"])

            summary: Dict[str, Any] = {
                "total_filings": 0,
                "form_3_count": 0,
                "form_4_count": 0,
                "form_5_count": 0,
                "recent_filings": [],
                "insiders": set(),
            }

            cutoff_date = datetime.now() - timedelta(days=days)

            for filing in filings:
                # Convert filing_date to datetime for comparison
                filing_date = filing.filing_date
                if isinstance(filing_date, str):
                    filing_date = datetime.fromisoformat(filing_date.replace("Z", "+00:00"))
                elif isinstance(filing_date, date) and not isinstance(filing_date, datetime):
                    filing_date = datetime.combine(filing_date, datetime.min.time())

                if not isinstance(filing_date, datetime):
                    continue

                if filing_date < cutoff_date:
                    continue

                summary["total_filings"] += 1

                if filing.form == "3":
                    summary["form_3_count"] += 1
                elif filing.form == "4":
                    summary["form_4_count"] += 1
                elif filing.form == "5":
                    summary["form_5_count"] += 1

                # Add to recent filings
                if len(summary["recent_filings"]) < 10:
                    summary["recent_filings"].append(
                        {
                            "date": filing.filing_date.isoformat(),
                            "form": filing.form,
                            "accession": filing.accession_number,
                        }
                    )

                # Try to get insider name
                try:
                    ownership = filing.obj()
                    if ownership and hasattr(ownership, "owner_name"):
                        summary["insiders"].add(ownership.owner_name)
                except Exception:
                    pass

            summary["unique_insiders"] = len(summary["insiders"])
            summary["insiders"] = list(summary["insiders"]) if isinstance(summary["insiders"], set) else []

            return {"success": True, "cik": company.cik, "name": company.name, "period_days": days, "summary": summary}
        except Exception as e:
            return {"success": False, "error": f"Failed to get insider summary: {str(e)}"}

    def get_form4_details(self, identifier: str, accession_number: str) -> ToolResponse:
        """Get detailed information from a specific Form 4."""
        try:
            company = self.client.get_company(identifier)

            # Find the specific filing
            filing = None
            for f in company.get_filings(form="4"):
                if f.accession_number.replace("-", "") == accession_number.replace("-", ""):
                    filing = f
                    break

            if not filing:
                raise FilingNotFoundError(f"Form 4 with accession {accession_number} not found")

            details = {
                "filing_date": filing.filing_date.isoformat(),
                "accession_number": filing.accession_number,
                "company_name": filing.company,
                "cik": filing.cik,
                "url": filing.url,
                "content_preview": filing.text()[:1000] if hasattr(filing, "text") else None,
            }

            # Try to get structured data
            try:
                form4 = filing.obj()
                if form4:
                    details["owner"] = {
                        "name": getattr(form4, "owner_name", ""),
                        "title": getattr(form4, "owner_title", ""),
                        "is_director": getattr(form4, "is_director", False),
                        "is_officer": getattr(form4, "is_officer", False),
                        "is_ten_percent_owner": getattr(form4, "is_ten_percent_owner", False),
                    }
            except Exception:
                pass

            return {"success": True, "form4_details": details}
        except Exception as e:
            return {"success": False, "error": f"Failed to get Form 4 details: {str(e)}"}

    def analyze_form4_transactions(self, identifier: str, days: int = 90, limit: int = 50) -> ToolResponse:
        """Analyze Form 4 filings and extract detailed transaction data."""
        try:
            company = self.client.get_company(identifier)

            # Get Form 4 filings
            filings = company.get_filings(form="4")

            detailed_transactions = []

            count = 0
            for filing in filings:
                if count >= limit:
                    break

                # Check date filter
                filing_date = filing.filing_date
                if isinstance(filing_date, str):
                    filing_date = datetime.fromisoformat(filing_date.replace("Z", "+00:00"))
                elif isinstance(filing_date, date) and not isinstance(filing_date, datetime):
                    filing_date = datetime.combine(filing_date, datetime.min.time())

                if not isinstance(filing_date, datetime):
                    continue

                if (datetime.now() - filing_date).days > days:
                    continue

                try:
                    # Get detailed Form 4 data
                    form4 = filing.obj()

                    transaction_detail = {
                        "filing_date": filing.filing_date.isoformat(),
                        "form_type": filing.form,
                        "accession_number": filing.accession_number,
                        "sec_url": f"https://www.sec.gov/Archives/edgar/data/{filing.cik}/{filing.accession_number.replace('-', '')}/{filing.accession_number}.txt",
                        "data_source": f"SEC EDGAR Filing {filing.accession_number}, extracted directly from Form 4 XBRL data",
                    }

                    if form4:
                        # Extract owner information
                        if hasattr(form4, "owner_name"):
                            transaction_detail["owner_name"] = form4.owner_name
                        if hasattr(form4, "owner_title"):
                            transaction_detail["owner_title"] = form4.owner_title
                        if hasattr(form4, "is_director"):
                            transaction_detail["is_director"] = form4.is_director
                        if hasattr(form4, "is_officer"):
                            transaction_detail["is_officer"] = form4.is_officer
                        if hasattr(form4, "is_ten_percent_owner"):
                            transaction_detail["is_ten_percent_owner"] = form4.is_ten_percent_owner

                        # Extract transaction data
                        if hasattr(form4, "transactions") and form4.transactions:
                            transactions = []
                            for tx in form4.transactions:
                                tx_data = {}
                                if hasattr(tx, "transaction_date"):
                                    tx_data["transaction_date"] = str(tx.transaction_date)
                                if hasattr(tx, "transaction_code"):
                                    tx_data["transaction_code"] = tx.transaction_code
                                if hasattr(tx, "shares"):
                                    tx_data["shares"] = float(tx.shares) if tx.shares else None
                                if hasattr(tx, "price_per_share"):
                                    tx_data["price_per_share"] = (
                                        float(tx.price_per_share) if tx.price_per_share else None
                                    )
                                if hasattr(tx, "transaction_amount"):
                                    tx_data["transaction_amount"] = (
                                        float(tx.transaction_amount) if tx.transaction_amount else None
                                    )
                                if hasattr(tx, "shares_owned_after"):
                                    tx_data["shares_owned_after"] = (
                                        float(tx.shares_owned_after) if tx.shares_owned_after else None
                                    )
                                if hasattr(tx, "acquisition_or_disposition"):
                                    tx_data["acquisition_or_disposition"] = tx.acquisition_or_disposition

                                if tx_data:  # Only add if we got some data
                                    transactions.append(tx_data)

                            if transactions:
                                transaction_detail["transactions"] = transactions

                        # Extract holdings data
                        if hasattr(form4, "holdings") and form4.holdings:
                            holdings = []
                            for holding in form4.holdings:
                                holding_data = {}
                                if hasattr(holding, "shares_owned"):
                                    holding_data["shares_owned"] = (
                                        float(holding.shares_owned) if holding.shares_owned else None
                                    )
                                if hasattr(holding, "ownership_nature"):
                                    holding_data["ownership_nature"] = holding.ownership_nature

                                if holding_data:
                                    holdings.append(holding_data)

                            if holdings:
                                transaction_detail["holdings"] = holdings

                    detailed_transactions.append(transaction_detail)
                    count += 1

                except Exception as e:
                    # If we can't parse this filing, add basic info
                    transaction_detail = {
                        "filing_date": filing.filing_date.isoformat(),
                        "form_type": filing.form,
                        "accession_number": filing.accession_number,
                        "sec_url": f"https://www.sec.gov/Archives/edgar/data/{filing.cik}/{filing.accession_number.replace('-', '')}/{filing.accession_number}.txt",
                        "data_source": f"SEC EDGAR Filing {filing.accession_number}, basic filing data only",
                        "parsing_error": f"Could not extract detailed data: {str(e)}",
                    }
                    detailed_transactions.append(transaction_detail)
                    count += 1
                    continue

            return {
                "success": True,
                "cik": company.cik,
                "name": company.name,
                "detailed_transactions": detailed_transactions,
                "count": len(detailed_transactions),
                "days_back": days,
                "filing_reference": {
                    "data_source": "SEC EDGAR Form 4 Filings - Detailed Transaction Analysis",
                    "disclaimer": "All transaction data extracted directly from SEC EDGAR Form 4 filings with exact precision. No estimates or calculations added.",
                    "verification_note": "Each transaction includes direct SEC URL for independent verification",
                    "period_analyzed": f"Last {days} days from {datetime.now().strftime('%Y-%m-%d')}",
                },
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to analyze Form 4 transactions: {str(e)}"}

    def analyze_insider_sentiment(self, identifier: str, months: int = 6) -> ToolResponse:
        """Analyze insider trading sentiment - simplified version."""
        try:
            company = self.client.get_company(identifier)

            # Get insider filings
            days = months * 30
            filings = company.get_filings(form=["4"])

            cutoff_date = datetime.now() - timedelta(days=days)

            # Filter filings with proper datetime comparison
            recent_filings = []
            for f in filings:
                filing_date = f.filing_date
                if isinstance(filing_date, str):
                    filing_date = datetime.fromisoformat(filing_date.replace("Z", "+00:00"))
                elif isinstance(filing_date, date) and not isinstance(filing_date, datetime):
                    filing_date = datetime.combine(filing_date, datetime.min.time())

                if isinstance(filing_date, datetime) and filing_date >= cutoff_date:
                    recent_filings.append(f)

            analysis: Dict[str, Any] = {
                "period_months": months,
                "total_form4_filings": len(recent_filings),
                "filing_frequency": "high"
                if len(recent_filings) > 10
                else "low"
                if len(recent_filings) < 3
                else "moderate",
                "recent_filings": [],
            }

            # Add recent filing details
            for filing in recent_filings[:10]:
                analysis["recent_filings"].append(
                    {"date": filing.filing_date.isoformat(), "accession": filing.accession_number, "url": filing.url}
                )

            return {"success": True, "cik": company.cik, "name": company.name, "analysis": analysis}
        except Exception as e:
            return {"success": False, "error": f"Failed to analyze insider sentiment: {str(e)}"}
