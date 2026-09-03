"""
filetypes - teach-by-attachment: extract readable text from uploaded files.

Pure standard library. Supports:
  plain text family : .txt .md .rst .csv .tsv .json .log .yaml/.yml .ini .toml
  source code       : .py .js .ts .c .cpp .h .java .go .rs .rb .php .sh .sql ...
  markup            : .html .htm .xml  (tags stripped)
  office            : .docx .pptx .xlsx (zip+XML, stdlib zipfile)
  pdf               : .pdf  (best-effort: inflate content streams, pull text
                     show operators Tj/TJ/'/"; works for most text PDFs, not
                     for scanned images)

Returns {"kind","text","error","note"} - `error` is set when nothing readable
could be extracted, so the agent can respond honestly.
"""
import html as _html
import io
import re
import zipfile
import zlib

TEXT_EXT = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".log",
    ".yaml", ".yml", ".ini", ".toml", ".cfg", ".conf", ".env", ".text",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".java", ".go", ".rs", ".rb", ".php", ".sh", ".bash", ".sql", ".r",
    ".pl", ".lua", ".swift", ".kt", ".scala", ".tex", ".bib", ".srt", ".vtt",
}
HTML_EXT = {".html", ".htm", ".xml", ".svg"}
MAX_TEXT_CHARS = 400_000          # trim very long documents before learning

_UNSUPPORTED_MSG = ("I can't read that file type yet - text, markdown, code, "
                    "csv/json, html, docx, pptx, xlsx and pdf work best.")


def _ext(name: str) -> str:
    m = re.search(r"(\.[a-z0-9]+)\s*$", (name or "").lower())
    return m.group(1) if m else ""


def _decode(raw: bytes):
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|section|article)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _looks_binary(text: str) -> bool:
    if not text:
        return True
    sample = text[:4000]
    bad = sum(1 for ch in sample if ord(ch) < 9 or (13 < ord(ch) < 32))
    return bad / max(1, len(sample)) > 0.05


# --- office (zip + xml) -------------------------------------------------
def _office_xml_text(raw: bytes, member_pat: str, para_split: str = None) -> str:
    zf = zipfile.ZipFile(io.BytesIO(raw))
    names = sorted(n for n in zf.namelist() if re.match(member_pat, n))
    out = []
    for n in names:
        try:
            xml = zf.read(n).decode("utf-8", "ignore")
        except Exception:
            continue
        if para_split:
            xml = re.sub(para_split, "\n", xml)
        xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
        txt = re.sub(r"(?s)<[^>]+>", "", xml)
        txt = _html.unescape(txt)
        txt = re.sub(r"[ \t]+", " ", txt)
        txt = re.sub(r"\n\s*\n+", "\n\n", txt).strip()
        if txt:
            out.append(txt)
    return "\n\n".join(out)


# --- pdf (best-effort) ---------------------------------------------------
_PDF_STR = re.compile(rb"\(((?:[^()\\]|\\.)*)\)\s*(Tj|TJ|'|\")")
_PDF_ARR = re.compile(rb"\[((?:[^\[\]\\]|\\.)*)\]\s*TJ")
_PDF_HEX = re.compile(rb"<([0-9A-Fa-f\s]+)>\s*Tj")


def _pdf_unescape(b: bytes) -> str:
    out = bytearray()
    i = 0
    while i < len(b):
        ch = b[i]
        if ch == 0x5C and i + 1 < len(b):          # backslash
            nxt = b[i + 1]
            pairs = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12,
                     0x28: 40, 0x29: 41, 0x5C: 92}
            if nxt in pairs:
                out.append(pairs[nxt]); i += 2; continue
            if 0x30 <= nxt <= 0x37:                # octal escape
                j, oct_digits = i + 1, b""
                while j < len(b) and 0x30 <= b[j] <= 0x37 and len(oct_digits) < 3:
                    oct_digits += bytes([b[j]]); j += 1
                out.append(int(oct_digits, 8) & 0xFF); i = j; continue
            out.append(nxt); i += 2; continue
        out.append(ch); i += 1
    return out.decode("latin-1", "ignore")


def _pdf_extract(raw: bytes) -> str:
    pieces = []
    # walk stream objects, inflate FlateDecode streams
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        data = raw[start:end]
        head = raw[max(0, m.start() - 400):m.start()]
        inflated = None
        if b"/FlateDecode" in head:
            for trim in (0, 1, 2):
                try:
                    inflated = zlib.decompress(data[trim:] if trim else data)
                    break
                except Exception:
                    try:
                        inflated = zlib.decompressobj().decompress(data[trim:])
                        break
                    except Exception:
                        continue
        else:
            inflated = data
        if not inflated:
            continue
        if b"BT" not in inflated and b"Tj" not in inflated and b"TJ" not in inflated:
            continue
        # text show operators
        buf = []
        for am in _PDF_ARR.finditer(inflated):
            inner = am.group(1)
            for sm in re.finditer(rb"\(((?:[^()\\]|\\.)*)\)", inner):
                buf.append(_pdf_unescape(sm.group(1)))
            buf.append(" ")
        for sm in _PDF_STR.finditer(inflated):
            buf.append(_pdf_unescape(sm.group(1)))
            buf.append(" ")
        for hm in _PDF_HEX.finditer(inflated):
            hx = re.sub(rb"\s+", b"", hm.group(1))
            try:
                dec = bytes.fromhex(hx.decode("ascii"))
                buf.append(dec.decode("utf-16-be", "ignore") if len(dec) % 2 == 0
                           else dec.decode("latin-1", "ignore"))
            except Exception:
                pass
        # newline hints from Td/TD/T* operators
        text = "".join(buf)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 12:
            pieces.append(text)
    full = "\n\n".join(pieces)
    full = re.sub(r"[ \t]+", " ", full)
    return full.strip()


# --- public API -----------------------------------------------------------
def extract(name: str, raw: bytes) -> dict:
    """Return {"kind","text","error","note"} for an uploaded file."""
    ext = _ext(name)
    note = ""
    try:
        if ext in TEXT_EXT:
            text = _decode(raw)
            if _looks_binary(text[:2000]):
                return {"kind": ext or "file", "text": "", "note": note,
                        "error": _UNSUPPORTED_MSG}
            kind = "text"
        elif ext in HTML_EXT:
            text = _strip_html(_decode(raw))
            kind = "document"
        elif ext == ".docx":
            text = _office_xml_text(raw, r"word/(document|header\d*|footer\d*)\.xml$",
                                    para_split=r"</w:p>")
            kind = "document"
            if not text:
                note = "the .docx looked empty"
        elif ext == ".pptx":
            text = _office_xml_text(raw, r"ppt/slides/slide\d+\.xml$",
                                    para_split=r"</a:p>")
            kind = "slides"
        elif ext == ".xlsx":
            text = _office_xml_text(raw, r"xl/sharedStrings\.xml$")
            kind = "spreadsheet"
            note = "spreadsheet cell values (without layout)"
        elif ext in (".doc", ".xls", ".ppt"):
            return {"kind": ext, "text": "", "note": "",
                    "error": ("Old binary Office formats aren't supported yet - "
                              "please re-save as .docx/.xlsx/.pptx or paste the text.")}
        elif ext == ".pdf":
            text = _pdf_extract(raw)
            kind = "pdf"
            if len(text) < 40:
                return {"kind": kind, "text": "", "note": "",
                        "error": ("I couldn't find readable text in that PDF - "
                                  "it may be a scan (images). A .txt/.md/.docx "
                                  "version would teach me better.")}
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".mp3",
                     ".wav", ".mp4", ".zip", ".tar", ".gz", ".exe", ".bin"):
            return {"kind": ext, "text": "", "note": "",
                    "error": _UNSUPPORTED_MSG}
        else:
            text = _decode(raw)
            if _looks_binary(text[:2000]):
                return {"kind": ext or "file", "text": "", "note": "",
                        "error": _UNSUPPORTED_MSG}
            kind = "text"
    except zipfile.BadZipFile:
        return {"kind": ext, "text": "", "note": "",
                "error": f"That .{ext.lstrip('.')} file looks corrupted - I couldn't open it."}
    except Exception as e:
        return {"kind": ext, "text": "", "note": "",
                "error": f"I had trouble reading that file ({e})."}

    text = (text or "").strip()[:MAX_TEXT_CHARS]
    if len(text) < 20:
        return {"kind": kind, "text": text, "note": note,
                "error": "That file had almost no text in it for me to learn."}
    return {"kind": kind, "text": text, "error": None, "note": note}
