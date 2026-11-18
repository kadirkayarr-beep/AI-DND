import game
import re


def _inside_speech(text, position):
    return any(span.start() < position < span.end() for span in _SPEECH_SPAN_RE.finditer(text))

_SPEECH_SPAN_RE = re.compile(r"""“[^”]*”|"[^"]*"|(?<!\w)'[^']*'(?!\w)""")
