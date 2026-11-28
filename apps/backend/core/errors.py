"""Retailer- and customer-facing error text.

Integrations keep the provider sentence for the action log. Anything that
leaves /api/v1 in an error field passes through retailer_message first.
"""

from __future__ import annotations

import re

_VENDOR_WORD = re.compile(r"\b(mobikwik|payu|cashfree|kaleyra|cloudflare)\b", re.I)
_DUMP = re.compile(r"<html|traceback|exception|invalid client|^\s*[\[{]|http/\d|returned http\b", re.I)
_CRYPTIC = frozenset(
    {
        "invalid request",
        "invalid client id",
        "unauthorized",
        "unauthorized access",
        "forbidden",
        "bad request",
        "internal server error",
        "error",
        "failed",
        "failure",
    }
)


def retailer_message(raw: str) -> str:
    """A short sentence the counter can show. Provider names stay in the log."""
    text = " ".join(str(raw or "").split())
    if not text:
        return "Something went wrong. Try again."
    low = text.lower()
    released = "wallet hold was released" in low or "auto-refund" in low
    public = _phrase(low)
    if public is None:
        if _is_dump(text, low):
            public = _category(low)
        else:
            public = _VENDOR_WORD.sub(_plain_vendor, text)
            if re.search(r"\btoken\b|agent [A-Za-z0-9]{8,}", public, re.I):
                public = _category(low)
    if released and "wallet" not in public.lower() and "back in" not in public.lower():
        public = public.rstrip(".") + ". The amount is back in the wallet."
    return public[:240]


def _phrase(low: str) -> str | None:
    if "unsupported payment channel" in low or ("lpg" in low and "reject" in low):
        return "This operator is not enabled for cylinder booking on your account. Try another gas provider."
    if "token" in low or "rate limit" in low or "1015" in low or "too many" in low:
        return "The biller service is busy. Wait a minute and try again."
    if "not configured" in low or "misconfigured" in low:
        return "This service is not available right now. Try again shortly."
    if "timed out" in low or "timeout" in low or "not reachable" in low or "did not respond" in low:
        return "The service did not respond. Try again."
    if "plans not available" in low or "recharge plans not" in low:
        return "No plans are available for this operator and circle."
    if "amount does not match" in low:
        return "The paid amount does not match this order."
    if "could not verify payment" in low:
        return "The payment could not be confirmed. Try again."
    if "email is required" in low and "payu" in low:
        return "Customer email is required for this payment."
    if "name is required" in low and "payu" in low:
        return "Customer name is required for this payment."
    if low.strip(" .") in _CRYPTIC:
        return "The request could not be completed. Check the details and try again."
    return None


def _is_dump(text: str, low: str) -> bool:
    if _DUMP.search(text):
        return True
    if low.strip(" .") in _CRYPTIC:
        return True
    if len(text) > 180 and _VENDOR_WORD.search(text):
        return True
    return False


def _category(low: str) -> str:
    if "plan" in low:
        return "No plans are available for this operator and circle."
    if "lpg" in low or "payment channel" in low:
        return "This operator is not enabled for cylinder booking on your account. Try another gas provider."
    if any(word in low for word in ("timeout", "timed out", "not reachable", "502", "503", "504")):
        return "The service did not respond. Try again."
    if any(word in low for word in ("token", "rate", "429", "1015", "busy")):
        return "The biller service is busy. Wait a minute and try again."
    if "not configured" in low or "misconfigured" in low:
        return "This service is not available right now. Try again shortly."
    return "The request could not be completed. Try again."


def _plain_vendor(match: re.Match) -> str:
    word = match.group(1).lower()
    if word in {"payu", "cashfree"}:
        return "the payment service"
    if word == "kaleyra":
        return "the message service"
    return "the biller service"
