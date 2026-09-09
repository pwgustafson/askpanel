"""AskPanel — in-app help chat and guided feature requests, grounded in your corpus.

Quickstart::

    from askpanel import AskPanelConfig, create_router

    config = AskPanelConfig(
        product_name="Orchard",
        corpus_dir="help/",
        user_dependency=current_user,
        on_escalate=save_feedback,
    )
    app.include_router(create_router(config), prefix="/api/askpanel")
"""

from .config import AskPanelConfig
from .corpus import (
    DEFAULT_BANNED_WORDS,
    LintIssue,
    estimate_tokens,
    lint_corpus,
    lint_text,
    load_corpus,
    system_blocks,
)
from .prompts import DEFAULT_INTERVIEW_AGENDA
from .protocol import (
    PROTOCOL_HEADER,
    PROTOCOL_VERSION,
    ChatRequest,
    DeltaFrame,
    DoneFrame,
    ErrorFrame,
    EscalateRequest,
    EscalationPayload,
    EscalationResult,
    Message,
    StatusOut,
    SummarizeRequest,
    SummaryOut,
    plain_text,
)
from .provider import (
    AnthropicProvider,
    Provider,
    ProviderCall,
    ProviderCheck,
    ProviderError,
    StubProvider,
    Usage,
)
from .quota import DailyTurnCap, MemoryCounter
from .router import QuotaExceeded, call_host, create_router
from .sinks import github_issue, webhook

__version__ = "0.1.3"

__all__ = [
    "__version__",
    "AskPanelConfig",
    "create_router",
    "QuotaExceeded",
    "call_host",
    # protocol
    "PROTOCOL_VERSION",
    "PROTOCOL_HEADER",
    "Message",
    "ChatRequest",
    "SummarizeRequest",
    "SummaryOut",
    "EscalateRequest",
    "EscalationPayload",
    "EscalationResult",
    "StatusOut",
    "DeltaFrame",
    "DoneFrame",
    "ErrorFrame",
    # corpus
    "load_corpus",
    "lint_corpus",
    "lint_text",
    "LintIssue",
    "system_blocks",
    "estimate_tokens",
    "DEFAULT_BANNED_WORDS",
    "DEFAULT_INTERVIEW_AGENDA",
    # providers
    "Provider",
    "ProviderCall",
    "ProviderCheck",
    "ProviderError",
    "DailyTurnCap",
    "MemoryCounter",
    "plain_text",
    "AnthropicProvider",
    "StubProvider",
    "Usage",
    # sinks
    "github_issue",
    "webhook",
]
