"""Filing-related tools for SEC EDGAR data."""

from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Union

from edgar import get_current_filings

from ..core.models import FilingInfo
from ..utils.exceptions import FilingNotFoundError
from .base import BaseTools, ToolResponse


class FilingsTools(BaseTools):
    """Tools for retrieving and analyzing SEC filings."""

    def get_recent_filings(
        self,
        identifier: Optional[str] = None,
        form_type: Optional[Union[str, List[str]]] = None,
        days: int = 30,
        limit: int = 40,
    ) -> ToolResponse:
        """Get recent filings for a company or across all companies."""
        try:
            if identifier:
                company = self.client.get_company(identifier)
                filings = company.get_filings(form=form_type)
            else:
                filings = get_current_filings(form=form_type, page_size=limit)

            filings_list = []
            for i, filing in enumerate(filings):
                if i >= limit:
                    break
                filing_info = self._create_filing_info(filing)
                if filing_info:
                    filings_list.append(filing_info.to_dict())

            return {"success": True, "filings": filings_list, "count": len(filings_list)}
        except Exception as e:
            return {"success": False, "error": f"Failed to get recent filings: {e}"}

    def get_filing_content(
        self,
        identifier: str,
        accession_number: str,
        offset: int = 0,
        max_chars: int = 50000,
    ) -> ToolResponse:
        """Get filing content with paging support."""
        try:
            company = self.client.get_company(identifier)
            filing = self._find_filing(company.get_filings(), accession_number)

            if not filing:
                raise FilingNotFoundError(f"Filing {accession_number} not found")

            content = filing.text()
            total_chars = len(content)

            safe_offset = max(0, int(offset))
            safe_max_chars = int(max_chars) if max_chars and int(max_chars) > 0 else 50000

            page_end = min(safe_offset + safe_max_chars, total_chars)
            if safe_offset >= total_chars:
                page_content = ""
                page_end = total_chars
            else:
                page_content = content[safe_offset:page_end]

            next_offset = page_end if page_end < total_chars else None

            return {
                "success": True,
                "accession_number": filing.accession_number,
                "form_type": filing.form,
                "filing_date": filing.filing_date.isoformat(),
                "content": page_content,
                "url": filing.url,
                "offset": safe_offset,
                "returned_chars": len(page_content),
                "total_chars": total_chars,
                "next_offset": next_offset,
            }
        except FilingNotFoundError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to get filing content: {e}"}

    def analyze_8k(self, identifier: str, accession_number: str) -> ToolResponse:
        """Analyze an 8-K filing for specific events."""
        try:
            company = self.client.get_company(identifier)
            filing = self._find_filing(company.get_filings(form="8-K"), accession_number)

            if not filing:
                raise FilingNotFoundError(f"8-K filing {accession_number} not found")

            eightk = filing.obj()
            analysis = self._analyze_8k_content(eightk)
            return {"success": True, "analysis": analysis}
        except Exception as e:
            return {"success": False, "error": f"Failed to analyze 8-K: {e}"}

    def get_filing_sections(self, identifier: str, accession_number: str, form_type: str) -> ToolResponse:
        """Get specific sections from a filing."""
        try:
            company = self.client.get_company(identifier)
            filing = self._find_filing(company.get_filings(form=form_type), accession_number)

            if not filing:
                raise FilingNotFoundError(f"Filing {accession_number} not found")

            filing_obj = filing.obj()
            full_text = filing.text()
            normalized_sections = self._extract_normalized_sections(full_text, form_type)
            sections = self._extract_sections(filing_obj, form_type, normalized_sections)
            return {
                "success": True,
                "form_type": form_type,
                "accession_number": filing.accession_number,
                "filing_date": filing.filing_date.isoformat(),
                "url": filing.url,
                "contract_version": "2.0",
                "sections": sections,
                "available_sections": list(sections.keys()),
                "normalized_sections": normalized_sections,
                "normalized_section_count": len(normalized_sections),
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to get filing sections: {e}"}

    def _create_filing_info(self, filing) -> Optional[FilingInfo]:
        """Create a FilingInfo object from a filing."""
        try:
            return FilingInfo(
                accession_number=filing.accession_number,
                filing_date=self._parse_date(filing.filing_date),
                form_type=filing.form,
                company_name=filing.company,
                cik=filing.cik,
                file_number=getattr(filing, "file_number", None),
                acceptance_datetime=self._parse_date(getattr(filing, "acceptance_datetime", None)),
                period_of_report=self._parse_date(getattr(filing, "period_of_report", None)),
            )
        except Exception:
            return None

    def _analyze_8k_content(self, eightk) -> Dict[str, Any]:
        """Analyze 8-K content and extract events."""
        analysis: Dict[str, Any] = {
            "date_of_report": None,
            "items": getattr(eightk, "items", []),
            "events": {},
        }

        if hasattr(eightk, "date_of_report"):
            try:
                analysis["date_of_report"] = datetime.strptime(eightk.date_of_report, "%B %d, %Y").isoformat()
            except (ValueError, TypeError):
                pass

        item_descriptions = {
            "1.01": "Entry into Material Agreement",
            "1.02": "Termination of Material Agreement",
            "2.01": "Completion of Acquisition or Disposition",
            "2.02": "Results of Operations and Financial Condition",
            "2.03": "Creation of Direct Financial Obligation",
            "3.01": "Notice of Delisting",
            "4.01": "Changes in Accountant",
            "5.01": "Changes in Control",
            "5.02": "Departure/Election of Directors or Officers",
            "5.03": "Amendments to Articles/Bylaws",
            "7.01": "Regulation FD Disclosure",
            "8.01": "Other Events",
        }

        for item_code, description in item_descriptions.items():
            if hasattr(eightk, "has_item") and eightk.has_item(item_code):
                analysis["events"][item_code] = {"present": True, "description": description}

        if hasattr(eightk, "has_press_release"):
            analysis["has_press_release"] = eightk.has_press_release
            if eightk.has_press_release and hasattr(eightk, "press_releases"):
                analysis["press_releases"] = list(eightk.press_releases)[:3]

        return analysis

    def _extract_sections(self, filing_obj, form_type: str, normalized_sections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract compatibility sections from normalized section records."""
        sections: Dict[str, Any] = {}

        by_key = {str(s.get("section_key", "")): str(s.get("text", "")) for s in normalized_sections}
        key_candidates = {
            "business": ["item_1"],
            "risk_factors": ["item_1a", "partii_item_1a"],
            "mda": ["item_7", "item_2"],  # 10-K -> Item 7, 10-Q -> Item 2
        }
        for out_key, candidates in key_candidates.items():
            for candidate in candidates:
                value = by_key.get(candidate, "")
                if value:
                    sections[out_key] = value
                    break

        if hasattr(filing_obj, "financials"):
            sections["has_financials"] = True
        else:
            sections["has_financials"] = any(
                "financial statements" in str(s.get("title", "")).lower() for s in normalized_sections
            )

        return sections

    def _extract_normalized_sections(self, content: str, form_type: str) -> List[Dict[str, Any]]:
        """Extract robust section records from filing text."""
        if not isinstance(content, str) or not content.strip():
            return []
        content = self._preprocess_filing_text(content)
        if not content.strip():
            return []

        heading_re = re.compile(
            r"(?im)^(?P<header>(?:PART\s+[IVXLC]+\s*[,.-]?\s*)?ITEM\s+\d+[A-Z]?(?:\.\d+)?\.[^\n]{0,180}|"
            r"NOTE\s+\d+[A-Z]?\s*[-.:][^\n]{0,180}|"
            r"PART\s+[IVXLC]+\b[^\n]{0,120})\s*$"
        )
        matches: List[re.Match[str]] = []
        for match in heading_re.finditer(content):
            header = match.group("header").strip()
            if self._is_probable_toc_header(header):
                continue
            context_window = content[max(0, match.start() - 240) : match.start()]
            if "table of contents" in context_window.lower():
                continue
            matches.append(match)

        if not matches:
            return []

        sections: List[Dict[str, Any]] = []
        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
            header = match.group("header").strip()
            text = content[start:end].strip()
            section_key = self._normalize_section_key(header, idx + 1)
            sections.append(
                {
                    "section_key": section_key,
                    "canonical_key": self._canonical_key_from_header(header, section_key),
                    "title": header,
                    "text": text,
                    "order": idx + 1,
                    "start_offset": start,
                    "end_offset": end,
                    "char_count": len(text),
                    "source": "filing_text_regex",
                    "form_type": form_type,
                }
            )
        return sections

    def _is_probable_toc_header(self, header: str) -> bool:
        """Return True when a heading line likely comes from table of contents artifacts."""
        h = header.strip()
        lowered = h.lower()
        if "annual report on form" in lowered or "incorporated herein" in lowered:
            return True
        if re.search(r"\s\d{1,3}\s*$", h):
            return True
        if len(h) > 180:
            return True
        return False

    def _preprocess_filing_text(self, text: str) -> str:
        """Normalize ASCII-art filing layouts before heading detection."""
        cleaned_lines: List[str] = []
        border_only = re.compile(r"^[\+\-\|=\s\u2500-\u257F_]+$")
        pipe_wrapped = re.compile(r"^\|\s*(.*?)\s*\|$")
        page_number_only = re.compile(r"^\d{1,3}$")
        for raw in text.splitlines():
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped:
                cleaned_lines.append("")
                continue
            if border_only.match(stripped):
                continue
            if "table of contents" in stripped.lower():
                continue
            if page_number_only.match(stripped):
                continue
            m = pipe_wrapped.match(stripped)
            if m:
                inner = m.group(1).strip()
                if inner:
                    cleaned_lines.append(inner)
                continue
            cleaned_lines.append(stripped)
        return "\n".join(cleaned_lines)

    def _normalize_section_key(self, header: str, order: int) -> str:
        """Normalize heading text into deterministic section keys."""
        normalized = re.sub(r"\s+", " ", header).strip().lower()
        m_part_item = re.search(r"part\s+([ivxlc]+)\s*[,.-]?\s*item\s+(\d+[a-z]?)", normalized)
        if m_part_item:
            part = m_part_item.group(1)
            item = m_part_item.group(2)
            return f"part{part}_item_{item}"
        m_item = re.search(r"\bitem\s+(\d+[a-z]?)", normalized)
        if m_item:
            return f"item_{m_item.group(1)}"
        m_note = re.search(r"\bnote\s+(\d+[a-z]?)", normalized)
        if m_note:
            return f"footnote_{m_note.group(1)}"
        m_part = re.search(r"\bpart\s+([ivxlc]+)\b", normalized)
        if m_part:
            return f"part_{m_part.group(1)}"
        safe = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
        return safe if safe else f"section_{order}"

    def _canonical_key_from_header(self, header: str, section_key: str) -> str:
        """Return a part-agnostic canonical key for deterministic downstream matching."""
        normalized = re.sub(r"\s+", " ", header).strip().lower()
        m_item = re.search(r"\bitem\s+(\d+[a-z]?)", normalized)
        if m_item:
            return f"item_{m_item.group(1)}"
        m_note = re.search(r"\bnote\s+(\d+[a-z]?)", normalized)
        if m_note:
            return f"footnote_{m_note.group(1)}"
        return section_key
