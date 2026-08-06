# -*- coding: utf-8 -*-
"""教案解析器:将爸爸的 TXT / DOCX / 图片教案解析为结构化课程。

基于真实教案样本(Unit01/Unit02 三段式格式)编写。
图片教案:文件先落盘保存,内容解析等待 DeepSeek 视觉(mock 阶段返回占位)。
"""

import io
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
DOC_EXTS = {".txt", ".md", ".docx", ".doc"}
PDF_EXTS = {".pdf"}


# ---------------------------------------------------------------- 文本提取
def extract_text_from_docx(raw: bytes) -> str:
    """从 docx 二进制提取纯文本(标准库 zipfile,已验证可用)。"""
    z = zipfile.ZipFile(io.BytesIO(raw))
    xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"<w:p[ >]", "\n<w:p ", xml)
    xml = re.sub(r"<w:tab[ /]", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\n{2,}", "\n", text).strip()


def extract_text_from_doc(raw: bytes, filename: str) -> str:
    """从旧版 .doc 提取文本。优先 pywin32(本机 Word/WPS COM),失败回退 PowerShell,再失败给明确提示。"""
    with tempfile.TemporaryDirectory(prefix="tutor_doc_") as td:
        src = Path(td) / "input.doc"
        src.write_bytes(raw)

        # ---- 方法 1:pywin32 COM(稳定,已在本机验证)
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            try:
                app = None
                for prog in ("Word.Application", "kwps.Application", "wps.Application"):
                    try:
                        app = win32com.client.Dispatch(prog)
                        break
                    except Exception:
                        app = None
                if app is not None:
                    try:
                        app.Visible = False
                        doc = app.Documents.Open(str(src))
                        text = doc.Content.Text
                        doc.Close(False)
                        return text.strip()
                    finally:
                        app.Quit()
            finally:
                pythoncom.CoUninitialize()
        except ImportError:
            pass
        except Exception:
            pass  # COM 失败,走 PowerShell 回退

        # ---- 方法 2:PowerShell COM(兜底)
        dst = Path(td) / "output.txt"
        script = r"""
$ErrorActionPreference='Stop'
$src=$args[0]; $dst=$args[1]
$word=$null
foreach($prog in @('Word.Application','kwps.Application','wps.Application')){
  try { $word=New-Object -ComObject $prog; break } catch {}
}
if(-not $word){ throw 'NO_OFFICE' }
$word.Visible=$false
try {
  $doc=$word.Documents.Open($src)
  $doc.SaveAs([string]$dst,7)
  $doc.Close($false)
} finally { $word.Quit() }
"""
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script, str(src), str(dst)],
                capture_output=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("解析 .doc 超时,请转存为 .docx / .txt")
        if dst.exists():
            return dst.read_text(encoding="utf-8-sig").strip()
        raw_err = r.stderr
        try:
            err = raw_err.decode("gb18030", errors="ignore")
        except Exception:
            err = raw_err.decode("utf-8", errors="ignore")
        if "NO_OFFICE" in err:
            raise ValueError("未检测到 Word / WPS,无法解析 .doc;请转存为 .docx / .txt 后上传")
        raise ValueError("解析 .doc 失败:" + (err.strip()[:200] or "请转存为 .docx / .txt"))


def extract_text_from_pdf(raw: bytes) -> str:
    """从 PDF 提取文本层(pypdf)。扫描件无文本层时返回空串。"""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw), strict=False)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def extract_text(filename: str, raw: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".docx":
        return extract_text_from_docx(raw)
    if ext == ".doc":
        return extract_text_from_doc(raw, filename)
    if ext == ".pdf":
        return extract_text_from_pdf(raw)
    if ext in (".txt", ".md"):
        for enc in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return raw.decode(enc).strip()
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="ignore").strip()
    raise ValueError(f"不支持的文档格式:{ext}")


# ---------------------------------------------------------------- 结构化解析
def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _list_lines(block: str) -> list:
    out = []
    for line in block.splitlines():
        line = line.strip().lstrip("-•*□").strip()
        if line and not re.match(r"^[A-Z]\s*[:：]", line):
            out.append(line)
    return out


def _parse_segment(block: str) -> dict:
    seg = {
        "code": "", "name_zh": "", "minutes": 0,
        "task": "", "words": [], "phonics": [], "patterns": [],
        "dialogue": [], "variation": "", "pass_rule": "", "transition": "",
    }
    m = re.search(r"【短环节\s*\d+｜([A-Za-z]+)｜([^｜]+)｜(\d+)分钟】", block)
    if m:
        seg["code"] = m.group(1).strip()
        seg["name_zh"] = m.group(2).strip()
        seg["minutes"] = int(m.group(3))
        body = block[m.end():]
    else:
        body = block
        m = re.search(r"([A-Z]{2,5})\s*[|｜]\s*([^\n]+)", block)
        if m:
            seg["code"] = m.group(1).strip()
            seg["name_zh"] = m.group(2).strip()

    def grab(pattern):
        m = re.search(pattern, body, re.S)
        return _clean(m.group(1)) if m else ""

    seg["task"] = grab(r"核心任务[：:]\s*([^\n【]+)")
    seg["words"] = [w.strip() for w in re.split(r"[；;,]",
                     grab(r"核心词与短语[：:]\s*([^\n【]+)")) if w.strip()]
    seg["phonics"] = [w.strip() for w in grab(r"语音点[：:]\s*([^\n【]+)").split("；") if w.strip()]

    p = re.search(r"关键句型[：:]\s*(.*?)(?=\n\s*必做对话|\n\s*换词|\n\s*语音点|$)", body, re.S)
    if p:
        seg["patterns"] = [x.strip().lstrip("-•*□").strip() for x in p.group(1).splitlines() if x.strip()]

    d = re.search(r"必做对话[：:]\s*(.*?)(?=\n\s*换词|\n\s*语音点|\n\s*过关|$)", body, re.S)
    if d:
        for line in d.group(1).splitlines():
            mm = re.match(r"\s*([AB])\s*[:：]\s*(.+)", line)
            if mm:
                seg["dialogue"].append([mm.group(1), mm.group(2).strip()])

    seg["variation"] = grab(r"换词与纠错提醒[：:]\s*([^\n【]+)")
    seg["pass_rule"] = grab(r"过关标准[：:]\s*([^\n【]+)")
    seg["transition"] = grab(r"转场句[：:]\s*([^\n【]+)")
    return seg


def parse_lesson_text(text: str, source: str = "", source_type: str = "txt") -> dict:
    """把教案全文解析为结构化课程。"""
    lesson = {
        "unit": 0, "title_zh": "", "title_en": "", "duration": "",
        "abilities": [], "rules": [], "segments": [],
        "closing_check": [], "record_scheme": {}, "ending_output": [],
        "source": source, "source_type": source_type,
    }

    m = re.search(r"[Uu]nit\s*(\d+)", text)
    if m:
        lesson["unit"] = int(m.group(1))

    m = re.search(r"[Uu]nit\s*\d+\s*[：:]\s*([^\n|｜]+)", text)
    if m:
        lesson["title_zh"] = _clean(m.group(1))

    m = re.search(r"([A-Z][A-Za-z ,'&-]{3,60})\s*[｜|]\s*AI带读发送稿", text)
    if m:
        lesson["title_en"] = _clean(m.group(1))

    m = re.search(r"【任务目标】\s*([^\n【]+)", text)
    if m:
        lesson["duration"] = _clean(m.group(1))

    m = re.search(r"【三四年级关键能力】\s*([^\n【]+)", text)
    if m:
        lesson["abilities"] = [x.strip() for x in m.group(1).split("；") if x.strip()]

    m = re.search(r"【带读规则】\s*(.*?)(?=\n\s*======|【短环节|$)", text, re.S)
    if m:
        lesson["rules"] = _list_lines(m.group(1))

    for m in re.finditer(r"(【短环节[^】]+】.*?)(?=\n\s*【短环节|\n\s*【可选|\n\s*【结束检测|$)", text, re.S):
        seg = _parse_segment(m.group(1))
        if seg["code"] or seg["task"]:
            lesson["segments"].append(seg)

    m = re.search(r"【结束检测[^】]*】\s*(.*?)(?=\n\s*【记录方式|$)", text, re.S)
    if m:
        lesson["closing_check"] = _list_lines(m.group(1))

    m = re.search(r"【记录方式】\s*(.*?)(?=\n\s*【结束时必须输出|$)", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"\s*([A-D])\s*[：:]\s*(.+)", line.strip())
            if mm:
                lesson["record_scheme"][mm.group(1)] = mm.group(2).strip()

    m = re.search(r"【结束时必须输出】\s*(.*)$", text, re.S)
    if m:
        lesson["ending_output"] = _list_lines(m.group(1))

    return lesson


# ---------------------------------------------------------------- 对外入口
def parse_lesson_file(filename: str, raw: bytes) -> dict:
    """解析上传的教案文件。返回结构化课程(图片/扫描件返回占位说明)。"""
    ext = Path(filename).suffix.lower()
    if ext in IMG_EXTS:
        return {
            "unit": 0, "title_zh": "", "title_en": "", "duration": "",
            "abilities": [], "rules": [], "segments": [],
            "closing_check": [], "record_scheme": {}, "ending_output": [],
            "source": filename, "source_type": "image",
            "image_pending": True,
            "note": "图片教案已保存,内容解析需 DeepSeek 视觉(未配置 Key,暂待处理)",
        }
    if ext in PDF_EXTS:
        text = extract_text_from_pdf(raw)
        if not text:
            return {
                "unit": 0, "title_zh": "", "title_en": "", "duration": "",
                "abilities": [], "rules": [], "segments": [],
                "closing_check": [], "record_scheme": {}, "ending_output": [],
                "source": filename, "source_type": "pdf",
                "image_pending": True,
                "note": "该 PDF 没有文本层(可能是扫描件),需 OCR 或 DeepSeek 视觉解析,暂待处理",
            }
        return parse_lesson_text(text, source=filename, source_type="pdf")
    if ext in DOC_EXTS:
        text = extract_text(filename, raw)
        return parse_lesson_text(text, source=filename, source_type=ext.lstrip("."))
    raise ValueError(f"不支持的文件类型:{ext}(支持 TXT / MD / DOCX / DOC / PDF / 图片)")
