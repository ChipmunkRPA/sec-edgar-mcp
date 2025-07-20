from typing import Dict, Union, List, Optional
from datetime import datetime, timedelta
from edgar import Company, get_insider_filings
from ..core.client import EdgarClient
from ..core.models import TransactionInfo
from ..utils.exceptions import FilingNotFoundError


class InsiderTools:
    """Tools for insider trading data (Forms 3, 4, 5)."""
    
    def __init__(self):
        self.client = EdgarClient()
    
    def get_insider_transactions(
        self,
        identifier: str,
        form_types: Optional[List[str]] = None,
        days: int = 90,
        limit: int = 50
    ) -> Dict[str, Union[bool, List]]:
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
                if (datetime.now() - filing.filing_date).days > days:
                    continue
                
                try:
                    # Get the ownership object
                    ownership = filing.obj()
                    
                    # Try to get transaction data using edgar-tools API
                    if hasattr(ownership, 'transactions'):
                        transactions_list = ownership.transactions
                        if transactions_list:
                            transaction = TransactionInfo(
                                transaction_date=row.get('transaction_date', filing.filing_date),
                                security_title=row.get('security_title', 'Common Stock'),
                                transaction_type=row.get('transaction_type', ''),
                                shares=float(row.get('shares', 0)),
                                price_per_share=float(row.get('price_per_share', 0)) if row.get('price_per_share') else None,
                                total_value=float(row.get('total_value', 0)) if row.get('total_value') else None,
                                ownership_type=row.get('ownership_type', 'Direct'),
                                owner_name=getattr(ownership, 'owner_name', ''),
                                owner_title=getattr(ownership, 'owner_title', '')
                            )
                            
                            transaction_dict = transaction.to_dict()
                            transaction_dict['filing_date'] = filing.filing_date.isoformat()
                            transaction_dict['form_type'] = filing.form
                            transaction_dict['accession_number'] = filing.accession_number
                            
                            transactions.append(transaction_dict)
                    
                    count += 1
                except Exception:
                    # Skip filings that can't be parsed
                    continue
            
            # Sort by transaction date
            transactions.sort(key=lambda x: x['transaction_date'], reverse=True)
            
            return {
                "success": True,
                "cik": company.cik,
                "name": company.name,
                "transactions": transactions,
                "count": len(transactions),
                "form_types": form_types,
                "days_back": days
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get insider transactions: {str(e)}"
            }
    
    def get_insider_summary(
        self,
        identifier: str,
        days: int = 180
    ) -> Dict[str, Union[bool, Dict]]:
        """Get summary of insider trading activity."""
        try:
            company = self.client.get_company(identifier)
            
            # Get all insider filings
            filings = company.get_filings(form=["3", "4", "5"])
            
            # Initialize summary data
            summary = {
                "total_transactions": 0,
                "buy_transactions": 0,
                "sell_transactions": 0,
                "total_shares_bought": 0,
                "total_shares_sold": 0,
                "total_value_bought": 0,
                "total_value_sold": 0,
                "unique_insiders": set(),
                "by_insider": {},
                "recent_activity": []
            }
            
            cutoff_date = datetime.now() - timedelta(days=days)
            
            for filing in filings:
                if filing.filing_date < cutoff_date:
                    continue
                
                try:
                    ownership = filing.obj()
                    df = ownership.to_dataframe()
                    
                    if not df.empty:
                        owner_name = getattr(ownership, 'owner_name', 'Unknown')
                        summary["unique_insiders"].add(owner_name)
                        
                        if owner_name not in summary["by_insider"]:
                            summary["by_insider"][owner_name] = {
                                "transactions": 0,
                                "shares_bought": 0,
                                "shares_sold": 0,
                                "value_bought": 0,
                                "value_sold": 0
                            }
                        
                        for _, row in df.iterrows():
                            summary["total_transactions"] += 1
                            summary["by_insider"][owner_name]["transactions"] += 1
                            
                            shares = float(row.get('shares', 0))
                            value = float(row.get('total_value', 0)) if row.get('total_value') else 0
                            transaction_type = row.get('transaction_type', '').upper()
                            
                            # Categorize transaction
                            if any(keyword in transaction_type for keyword in ['BUY', 'PURCHASE', 'ACQUIRE', 'GRANT']):
                                summary["buy_transactions"] += 1
                                summary["total_shares_bought"] += shares
                                summary["total_value_bought"] += value
                                summary["by_insider"][owner_name]["shares_bought"] += shares
                                summary["by_insider"][owner_name]["value_bought"] += value
                            elif any(keyword in transaction_type for keyword in ['SELL', 'SALE', 'DISPOSE']):
                                summary["sell_transactions"] += 1
                                summary["total_shares_sold"] += shares
                                summary["total_value_sold"] += value
                                summary["by_insider"][owner_name]["shares_sold"] += shares
                                summary["by_insider"][owner_name]["value_sold"] += value
                            
                            # Add to recent activity
                            if len(summary["recent_activity"]) < 10:
                                summary["recent_activity"].append({
                                    "date": row.get('transaction_date', filing.filing_date).isoformat() if hasattr(row.get('transaction_date', filing.filing_date), 'isoformat') else str(row.get('transaction_date', filing.filing_date)),
                                    "insider": owner_name,
                                    "type": transaction_type,
                                    "shares": shares,
                                    "value": value
                                })
                except:
                    continue
            
            # Convert set to count
            summary["unique_insiders"] = len(summary["unique_insiders"])
            
            # Calculate net activity
            summary["net_shares"] = summary["total_shares_bought"] - summary["total_shares_sold"]
            summary["net_value"] = summary["total_value_bought"] - summary["total_value_sold"]
            summary["buy_sell_ratio"] = (
                summary["buy_transactions"] / summary["sell_transactions"] 
                if summary["sell_transactions"] > 0 else float('inf')
            )
            
            return {
                "success": True,
                "cik": company.cik,
                "name": company.name,
                "period_days": days,
                "summary": summary
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get insider summary: {str(e)}"
            }
    
    def get_form4_details(
        self,
        identifier: str,
        accession_number: str
    ) -> Dict[str, Union[bool, Dict]]:
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
            
            # Get the ownership object
            form4 = filing.obj()
            
            # Extract detailed information
            details = {
                "filing_date": filing.filing_date.isoformat(),
                "accession_number": filing.accession_number,
                "issuer": {
                    "cik": company.cik,
                    "name": company.name
                },
                "reporting_owner": {
                    "name": getattr(form4, 'owner_name', ''),
                    "title": getattr(form4, 'owner_title', ''),
                    "is_director": getattr(form4, 'is_director', False),
                    "is_officer": getattr(form4, 'is_officer', False),
                    "is_ten_percent_owner": getattr(form4, 'is_ten_percent_owner', False),
                    "is_other": getattr(form4, 'is_other', False)
                },
                "transactions": [],
                "holdings": []
            }
            
            # Get transaction data
            df = form4.to_dataframe()
            
            if not df.empty:
                for _, row in df.iterrows():
                    transaction = {
                        "transaction_date": str(row.get('transaction_date', '')),
                        "security_title": row.get('security_title', ''),
                        "transaction_type": row.get('transaction_type', ''),
                        "transaction_code": row.get('transaction_code', ''),
                        "shares": float(row.get('shares', 0)),
                        "price_per_share": float(row.get('price_per_share', 0)) if row.get('price_per_share') else None,
                        "acquired_disposed": row.get('acquired_disposed', ''),
                        "ownership_type": row.get('ownership_type', 'Direct'),
                        "shares_owned_after": float(row.get('shares_owned_after', 0)) if row.get('shares_owned_after') else None
                    }
                    details["transactions"].append(transaction)
            
            # Try to get holdings summary
            if hasattr(form4, 'holdings'):
                for holding in form4.holdings:
                    details["holdings"].append({
                        "security_title": getattr(holding, 'security_title', ''),
                        "shares_owned": getattr(holding, 'shares_owned', 0),
                        "ownership_type": getattr(holding, 'ownership_type', 'Direct')
                    })
            
            return {
                "success": True,
                "form4_details": details
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get Form 4 details: {str(e)}"
            }
    
    def analyze_insider_sentiment(
        self,
        identifier: str,
        months: int = 6
    ) -> Dict[str, Union[bool, Dict]]:
        """Analyze insider trading sentiment over time."""
        try:
            company = self.client.get_company(identifier)
            
            # Get insider filings for the period
            days = months * 30
            filings = company.get_filings(form=["4"])
            
            # Group transactions by month
            monthly_data = {}
            cutoff_date = datetime.now() - timedelta(days=days)
            
            for filing in filings:
                if filing.filing_date < cutoff_date:
                    continue
                
                month_key = filing.filing_date.strftime("%Y-%m")
                
                if month_key not in monthly_data:
                    monthly_data[month_key] = {
                        "buys": 0,
                        "sells": 0,
                        "buy_value": 0,
                        "sell_value": 0,
                        "net_shares": 0,
                        "transactions": 0
                    }
                
                try:
                    ownership = filing.obj()
                    df = ownership.to_dataframe()
                    
                    if not df.empty:
                        for _, row in df.iterrows():
                            monthly_data[month_key]["transactions"] += 1
                            
                            shares = float(row.get('shares', 0))
                            value = float(row.get('total_value', 0)) if row.get('total_value') else 0
                            transaction_type = row.get('transaction_type', '').upper()
                            
                            if any(keyword in transaction_type for keyword in ['BUY', 'PURCHASE', 'ACQUIRE']):
                                monthly_data[month_key]["buys"] += 1
                                monthly_data[month_key]["buy_value"] += value
                                monthly_data[month_key]["net_shares"] += shares
                            elif any(keyword in transaction_type for keyword in ['SELL', 'SALE', 'DISPOSE']):
                                monthly_data[month_key]["sells"] += 1
                                monthly_data[month_key]["sell_value"] += value
                                monthly_data[month_key]["net_shares"] -= shares
                except:
                    continue
            
            # Calculate sentiment scores
            sentiment_analysis = {
                "monthly_data": monthly_data,
                "overall_sentiment": "neutral",
                "sentiment_score": 0,
                "trend": "stable"
            }
            
            # Calculate overall sentiment
            total_buys = sum(m["buys"] for m in monthly_data.values())
            total_sells = sum(m["sells"] for m in monthly_data.values())
            total_net_shares = sum(m["net_shares"] for m in monthly_data.values())
            
            if total_buys + total_sells > 0:
                sentiment_analysis["sentiment_score"] = (total_buys - total_sells) / (total_buys + total_sells)
                
                if sentiment_analysis["sentiment_score"] > 0.2:
                    sentiment_analysis["overall_sentiment"] = "bullish"
                elif sentiment_analysis["sentiment_score"] < -0.2:
                    sentiment_analysis["overall_sentiment"] = "bearish"
            
            # Analyze trend
            sorted_months = sorted(monthly_data.keys())
            if len(sorted_months) >= 3:
                recent_net = sum(monthly_data[m]["net_shares"] for m in sorted_months[-3:])
                older_net = sum(monthly_data[m]["net_shares"] for m in sorted_months[:-3])
                
                if recent_net > older_net * 1.5:
                    sentiment_analysis["trend"] = "improving"
                elif recent_net < older_net * 0.5:
                    sentiment_analysis["trend"] = "deteriorating"
            
            return {
                "success": True,
                "cik": company.cik,
                "name": company.name,
                "period_months": months,
                "analysis": sentiment_analysis,
                "summary": {
                    "total_buy_transactions": total_buys,
                    "total_sell_transactions": total_sells,
                    "net_shares_traded": total_net_shares,
                    "months_analyzed": len(monthly_data)
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to analyze insider sentiment: {str(e)}"
            }