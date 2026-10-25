"""Request-local review of a bounded, tool-free, non-sensitive input.

The caller's digest attests review of the exact input for possible provider
retention/training. It is not content classification or secret detection.
"""

import hashlib
import hmac

from ai_provider.contracts import AIMessage, AIRequest, MessageRole, PrivacyClass

MAX_REVIEWED_INPUT_BYTES = 65_536
REVIEWED_INPUT_METADATA = "reviewed_non_sensitive_sha256"


def reviewed_input_sha256(text: str) -> str:
    """Hash exactly the UTF-8 text supplied to the model, without normalization."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reviewed_input_request(
    text: str,
    *,
    approved_sha256: str,
    model: str,
    max_output_tokens: int = 2048,
) -> AIRequest:
    """Bind explicit non-sensitive-input review to one immutable request.

    Reviewing the digest means the caller approved these exact bytes for
    possible retention/training and excluded secrets and genuinely private data.
    No repository instructions, history, tools or continuation are composed here.
    """
    if not text.strip() or len(text.encode("utf-8")) > MAX_REVIEWED_INPUT_BYTES:
        raise ValueError("Reviewed input must be nonempty and at most 65536 UTF-8 bytes.")
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 8192:
        raise ValueError("Reviewed output allowance must be between 1 and 8192 tokens.")
    request = AIRequest(
        messages=(AIMessage(MessageRole.USER, text),),
        model=model,
        max_output_tokens=max_output_tokens,
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        metadata={REVIEWED_INPUT_METADATA: approved_sha256},
    )
    if not has_reviewed_non_sensitive_input(request):
        raise ValueError("Approval digest does not match the complete reviewed input.")
    return request


def has_reviewed_non_sensitive_input(request: AIRequest) -> bool:
    """Verify review is still bound to one bounded user message without tools.

    Recheck at the adapter boundary so adding history, a system prompt, tool
    schemas/results or private continuation invalidates this narrow exception.
    """
    if (
        request.privacy_class is not PrivacyClass.PUBLIC_OR_LOW_RISK
        or request.tools
        or len(request.messages) != 1
        or type(request.max_output_tokens) is not int
        or not 1 <= request.max_output_tokens <= 8192
    ):
        return False
    message = request.messages[0]
    digest = request.metadata.get(REVIEWED_INPUT_METADATA)
    if (
        message.role is not MessageRole.USER
        or message.name is not None
        or message.tool_call_id is not None
        or message.tool_calls
        or message.continuation is not None
        or not message.content.strip()
        or len(message.content.encode("utf-8")) > MAX_REVIEWED_INPUT_BYTES
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        return False
    return hmac.compare_digest(digest, reviewed_input_sha256(message.content))
