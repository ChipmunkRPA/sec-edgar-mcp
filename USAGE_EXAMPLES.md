# SEC EDGAR MCP Server - Large Document Handling Examples

This document provides examples of using the new document content retrieval and chunking capabilities.

## New Tools Available

The SEC EDGAR MCP server now includes 4 new tools for handling large filing documents:

1. **`get_filing_document`** - Retrieve full document content
2. **`get_filing_sections`** - Extract document sections with summary
3. **`get_filing_section_content`** - Get specific section content with chunking
4. **`stream_filing_chunks`** - Stream document chunks with pagination

## Usage Examples

### 1. Getting Document Sections Overview

First, get an overview of the document structure:

```python
# Get sections overview for Apple's 2023 10-K
result = get_filing_sections(
    cik="320193",  # Apple's CIK
    accession_number="0000320193-23-000106", 
    document_name="aapl-20230930_10k.htm"
)

print(f"Document has {result['summary']['total_sections']} sections")
print(f"Total document length: {result['summary']['total_chars']} characters")

# Available sections:
for section in result['sections']:
    print(f"- {section['name']}: {section['word_count']} words ({section['section_type']})")
```

### 2. Reading Specific Section Content

Get content from a specific section (e.g., Business Overview - Item 1):

```python
# Get Item 1 (Business) content in chunks
business_content = get_filing_section_content(
    cik="320193",
    accession_number="0000320193-23-000106",
    document_name="aapl-20230930_10k.htm",
    section_type="item_1",  # Business section
    chunk_size=8000,  # 8K characters per chunk
    chunk_index=0     # First chunk
)

if business_content['success']:
    print(f"Section: {business_content['section_name']}")
    print(f"Chunk {business_content['chunk_index']} of {business_content['total_chunks']}")
    print(f"Content length: {len(business_content['content'])} characters")
    print("Content preview:")
    print(business_content['content'][:500] + "...")
```

### 3. Streaming Document Chunks

For very large documents, use streaming with pagination:

```python
# Stream chunks starting from chunk 0, get 3 chunks at a time
chunk_stream = stream_filing_chunks(
    cik="320193",
    accession_number="0000320193-23-000106",
    document_name="aapl-20230930_10k.htm",
    chunk_size=6000,      # 6K characters per chunk
    start_chunk=0,        # Start from beginning
    max_chunks=3          # Get 3 chunks
)

if chunk_stream['success']:
    print(f"Retrieved chunks {chunk_stream['pagination']['start_chunk']}-{chunk_stream['pagination']['end_chunk']}")
    print(f"Total document chunks: {chunk_stream['pagination']['total_chunks']}")
    
    for chunk in chunk_stream['chunks']:
        print(f"\nChunk {chunk['chunk_index']} from section '{chunk['section_name']}':")
        print(f"  Length: {chunk['char_count']} characters")
        print(f"  Preview: {chunk['content'][:200]}...")
    
    # Check if there are more chunks
    if chunk_stream['pagination']['has_next']:
        next_start = chunk_stream['pagination']['next_start']
        print(f"\nMore chunks available starting from index {next_start}")
```

### 4. Complete Document Workflow

Here's a complete workflow for analyzing a large SEC filing:

```python
def analyze_filing(cik, accession_number, document_name):
    """Complete workflow for analyzing a SEC filing."""
    
    # Step 1: Get document overview
    print("📄 Getting document overview...")
    sections = get_filing_sections(cik, accession_number, document_name)
    
    if not sections['success']:
        print(f"❌ Error: {sections['error']}")
        return
    
    print(f"✅ Document loaded: {sections['summary']['total_chars']} characters")
    print(f"📊 Found {sections['summary']['total_sections']} sections:")
    
    for section in sections['sections']:
        pct = (section['char_count'] / sections['summary']['total_chars']) * 100
        print(f"  - {section['name']}: {pct:.1f}% of document")
    
    # Step 2: Focus on key sections (Business, Risk Factors, MD&A)
    key_sections = ['item_1', 'item_1a', 'item_7']
    
    for section_type in key_sections:
        print(f"\n📋 Analyzing section: {section_type}")
        
        # Get first chunk of this section
        content = get_filing_section_content(
            cik, accession_number, document_name,
            section_type=section_type,
            chunk_size=4000,
            chunk_index=0
        )
        
        if content['success']:
            print(f"  Section: {content['section_name']}")
            print(f"  Total size: {content['section_summary']['total_chars']} characters")
            print(f"  Available in {content['total_chunks']} chunks")
            print(f"  First chunk preview: {content['content'][:300]}...")
        else:
            print(f"  ⚠️  Section not found: {content.get('error', 'Unknown error')}")

# Example usage
analyze_filing(
    cik="320193",  # Apple
    accession_number="0000320193-23-000106",
    document_name="aapl-20230930_10k.htm"
)
```

## Key Benefits

### 🎯 **Context-Aware Chunking**
- Documents are chunked at natural boundaries (paragraphs, sentences)
- Section-based organization preserves document structure
- Configurable chunk sizes (default: 8000 characters)

### 📊 **Intelligent Content Filtering** 
- Removes HTML markup and XBRL tags (can reduce size by 60%+)
- Extracts readable text content only
- Preserves document structure and formatting

### 🔄 **Streaming Support**
- Paginated access to large documents
- Navigate forward/backward through chunks
- Memory-efficient processing

### 📈 **Performance Optimized**
- Section extraction using regex patterns
- Overlap between chunks to maintain context
- Metadata tracking for navigation

## Section Types Available

The parser recognizes these 10-K section types:

- `item_1` - Business
- `item_1a` - Risk Factors  
- `item_2` - Properties
- `item_3` - Legal Proceedings
- `item_4` - Mine Safety Disclosures
- `item_5` - Market for Common Equity
- `item_6` - Selected Financial Data
- `item_7` - Management's Discussion and Analysis
- `item_7a` - Quantitative and Qualitative Market Risk
- `item_8` - Financial Statements
- `item_9` - Controls and Procedures
- `item_9a` - Controls and Procedures
- `item_9b` - Other Information
- `item_10` - Directors and Officers
- `item_11` - Executive Compensation
- `item_12` - Security Ownership
- `item_13` - Certain Relationships
- `item_14` - Principal Accountant Fees
- `item_15` - Exhibits

This enables targeted analysis of specific parts of SEC filings without being overwhelmed by the full document size.