"""Vertex AI Search query surface — classical search + Gemini RAG answers."""
from .search import search
from .answer import answer

__all__ = ["search", "answer"]
