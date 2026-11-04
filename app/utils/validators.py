"""Small, dependency-free validation helpers (server-side validation)."""
import re
from datetime import date
from urllib.parse import urljoin, urlparse

PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{6,18}$")
UPI_RE = re.compile(r"^[A-Za-z0-9._\-]{2,64}@[A-Za-z]{2,32}$")


def is_valid_phone(value: str) -> bool:
    return bool(value and PHONE_RE.match(value.strip()))


def is_valid_upi(value: str) -> bool:
    return bool(value and UPI_RE.match(value.strip()))


def luhn_ok(number: str) -> bool:
    """Luhn checksum - catches typos in card numbers (demo validation only)."""
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def card_brand(number: str) -> str:
    n = re.sub(r"\D", "", number)
    if n.startswith("4"):
        return "Visa"
    if n[:2] in {"51", "52", "53", "54", "55"}:
        return "Mastercard"
    if n[:2] in {"34", "37"}:
        return "Amex"
    if n[:2] in {"60", "65", "81", "82"}:
        return "RuPay"
    return "Card"


def parse_expiry(text: str):
    """'MM/YY' or 'MM/YYYY' -> (month, year) or None."""
    m = re.match(r"^\s*(\d{1,2})\s*/\s*(\d{2}|\d{4})\s*$", text or "")
    if not m:
        return None
    month, year = int(m.group(1)), int(m.group(2))
    if year < 100:
        year += 2000
    if not 1 <= month <= 12:
        return None
    return month, year


def expiry_is_future(text: str, today: date) -> bool:
    parsed = parse_expiry(text)
    if not parsed:
        return False
    month, year = parsed
    return (year, month) >= (today.year, today.month)


def password_problems(password: str) -> list:
    problems = []
    if len(password or "") < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Za-z]", password or ""):
        problems.append("a letter")
    if not re.search(r"\d", password or ""):
        problems.append("a digit")
    return problems


def is_safe_redirect(target: str, host_url: str) -> bool:
    """Only allow redirects back to this same site (prevents open redirects)."""
    if not target:
        return False
    ref = urlparse(host_url)
    test = urlparse(urljoin(host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc
