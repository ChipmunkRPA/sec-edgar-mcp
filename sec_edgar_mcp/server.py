import argparse
import requests
import xml.etree.ElementTree as ET
import re
from typing import List, Union, Dict, Optional, Any
from secedgar.core.rest import (
    get_submissions,
    get_company_concepts,
    get_xbrl_frames,
)
from mcp.server.fastmcp import FastMCP

try:
    from .config import initialize_config
    from .document_parser import SECDocumentParser
except ImportError:
    from config import initialize_config
    from document_parser import SECDocumentParser


sec_edgar_user_agent = initialize_config()

# Cache for ticker to CIK mapping
_ticker_to_cik_cache: Optional[Dict[str, int]] = None

# Initialize document parser
document_parser = SECDocumentParser(sec_edgar_user_agent)

# Initialize MCP
mcp = FastMCP("SEC EDGAR MCP", dependencies=["secedgar"])


def _fetch_ticker_to_cik_mapping() -> Dict[str, int]:
    """
    Fetch and cache the ticker to CIK mapping from SEC's company_tickers_exchange.json.

    Returns:
        Dict[str, int]: A dictionary mapping ticker symbols (uppercase) to CIK numbers.
    """
    global _ticker_to_cik_cache

    if _ticker_to_cik_cache is not None:
        return _ticker_to_cik_cache

    try:
        url = "https://www.sec.gov/files/company_tickers_exchange.json"
        headers = {"User-Agent": sec_edgar_user_agent}
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()

        # Build ticker to CIK mapping
        ticker_to_cik = {}
        # The data format is either a dict with "data" key containing a dict/list,
        # or the data itself is a list
        data_items = data.get("data", data) if isinstance(data, dict) else data

        # Handle both dict and list formats
        if isinstance(data_items, dict):
            # If data is a dict, iterate over values
            for company_data in data_items.values():
                if isinstance(company_data, list) and len(company_data) >= 3:
                    cik = company_data[0]  # CIK is at index 0
                    ticker = company_data[2]  # Ticker is at index 2
                    if ticker:  # Only add if ticker exists
                        ticker_to_cik[ticker.upper()] = cik
        elif isinstance(data_items, list):
            # If data is a list, iterate over items
            for company_data in data_items:
                if isinstance(company_data, list) and len(company_data) >= 3:
                    cik = company_data[0]  # CIK is at index 0
                    ticker = company_data[2]  # Ticker is at index 2
                    if ticker:  # Only add if ticker exists
                        ticker_to_cik[ticker.upper()] = cik

        _ticker_to_cik_cache = ticker_to_cik
        return ticker_to_cik

    except Exception as e:
        raise Exception(f"Failed to fetch ticker to CIK mapping: {str(e)}")


@mcp.tool("get_cik_by_ticker")
def get_cik_by_ticker_tool(ticker: str) -> Dict[str, Union[int, str]]:
    """
    Get the CIK (Central Index Key) for a company based on its ticker symbol.

    Parameters:
        ticker (str): The ticker symbol of the company (e.g., "NVDA", "AAPL").

    Returns:
        Dict[str, Union[int, str]]: A dictionary containing the CIK number or error message.
    """
    try:
        ticker_to_cik = _fetch_ticker_to_cik_mapping()
        ticker_upper = ticker.upper()

        if ticker_upper in ticker_to_cik:
            raw_cik = ticker_to_cik[ticker_upper]
            formatted_cik = f"CIK{str(raw_cik).zfill(10)}"
            return {
                "ticker": ticker_upper,
                "cik": raw_cik,
                "formatted_cik": formatted_cik,
                "api_url": f"https://data.sec.gov/api/xbrl/companyfacts/{formatted_cik}.json",
                "success": True,
            }
        else:
            return {"error": f"Ticker '{ticker}' not found in SEC database", "ticker": ticker_upper, "success": False}

    except Exception as e:
        return {"error": f"Failed to lookup CIK for ticker '{ticker}': {str(e)}", "ticker": ticker, "success": False}


@mcp.tool("get_submissions")
def get_submissions_tool(
    lookups: Union[str, List[str]],
    user_agent: str = sec_edgar_user_agent,
    recent: bool = True,
) -> Dict[str, Any]:
    """
    Retrieve submission records for specified companies using the SEC EDGAR REST API.

    Parameters:
        lookups (Union[str, List[str]]): Ticker(s) or CIK(s) of the companies.
        user_agent (str): User agent string required by the SEC.
        recent (bool): If True, retrieves at least one year of filings or the last 1000 filings. Defaults to True.

    Returns:
        Dict[str, dict]: A dictionary mapping each lookup to its submission data.
    """
    try:
        return get_submissions(lookups=lookups, user_agent=user_agent, recent=recent)
    except Exception as e:
        return {
            "error": f"Failed to get submissions: {str(e)}",
            "lookups": lookups if isinstance(lookups, list) else [lookups],
        }


@mcp.tool("get_company_concepts")
def get_company_concepts_tool(
    lookups: Union[str, List[str]],
    concept_name: str,
    user_agent: str = sec_edgar_user_agent,
) -> Dict[str, Any]:
    """
    Retrieve data for a specific financial concept for specified companies using the SEC EDGAR REST API.

    Parameters:
        lookups (Union[str, List[str]]): Ticker(s) or CIK(s) of the companies.
        concept_name (str): The financial concept to retrieve (e.g., "AccountsPayableCurrent").
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict[str, dict]: A dictionary mapping each lookup to its concept data.
    """
    try:
        return get_company_concepts(
            lookups=lookups,
            concept_name=concept_name,
            user_agent=user_agent,
        )
    except Exception as e:
        return {
            "error": f"Failed to get company concepts: {str(e)}",
            "lookups": lookups if isinstance(lookups, list) else [lookups],
            "concept_name": concept_name,
        }


@mcp.tool("get_xbrl_frames")
def get_xbrl_frames_tool(
    concept_name: str,
    year: int,
    quarter: Union[int, None] = None,
    currency: str = "USD",
    instantaneous: bool = False,
    user_agent: str = sec_edgar_user_agent,
) -> dict:
    """
    Retrieve XBRL 'frames' data for a concept across companies for a specified time frame using the SEC EDGAR REST API.

    Parameters:
        concept_name (str): The financial concept to query (e.g., "Assets").
        year (int): The year for which to retrieve the data.
        quarter (Union[int, None]): The fiscal quarter (1-4) within the year. If None, data for the entire year is returned.
        currency (str): The reporting currency filter (default is "USD").
        instantaneous (bool): Whether to retrieve instantaneous values (True) or duration values (False) for the concept.
        user_agent (str): User agent string required by the SEC.

    Returns:
        dict: A dictionary containing the frame data for the specified concept and period.
    """
    try:
        return get_xbrl_frames(
            user_agent=user_agent,
            concept_name=concept_name,
            year=year,
            quarter=quarter,
            currency=currency,
            instantaneous=instantaneous,
        )
    except Exception as e:
        return {
            "error": f"Failed to get XBRL frames: {str(e)}",
            "concept_name": concept_name,
            "year": year,
            "quarter": quarter,
        }


@mcp.tool("get_filing_txt")
def get_filing_txt_tool(cik: str, accession_number: str, extract_main_only: bool = True) -> Dict[str, Any]:
    """
    Retrieve SEC filing content using the reliable .txt format (always works).

    Parameters:
        cik (str): Central Index Key of the company.
        accession_number (str): Accession number of the filing.
        extract_main_only (bool): If True, extract only the main document (default: True).

    Returns:
        Dict: Document content with metadata.
    """
    try:
        # Normalize CIK to 10 digits
        normalized_cik = str(int(cik)).zfill(10)

        # Fetch .txt filing (most reliable)
        txt_content = document_parser.fetch_filing_txt(normalized_cik, accession_number)

        # Extract and clean content
        if extract_main_only:
            text_content = document_parser.extract_main_document_from_txt(txt_content)
            # If main document is too small, try best content extraction
            if len(text_content.strip()) < 500:
                text_content = document_parser.extract_best_content_from_txt(txt_content)
        else:
            text_content = document_parser.clean_txt_content(txt_content)

        # Safety check for response size
        max_response_size = 800000  # 800KB to stay well under 1MB limit
        if len(text_content) > max_response_size:
            return {
                "error": f"Content too large ({len(text_content):,} chars). Use streaming tools instead.",
                "cik": normalized_cik,
                "accession_number": accession_number,
                "content_length": len(text_content),
                "raw_length": len(txt_content),
                "suggested_tools": ["stream_filing_txt_chunks", "get_filing_txt_sections"],
                "success": False,
            }

        return {
            "cik": normalized_cik,
            "accession_number": accession_number,
            "document_format": "txt",
            "content": text_content,
            "content_length": len(text_content),
            "word_count": len(text_content.split()),
            "raw_length": len(txt_content),
            "compression_ratio": round(len(text_content) / len(txt_content), 2),
            "extract_main_only": extract_main_only,
            "success": True,
        }
    except Exception as e:
        return {
            "error": f"Failed to get filing txt: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


@mcp.tool("get_filing_txt_sections")
def get_filing_txt_sections_tool(cik: str, accession_number: str, extract_main_only: bool = True) -> Dict[str, Any]:
    """
    Extract sections from SEC filing using reliable .txt format.

    Parameters:
        cik (str): Central Index Key of the company.
        accession_number (str): Accession number of the filing.
        extract_main_only (bool): If True, extract only the main document (default: True).

    Returns:
        Dict: Document sections with summary information.
    """
    try:
        # Normalize CIK
        normalized_cik = str(int(cik)).zfill(10)

        # Fetch and clean .txt filing
        txt_content = document_parser.fetch_filing_txt(normalized_cik, accession_number)

        if extract_main_only:
            text_content = document_parser.extract_main_document_from_txt(txt_content)
            # If main document is too small, try best content extraction
            if len(text_content.strip()) < 500:
                text_content = document_parser.extract_best_content_from_txt(txt_content)
        else:
            text_content = document_parser.clean_txt_content(txt_content)

        # Extract sections
        sections = document_parser.extract_sections(text_content)

        # Generate summary
        summary = document_parser.get_filing_summary(sections)

        # Convert sections to dict format
        sections_data = []
        for section in sections:
            sections_data.append(
                {
                    "name": section.name,
                    "section_type": section.section_type,
                    "word_count": section.word_count,
                    "char_count": section.char_count,
                    "content_preview": section.content[:200] + "..." if len(section.content) > 200 else section.content,
                }
            )

        return {
            "cik": normalized_cik,
            "accession_number": accession_number,
            "document_format": "txt",
            "summary": summary,
            "sections": sections_data,
            "raw_length": len(txt_content),
            "processed_length": len(text_content),
            "compression_ratio": round(len(text_content) / len(txt_content), 2),
            "extract_main_only": extract_main_only,
            "success": True,
        }
    except Exception as e:
        return {
            "error": f"Failed to get filing txt sections: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


@mcp.tool("stream_filing_txt_chunks")
def stream_filing_txt_chunks_tool(
    cik: str,
    accession_number: str,
    chunk_size: int = 8000,
    start_chunk: int = 0,
    max_chunks: int = 5,
    extract_main_only: bool = True,
) -> Dict[str, Any]:
    """
    Stream SEC filing chunks using reliable .txt format with pagination.

    Parameters:
        cik (str): Central Index Key of the company.
        accession_number (str): Accession number of the filing.
        chunk_size (int): Maximum size of each chunk in characters (default: 8000).
        start_chunk (int): Starting chunk index (default: 0).
        max_chunks (int): Maximum number of chunks to return (default: 5).
        extract_main_only (bool): If True, extract only the main document (default: True).

    Returns:
        Dict: Paginated chunks with navigation metadata.
    """
    try:
        # Normalize CIK
        normalized_cik = str(int(cik)).zfill(10)

        # Fetch and clean .txt filing
        txt_content = document_parser.fetch_filing_txt(normalized_cik, accession_number)

        if extract_main_only:
            text_content = document_parser.extract_main_document_from_txt(txt_content)
            # If main document is too small, try best content extraction
            if len(text_content.strip()) < 500:
                text_content = document_parser.extract_best_content_from_txt(txt_content)
        else:
            text_content = document_parser.clean_txt_content(txt_content)

        # Extract sections and chunk by sections
        sections = document_parser.extract_sections(text_content)
        all_chunks = document_parser.chunk_by_sections(sections, chunk_size)

        # Paginate chunks
        end_chunk = min(start_chunk + max_chunks, len(all_chunks))
        page_chunks = all_chunks[start_chunk:end_chunk]

        # Convert to dict format
        chunks_data = []
        for i, chunk in enumerate(page_chunks):
            chunks_data.append(
                {
                    "chunk_index": start_chunk + i,
                    "section_name": chunk.section_name,
                    "content": chunk.content,
                    "word_count": chunk.word_count,
                    "char_count": chunk.char_count,
                    "metadata": chunk.metadata,
                }
            )

        return {
            "cik": normalized_cik,
            "accession_number": accession_number,
            "document_format": "txt",
            "chunks": chunks_data,
            "pagination": {
                "start_chunk": start_chunk,
                "end_chunk": end_chunk - 1,
                "total_chunks": len(all_chunks),
                "has_next": end_chunk < len(all_chunks),
                "has_prev": start_chunk > 0,
                "next_start": end_chunk if end_chunk < len(all_chunks) else None,
                "prev_start": max(0, start_chunk - max_chunks) if start_chunk > 0 else None,
            },
            "raw_length": len(txt_content),
            "processed_length": len(text_content),
            "compression_ratio": round(len(text_content) / len(txt_content), 2),
            "extract_main_only": extract_main_only,
            "success": True,
        }
    except Exception as e:
        return {
            "error": f"Failed to stream filing txt chunks: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


@mcp.tool("get_recent_filings_rss")
def get_recent_filings_rss_tool(cik: str, filing_type: str = "*", count: int = 40) -> Dict[str, Any]:
    """
    Get recent SEC filings for a company using RSS feed (ATOM format).

    Parameters:
        cik (str): Central Index Key of the company.
        filing_type (str): Type of filings to retrieve (default: "*" for all types).
        count (int): Maximum number of filings to retrieve (default: 40, max: 100).

    Returns:
        Dict: Recent filings data parsed from RSS/ATOM feed.
    """
    try:
        # Normalize CIK
        normalized_cik = str(int(cik)).zfill(10)

        # Build RSS URL
        rss_url = f"https://data.sec.gov/rss?cik={normalized_cik}&type={filing_type}&count={count}"

        # Fetch RSS feed
        headers = {
            "User-Agent": sec_edgar_user_agent,
            "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        response = requests.get(rss_url, headers=headers, timeout=30)
        response.raise_for_status()

        # Parse XML/ATOM content
        root = ET.fromstring(response.text)

        # Define namespaces
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}

        # Extract feed metadata
        feed_info = {
            "title": root.find("atom:title", namespaces).text
            if root.find("atom:title", namespaces) is not None
            else "",
            "subtitle": root.find("atom:subtitle", namespaces).text
            if root.find("atom:subtitle", namespaces) is not None
            else "",
            "updated": root.find("atom:updated", namespaces).text
            if root.find("atom:updated", namespaces) is not None
            else "",
            "id": root.find("atom:id", namespaces).text if root.find("atom:id", namespaces) is not None else "",
        }

        # Extract company info
        company_info = {}
        company_info_elem = root.find("company-info")
        if company_info_elem is not None:
            # Basic company data
            company_info["confirmed_name"] = (
                company_info_elem.find("confirmed-name").text
                if company_info_elem.find("confirmed-name") is not None
                else ""
            )
            company_info["ein"] = (
                company_info_elem.find("employer-identification-number").text
                if company_info_elem.find("employer-identification-number") is not None
                else ""
            )
            company_info["fiscal_year_end"] = (
                company_info_elem.find("fiscal-year-end").text
                if company_info_elem.find("fiscal-year-end") is not None
                else ""
            )
            company_info["assigned_sic"] = (
                company_info_elem.find("assigned-sic").text
                if company_info_elem.find("assigned-sic") is not None
                else ""
            )
            company_info["assigned_sic_desc"] = (
                company_info_elem.find("assigned-sic-desc").text
                if company_info_elem.find("assigned-sic-desc") is not None
                else ""
            )
            company_info["state_location"] = (
                company_info_elem.find("state-location").text
                if company_info_elem.find("state-location") is not None
                else ""
            )
            company_info["state_of_incorporation"] = (
                company_info_elem.find("state-of-incorporation").text
                if company_info_elem.find("state-of-incorporation") is not None
                else ""
            )
            company_info["office"] = (
                company_info_elem.find("office").text if company_info_elem.find("office") is not None else ""
            )

            # Addresses
            addresses = []
            addresses_elem = company_info_elem.find("addresses")
            if addresses_elem is not None:
                for addr in addresses_elem.findall("address"):
                    address_type = addr.get("type", "")
                    addr_data = {
                        "type": address_type,
                        "street1": addr.find("street1").text if addr.find("street1") is not None else "",
                        "city": addr.find("city").text if addr.find("city") is not None else "",
                        "state": addr.find("stateOrCountry").text if addr.find("stateOrCountry") is not None else "",
                        "zip_code": addr.find("zipCode").text if addr.find("zipCode") is not None else "",
                    }
                    addresses.append(addr_data)
            company_info["addresses"] = addresses

            # Former names
            former_names = []
            formerly_names_elem = company_info_elem.find("formerly-names")
            if formerly_names_elem is not None:
                for name_elem in formerly_names_elem.findall("names"):
                    former_name = {
                        "date": name_elem.find("date").text if name_elem.find("date") is not None else "",
                        "name": name_elem.find("name").text if name_elem.find("name") is not None else "",
                    }
                    former_names.append(former_name)
            company_info["former_names"] = former_names

        # Extract filings
        filings = []
        for entry in root.findall("atom:entry", namespaces):
            filing = {}

            # Basic entry info
            filing["title"] = (
                entry.find("atom:title", namespaces).text if entry.find("atom:title", namespaces) is not None else ""
            )
            filing["updated"] = (
                entry.find("atom:updated", namespaces).text
                if entry.find("atom:updated", namespaces) is not None
                else ""
            )
            filing["id"] = (
                entry.find("atom:id", namespaces).text if entry.find("atom:id", namespaces) is not None else ""
            )

            # Category (form type)
            category = entry.find("atom:category", namespaces)
            if category is not None:
                filing["form_type"] = category.get("term", "")
                filing["form_label"] = category.get("label", "")

            # Content details
            content_type = entry.find("content-type")
            if content_type is not None:
                filing["acceptance_datetime"] = (
                    content_type.find("acceptance-date-time").text
                    if content_type.find("acceptance-date-time") is not None
                    else ""
                )
                filing["accession_number"] = (
                    content_type.find("accession-number").text
                    if content_type.find("accession-number") is not None
                    else ""
                )
                filing["act"] = content_type.find("act").text if content_type.find("act") is not None else ""
                filing["file_number"] = (
                    content_type.find("file-number").text if content_type.find("file-number") is not None else ""
                )
                filing["filing_date"] = (
                    content_type.find("filing-date").text if content_type.find("filing-date") is not None else ""
                )
                filing["filing_href"] = (
                    content_type.find("filing-href").text if content_type.find("filing-href") is not None else ""
                )
                filing["film_number"] = (
                    content_type.find("film-number").text if content_type.find("film-number") is not None else ""
                )
                filing["form_name"] = (
                    content_type.find("form-name").text if content_type.find("form-name") is not None else ""
                )
                filing["items_desc"] = (
                    content_type.find("items-desc").text if content_type.find("items-desc") is not None else ""
                )
                filing["report_date"] = (
                    content_type.find("report-date").text if content_type.find("report-date") is not None else ""
                )
                filing["size"] = content_type.find("size").text if content_type.find("size") is not None else ""

                # XBRL link
                xbrl_href = content_type.find("xbrl_href")
                filing["xbrl_href"] = xbrl_href.text if xbrl_href is not None else ""

            # Links
            link = entry.find("atom:link", namespaces)
            if link is not None:
                filing["document_link"] = link.get("href", "")

            # Summary
            summary = entry.find("atom:summary", namespaces)
            filing["summary"] = summary.text if summary is not None else ""

            filings.append(filing)

        return {
            "cik": normalized_cik,
            "filing_type": filing_type,
            "count_requested": count,
            "count_returned": len(filings),
            "rss_url": rss_url,
            "feed_info": feed_info,
            "company_info": company_info,
            "filings": filings,
            "raw_content": response.text,
            "success": True,
        }

    except Exception as e:
        return {
            "error": f"Failed to get RSS feed: {str(e)}",
            "cik": cik,
            "filing_type": filing_type,
            "count": count,
            "success": False,
        }


@mcp.tool("get_filing_document_info")
def get_filing_document_info_tool(cik: str, accession_number: str) -> Dict[str, Any]:
    """
    Get information about all documents in a SEC filing .txt file.

    Parameters:
        cik (str): Central Index Key of the company.
        accession_number (str): Accession number of the filing.

    Returns:
        Dict: Information about all documents in the filing.
    """
    try:
        # Normalize CIK to 10 digits
        normalized_cik = str(int(cik)).zfill(10)

        # Fetch .txt filing
        txt_content = document_parser.fetch_filing_txt(normalized_cik, accession_number)

        # Get document info
        documents = document_parser.get_document_info_from_txt(txt_content)

        return {
            "cik": normalized_cik,
            "accession_number": accession_number,
            "total_documents": len(documents),
            "total_size": len(txt_content),
            "documents": documents,
            "success": True,
        }
    except Exception as e:
        return {
            "error": f"Failed to get document info: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


@mcp.tool("get_filing_best_content")
def get_filing_best_content_tool(cik: str, accession_number: str) -> Dict[str, Any]:
    """
    Get the best available content from a SEC filing, handling edge cases like Apple's format.

    Parameters:
        cik (str): Central Index Key of the company.
        accession_number (str): Accession number of the filing.

    Returns:
        Dict: Best available document content.
    """
    try:
        # Normalize CIK to 10 digits
        normalized_cik = str(int(cik)).zfill(10)

        # Fetch .txt filing
        txt_content = document_parser.fetch_filing_txt(normalized_cik, accession_number)

        # Extract best content
        best_content = document_parser.extract_best_content_from_txt(txt_content)

        # Safety check for response size
        max_response_size = 800000  # 800KB to stay well under 1MB limit
        if len(best_content) > max_response_size:
            return {
                "error": f"Content too large ({len(best_content):,} chars). Use streaming tools instead.",
                "cik": normalized_cik,
                "accession_number": accession_number,
                "content_length": len(best_content),
                "raw_length": len(txt_content),
                "suggested_tools": ["stream_filing_txt_chunks", "get_filing_txt_sections"],
                "success": False,
            }

        return {
            "cik": normalized_cik,
            "accession_number": accession_number,
            "document_format": "txt",
            "content": best_content,
            "content_length": len(best_content),
            "word_count": len(best_content.split()),
            "raw_length": len(txt_content),
            "compression_ratio": round(len(best_content) / len(txt_content), 3) if len(txt_content) > 0 else 0,
            "method": "best_content_extraction",
            "success": True,
        }
    except Exception as e:
        return {
            "error": f"Failed to get best content: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


@mcp.tool("get_company_facts_summary")
def get_company_facts_summary_tool(cik: str, user_agent: str = sec_edgar_user_agent) -> Dict[str, Any]:
    """
    Get a summary of company facts without the full data (avoids large response).

    Parameters:
        cik (str): Central Index Key of the company (will be formatted with leading zeros).
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: Summary of available company facts.
    """
    try:
        # Format CIK with leading zeros for API
        formatted_cik = f"CIK{str(int(cik)).zfill(10)}"

        # Build API URL
        api_url = f"https://data.sec.gov/api/xbrl/companyfacts/{formatted_cik}.json"

        headers = {"User-Agent": user_agent, "Accept": "application/json"}

        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Extract summary information
        summary = {
            "cik": formatted_cik,
            "entity_name": data.get("entityName", ""),
            "api_url": api_url,
            "total_size_mb": round(len(response.text) / 1024 / 1024, 1),
            "total_characters": len(response.text),
        }

        # Analyze facts structure
        if "facts" in data:
            facts = data["facts"]
            summary["fact_categories"] = list(facts.keys())

            category_summary = {}
            for category, concepts in facts.items():
                category_summary[category] = {
                    "concept_count": len(concepts),
                    "sample_concepts": list(concepts.keys())[:10],
                }

            summary["categories"] = category_summary

        return {**summary, "success": True, "note": "Use get_company_facts_concepts to get specific concept data"}

    except Exception as e:
        return {
            "error": f"Failed to get company facts summary: {str(e)}",
            "cik": cik,
            "formatted_cik": f"CIK{str(int(cik)).zfill(10)}",
            "success": False,
        }


@mcp.tool("get_company_facts_concepts")
def get_company_facts_concepts_tool(
    cik: str,
    category: str = "us-gaap",
    concepts: Optional[List[str]] = None,
    start_index: int = 0,
    max_concepts: int = 20,
    user_agent: str = sec_edgar_user_agent,
) -> Dict[str, Any]:
    """
    Get specific concepts from company facts data in manageable chunks.

    Parameters:
        cik (str): Central Index Key of the company.
        category (str): Facts category ("us-gaap", "dei", etc.) - default: "us-gaap".
        concepts (List[str]): Specific concept names to retrieve (optional).
        start_index (int): Starting index for concept retrieval (default: 0).
        max_concepts (int): Maximum concepts to return (default: 20).
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: Specific company facts concepts data.
    """
    try:
        # Format CIK with leading zeros
        formatted_cik = f"CIK{str(int(cik)).zfill(10)}"

        # Build API URL
        api_url = f"https://data.sec.gov/api/xbrl/companyfacts/{formatted_cik}.json"

        headers = {"User-Agent": user_agent, "Accept": "application/json"}

        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        if "facts" not in data or category not in data["facts"]:
            return {
                "error": f"Category '{category}' not found in company facts",
                "available_categories": list(data.get("facts", {}).keys()),
                "cik": formatted_cik,
                "success": False,
            }

        category_facts = data["facts"][category]
        all_concepts = list(category_facts.keys())

        # Handle specific concepts request
        if concepts:
            selected_concepts = {k: category_facts[k] for k in concepts if k in category_facts}
            missing_concepts = [k for k in concepts if k not in category_facts]

            return {
                "cik": formatted_cik,
                "category": category,
                "requested_concepts": concepts,
                "found_concepts": list(selected_concepts.keys()),
                "missing_concepts": missing_concepts,
                "concept_data": selected_concepts,
                "total_available_concepts": len(all_concepts),
                "success": True,
            }

        # Handle paginated concepts
        end_index = min(start_index + max_concepts, len(all_concepts))
        selected_concept_names = all_concepts[start_index:end_index]
        selected_concepts = {k: category_facts[k] for k in selected_concept_names}

        return {
            "cik": formatted_cik,
            "category": category,
            "start_index": start_index,
            "end_index": end_index - 1,
            "returned_concepts": len(selected_concepts),
            "total_available_concepts": len(all_concepts),
            "concept_names": selected_concept_names,
            "concept_data": selected_concepts,
            "pagination": {
                "has_next": end_index < len(all_concepts),
                "has_prev": start_index > 0,
                "next_start": end_index if end_index < len(all_concepts) else None,
                "prev_start": max(0, start_index - max_concepts) if start_index > 0 else None,
            },
            "success": True,
        }

    except Exception as e:
        return {
            "error": f"Failed to get company facts concepts: {str(e)}",
            "cik": cik,
            "formatted_cik": f"CIK{str(int(cik)).zfill(10)}",
            "category": category,
            "success": False,
        }


@mcp.tool("list_company_facts_concepts")
def list_company_facts_concepts_tool(
    cik: str, category: str = "us-gaap", search_term: Optional[str] = None, user_agent: str = sec_edgar_user_agent
) -> Dict[str, Any]:
    """
    List available concepts in company facts data with optional search.

    Parameters:
        cik (str): Central Index Key of the company.
        category (str): Facts category to list ("us-gaap", "dei", etc.) - default: "us-gaap".
        search_term (str): Optional search term to filter concepts.
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: List of available concepts.
    """
    try:
        # Format CIK with leading zeros
        formatted_cik = f"CIK{str(int(cik)).zfill(10)}"

        # Build API URL
        api_url = f"https://data.sec.gov/api/xbrl/companyfacts/{formatted_cik}.json"

        headers = {"User-Agent": user_agent, "Accept": "application/json"}

        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        if "facts" not in data or category not in data["facts"]:
            return {
                "error": f"Category '{category}' not found",
                "available_categories": list(data.get("facts", {}).keys()),
                "cik": formatted_cik,
                "success": False,
            }

        category_facts = data["facts"][category]
        all_concepts = list(category_facts.keys())

        # Apply search filter if provided
        if search_term:
            search_lower = search_term.lower()
            filtered_concepts = [c for c in all_concepts if search_lower in c.lower()]
        else:
            filtered_concepts = all_concepts

        # Sort concepts alphabetically
        filtered_concepts.sort()

        return {
            "cik": formatted_cik,
            "category": category,
            "search_term": search_term,
            "total_concepts": len(all_concepts),
            "filtered_concepts": len(filtered_concepts),
            "concepts": filtered_concepts,
            "sample_usage": f"Use get_company_facts_concepts with concepts=['{filtered_concepts[0] if filtered_concepts else 'ConceptName'}']",
            "success": True,
        }

    except Exception as e:
        return {
            "error": f"Failed to list company facts concepts: {str(e)}",
            "cik": cik,
            "formatted_cik": f"CIK{str(int(cik)).zfill(10)}",
            "category": category,
            "success": False,
        }


@mcp.tool("get_specific_concept_values")
def get_specific_concept_values_tool(
    cik: str,
    concept: str,
    category: str = "us-gaap",
    unit: str = "USD",
    recent_periods: int = 4,
    user_agent: str = sec_edgar_user_agent,
) -> Dict[str, Any]:
    """
    Get precise values for a specific financial concept with clear formatting.

    Parameters:
        cik (str): Central Index Key of the company.
        concept (str): Exact concept name (e.g., "RevenueFromContractWithCustomerExcludingAssessedTax").
        category (str): Facts category ("us-gaap", "dei", etc.) - default: "us-gaap".
        unit (str): Unit to retrieve (default: "USD").
        recent_periods (int): Number of recent periods to return (default: 4).
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: Precise concept values with clear formatting.
    """
    try:
        # Format CIK with leading zeros
        formatted_cik = f"CIK{str(int(cik)).zfill(10)}"

        # Build API URL
        api_url = f"https://data.sec.gov/api/xbrl/companyfacts/{formatted_cik}.json"

        headers = {"User-Agent": user_agent, "Accept": "application/json"}

        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Navigate to the specific concept
        if "facts" not in data or category not in data["facts"]:
            return {
                "error": f"Category '{category}' not found",
                "available_categories": list(data.get("facts", {}).keys()),
                "cik": formatted_cik,
                "success": False,
            }

        category_facts = data["facts"][category]

        if concept not in category_facts:
            return {
                "error": f"Concept '{concept}' not found in {category}",
                "available_concepts": list(category_facts.keys())[:20],
                "suggestion": "Use list_company_facts_concepts to find the exact concept name",
                "cik": formatted_cik,
                "success": False,
            }

        concept_data = category_facts[concept]

        # Extract concept metadata
        concept_info = {
            "label": concept_data.get("label", ""),
            "description": concept_data.get("description", ""),
        }

        # Get values for the specified unit
        if "units" not in concept_data or unit not in concept_data["units"]:
            available_units = list(concept_data.get("units", {}).keys())
            return {
                "error": f"Unit '{unit}' not found for concept '{concept}'",
                "available_units": available_units,
                "cik": formatted_cik,
                "concept": concept,
                "success": False,
            }

        unit_data = concept_data["units"][unit]

        # Sort by end date (most recent first)
        sorted_data = sorted(unit_data, key=lambda x: x.get("end", ""), reverse=True)

        # Take the most recent periods
        recent_data = sorted_data[:recent_periods]

        # Format the values clearly
        formatted_periods = []
        for item in recent_data:
            end_date = item.get("end", "")
            value = item.get("val", 0)
            form = item.get("form", "")
            fiscal_year = item.get("fy", "")
            fiscal_period = item.get("fp", "")

            # Format value with commas and billions if applicable
            if value >= 1000000000:
                formatted_value = f"${value / 1000000000:.3f} billion"
            elif value >= 1000000:
                formatted_value = f"${value / 1000000:.3f} million"
            else:
                formatted_value = f"${value:,.0f}"

            formatted_periods.append(
                {
                    "end_date": end_date,
                    "value": value,
                    "formatted_value": formatted_value,
                    "form": form,
                    "fiscal_year": fiscal_year,
                    "fiscal_period": fiscal_period,
                    "accession_number": item.get("accn", ""),
                }
            )

        # Calculate period-over-period changes
        for i in range(len(formatted_periods) - 1):
            current = formatted_periods[i]["value"]
            previous = formatted_periods[i + 1]["value"]
            if previous != 0:
                change_pct = ((current - previous) / previous) * 100
                formatted_periods[i]["change_vs_previous"] = f"{change_pct:+.1f}%"
                formatted_periods[i]["change_amount"] = current - previous

        return {
            "cik": formatted_cik,
            "entity_name": data.get("entityName", ""),
            "concept": concept,
            "category": category,
            "unit": unit,
            "concept_info": concept_info,
            "periods": formatted_periods,
            "total_periods_available": len(unit_data),
            "success": True,
        }

    except Exception as e:
        return {
            "error": f"Failed to get specific concept values: {str(e)}",
            "cik": cik,
            "concept": concept,
            "success": False,
        }


@mcp.tool("compare_concept_periods")
def compare_concept_periods_tool(
    cik: str,
    concept: str,
    date1: str,
    date2: str,
    category: str = "us-gaap",
    unit: str = "USD",
    user_agent: str = sec_edgar_user_agent,
) -> Dict[str, Any]:
    """
    Compare specific concept values between two dates.

    Parameters:
        cik (str): Central Index Key of the company.
        concept (str): Exact concept name.
        date1 (str): First date (YYYY-MM-DD format).
        date2 (str): Second date (YYYY-MM-DD format).
        category (str): Facts category - default: "us-gaap".
        unit (str): Unit to retrieve (default: "USD").
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: Comparison between two specific periods.
    """
    try:
        # Format CIK with leading zeros
        formatted_cik = f"CIK{str(int(cik)).zfill(10)}"

        # Build API URL
        api_url = f"https://data.sec.gov/api/xbrl/companyfacts/{formatted_cik}.json"

        headers = {"User-Agent": user_agent, "Accept": "application/json"}

        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Navigate to the specific concept
        if "facts" not in data or category not in data["facts"] or concept not in data["facts"][category]:
            return {"error": f"Concept '{concept}' not found in {category}", "cik": formatted_cik, "success": False}

        concept_data = data["facts"][category][concept]

        if "units" not in concept_data or unit not in concept_data["units"]:
            return {
                "error": f"Unit '{unit}' not found for concept '{concept}'",
                "available_units": list(concept_data.get("units", {}).keys()),
                "success": False,
            }

        unit_data = concept_data["units"][unit]

        # Find values for the specified dates
        value1 = None
        value2 = None
        period1_info = None
        period2_info = None

        for item in unit_data:
            end_date = item.get("end", "")
            if end_date == date1:
                value1 = item.get("val", 0)
                period1_info = item
            elif end_date == date2:
                value2 = item.get("val", 0)
                period2_info = item

        if value1 is None:
            available_dates = [item.get("end", "") for item in unit_data][-10:]  # Last 10 dates
            return {
                "error": f"No data found for date '{date1}'",
                "recent_available_dates": available_dates,
                "success": False,
            }

        if value2 is None:
            available_dates = [item.get("end", "") for item in unit_data][-10:]  # Last 10 dates
            return {
                "error": f"No data found for date '{date2}'",
                "recent_available_dates": available_dates,
                "success": False,
            }

        # Calculate comparison
        change_amount = value1 - value2
        change_pct = ((value1 - value2) / value2) * 100 if value2 != 0 else 0

        # Format values
        def format_value(val):
            if val >= 1000000000:
                return f"${val / 1000000000:.3f} billion"
            elif val >= 1000000:
                return f"${val / 1000000:.3f} million"
            else:
                return f"${val:,.0f}"

        return {
            "cik": formatted_cik,
            "entity_name": data.get("entityName", ""),
            "concept": concept,
            "concept_label": concept_data.get("label", ""),
            "comparison": {
                "date1": date1,
                "value1": value1,
                "formatted_value1": format_value(value1),
                "period1_info": {
                    "fiscal_year": period1_info.get("fy", ""),
                    "fiscal_period": period1_info.get("fp", ""),
                    "form": period1_info.get("form", ""),
                },
                "date2": date2,
                "value2": value2,
                "formatted_value2": format_value(value2),
                "period2_info": {
                    "fiscal_year": period2_info.get("fy", ""),
                    "fiscal_period": period2_info.get("fp", ""),
                    "form": period2_info.get("form", ""),
                },
                "change_amount": change_amount,
                "formatted_change": format_value(abs(change_amount)),
                "change_percentage": f"{change_pct:+.1f}%",
                "direction": "increase" if change_amount > 0 else "decrease" if change_amount < 0 else "no change",
            },
            "success": True,
        }

    except Exception as e:
        return {
            "error": f"Failed to compare concept periods: {str(e)}",
            "cik": cik,
            "concept": concept,
            "success": False,
        }


@mcp.tool("get_company_specific_concepts")
def get_company_specific_concepts_tool(
    cik: str, accession_number: str, user_agent: str = sec_edgar_user_agent
) -> Dict[str, Any]:
    """
    Discover company-specific XBRL concepts (aapl:, msft:, etc.) that are ONLY in filing data.

    **BEST TOOL FOR**: Finding company-specific concepts like segment members, proprietary metrics.
    **DISCOVERS**: aapl:AmericasSegmentMember, geographic segments, product categories, etc.
    **NOT IN APIs**: These concepts are exclusive to XBRL data, not available in SEC JSON APIs.

    Use this FIRST when you need to understand what company-specific data is available.

    Parameters:
        cik (str): Central Index Key of the company.
        accession_number (str): Filing accession number (e.g., "0000320193-25-000057").
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: All company-specific concepts categorized by type (segments, financial, etc.).
    """
    try:
        # Fetch the filing content
        txt_content = document_parser.fetch_filing_txt(cik, accession_number)

        if not txt_content:
            return {
                "error": "Failed to fetch filing content",
                "cik": cik,
                "accession_number": accession_number,
                "success": False,
            }

        # Extract company prefix from ticker (get first 4 chars of company name/ticker)
        # Try to determine company prefix from content
        import re

        # Look for company-specific namespace declarations
        namespace_pattern = r'xmlns:([a-z]+)="http://[^"]*'
        namespace_matches = re.findall(namespace_pattern, txt_content, re.IGNORECASE)

        # Filter out standard namespaces
        standard_namespaces = {
            "ix",
            "xsi",
            "xlink",
            "link",
            "xbrldt",
            "xbrldi",
            "dei",
            "us-gaap",
            "country",
            "currency",
            "exch",
            "invest",
            "naics",
            "sic",
            "stpr",
            "utr",
        }
        company_namespaces = [ns for ns in set(namespace_matches) if ns not in standard_namespaces and len(ns) <= 6]

        all_concepts = {}

        for company_prefix in company_namespaces:
            # Extract concepts for this company prefix
            concept_pattern = rf"{re.escape(company_prefix)}:([A-Za-z0-9_]+)"
            concept_matches = re.findall(concept_pattern, txt_content)
            unique_concepts = list(set(concept_matches))

            if unique_concepts:
                # Dynamic keyword analysis - find patterns in concept names
                keyword_groups: Dict[str, List[str]] = {}

                for concept in unique_concepts:
                    # Extract meaningful keywords from concept names
                    # Split on camelCase and common separators
                    import re

                    words = re.findall(r"[A-Z][a-z]*|[a-z]+", concept)
                    words = [w.lower() for w in words if len(w) > 2]  # Only meaningful words

                    for word in words:
                        if word not in keyword_groups:
                            keyword_groups[word] = []
                        keyword_groups[word].append(concept)

                # Find the most common keywords (categories)
                keyword_counts = {k: len(v) for k, v in keyword_groups.items()}

                # Sort keywords by frequency, keep top categories
                top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)

                # Build dynamic categories
                dynamic_categories: Dict[str, List[str]] = {}
                categorized_concepts = set()

                # Use top keywords as categories (only if they have 2+ concepts)
                for keyword, count in top_keywords:
                    if count >= 2 and len(dynamic_categories) < 8:  # Max 8 categories
                        category_name = f"{keyword}_concepts"
                        dynamic_categories[category_name] = sorted(keyword_groups[keyword])
                        categorized_concepts.update(keyword_groups[keyword])

                # Remaining concepts go to 'other_concepts'
                uncategorized = [c for c in unique_concepts if c not in categorized_concepts]
                if uncategorized:
                    dynamic_categories["other_concepts"] = sorted(uncategorized)

                all_concepts[company_prefix] = {
                    "total_concepts": len(unique_concepts),
                    "categories": dynamic_categories,
                    "all_concepts": sorted(unique_concepts),
                    "keyword_analysis": {
                        "total_keywords_found": len(keyword_groups),
                        "top_keywords": dict(top_keywords[:10]),  # Show top 10 patterns
                    },
                }

        # Also extract values for some key concepts if they exist
        concept_values = {}
        if all_concepts:
            # Look for some sample concept usage
            for company_prefix, data in all_concepts.items():
                # Get first few concepts from any category for sampling
                sample_concepts: List[str] = []
                for category_name, concepts_list in data["categories"].items():
                    if concepts_list and len(sample_concepts) < 3:
                        sample_concepts.extend(concepts_list[:2])  # Take up to 2 from each category

                # Extract usage for sample concepts
                for concept in sample_concepts[:3]:  # Limit to 3 total samples
                    # Look for contextual usage of this concept
                    concept_pattern = rf"{re.escape(company_prefix)}:{re.escape(concept)}"
                    matches = re.finditer(concept_pattern, txt_content)
                    concept_usages = []
                    for match in matches:
                        # Get context around the match
                        start = max(0, match.start() - 100)
                        end = min(len(txt_content), match.end() + 100)
                        context = txt_content[start:end].strip()
                        concept_usages.append(context[:200])  # Limit context length
                        if len(concept_usages) >= 2:  # Only get first 2 usages
                            break

                    if concept_usages:
                        concept_values[f"{company_prefix}:{concept}"] = concept_usages

        return {
            "cik": cik,
            "accession_number": accession_number,
            "filing_size_chars": len(txt_content),
            "company_namespaces": company_namespaces,
            "concepts_by_namespace": all_concepts,
            "total_company_concepts": sum(data["total_concepts"] for data in all_concepts.values()),
            "sample_concept_usage": concept_values,
            "note": "These company-specific concepts are NOT available through SEC JSON APIs - only in XBRL data",
            "success": True,
        }

    except Exception as e:
        return {
            "error": f"Failed to extract company-specific concepts: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


@mcp.tool("list_company_specific_concepts")
def list_company_specific_concepts_tool(
    cik: str,
    accession_number: str,
    namespace: Optional[str] = None,
    category: Optional[str] = None,
    user_agent: str = sec_edgar_user_agent,
) -> Dict[str, Any]:
    """
    Get clean list of company-specific concepts (aapl:AmericasSegmentMember, etc.) ready to use.

    **BEST TOOL FOR**: Getting exact concept names to copy/use, filtering by category.
    **OUTPUTS**: Clean list format perfect for selecting specific concepts.
    **FILTERS**: By namespace (aapl, msft) or category (member_concepts, securities_concepts).

    Examples: Get all Apple segment members, filter Microsoft financial concepts, etc.

    Parameters:
        cik (str): Central Index Key of the company.
        accession_number (str): Filing accession number (e.g., "0000320193-25-000057").
        namespace (str): Filter by company namespace (e.g., "aapl", "msft"). Shows all if None.
        category (str): Filter by category (member_concepts, securities_concepts, etc.). Shows all if None.
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: Clean, filtered list of company-specific concepts ready to use.
    """
    try:
        # Fetch the filing content
        txt_content = document_parser.fetch_filing_txt(cik, accession_number)

        if not txt_content:
            return {
                "error": "Failed to fetch filing content",
                "cik": cik,
                "accession_number": accession_number,
                "success": False,
            }

        import re

        # Extract company-specific namespaces
        namespace_pattern = r'xmlns:([a-z]+)="http://[^"]*'
        namespace_matches = re.findall(namespace_pattern, txt_content, re.IGNORECASE)

        # Filter out standard namespaces
        standard_namespaces = {
            "ix",
            "xsi",
            "xlink",
            "link",
            "xbrldt",
            "xbrldi",
            "dei",
            "us-gaap",
            "country",
            "currency",
            "exch",
            "invest",
            "naics",
            "sic",
            "stpr",
            "utr",
        }
        company_namespaces = [ns for ns in set(namespace_matches) if ns not in standard_namespaces and len(ns) <= 6]

        # If namespace filter provided, only use that one
        if namespace:
            if namespace in company_namespaces:
                company_namespaces = [namespace]
            else:
                return {
                    "error": f"Namespace '{namespace}' not found in filing",
                    "available_namespaces": company_namespaces,
                    "cik": cik,
                    "accession_number": accession_number,
                    "success": False,
                }

        all_concepts_list = []

        for company_prefix in company_namespaces:
            # Extract concepts for this company prefix
            concept_pattern = rf"{re.escape(company_prefix)}:([A-Za-z0-9_]+)"
            concept_matches = re.findall(concept_pattern, txt_content)
            unique_concepts = list(set(concept_matches))

            # Build dynamic keyword groups for this namespace
            keyword_groups: Dict[str, List[str]] = {}
            for concept in unique_concepts:
                # Extract meaningful keywords from concept names
                words = re.findall(r"[A-Z][a-z]*|[a-z]+", concept)
                words = [w.lower() for w in words if len(w) > 2]  # Only meaningful words

                for word in words:
                    if word not in keyword_groups:
                        keyword_groups[word] = []
                    keyword_groups[word].append(concept)

            # Find top keywords for categorization
            keyword_counts = {k: len(v) for k, v in keyword_groups.items()}
            top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)

            # Create dynamic category mapping
            concept_to_category: Dict[str, str] = {}
            used_categories: set[str] = set()

            # Assign concepts to dynamic categories
            for keyword, count in top_keywords:
                if count >= 2 and len(used_categories) < 8:  # Max 8 categories
                    category_name = f"{keyword}_concepts"
                    used_categories.add(category_name)
                    for concept in keyword_groups[keyword]:
                        if concept not in concept_to_category:
                            concept_to_category[concept] = category_name

            # Assign remaining concepts to 'other_concepts'
            for concept in unique_concepts:
                if concept not in concept_to_category:
                    concept_to_category[concept] = "other_concepts"

            # Build concept list with dynamic categories
            for concept in unique_concepts:
                concept_category = concept_to_category[concept]

                # Apply category filter if provided
                if category and concept_category != category:
                    continue

                all_concepts_list.append(
                    {
                        "full_concept": f"{company_prefix}:{concept}",
                        "namespace": company_prefix,
                        "concept_name": concept,
                        "category": concept_category,
                    }
                )

        # Sort by namespace, then by concept name
        all_concepts_list.sort(key=lambda x: (x["namespace"], x["concept_name"]))

        # Create summary by namespace
        namespace_summary: Dict[str, Dict[str, Any]] = {}
        for concept in all_concepts_list:
            ns = concept["namespace"]
            if ns not in namespace_summary:
                namespace_summary[ns] = {"total_concepts": 0, "categories": {}}
            if isinstance(namespace_summary[ns]["total_concepts"], int):
                namespace_summary[ns]["total_concepts"] += 1
            cat = concept["category"]
            if cat not in namespace_summary[ns]["categories"]:
                namespace_summary[ns]["categories"][cat] = 0
            if isinstance(namespace_summary[ns]["categories"][cat], int):
                namespace_summary[ns]["categories"][cat] += 1

        # Create clean concept list for easy copying
        clean_concept_list = [concept["full_concept"] for concept in all_concepts_list]

        return {
            "cik": cik,
            "accession_number": accession_number,
            "filters_applied": {"namespace": namespace, "category": category},
            "available_namespaces": company_namespaces,
            "total_concepts_found": len(all_concepts_list),
            "namespace_summary": namespace_summary,
            "concepts": all_concepts_list,
            "clean_concept_list": clean_concept_list,
            "usage_examples": {
                "copy_all_concepts": clean_concept_list,
                "sample_usage": f"Use concepts like: {clean_concept_list[0] if clean_concept_list else 'No concepts found'}",
            },
            "success": True,
        }

    except Exception as e:
        return {
            "error": f"Failed to list company-specific concepts: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


@mcp.tool("get_segment_revenue_data")
def get_segment_revenue_data_tool(
    cik: str, accession_number: str, user_agent: str = sec_edgar_user_agent
) -> Dict[str, Any]:
    """
    Get revenue breakdown by geographic segments (Americas, Europe, China, etc.) from SEC filing.

    **BEST TOOL FOR**: Getting revenue by geographic region, segment analysis, regional breakdown.
    **REPLACES**: Manual parsing of filing documents - this extracts exact revenue values automatically.
    **USE WHEN**: User asks for revenue by region, geographic breakdown, segment revenue, etc.

    Examples: "Apple revenue by region", "geographic segment breakdown", "Americas vs Europe revenue"

    Parameters:
        cik (str): Central Index Key of the company.
        accession_number (str): Filing accession number (e.g., "0000320193-24-000123").
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: Complete segment revenue breakdown with formatted values by region.
    """
    try:
        # Fetch the filing content
        txt_content = document_parser.fetch_filing_txt(cik, accession_number)

        if not txt_content:
            return {
                "error": "Failed to fetch filing content",
                "cik": cik,
                "accession_number": accession_number,
                "success": False,
            }

        import re

        # Find company namespace
        namespace_pattern = r'xmlns:([a-z]+)="http://[^"]*'
        namespace_matches = re.findall(namespace_pattern, txt_content, re.IGNORECASE)
        standard_namespaces = {
            "ix",
            "xsi",
            "xlink",
            "link",
            "xbrldt",
            "xbrldi",
            "dei",
            "us-gaap",
            "country",
            "currency",
            "exch",
            "invest",
            "naics",
            "sic",
            "stpr",
            "utr",
            "srt",
            "ecd",
            "xbrli",
            "ixt",
            "xs",
        }
        company_namespaces = [ns for ns in set(namespace_matches) if ns not in standard_namespaces and len(ns) <= 6]

        if not company_namespaces:
            return {
                "error": "No company-specific namespace found",
                "cik": cik,
                "accession_number": accession_number,
                "success": False,
            }

        company_prefix = company_namespaces[0]  # Use first company namespace

        # Find segment members
        segment_pattern = rf"{re.escape(company_prefix)}:([A-Za-z0-9_]*Segment[A-Za-z0-9_]*Member)"
        segment_matches = re.findall(segment_pattern, txt_content)
        unique_segments = list(set(segment_matches))

        if not unique_segments:
            return {
                "error": "No segment members found",
                "available_members": [],
                "cik": cik,
                "accession_number": accession_number,
                "success": False,
            }

        # Extract revenue data for each segment
        segment_revenues: Dict[str, Any] = {}

        # Look for revenue-related XBRL facts with segment context
        for segment in unique_segments:
            segment_concept = f"{company_prefix}:{segment}"

            # Search for revenue values with this segment in context
            # Pattern to find XBRL facts with segment dimension
            revenue_pattern = r'<ix:nonFraction[^>]*contextRef="([^"]*)"[^>]*name="([^"]*[Rr]evenue[^"]*)"[^>]*>([^<]+)</ix:nonFraction>'

            revenue_matches = re.finditer(revenue_pattern, txt_content)

            for match in revenue_matches:
                context_ref = match.group(1)
                revenue_concept = match.group(2)
                value_text = match.group(3)

                # Check if this context contains our segment
                context_pattern = rf'<xbrli:context[^>]*id="{re.escape(context_ref)}"[^>]*>.*?</xbrli:context>'
                context_match = re.search(context_pattern, txt_content, re.DOTALL)

                if context_match and segment_concept in context_match.group(0):
                    # Extract period information
                    period_pattern = r"<xbrli:period>.*?<xbrli:endDate>([^<]+)</xbrli:endDate>.*?</xbrli:period>"
                    period_match = re.search(period_pattern, context_match.group(0))
                    end_date = period_match.group(1) if period_match else "Unknown"

                    # Clean and parse value
                    clean_value = re.sub(r"[^\d.]", "", value_text.replace(",", ""))
                    try:
                        numeric_value = float(clean_value)

                        # Get scale attribute
                        scale_pattern = (
                            rf'<ix:nonFraction[^>]*contextRef="{re.escape(context_ref)}"[^>]*scale="([^"]*)"'
                        )
                        scale_match = re.search(scale_pattern, txt_content)
                        scale = int(scale_match.group(1)) if scale_match else 0

                        # Apply scale
                        actual_value = numeric_value * (10**scale)

                        if segment not in segment_revenues:
                            segment_revenues[segment] = []

                        # Format value
                        if actual_value >= 1000000000:
                            formatted_value = f"${actual_value / 1000000000:.1f}B"
                        elif actual_value >= 1000000:
                            formatted_value = f"${actual_value / 1000000:.1f}M"
                        else:
                            formatted_value = f"${actual_value:,.0f}"

                        segment_revenues[segment].append(
                            {
                                "concept": revenue_concept,
                                "value": actual_value,
                                "formatted_value": formatted_value,
                                "end_date": end_date,
                                "context_ref": context_ref,
                            }
                        )
                    except (ValueError, TypeError):
                        continue

        # Also try to find revenue data using us-gaap concepts with segment dimensions
        us_gaap_revenue_concepts = [
            "us-gaap:Revenues",
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:SalesRevenueNet",
        ]

        for revenue_concept in us_gaap_revenue_concepts:
            revenue_pattern = rf'<ix:nonFraction[^>]*contextRef="([^"]*)"[^>]*name="{re.escape(revenue_concept)}"[^>]*>([^<]+)</ix:nonFraction>'
            revenue_matches = re.finditer(revenue_pattern, txt_content)

            for match in revenue_matches:
                context_ref = match.group(1)
                value_text = match.group(2)

                # Check if this context contains segment information
                context_pattern = rf'<xbrli:context[^>]*id="{re.escape(context_ref)}"[^>]*>.*?</xbrli:context>'
                context_match = re.search(context_pattern, txt_content, re.DOTALL)

                if context_match:
                    context_content = context_match.group(0)

                    # Find which segment this belongs to
                    for segment in unique_segments:
                        segment_concept = f"{company_prefix}:{segment}"
                        if segment_concept in context_content:
                            # Extract period and value
                            period_pattern = (
                                r"<xbrli:period>.*?<xbrli:endDate>([^<]+)</xbrli:endDate>.*?</xbrli:period>"
                            )
                            period_match = re.search(period_pattern, context_content)
                            end_date = period_match.group(1) if period_match else "Unknown"

                            # Clean and parse value
                            clean_value = re.sub(r"[^\d.]", "", value_text.replace(",", ""))
                            try:
                                numeric_value = float(clean_value)

                                # Get scale attribute
                                scale_pattern = (
                                    rf'<ix:nonFraction[^>]*contextRef="{re.escape(context_ref)}"[^>]*scale="([^"]*)"'
                                )
                                scale_match = re.search(scale_pattern, txt_content)
                                scale = int(scale_match.group(1)) if scale_match else 0

                                # Apply scale
                                actual_value = numeric_value * (10**scale)

                                if segment not in segment_revenues:
                                    segment_revenues[segment] = []

                                # Format value
                                if actual_value >= 1000000000:
                                    formatted_value = f"${actual_value / 1000000000:.1f}B"
                                elif actual_value >= 1000000:
                                    formatted_value = f"${actual_value / 1000000:.1f}M"
                                else:
                                    formatted_value = f"${actual_value:,.0f}"

                                segment_revenues[segment].append(
                                    {
                                        "concept": revenue_concept,
                                        "value": actual_value,
                                        "formatted_value": formatted_value,
                                        "end_date": end_date,
                                        "context_ref": context_ref,
                                    }
                                )
                            except (ValueError, TypeError):
                                continue

        return {
            "cik": cik,
            "accession_number": accession_number,
            "company_namespace": company_prefix,
            "total_segments_found": len(unique_segments),
            "segments_with_revenue_data": len(segment_revenues),
            "segment_revenues": segment_revenues,
            "all_segments_found": unique_segments,
            "note": "Revenue data extracted from XBRL contexts with segment dimensions",
            "success": True,
        }

    except Exception as e:
        return {
            "error": f"Failed to extract segment revenue data: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


@mcp.tool("get_segment_breakdown")
def get_segment_breakdown_tool(
    cik: str, accession_number: str, concept_filter: str = "", user_agent: str = sec_edgar_user_agent
) -> Dict[str, Any]:
    """
    **UNIVERSAL TOOL**: Get ANY company's segment breakdown from ANY filing with ANY concepts.

    **COMPLETELY GENERAL**: No assumptions about data types, segment names, or company structure
    **DYNAMIC DISCOVERY**: Finds all segment concepts automatically without hardcoded patterns
    **FLEXIBLE FILTERING**: Optional concept filter to focus on specific types (revenue, assets, etc.)
    **UNIVERSAL TAXONOMIES**: Works with any company namespace (aapl:, nvda:, msft:, googl:, etc.)

    This tool discovers and extracts segment data patterns dynamically without any hardcoded logic.

    Parameters:
        cik (str): Central Index Key of the company (e.g., "320193" for Apple, "1045810" for NVIDIA).
        accession_number (str): REQUIRED - Filing accession number (e.g., "0000320193-24-000123").
        concept_filter (str): OPTIONAL - Filter concepts containing this term (e.g., "Revenue", "Asset", "Income").
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: Dynamic segment breakdown with discovered patterns, values, and automatic grouping.
    """
    try:
        # Get all company-specific concepts
        concepts_result = get_company_specific_concepts_tool(cik, accession_number, user_agent)

        if not concepts_result.get("success"):
            return concepts_result

        # Extract all segment-like concepts dynamically
        company_namespaces = concepts_result.get("company_namespaces", [])
        concepts_by_namespace = concepts_result.get("concepts_by_namespace", {})

        # Find segment concepts (Member suffix) and related financial concepts
        segment_members = []
        financial_concepts = []

        for namespace, namespace_data in concepts_by_namespace.items():
            if namespace in company_namespaces:
                for category, concepts in namespace_data.items():
                    if isinstance(concepts, list):
                        for concept in concepts:
                            if "Member" in concept:
                                segment_members.append(f"{namespace}:{concept}")
                            else:
                                # Check if concept matches filter
                                if not concept_filter or concept_filter.lower() in concept.lower():
                                    financial_concepts.append(f"{namespace}:{concept}")

        if not segment_members and not financial_concepts:
            return {
                "error": "No segment or filtered concepts found in filing",
                "cik": cik,
                "accession_number": accession_number,
                "success": False,
            }

        # Get the raw filing content to extract XBRL context data
        filing_content = document_parser.fetch_filing_txt(cik, accession_number)

        # Extract XBRL contexts and values dynamically
        import re

        # Find all XBRL contexts with segments
        context_pattern = r'<xbrli:context[^>]*id="([^"]+)"[^>]*>(.*?)</xbrli:context>'
        contexts = re.findall(context_pattern, filing_content, re.DOTALL | re.IGNORECASE)

        # Find all concept values with contexts
        value_pattern = r'<([^>]+):([^>\s]+)[^>]*contextRef="([^"]+)"[^>]*>([^<]+)</[^>]+:[^>]+>'
        values = re.findall(value_pattern, filing_content, re.IGNORECASE)

        # Group data by segment patterns discovered dynamically
        segment_data = {}

        # Process values and match with contexts
        for namespace, concept, context_ref, value in values:
            full_concept = f"{namespace}:{concept}"

            # Apply concept filter if specified
            if concept_filter and concept_filter.lower() not in concept.lower():
                continue

            # Find matching context
            context_content = None
            for ctx_id, ctx_content in contexts:
                if ctx_id == context_ref:
                    context_content = ctx_content
                    break

            if context_content:
                # Extract segment information from context
                segment_refs = re.findall(
                    r'<xbrldi:explicitMember[^>]+dimension="[^"]*:([^"]+)Axis"[^>]*>([^<]+)</xbrldi:explicitMember>',
                    context_content,
                    re.IGNORECASE,
                )

                # Parse date from context
                date_match = re.search(
                    r"<xbrli:instant>([^<]+)</xbrli:instant>|<xbrli:endDate>([^<]+)</xbrli:endDate>",
                    context_content,
                    re.IGNORECASE,
                )
                end_date = date_match.group(1) or date_match.group(2) if date_match else "unknown"

                # Clean and parse value
                try:
                    clean_value = re.sub(r"[^0-9.-]", "", value)
                    numeric_value = float(clean_value) if clean_value else 0
                except ValueError:
                    numeric_value = 0

                # Format value
                if numeric_value >= 1000000000:
                    formatted_value = f"${numeric_value / 1000000000:.1f}B"
                elif numeric_value >= 1000000:
                    formatted_value = f"${numeric_value / 1000000:.1f}M"
                elif numeric_value >= 1000:
                    formatted_value = f"${numeric_value / 1000:.1f}K"
                else:
                    formatted_value = f"${numeric_value:.0f}"

                # Store data with discovered segment grouping
                segment_key = (
                    "_".join([seg[1].split(":")[-1] for seg in segment_refs]) if segment_refs else "no_segment"
                )

                if segment_key not in segment_data:
                    segment_data[segment_key] = {
                        "segment_dimensions": segment_refs,
                        "concepts": {},
                        "raw_segment_key": segment_key,
                    }

                if full_concept not in segment_data[segment_key]["concepts"]:
                    segment_data[segment_key]["concepts"][full_concept] = []

                segment_data[segment_key]["concepts"][full_concept].append(
                    {
                        "value": numeric_value,
                        "formatted_value": formatted_value,
                        "end_date": end_date,
                        "context_ref": context_ref,
                        "raw_value": value,
                    }
                )

        # Calculate totals and patterns automatically
        summary = {
            "total_segments_discovered": len(segment_data),
            "concepts_found": len(set(concept for seg in segment_data.values() for concept in seg["concepts"].keys())),
            "concept_filter_applied": concept_filter if concept_filter else "none",
            "company_namespaces": company_namespaces,
        }

        # Find the most common concept (likely the one with values across segments)
        concept_counts: Dict[str, int] = {}
        for seg_data in segment_data.values():
            for concept in seg_data["concepts"].keys():
                concept_counts[concept] = concept_counts.get(concept, 0) + 1

        primary_concept = max(concept_counts.items(), key=lambda x: x[1])[0] if concept_counts else None

        return {
            "cik": cik,
            "accession_number": accession_number,
            "filing_size_chars": len(filing_content),
            "segment_data": segment_data,
            "summary": summary,
            "primary_concept": primary_concept,
            "discovered_patterns": {
                "segment_members_found": len(segment_members),
                "financial_concepts_found": len(financial_concepts),
                "total_contexts_found": len(contexts),
                "total_values_found": len(values),
            },
            "success": True,
        }

    except Exception as e:
        return {
            "error": f"Failed to get segment breakdown: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


@mcp.tool("get_recommended_tools")
def get_recommended_tools_tool(form_type: str, analysis_goal: str = "financial_analysis") -> Dict[str, Any]:
    """
    **SMART RECOMMENDATIONS**: Get the best tools to use for specific SEC form types and analysis goals.

    **OPTIMIZED WORKFLOWS**: Recommends the most efficient tools for each form type
    **AVOIDS INEFFICIENT TOOLS**: Prevents using text extraction on XML forms, etc.
    **XBRL PREFERENCE**: For XBRL forms, recommends precise financial tools over text parsing

    Parameters:
        form_type (str): SEC form type (e.g., "10-Q", "10-K", "8-K", "4", "3", "5").
        analysis_goal (str): What you want to analyze (e.g., "financial_analysis", "segment_analysis", "insider_trading").

    Returns:
        Dict: Recommended tools with usage examples and explanations.
    """

    # Define form type categories
    xbrl_forms = ["10-Q", "10-K", "10-K/A", "10-Q/A", "8-K", "8-K/A", "20-F", "40-F", "6-K"]
    xml_forms = ["3", "4", "5", "11-K", "13F-HR", "13F-NT"]
    text_forms = ["S-1", "S-3", "S-4", "424B", "485BPOS", "N-1A", "DEF 14A", "PREM14A"]

    form_type_upper = form_type.upper()

    recommendations = {
        "form_type": form_type_upper,
        "analysis_goal": analysis_goal,
        "primary_tools": [],
        "avoid_tools": [],
        "workflow_examples": [],
        "notes": [],
    }

    # XBRL Forms (Financial Statements with structured data)
    if form_type_upper in xbrl_forms:
        recommendations["category"] = "XBRL_FINANCIAL"
        recommendations["notes"].append("XBRL forms contain structured financial data - use precise financial tools")

        if analysis_goal in ["financial_analysis", "revenue_analysis", "financial_metrics"]:
            recommendations["primary_tools"] = [
                "get_specific_concept_values",
                "compare_concept_periods",
                "get_company_facts_concepts",
                "list_company_facts_concepts",
            ]
            recommendations["workflow_examples"] = [
                "1. Use list_company_facts_concepts to find available concepts",
                "2. Use get_specific_concept_values for precise financial data",
                "3. Use compare_concept_periods for period-over-period analysis",
            ]

        elif analysis_goal in ["segment_analysis", "geographic_analysis", "product_analysis"]:
            recommendations["primary_tools"] = [
                "get_segment_breakdown",
                "get_company_specific_concepts",
                "list_company_specific_concepts",
            ]
            recommendations["workflow_examples"] = [
                "1. Use get_recent_filings_smart to get accession number",
                "2. Use get_segment_breakdown for automatic segment discovery",
                "3. Use get_company_specific_concepts for detailed segment concepts",
            ]

        else:  # General analysis
            recommendations["primary_tools"] = [
                "get_segment_breakdown",
                "get_specific_concept_values",
                "get_company_specific_concepts",
            ]

        recommendations["avoid_tools"] = ["stream_filing_txt_chunks", "get_filing_txt", "get_filing_best_content"]
        recommendations["notes"].append(
            "⚠️ AVOID text extraction tools for XBRL forms - use structured data tools instead"
        )

    # XML Forms (Insider Trading, Ownership)
    elif form_type_upper in xml_forms:
        recommendations["category"] = "XML_STRUCTURED"
        recommendations["notes"].append("XML forms need special parsing - text extraction often fails")

        if form_type_upper in ["3", "4", "5"]:  # Insider trading forms
            recommendations["primary_tools"] = [
                "parse_xml_filing",  # NEW: Specialized XML parser
                "get_filing_document_info",  # For understanding structure
            ]
            recommendations["workflow_examples"] = [
                "1. Use get_recent_filings_smart to get filings",
                "2. Use parse_xml_filing to extract structured insider trading data",
                "3. Use extract_data parameter: 'transactions', 'ownership', or 'all'",
            ]
            recommendations["notes"].append("✅ NEW: parse_xml_filing tool now handles Form 4 XML properly")

        recommendations["avoid_tools"] = ["get_filing_txt", "get_filing_best_content", "stream_filing_txt_chunks"]
        recommendations["notes"].append("⚠️ AVOID text extraction - XML forms don't extract well as text")

    # Text/HTML Forms (Registration, Proxy statements)
    elif form_type_upper in text_forms:
        recommendations["category"] = "TEXT_HTML"
        recommendations["notes"].append("Text/HTML forms - text extraction tools work well")

        recommendations["primary_tools"] = [
            "get_filing_best_content",
            "stream_filing_txt_chunks",
            "get_filing_txt_sections",
        ]
        recommendations["workflow_examples"] = [
            "1. Use get_recent_filings_smart to get filings",
            "2. Use get_filing_best_content for clean text extraction",
            "3. Use stream_filing_txt_chunks for large documents",
        ]

    # Unknown/Other forms
    else:
        recommendations["category"] = "UNKNOWN"
        recommendations["notes"].append("Unknown form type - try document info first")

        recommendations["primary_tools"] = ["get_filing_document_info", "get_filing_best_content"]
        recommendations["workflow_examples"] = [
            "1. Use get_filing_document_info to understand structure",
            "2. Try get_filing_best_content for text extraction",
            "3. If that fails, try structured data tools",
        ]

    # Add general recommendations
    recommendations["general_workflow"] = [
        "1. ALWAYS start with get_recent_filings_smart (most efficient)",
        "2. Use recommended primary_tools for your form type",
        "3. Avoid the avoid_tools list for better performance",
    ]

    return {
        "recommendations": recommendations,
        "xbrl_forms": xbrl_forms,
        "xml_forms": xml_forms,
        "text_forms": text_forms,
        "success": True,
    }


@mcp.tool("parse_xml_filing")
def parse_xml_filing_tool(
    cik: str, accession_number: str, extract_data: str = "all", user_agent: str = sec_edgar_user_agent
) -> Dict[str, Any]:
    """
    **XML PARSER**: Parse SEC XML filings (Form 4, 3, 5, etc.) and extract structured data.

    **HANDLES XML FORMS**: Specifically designed for XML-based SEC filings that text extraction can't handle
    **INSIDER TRADING**: Extracts transaction data from Form 4 filings
    **OWNERSHIP DATA**: Parses Form 3/5 ownership information
    **STRUCTURED OUTPUT**: Returns clean, structured data instead of raw XML

    Parameters:
        cik (str): Central Index Key of the company.
        accession_number (str): Filing accession number.
        extract_data (str): What to extract - "all", "transactions", "ownership", "summary".
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: Parsed XML data with structured information.
    """
    try:
        # Get the filing content
        filing_content = document_parser.fetch_filing_txt(cik, accession_number)

        if not filing_content:
            return {
                "error": "Could not fetch filing content",
                "cik": cik,
                "accession_number": accession_number,
                "success": False,
            }

        # Extract XML documents from the filing
        documents = document_parser.get_document_info_from_txt(filing_content)

        xml_documents = []
        for doc in documents:
            if doc.get("filename", "").endswith(".xml") or doc.get("type", "") in ["4", "3", "5"]:
                xml_documents.append(doc)

        if not xml_documents:
            return {
                "error": "No XML documents found in filing",
                "cik": cik,
                "accession_number": accession_number,
                "documents_found": documents,
                "success": False,
            }

        # Extract the main XML content
        lines = filing_content.split("\n")
        xml_content = None
        in_xml_doc = False
        xml_lines: List[str] = []
        collecting_xml = False

        for line in lines:
            line_stripped = line.strip()

            # Look for document boundaries
            if line_stripped.startswith("<DOCUMENT>"):
                in_xml_doc = True
                xml_lines = []
                collecting_xml = False
                continue
            elif line_stripped.startswith("</DOCUMENT>"):
                if collecting_xml and xml_lines:
                    xml_content = "\n".join(xml_lines)
                    break
                in_xml_doc = False
                xml_lines = []
                collecting_xml = False
                continue

            # Skip SEC metadata lines when in document
            if in_xml_doc:
                # Skip metadata lines like <TYPE>, <SEQUENCE>, <FILENAME>, <DESCRIPTION>
                if (
                    line_stripped.startswith("<TYPE>")
                    or line_stripped.startswith("<SEQUENCE>")
                    or line_stripped.startswith("<FILENAME>")
                    or line_stripped.startswith("<DESCRIPTION>")
                ):
                    continue

                # Start collecting when we hit XML declaration
                if "<?xml" in line_stripped:
                    collecting_xml = True
                    xml_lines.append(line)
                # Continue collecting XML content until we hit closing tags
                elif collecting_xml:
                    # Stop at SEC wrapper tags
                    if (
                        line_stripped.startswith("</XML>")
                        or line_stripped.startswith("</TEXT>")
                        or line_stripped.startswith("</HTML>")
                    ):
                        break
                    xml_lines.append(line)

        if not xml_content:
            # Try to find XML content directly
            xml_start = filing_content.find("<?xml")
            if xml_start > -1:
                # Find the end of the XML document
                xml_end = filing_content.find("</edgarSubmission>", xml_start)
                if xml_end == -1:
                    xml_end = filing_content.find("</ownershipDocument>", xml_start)
                if xml_end > -1:
                    xml_content = filing_content[xml_start : xml_end + 20]

        if not xml_content:
            return {
                "error": "Could not extract XML content from filing",
                "cik": cik,
                "accession_number": accession_number,
                "content_preview": filing_content[:500] + "..." if len(filing_content) > 500 else filing_content,
                "success": False,
            }

        # Parse the XML
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            # Try to clean the XML
            xml_clean = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)", "&amp;", xml_content)
            try:
                root = ET.fromstring(xml_clean)
            except ET.ParseError:
                return {
                    "error": f"XML parsing failed: {str(e)}",
                    "cik": cik,
                    "accession_number": accession_number,
                    "xml_preview": xml_content[:500] + "..." if len(xml_content) > 500 else xml_content,
                    "success": False,
                }

        # Determine document type and extract relevant data
        parsed_data = {
            "cik": cik,
            "accession_number": accession_number,
            "xml_size_chars": len(xml_content),
            "root_tag": root.tag,
            "document_type": "unknown",
        }

        # Parse ownership document (Form 4, 3, 5)
        if "ownershipDocument" in root.tag or root.find(".//ownershipDocument") is not None:
            ownership_doc = root if "ownershipDocument" in root.tag else root.find(".//ownershipDocument")
            parsed_data["document_type"] = "ownership_document"

            # Extract basic info
            parsed_data.update(parse_ownership_document(ownership_doc, extract_data))

        # Parse EDGAR submission wrapper
        elif "edgarSubmission" in root.tag:
            parsed_data["document_type"] = "edgar_submission"

            # Look for ownership document inside
            ownership_doc = root.find(".//ownershipDocument")
            if ownership_doc is not None:
                parsed_data.update(parse_ownership_document(ownership_doc, extract_data))
            else:
                # Extract general submission info
                parsed_data["submission_info"] = extract_edgar_submission_info(root)

        else:
            # Unknown XML structure - provide basic info
            parsed_data["document_type"] = "unknown_xml"
            parsed_data["xml_structure"] = analyze_xml_structure(root)

        parsed_data["success"] = True
        return parsed_data

    except Exception as e:
        return {
            "error": f"Failed to parse XML filing: {str(e)}",
            "cik": cik,
            "accession_number": accession_number,
            "success": False,
        }


def parse_ownership_document(ownership_doc, extract_data="all"):
    """Parse ownership document (Form 4/3/5) XML structure."""
    result = {}

    try:
        # Document info
        doc_info = ownership_doc.find("documentInfo")
        if doc_info is not None:
            result["document_info"] = {
                "form_type": get_xml_text(doc_info.find("formType")),
                "period_of_report": get_xml_text(doc_info.find("periodOfReport")),
                "date_of_filing": get_xml_text(doc_info.find("dateOfFilingString")),
            }

        # Issuer info
        issuer = ownership_doc.find("issuer")
        if issuer is not None:
            result["issuer"] = {
                "cik": get_xml_text(issuer.find("issuerCik")),
                "name": get_xml_text(issuer.find("issuerName")),
                "trading_symbol": get_xml_text(issuer.find("issuerTradingSymbol")),
            }

        # Reporting owner info
        reporting_owner = ownership_doc.find("reportingOwner")
        if reporting_owner is not None:
            owner_info = reporting_owner.find("reportingOwnerId")
            relationship = reporting_owner.find("reportingOwnerRelationship")

            result["reporting_owner"] = {
                "cik": get_xml_text(owner_info.find("rptOwnerCik")) if owner_info is not None else None,
                "name": get_xml_text(owner_info.find("rptOwnerName")) if owner_info is not None else None,
                "is_director": get_xml_text(relationship.find("isDirector")) if relationship is not None else None,
                "is_officer": get_xml_text(relationship.find("isOfficer")) if relationship is not None else None,
                "is_ten_percent_owner": get_xml_text(relationship.find("isTenPercentOwner"))
                if relationship is not None
                else None,
                "officer_title": get_xml_text(relationship.find("officerTitle")) if relationship is not None else None,
            }

        # Non-derivative transactions (if requested)
        if extract_data in ["all", "transactions"]:
            non_deriv_table = ownership_doc.find("nonDerivativeTable")
            if non_deriv_table is not None:
                transactions = []
                for transaction in non_deriv_table.findall("nonDerivativeTransaction"):
                    trans_data = parse_transaction(transaction)
                    if trans_data:
                        transactions.append(trans_data)
                result["non_derivative_transactions"] = transactions

            # Derivative transactions
            deriv_table = ownership_doc.find("derivativeTable")
            if deriv_table is not None:
                deriv_transactions = []
                for transaction in deriv_table.findall("derivativeTransaction"):
                    trans_data = parse_derivative_transaction(transaction)
                    if trans_data:
                        deriv_transactions.append(trans_data)
                result["derivative_transactions"] = deriv_transactions

        # Ownership summary
        if extract_data in ["all", "ownership", "summary"]:
            non_deriv_holdings = ownership_doc.find("nonDerivativeTable")
            if non_deriv_holdings is not None:
                holdings = []
                for holding in non_deriv_holdings.findall("nonDerivativeHolding"):
                    hold_data = parse_holding(holding)
                    if hold_data:
                        holdings.append(hold_data)
                result["non_derivative_holdings"] = holdings

    except Exception as e:
        result["parsing_error"] = str(e)

    return result


def parse_transaction(transaction):
    """Parse a non-derivative transaction."""
    try:
        trans_data = {}

        # Security info
        security = transaction.find("securityTitle")
        if security is not None:
            trans_data["security_title"] = get_xml_text(security.find("value"))

        # Transaction date
        trans_date = transaction.find("transactionDate")
        if trans_date is not None:
            trans_data["transaction_date"] = get_xml_text(trans_date.find("value"))

        # Transaction coding
        trans_coding = transaction.find("transactionCoding")
        if trans_coding is not None:
            trans_data["transaction_code"] = get_xml_text(trans_coding.find("transactionCode"))
            trans_data["equity_swap_involved"] = get_xml_text(trans_coding.find("equitySwapInvolved"))
            trans_data["form_type"] = get_xml_text(trans_coding.find("transactionFormType"))

        # Transaction amounts
        trans_amounts = transaction.find("transactionAmounts")
        if trans_amounts is not None:
            shares_elem = trans_amounts.find("transactionShares")
            price_elem = trans_amounts.find("transactionPricePerShare")
            acquired_elem = trans_amounts.find("transactionAcquiredDisposedCode")

            trans_data["shares"] = get_xml_text(shares_elem.find("value")) if shares_elem is not None else None
            trans_data["price_per_share"] = get_xml_text(price_elem.find("value")) if price_elem is not None else None
            trans_data["acquired_disposed"] = (
                get_xml_text(acquired_elem.find("value")) if acquired_elem is not None else None
            )

        # Post-transaction amounts
        post_trans = transaction.find("postTransactionAmounts")
        if post_trans is not None:
            shares_owned_elem = post_trans.find("sharesOwnedFollowingTransaction")
            trans_data["shares_owned_after"] = (
                get_xml_text(shares_owned_elem.find("value")) if shares_owned_elem is not None else None
            )

        # Ownership nature
        ownership = transaction.find("ownershipNature")
        if ownership is not None:
            direct_elem = ownership.find("directOrIndirectOwnership")
            trans_data["direct_indirect_ownership"] = (
                get_xml_text(direct_elem.find("value")) if direct_elem is not None else None
            )

        return trans_data

    except Exception:
        return None


def parse_derivative_transaction(transaction):
    """Parse a derivative transaction."""
    try:
        trans_data = {"type": "derivative"}

        # Security info
        security = transaction.find("securityTitle")
        if security is not None:
            trans_data["security_title"] = get_xml_text(security.find("value"))

        # Conversion or exercise price
        conv_price = transaction.find("conversionOrExercisePrice")
        if conv_price is not None:
            trans_data["conversion_price"] = get_xml_text(conv_price.find("value"))

        # Transaction info
        trans_info = transaction.find("transactionInfo")
        if trans_info is not None:
            trans_data["transaction_date"] = get_xml_text(trans_info.find("transactionDate/value"))
            trans_data["transaction_code"] = get_xml_text(trans_info.find("transactionCode/value"))

            # Transaction amounts
            trans_amounts = trans_info.find("transactionAmounts")
            if trans_amounts is not None:
                trans_data["shares"] = get_xml_text(trans_amounts.find("transactionShares/value"))
                trans_data["price_per_share"] = get_xml_text(trans_amounts.find("transactionPricePerShare/value"))

        return trans_data

    except Exception:
        return None


def parse_holding(holding):
    """Parse a non-derivative holding."""
    try:
        hold_data = {}

        # Security info
        security = holding.find("securityTitle")
        if security is not None:
            hold_data["security_title"] = get_xml_text(security.find("value"))

        # Post-transaction amounts
        post_trans = holding.find("postTransactionAmounts")
        if post_trans is not None:
            hold_data["shares_owned"] = get_xml_text(post_trans.find("sharesOwnedFollowingTransaction/value"))
            hold_data["direct_indirect"] = get_xml_text(post_trans.find("directOrIndirectOwnership/value"))

        return hold_data

    except Exception:
        return None


def get_xml_text(element):
    """Safely get text from XML element."""
    if element is not None and element.text:
        return element.text.strip()
    return None


def extract_edgar_submission_info(root):
    """Extract basic info from EDGAR submission wrapper."""
    info = {}

    try:
        # Look for header info
        header_data = root.find(".//headerData")
        if header_data is not None:
            info["submission_type"] = get_xml_text(header_data.find("submissionType"))
            info["filer_info"] = get_xml_text(header_data.find("filerInfo"))

        # Look for company info
        company_data = root.find(".//companyData")
        if company_data is not None:
            info["company_name"] = get_xml_text(company_data.find("companyConformedName"))
            info["cik"] = get_xml_text(company_data.find("cik"))

    except Exception:
        pass

    return info


def analyze_xml_structure(root):
    """Analyze unknown XML structure."""
    structure = {"root_tag": root.tag, "attributes": dict(root.attrib) if root.attrib else {}, "child_tags": []}

    for child in root:
        child_info = {
            "tag": child.tag,
            "has_text": bool(child.text and child.text.strip()),
            "has_children": len(list(child)) > 0,
            "attributes": dict(child.attrib) if child.attrib else {},
        }
        structure["child_tags"].append(child_info)

    return structure


@mcp.tool("get_recent_filings_smart")
def get_recent_filings_smart_tool(
    ticker: str = "",
    cik: str = "",
    form_types: str = "10-Q,10-K",
    count: int = 10,
    user_agent: str = sec_edgar_user_agent,
) -> Dict[str, Any]:
    """
    **OPTIMIZED TOOL**: Get recent filings efficiently with smart filtering from the start.

    **ELIMINATES WASTE**: Replaces the inefficient workflow of multiple get_recent_filings_rss calls.
    **DIRECT FILTERING**: Filters by form type immediately, not after multiple calls.
    **ONE-STOP SHOP**: Gets CIK + filtered filings in one efficient call.

    This should be the FIRST tool called after wanting to analyze a company's filings.

    Parameters:
        ticker (str): OPTIONAL - Ticker symbol (e.g., "AAPL", "NVDA"). Will get CIK automatically.
        cik (str): OPTIONAL - Central Index Key if you already have it.
        form_types (str): Comma-separated form types to filter (e.g., "10-Q,10-K", "8-K", "10-Q").
        count (int): Number of recent filings to return (default: 10).
        user_agent (str): User agent string required by the SEC.

    Returns:
        Dict: Recent filings with accession numbers, dates, and form types - ready to use.
    """
    try:
        # Step 1: Get CIK if ticker provided
        if ticker and not cik:
            cik_result = get_cik_by_ticker_tool(ticker)
            if "error" in cik_result:
                return {"error": cik_result["error"], "ticker": ticker, "success": False}
            cik = str(cik_result["cik"])

        if not cik:
            return {"error": "Either ticker or cik must be provided", "success": False}

        # Step 2: Use RSS feed approach (much more reliable!)
        import xml.etree.ElementTree as ET

        # Parse form types
        form_type_list = [ft.strip().upper() for ft in form_types.split(",") if ft.strip()]

        # Normalize CIK for RSS (needs to be zero-padded to 10 digits)
        normalized_cik = str(cik).zfill(10)

        filtered_filings: List[Dict[str, Any]] = []
        entity_name = "Unknown Company"

        # Try each form type with RSS feed
        for form_type in form_type_list:
            if len(filtered_filings) >= count:
                break

            try:
                rss_url = f"https://data.sec.gov/rss?cik={normalized_cik}&type={form_type}&count={count}"
                headers = {"User-Agent": user_agent}
                response = requests.get(rss_url, headers=headers, timeout=30)
                response.raise_for_status()

                content_text = response.text

                # Try ATOM parsing first (SEC uses ATOM format)
                try:
                    root = ET.fromstring(response.content)

                    # Check if it's ATOM format
                    if "feed" in root.tag:
                        # Define ATOM namespace
                        atom_ns = {"atom": "http://www.w3.org/2005/Atom"}

                        # Extract company name from feed title
                        feed_title = root.find("atom:title", atom_ns)
                        if feed_title is not None and feed_title.text:
                            title_text = feed_title.text
                            if "(" in title_text:
                                entity_name = title_text.split("(")[0].strip()

                        # Extract filings from ATOM entries
                        for entry in root.findall("atom:entry", atom_ns):
                            if len(filtered_filings) >= count:
                                break

                            title_elem = entry.find("atom:title", atom_ns)
                            link_elem = entry.find("atom:link", atom_ns)
                            updated_elem = entry.find("atom:updated", atom_ns)
                            summary_elem = entry.find("atom:summary", atom_ns)

                            if title_elem is not None and link_elem is not None:
                                title_text = title_elem.text or ""
                                link_href = link_elem.get("href", "") if link_elem is not None else ""
                                updated_date = updated_elem.text if updated_elem is not None else ""
                                summary_text = summary_elem.text if summary_elem is not None else ""

                                # Extract accession number from link
                                accession_match = re.search(r"(\d{10}-\d{2}-\d{6})", link_href)
                                if not accession_match and summary_text:
                                    accession_match = re.search(r"(\d{10}-\d{2}-\d{6})", summary_text)

                                if accession_match:
                                    accession_number = accession_match.group(1)

                                    # Extract filing date from updated date
                                    filing_date = ""
                                    if updated_date:
                                        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", updated_date)
                                        if date_match:
                                            filing_date = date_match.group(1)

                                    filing = {
                                        "accession_number": accession_number,
                                        "filing_date": filing_date,
                                        "form_type": form_type,
                                        "report_date": filing_date,
                                        "title": title_text,
                                        "link": link_href,
                                        "updated": updated_date,
                                        "summary": summary_text[:200] + "..."
                                        if len(summary_text) > 200
                                        else summary_text,
                                        "source": "atom_feed",
                                    }
                                    filtered_filings.append(filing)

                    # ATOM parsing succeeded, no need for fallbacks
                    if filtered_filings:
                        break  # Exit the try/except blocks

                except ET.ParseError:
                    # If ATOM parsing fails, try RSS parsing as fallback
                    try:
                        root = ET.fromstring(response.content)

                        # Try RSS format
                        channel = root.find("channel")
                        if channel is not None:
                            title = channel.find("title")
                            if title is not None and title.text:
                                title_text = title.text
                                if "(" in title_text:
                                    entity_name = title_text.split("(")[0].strip()

                        # Extract RSS items
                        for item in root.findall(".//item"):
                            if len(filtered_filings) >= count:
                                break

                            title_elem = item.find("title")
                            link_elem = item.find("link")
                            pub_date_elem = item.find("pubDate")

                            if title_elem is not None and link_elem is not None:
                                title_text = title_elem.text or ""
                                link_text = link_elem.text or ""
                                pub_date = pub_date_elem.text if pub_date_elem is not None else ""

                                accession_match = re.search(r"(\d{10}-\d{2}-\d{6})", link_text)
                                if accession_match:
                                    accession_number = accession_match.group(1)

                                    filing_date = ""
                                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", title_text)
                                    if date_match:
                                        filing_date = date_match.group(1)

                                    filing = {
                                        "accession_number": accession_number,
                                        "filing_date": filing_date,
                                        "form_type": form_type,
                                        "report_date": filing_date,
                                        "title": title_text,
                                        "link": link_text,
                                        "pub_date": pub_date,
                                    }
                                    filtered_filings.append(filing)

                    except Exception:
                        # If both fail, try regex parsing on raw content
                        accession_matches = re.findall(r"(\d{10}-\d{2}-\d{6})", content_text)
                        for accession_number in accession_matches[:count]:
                            filing = {
                                "accession_number": accession_number,
                                "filing_date": "",
                                "form_type": form_type,
                                "report_date": "",
                                "title": f"Filing {accession_number}",
                                "link": f"https://www.sec.gov/Archives/edgar/data/{normalized_cik.lstrip('0')}/{accession_number.replace('-', '')}/{accession_number}-index.htm",
                            }
                            filtered_filings.append(filing)

            except requests.RequestException:
                # Continue to next form type if HTTP request fails
                continue

        # If no form types specified, try a few common ones
        if not form_type_list:
            for default_form in ["10-Q", "10-K", "8-K"]:
                if len(filtered_filings) >= count:
                    break

                try:
                    rss_url = f"https://data.sec.gov/rss?cik={normalized_cik}&type={default_form}&count={count}"
                    headers = {"User-Agent": user_agent}
                    response = requests.get(rss_url, headers=headers, timeout=30)
                    response.raise_for_status()

                    # Parse ATOM XML
                    root = ET.fromstring(response.content)

                    # Define ATOM namespace
                    atom_ns = {"atom": "http://www.w3.org/2005/Atom"}

                    # Extract company name
                    feed_title = root.find("atom:title", atom_ns)
                    if feed_title is not None and feed_title.text:
                        title_text = feed_title.text
                        if "(" in title_text:
                            entity_name = title_text.split("(")[0].strip()

                    # Extract filings from ATOM entries
                    for entry in root.findall("atom:entry", atom_ns):
                        if len(filtered_filings) >= count:
                            break

                        title_elem = entry.find("atom:title", atom_ns)
                        link_elem = entry.find("atom:link", atom_ns)
                        updated_elem = entry.find("atom:updated", atom_ns)
                        summary_elem = entry.find("atom:summary", atom_ns)

                        if title_elem is not None and link_elem is not None:
                            title_text = title_elem.text or ""
                            link_href = link_elem.get("href", "") if link_elem is not None else ""
                            updated_date = updated_elem.text if updated_elem is not None else ""
                            summary_text = summary_elem.text if summary_elem is not None else ""

                            accession_match = re.search(r"(\d{10}-\d{2}-\d{6})", link_href)
                            if not accession_match and summary_text:
                                accession_match = re.search(r"(\d{10}-\d{2}-\d{6})", summary_text)

                            if accession_match:
                                accession_number = accession_match.group(1)

                                filing_date = ""
                                if updated_date:
                                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", updated_date)
                                    if date_match:
                                        filing_date = date_match.group(1)

                                if not filing_date:
                                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", title_text)
                                    if date_match:
                                        filing_date = date_match.group(1)

                                filing = {
                                    "accession_number": accession_number,
                                    "filing_date": filing_date,
                                    "form_type": default_form,
                                    "report_date": filing_date,
                                    "title": title_text,
                                    "link": link_href,
                                    "updated": updated_date,
                                    "summary": summary_text[:200] + "..." if len(summary_text) > 200 else summary_text,
                                }
                                filtered_filings.append(filing)

                except Exception:
                    continue

        # No expensive submissions API fallback - RSS/ATOM should work!

        if not filtered_filings:
            return {
                "error": f"No filings found using RSS feed for CIK {normalized_cik}",
                "cik": cik,
                "normalized_cik": normalized_cik,
                "requested_form_types": form_type_list,
                "rss_urls_tried": [
                    f"https://data.sec.gov/rss?cik={normalized_cik}&type={ft}&count={count}"
                    for ft in (form_type_list or ["10-Q", "10-K", "8-K"])
                ],
                "debug_info": "Tried ATOM parsing, RSS parsing, regex parsing, and submissions API fallback",
                "success": False,
            }

        # Add smart tool recommendations for found form types
        found_form_types = list(set(filing["form_type"] for filing in filtered_filings))
        tool_recommendations = {}

        for form_type in found_form_types:
            rec_result = get_recommended_tools_tool(form_type, "financial_analysis")
            if rec_result.get("success"):
                rec = rec_result["recommendations"]
                tool_recommendations[form_type] = {
                    "category": rec["category"],
                    "recommended_tools": rec["primary_tools"],
                    "avoid_tools": rec["avoid_tools"],
                    "key_note": rec["notes"][0] if rec["notes"] else "",
                }

        return {
            "cik": cik,
            "normalized_cik": normalized_cik,
            "entity_name": entity_name,
            "ticker": ticker if ticker else "unknown",
            "form_types_requested": form_type_list,
            "filings_found": len(filtered_filings),
            "filings": filtered_filings,
            "tool_recommendations": tool_recommendations,
            "data_source": "SEC RSS Feed (more reliable than submissions API)",
            "next_steps": "Use recommended tools above for each form type, or call get_recommended_tools for detailed guidance",
            "success": True,
        }

    except Exception as e:
        return {"error": f"Failed to get recent filings: {str(e)}", "ticker": ticker, "cik": cik, "success": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEC EDGAR MCP Server")
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["streamable-http", "sse", "stdio"],
        help="Transport protocol to use (default: stdio)",
    )
    args = parser.parse_args()

    mcp.run(transport=args.transport)
