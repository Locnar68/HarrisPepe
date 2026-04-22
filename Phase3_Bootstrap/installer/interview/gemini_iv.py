"""
Phase 4 -- Gemini AI Chat interview section.

Asks whether to enable the /bob Gemini chat UI, collects the AI Studio
API key, and lets the operator pick the model.  Writes to GeminiConfig
which report.py emits as:

    PHASE4_ENABLED, GEMINI_API_KEY, GEMINI_MODEL
"""

from __future__ import annotations
from installer.config.schema import GeminiConfig
from installer.utils import ui

_MODEL_CHOICES = [
    "gemini-1.5-flash              (fast, cost-efficient -- recommended)",
    "gemini-1.5-pro                (higher reasoning quality)",
    "gemini-2.0-flash              (next-gen speed + quality)",
    "gemini-2.5-pro-preview-03-25  (highest capability, higher cost)",
]
_MODEL_VALUES = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.5-pro-preview-03-25",
]


def run() -> GeminiConfig:
    ui.section(
        "2g -- Phase 4 Gemini AI Chat (optional)",
        "The /bob interface pairs Vertex AI Search with Gemini to give\n"
        "synthesized, cited answers instead of raw search results.\n"
        "You need a free Gemini API key from Google AI Studio.\n"
        "/bob will become the default landing page when the server starts.",
    )

    if not ui.ask_bool("Enable Gemini AI chat (/bob interface)?", default=True):
        ui.note("Gemini disabled -- the plain Vertex search UI (/) will be used.")
        return GeminiConfig(enabled=False)

    ui.note(
        "GET YOUR API KEY:\n"
        "  1. Go to: https://aistudio.google.com/app/apikey\n"
        "  2. Click 'Create API key'\n"
        "  3. Copy the key and paste it below\n"
    )

    api_key = ui.ask_text(
        "Gemini API key",
        help_text="Starts with 'AIza...'  Stored in secrets/.env, never committed.",
        required=True,
    )

    choice = ui.ask_select(
        "Gemini model",
        choices=_MODEL_CHOICES,
        default=_MODEL_CHOICES[0],
    )
    model = _MODEL_VALUES[_MODEL_CHOICES.index(choice)]

    ui.success(
        f"Gemini enabled  |  model: {model}\n"
        "  /bob will open automatically when the web server starts."
    )

    return GeminiConfig(enabled=True, api_key=api_key, model=model, phase4_start_page=True)
