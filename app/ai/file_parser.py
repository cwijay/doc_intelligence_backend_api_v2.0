import os
from dotenv import load_dotenv
import nest_asyncio
from typing import List, Tuple, Dict, Any
import json
import requests
import time
import re
import pandas as pd
import csv

# Conditional imports to handle Pydantic v1/v2 compatibility issues
try:
    from llama_index.core.schema import TextNode
    LLAMA_INDEX_AVAILABLE = True
except ImportError as e:
    # Create a fallback TextNode class
    class TextNode:
        def __init__(self, text: str, metadata: Dict[str, Any] = None):
            self.text = text
            self.metadata = metadata or {}
    LLAMA_INDEX_AVAILABLE = False
    print(f"LlamaIndex not available: {e}")

try:
    from llama_parse import LlamaParse
    LLAMA_PARSE_AVAILABLE = True
except ImportError as e:
    LLAMA_PARSE_AVAILABLE = False
    print(f"LlamaParse not available: {e}")

_ = load_dotenv()

# Apply nest_asyncio to support nested event loops
try:
    nest_asyncio.apply()
    print("Applied nest_asyncio for nested event loop support")
except (RuntimeError, ValueError) as e:
    print(f"Skipping nest_asyncio patch: {e}")

llama_cloud_api_key = os.getenv("LLAMA_CLOUD_API_KEY")

def clean_parsed_content(text: str) -> str:
    """
    Clean up parsed content by removing NaN values and formatting issues.
    """
    if not text:
        return ""
    
    # Remove various forms of NaN and null values
    text = re.sub(r'\bNaN\b', '', text)
    text = re.sub(r'\bnull\b', '', text)
    text = re.sub(r'\bundefined\b', '', text)
    text = re.sub(r'\bN/A\b', '', text)
    
    # Clean up extra whitespace
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Multiple newlines to double
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
    text = text.strip()
    
    return text

def convert_html_tables_to_markdown(text: str) -> str:
    """
    Convert HTML tables to Markdown tables in the given text.
    """
    # Simple HTML to Markdown table conversion
    # Replace <table> tags
    text = re.sub(r'<table[^>]*>', '', text)
    text = re.sub(r'</table>', '', text)
    
    # Replace <tr> tags with newlines
    text = re.sub(r'<tr[^>]*>', '', text)
    text = re.sub(r'</tr>', '\n', text)
    
    # Replace <td> and <th> tags with pipe separators
    text = re.sub(r'<td[^>]*>', '| ', text)
    text = re.sub(r'</td>', ' ', text)
    text = re.sub(r'<th[^>]*>', '| ', text)
    text = re.sub(r'</th>', ' ', text)
    
    # Clean up any remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    return text

def get_text_nodes(json_list: List[dict]) -> List[TextNode]:
    """
    Convert JSON list to TextNodes for further processing.
    """
    text_nodes = []
    for idx, page in enumerate(json_list):
        # Include header and footer content if available
        page_content = ""
        
        # Add header if present
        if "pageHeaderMarkdown" in page and page["pageHeaderMarkdown"]:
            page_content += f"**Header:**\n{page['pageHeaderMarkdown']}\n\n"
        
        # Add main content
        page_content += page.get("md", "")
        
        # Add footer if present
        if "pageFooterMarkdown" in page and page["pageFooterMarkdown"]:
            page_content += f"\n\n**Footer:**\n{page['pageFooterMarkdown']}"
        
        text_node = TextNode(
            text=page_content, 
            metadata={
                "page": page.get("page", idx + 1),
                "has_header": bool(page.get("pageHeaderMarkdown")),
                "has_footer": bool(page.get("pageFooterMarkdown"))
            }
        )
        text_nodes.append(text_node)
    return text_nodes

def parse_csv_to_markdown(file_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse CSV file to markdown format.
    
    Args:
        file_path: Path to the CSV file
        
    Returns:
        Tuple of (markdown_content, metadata)
    """
    try:
        # Read CSV file
        df = pd.read_csv(file_path)
        
        # Generate filename for header
        filename = os.path.basename(file_path)
        
        # Create markdown content
        markdown_content = f"# {filename}\n\n"
        markdown_content += f"**File Type:** CSV\n"
        markdown_content += f"**Rows:** {len(df)}\n"
        markdown_content += f"**Columns:** {len(df.columns)}\n\n"
        
        # Add column information
        markdown_content += "## Column Information\n\n"
        for i, col in enumerate(df.columns):
            data_type = str(df[col].dtype)
            non_null_count = df[col].count()
            markdown_content += f"- **{col}**: {data_type} ({non_null_count} non-null values)\n"
        
        markdown_content += "\n"
        
        # Convert dataframe to markdown table
        markdown_content += "## Data\n\n"
        
        # Limit rows to prevent extremely large outputs
        display_df = df.head(100) if len(df) > 100 else df
        if len(df) > 100:
            markdown_content += f"*Showing first 100 rows of {len(df)} total rows*\n\n"
        
        # Convert to markdown table
        markdown_table = display_df.to_markdown(index=False)
        markdown_content += markdown_table
        
        # Add summary statistics if numeric columns exist
        numeric_columns = df.select_dtypes(include=['number']).columns
        if len(numeric_columns) > 0:
            markdown_content += "\n\n## Summary Statistics\n\n"
            stats_df = df[numeric_columns].describe()
            markdown_content += stats_df.to_markdown()
        
        # Create metadata
        metadata = {
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "column_names": df.columns.tolist(),
            "column_types": {col: str(df[col].dtype) for col in df.columns},
            "numeric_columns": len(numeric_columns),
            "file_type": ".csv",
            "content_length": len(markdown_content),
            "has_headers": True,
            "has_footers": False,
            "total_pages": 1,
            "pages_with_content": 1
        }
        
        return markdown_content, metadata
        
    except Exception as e:
        raise Exception(f"Failed to parse CSV file: {str(e)}")


def parse_excel_to_markdown(file_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse Excel file to markdown format.
    
    Args:
        file_path: Path to the Excel file
        
    Returns:
        Tuple of (markdown_content, metadata)
    """
    try:
        # Read Excel file
        if file_path.endswith('.xlsx'):
            excel_file = pd.ExcelFile(file_path, engine='openpyxl')
        else:  # .xls
            excel_file = pd.ExcelFile(file_path, engine='xlrd')
        
        # Generate filename for header
        filename = os.path.basename(file_path)
        
        # Start markdown content
        markdown_content = f"# {filename}\n\n"
        markdown_content += f"**File Type:** Excel ({os.path.splitext(filename)[1]})\n"
        markdown_content += f"**Worksheets:** {len(excel_file.sheet_names)}\n\n"
        
        # List all worksheets
        markdown_content += "## Worksheets\n\n"
        for i, sheet_name in enumerate(excel_file.sheet_names, 1):
            markdown_content += f"{i}. {sheet_name}\n"
        markdown_content += "\n"
        
        total_rows = 0
        total_columns = 0
        all_column_names = []
        
        # Process each worksheet
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            total_rows += len(df)
            total_columns += len(df.columns)
            all_column_names.extend(df.columns.tolist())
            
            markdown_content += f"## Worksheet: {sheet_name}\n\n"
            markdown_content += f"**Rows:** {len(df)}\n"
            markdown_content += f"**Columns:** {len(df.columns)}\n\n"
            
            # Add column information
            if len(df.columns) > 0:
                markdown_content += "### Columns\n\n"
                for col in df.columns:
                    data_type = str(df[col].dtype)
                    non_null_count = df[col].count()
                    markdown_content += f"- **{col}**: {data_type} ({non_null_count} non-null values)\n"
                markdown_content += "\n"
            
            # Add data (limit rows to prevent extremely large outputs)
            if len(df) > 0:
                markdown_content += "### Data\n\n"
                display_df = df.head(50) if len(df) > 50 else df
                if len(df) > 50:
                    markdown_content += f"*Showing first 50 rows of {len(df)} total rows*\n\n"
                
                # Convert to markdown table
                try:
                    markdown_table = display_df.to_markdown(index=False)
                    markdown_content += markdown_table
                except Exception:
                    # Fallback if markdown conversion fails
                    markdown_content += "```\n"
                    markdown_content += str(display_df)
                    markdown_content += "\n```"
                
                markdown_content += "\n\n"
                
                # Add summary statistics for numeric columns
                numeric_columns = df.select_dtypes(include=['number']).columns
                if len(numeric_columns) > 0:
                    markdown_content += f"### Summary Statistics for {sheet_name}\n\n"
                    try:
                        stats_df = df[numeric_columns].describe()
                        markdown_content += stats_df.to_markdown()
                        markdown_content += "\n\n"
                    except Exception:
                        markdown_content += "Could not generate summary statistics.\n\n"
        
        # Create metadata
        metadata = {
            "total_rows": total_rows,
            "total_columns": total_columns,
            "worksheets": len(excel_file.sheet_names),
            "worksheet_names": excel_file.sheet_names,
            "all_column_names": list(set(all_column_names)),
            "file_type": os.path.splitext(filename)[1],
            "content_length": len(markdown_content),
            "has_headers": True,
            "has_footers": False,
            "total_pages": len(excel_file.sheet_names),
            "pages_with_content": len(excel_file.sheet_names)
        }
        
        return markdown_content, metadata
        
    except Exception as e:
        raise Exception(f"Failed to parse Excel file: {str(e)}")


system_prompt = """
You are a comprehensive document parser that must capture EVERY piece of information from the document.

CRITICAL REQUIREMENTS:
1. Extract ALL text content including headers, footers, titles, labels, and field names
2. Preserve ALL form fields and their values
3. Capture ALL table data including headers, cells, and any merged cells
4. Include ALL metadata, annotations, and formatting information
5. Extract text from ALL areas of the page including margins, sidebars, and watermarks
6. Do NOT skip or summarize any content - include everything verbatim
7. Pay special attention to handwritten text and annotations
8. Preserve document structure and formatting as much as possible
9. Include page numbers, headers, and footers with clear identification
10. Extract text from images, charts, and diagrams when present

For handwritten content:
- Identify and transcribe all handwritten text
- Note where handwritten content appears (margins, forms, annotations)
- Preserve the context and location of handwritten elements

For headers and footers:
- Clearly identify and extract all header content
- Clearly identify and extract all footer content
- Include page numbers and document metadata
- Preserve formatting and positioning information
"""

def parse_file_with_llama_parse(file_path: str, result_type: str = "markdown") -> str:
    """
    Parse file using LlamaParse with enhanced options for handwritten content and header/footer detection.
    
    Args:
        file_path: Path to the file to parse
        result_type: Type of result to return ("markdown" or "text")
        
    Returns:
        Parsed content as string
    """
    if not LLAMA_PARSE_AVAILABLE:
        raise ValueError("LlamaParse is not available due to dependency conflicts")
        
    if not llama_cloud_api_key:
        raise ValueError("LLAMA_CLOUD_API_KEY environment variable is required")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        # Initialize LlamaParse with enhanced parsing options
        parser = LlamaParse(
            api_key=llama_cloud_api_key,
            result_type=result_type,
            verbose=True,
            language="en",
            
            # Header/Footer handling options
            hide_headers=False,  # Keep headers visible but also preserve in metadata
            hide_footers=False,  # Keep footers visible but also preserve in metadata
            page_header_prefix="**PAGE HEADER:** ",
            page_header_suffix=" **END HEADER**\n",
            page_footer_prefix="**PAGE FOOTER:** ",
            page_footer_suffix=" **END FOOTER**\n",
            
            # Enhanced parsing options for comprehensive extraction
            parsing_instruction=system_prompt,
            
            # Additional options for better content extraction
            premium_mode=True,  # Use premium mode for better accuracy
            
            # Table extraction
            table_special_token="<table>",
            
            # Image extraction (if needed)
            extract_images=True,
        )
        
        print(f"Starting to parse file: {file_path}")
        
        # Parse the document
        documents = parser.load_data(file_path)
        
        if not documents:
            print(f"Warning: No content extracted from file: {file_path}")
            return ""
        
        # Process documents and extract content
        if result_type == "markdown":
            # Get JSON result for metadata access
            json_result = parser.get_json_result(file_path)
            
            # Combine all content including headers and footers
            all_content = []
            for i, doc in enumerate(documents):
                content = clean_parsed_content(doc.text)
                
                # Add page separator for multi-page documents
                if i > 0:
                    all_content.append(f"\n\n--- Page {i + 1} ---\n\n")
                
                all_content.append(content)
            
            parsed_content = "".join(all_content)
            
            # Convert any HTML tables to Markdown
            parsed_content = convert_html_tables_to_markdown(parsed_content)
            
        else:
            # For text result type, simply combine all document text
            parsed_content = "\n\n".join([clean_parsed_content(doc.text) for doc in documents])
        
        print(f"Successfully parsed file: {file_path}")
        print(f"Content length: {len(parsed_content)} characters")
        
        return parsed_content
        
    except Exception as e:
        print(f"Error parsing file {file_path}: {str(e)}")
        raise Exception(f"Failed to parse file: {str(e)}")

def get_supported_file_types() -> List[str]:
    """
    Get list of file types supported by LlamaParse and custom parsers.
    
    Returns:
        List of supported file extensions
    """
    return ['.pdf', '.docx', '.doc', '.pptx', '.ppt', '.txt', '.rtf', '.html', '.xml', '.xlsx', '.xls', '.csv']

def is_supported_file_type(file_path: str) -> bool:
    """
    Check if file type is supported for parsing.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file type is supported, False otherwise
    """
    file_extension = os.path.splitext(file_path)[1].lower()
    return file_extension in get_supported_file_types()

def parse_with_metadata(file_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse file and return both content and metadata including headers/footers.
    
    Args:
        file_path: Path to the file to parse
        
    Returns:
        Tuple of (parsed_content, metadata_dict)
    """
    # Get file extension to determine parsing method
    file_extension = os.path.splitext(file_path)[1].lower()
    
    # Handle CSV files
    if file_extension == '.csv':
        return parse_csv_to_markdown(file_path)
    
    # Handle Excel files
    elif file_extension in ['.xlsx', '.xls']:
        return parse_excel_to_markdown(file_path)
    
    # Handle other files with LlamaParse
    else:
        if not LLAMA_PARSE_AVAILABLE:
            raise ValueError("LlamaParse is not available due to dependency conflicts")
            
        if not llama_cloud_api_key:
            raise ValueError("LLAMA_CLOUD_API_KEY environment variable is required")
        
        parser = LlamaParse(
            api_key=llama_cloud_api_key,
            result_type="markdown",
            verbose=True,
            hide_headers=False,
            hide_footers=False,
            parsing_instruction=system_prompt,
        )
        
        # Get both documents and JSON result
        documents = parser.load_data(file_path)
        json_result = parser.get_json_result(file_path)
        
        # Extract content
        content = "\n\n".join([clean_parsed_content(doc.text) for doc in documents])
        
        # Extract metadata
        try:
            metadata = {
                "total_pages": len(json_result) if json_result else len(documents),
                "has_headers": any(page.get("pageHeaderMarkdown") for page in json_result) if json_result else False,
                "has_footers": any(page.get("pageFooterMarkdown") for page in json_result) if json_result else False,
                "file_type": os.path.splitext(file_path)[1],
                "content_length": len(content),
                "pages_with_content": len([doc for doc in documents if doc.text.strip()]),
            }
        except Exception as e:
            print(f"Debug: Error creating metadata: {e}")
            metadata = {
                "total_pages": len(documents) if documents else 0,
                "has_headers": False,
                "has_footers": False,
                "file_type": os.path.splitext(file_path)[1],
                "content_length": len(content),
                "pages_with_content": len([doc for doc in documents if doc.text.strip()]),
            }
        
        if json_result:
            # Add page-specific metadata
            metadata["pages"] = []
            for i, page in enumerate(json_result):
                page_meta = {
                    "page_number": page.get("page", i + 1),
                    "has_header": bool(page.get("pageHeaderMarkdown")),
                    "has_footer": bool(page.get("pageFooterMarkdown")),
                    "content_length": len(page.get("md", "")),
                }
                if page.get("pageHeaderMarkdown"):
                    page_meta["header_content"] = page["pageHeaderMarkdown"]
                if page.get("pageFooterMarkdown"):
                    page_meta["footer_content"] = page["pageFooterMarkdown"]
                metadata["pages"].append(page_meta)
        
        return content, metadata