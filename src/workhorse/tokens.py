"""Lexical normalization with source line provenance; not a compiler parser."""

from dataclasses import dataclass
import hashlib
import io
import keyword
import re
import tokenize
from .bindings import python_bindings


C_WORDS = set("alignas alignof asm auto bool break case catch char class const constexpr continue default delete do double else enum explicit extern false final float for friend goto if inline int interface long namespace new noexcept null nullptr operator package private protected public return short signed sizeof static strictfp struct super switch synchronized template this throw throws true try typedef typename union unsigned using virtual void volatile while import implements extends abstract assert instanceof native transient record var yield".split())
C_LEXER = re.compile(
    r"(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)"
    r'|(?P<raw>R"(?P<delimiter>[^ ()\\\t\r\n]{0,16})\([\s\S]*?\)(?P=delimiter)")'
    r'|(?P<string>"""[\s\S]*?"""|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\')'
    r"|(?P<word>[A-Za-z_$][\w$]*)"
    r"|(?P<number>0[xX][\da-fA-F]+|\d+(?:\.\d*)?(?:[eE][+-]?\d+)?[uUlLfF]*)"
    r"|(?P<space>\s+)"
    r"|(?P<operator>>>?=?|<<=?|==|!=|<=|>=|&&|\|\||\+\+|--|->|::|[+*/%&|^!~=-]=?|[^\s])"
)


@dataclass(frozen=True)
class Token:
    value: str
    line: int


def normalize(source: str, language: str, mode: str = "relationships") -> list[Token]:
    """Preserve name relationships by default; raw and legacy modes aid evaluation."""
    if mode not in ("relationships", "raw", "legacy"):
        raise ValueError("Unknown normalization mode")
    result = []
    if language == "python":
        bindings = python_bindings(source) if mode == "relationships" else {}
        try:
            for item in tokenize.generate_tokens(io.StringIO(source).readline):
                if item.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                                 tokenize.ENCODING, tokenize.ENDMARKER):
                    continue
                value = item.string
                if item.type == tokenize.NAME and not keyword.iskeyword(value):
                    if mode == "legacy":
                        value = "NAME"
                    elif mode == "relationships":
                        value = bindings.get(item.start, value)
                elif item.type == tokenize.INDENT:
                    value = "INDENT"
                elif item.type == tokenize.DEDENT:
                    value = "DEDENT"
                result.append(Token(value, item.start[0]))
        except (tokenize.TokenError, IndentationError) as exc:
            raise ValueError(f"Cannot tokenize Python source: {exc}") from exc
    else:
        line = 1
        identifiers = {}
        previous = ""
        for match in C_LEXER.finditer(source):
            value = match.group()
            original = value
            kind = match.lastgroup
            if kind not in ("comment", "space"):
                if kind == "word" and value not in C_WORDS:
                    if mode == "legacy":
                        value = "NAME"
                    elif mode == "relationships" and previous not in (".", "::", "->"):
                        value = identifiers.setdefault(value, f"V{len(identifiers)}")
                result.append(Token(value, line))
                previous = original
            line += original.count("\n")
    return result


def fingerprints(tokens: list[Token], k: int = 9, window: int = 4) -> dict[int, int]:
    """Winnow k-token shingles, keeping the rightmost minimum in each window."""
    if k < 1 or window < 1:
        raise ValueError("Fingerprint dimensions must be positive")
    hashes = []
    for start in range(len(tokens) - k + 1):
        payload = "\0".join(t.value for t in tokens[start:start + k]).encode()
        hashes.append(int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big"))
    if not hashes:
        return {}
    width = min(window, len(hashes))
    result = {}
    for start in range(len(hashes) - width + 1):
        index = min(range(start, start + width), key=lambda i: (hashes[i], -i))
        result.setdefault(hashes[index], index)
    return result
