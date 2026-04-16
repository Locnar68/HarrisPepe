"""Template drafting — fill document templates with RAG answers."""
from .engine import DraftingEngine, FillResult, load_query_map
from .writer import write_markdown, write_docx, fill_docx_template

__all__ = [
    "DraftingEngine", "FillResult", "load_query_map",
    "write_markdown", "write_docx", "fill_docx_template",
]
