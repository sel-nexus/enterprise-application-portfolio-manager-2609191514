"""Validate user-entered display text at write boundaries."""

import html
import re

_MARKUP = re.compile(r'<\s*(?:/?\s*[a-zA-Z]|!|\?)[^>]*>')


def reject_markup(value: str) -> str:
    """Reject HTML-like markup without altering accepted text.

    Decode nested HTML entities only for inspection. Output rendering must
    still escape all text, including legacy records and accepted comparisons.
    """
    decoded = value
    while True:
        if _MARKUP.search(decoded):
            raise ValueError('Text must not contain HTML markup.')
        unescaped = html.unescape(decoded)
        if unescaped == decoded:
            return value
        decoded = unescaped
