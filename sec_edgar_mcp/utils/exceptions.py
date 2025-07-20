class SECEdgarMCPError(Exception):
    """Base exception for SEC EDGAR MCP."""
    pass


class CompanyNotFoundError(SECEdgarMCPError):
    """Raised when a company cannot be found."""
    pass


class FilingNotFoundError(SECEdgarMCPError):
    """Raised when a filing cannot be found."""
    pass


class APIError(SECEdgarMCPError):
    """Raised when the SEC API returns an error."""
    pass


class ParseError(SECEdgarMCPError):
    """Raised when parsing fails."""
    pass