"""Email validation.

Returns a four-state enum rather than a boolean. `risky` matters: for SMB
acquisition targets an `info@` address is frequently the owner's own inbox, so
collapsing role accounts into `invalid` would throw away good leads.
"""

from __future__ import annotations

import re
from functools import lru_cache

try:
    import dns.resolver  # type: ignore

    _DNS = True
except Exception:  # pragma: no cover - dnspython always present in requirements
    _DNS = False

VALID = "valid"
RISKY = "risky"
INVALID = "invalid"
UNKNOWN = "unknown"

_SYNTAX = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

ROLE_LOCALS = {
    "info", "sales", "admin", "support", "contact", "hello", "office",
    "enquiries", "inquiries", "team", "help", "service", "mail", "marketing",
    "billing", "accounts", "noreply", "no-reply", "webmaster", "postmaster",
}

DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "yopmail.com", "trashmail.com", "sharklasers.com", "getnada.com",
}

FREE_PROVIDERS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "protonmail.com", "gmx.com", "live.com", "msn.com",
}


@lru_cache(maxsize=4096)
def _has_mx(domain: str) -> bool | None:
    """None = lookup could not be performed (no egress / resolver error)."""
    if not _DNS:
        return None
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=3.0)
        return len(answers) > 0
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        return False
    except Exception:
        return None


def validate_email(email: str | None, *, check_mx: bool = True) -> tuple[str, str]:
    """-> (status, reason)"""
    if not email:
        return UNKNOWN, "no address"
    addr = email.strip().lower()
    if not _SYNTAX.match(addr):
        return INVALID, "malformed address"

    local, domain = addr.rsplit("@", 1)

    if domain in DISPOSABLE:
        return INVALID, "disposable domain"

    reasons = []
    if local in ROLE_LOCALS:
        reasons.append("role account")
    if domain in FREE_PROVIDERS:
        reasons.append("free provider, not a company domain")

    if check_mx:
        mx = _has_mx(domain)
        if mx is False:
            return INVALID, "no MX record"
        if mx is None:
            reasons.append("MX not verified")
            return (RISKY if reasons else UNKNOWN), "; ".join(reasons) or "MX not verified"

    if reasons:
        return RISKY, "; ".join(reasons)
    return VALID, "syntax and MX ok"


def email_quality(status: str) -> float:
    """Normalized 0-1 contribution of an email to contactability."""
    return {VALID: 1.0, RISKY: 0.55, UNKNOWN: 0.2, INVALID: 0.0}.get(status, 0.0)
