"""
Конвертер Markdown -> Word (.docx) на стандартной библиотеке Python (без установки пакетов).

    python tools/md_to_docx.py                       — все документы папки -> word/
    python tools/md_to_docx.py файл.md файл.docx     — один файл
    python tools/md_to_docx.py --code файл.py ... файл.docx  — исходный код с подсветкой комментариев

Файл .docx — это zip-архив с XML-файлами (стандарт Office Open XML). Мы пишем эти XML сами:
document.xml (текст), styles.xml (стили), numbering.xml (списки), footer1.xml (номер страницы).
Поддерживается: заголовки #..####, абзацы, **жирный**, `код`, [ссылка](адрес), списки * / - / 1.,
вложенные списки, таблицы | a | b |, блоки ``` кода ```, цитаты >, линия ---, «[ ]» в чек-листах.
Оглавление вставляется как поле Word; его заполняет Word при обновлении полей.
"""
import datetime
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape

PAGE_W, MARGIN = 11906, 1134                 # A4: ширина 21 см; поля 2 см (в twip: 1 см = 567)
TEXT_W = PAGE_W - 2 * MARGIN                 # ширина текста
BODY_FONT, CODE_FONT = "Calibri", "Consolas"


def esc(text):
    return escape(text, {'"': "&quot;"})


# --------------------------------------------------------------------------- строчная разметка
STAR = "\x01"                                # временная замена для \* (чтобы не спутать с курсивом)
INLINE = re.compile(r"(`[^`]+`|\*\*.+?\*\*|(?<![\w*])\*[^*\s][^*]*?\*(?![\w*])|\[[^\]]+\]\([^)]+\))")


def run(text, bold=False, italic=False, code=False, color=None, size=None, underline=False):
    """Один «прогон» текста с форматированием (w:r)."""
    props = ""
    if code:
        props += f'<w:rFonts w:ascii="{CODE_FONT}" w:hAnsi="{CODE_FONT}" w:cs="{CODE_FONT}"/>'
    if bold:
        props += "<w:b/>"
    if italic:
        props += "<w:i/>"
    if underline:
        props += '<w:u w:val="single"/>'
    if color:
        props += f'<w:color w:val="{color}"/>'
    if code and not size:
        size = 19
    if size:
        props += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    if code:
        props += '<w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>'
    rpr = f"<w:rPr>{props}</w:rPr>" if props else ""
    text = text.replace(STAR, "*")                 # экранированная звёздочка \* -> обычная *
    return f'<w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def inline(text, bold=False, size=None):
    """Разбор строки на **жирный**, `код`, [ссылки] и обычный текст."""
    out = []
    for part in INLINE.split(text.replace("\\|", "|").replace("\\*", STAR)):
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(run(part[1:-1], code=True, bold=bold))
        elif part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(inline(part[2:-2], bold=True, size=size))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(run(part[1:-1], italic=True, bold=bold, size=size))
        elif part.startswith("[") and "](" in part:
            label = part[1:part.index("](")]
            out.append(run(label.strip("`"), color="1F5FBF", underline=True, bold=bold, size=size,
                           code=label.startswith("`")))
        else:
            out.append(run(part, bold=bold, size=size))
    return "".join(out)


def para(content, style=None, num=None, extra_ppr="", keep_next=False):
    ppr = ""
    if style:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if keep_next:
        ppr += "<w:keepNext/>"
    if num:
        ppr += f'<w:numPr><w:ilvl w:val="{num[1]}"/><w:numId w:val="{num[0]}"/></w:numPr>'
    ppr += extra_ppr
    return f"<w:p><w:pPr>{ppr}</w:pPr>{content}</w:p>"


# --------------------------------------------------------------------------- блоки
class Doc:
    def __init__(self):
        self.body = []
        self.nums = []              # список numId: ("bullet"|"decimal")

    def new_num(self, kind, start=1):
        self.nums.append((kind, start))
        return len(self.nums)       # numId начинается с 1

    def code_block(self, lines, lang=""):
        # шрифт подбираем так, чтобы самая длинная строка поместилась (Consolas: ~1750/размер символов в строке)
        longest = max((len(l) for l in lines), default=0)
        size = 19 if longest <= 92 else max(14, 1750 // longest)
        for i, line in enumerate(lines or [""]):
            spacing = '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
            ppr = ('<w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>' + spacing +
                   '<w:ind w:left="113" w:right="113"/>')
            if i == len(lines) - 1:
                ppr = ppr.replace('w:after="0"', 'w:after="120"')
            if i < len(lines) - 1:
                ppr = "<w:keepNext/>" + ppr if len(lines) <= 15 else ppr
            self.body.append(f'<w:p><w:pPr><w:pStyle w:val="Code"/>{ppr}</w:pPr>{run(line, code=True, size=size) if line else ""}</w:p>')

    def table(self, rows):
        ncol = max(len(r) for r in rows)
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        lens = [max(min(len(re.sub(r"[`*]", "", r[c])), 60) for r in rows) + 4 for c in range(ncol)]
        total = sum(lens)
        widths = [max(int(TEXT_W * l / total), 900) for l in lens]
        widths[-1] += TEXT_W - sum(widths)
        border = "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>'
                         for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
        xml = [f'<w:tbl><w:tblPr><w:tblW w:w="{TEXT_W}" w:type="dxa"/><w:tblBorders>{border}</w:tblBorders>'
               f'<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
               f'<w:bottom w:w="40" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>']
        xml += [f'<w:gridCol w:w="{w}"/>' for w in widths]
        xml.append("</w:tblGrid>")
        for i, row in enumerate(rows):
            header = i == 0
            trpr = "<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>" if header else "<w:trPr><w:cantSplit/></w:trPr>"
            xml.append(f"<w:tr>{trpr}")
            for c, cell in enumerate(row):
                shade = '<w:shd w:val="clear" w:color="auto" w:fill="DCE6F2"/>' if header else ""
                content = inline(cell.strip(), bold=header, size=19)
                xml.append(f'<w:tc><w:tcPr><w:tcW w:w="{widths[c]}" w:type="dxa"/>{shade}</w:tcPr>'
                           f'<w:p><w:pPr><w:pStyle w:val="TableText"/></w:pPr>{content}</w:p></w:tc>')
            xml.append("</w:tr>")
        xml.append("</w:tbl>")
        self.body.append("".join(xml))
        self.body.append(para("", extra_ppr='<w:spacing w:before="0" w:after="60"/>'))


def split_row(line):
    cells = re.split(r"(?<!\\)\|", line.strip())
    return [c.strip() for c in cells[1:-1]]


def convert_markdown(md, title_note=""):
    doc = Doc()
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    first_h1 = True
    list_stack = []                  # [(indent, kind, numId)]
    para_buf = []

    def flush_para():
        if para_buf:
            doc.body.append(para(inline(" ".join(s.strip() for s in para_buf))))
            para_buf.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # ---- блок кода
        if stripped.startswith("```"):
            flush_para()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i].rstrip())
                i += 1
            indent = min((len(l) - len(l.lstrip()) for l in block if l.strip()), default=0)
            doc.code_block([l[indent:] for l in block])
            i += 1
            continue
        # ---- пустая строка: список продолжается, если дальше снова пункт списка или блок кода внутри списка
        if not stripped:
            flush_para()
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if not (re.match(r"\s*([*-]|\d+\.)\s", nxt) or (list_stack and nxt.strip().startswith("```"))):
                list_stack = []
            i += 1
            continue
        # ---- заголовки
        m = re.match(r"(#{1,4})\s+(.*)", stripped)
        if m:
            flush_para()
            list_stack = []
            level = len(m.group(1))
            text = m.group(2)
            if level == 1 and first_h1:
                first_h1 = False
                doc.body.append(para(inline(text), style="Title"))
                if title_note:
                    doc.body.append(para(run(title_note, italic=True, color="595959")))
                doc.body.append(para(run("Содержание", bold=True, size=28), keep_next=True))
                doc.body.append('<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
                                '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-2" \\h \\z \\u </w:instrText></w:r>'
                                '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
                                + run("Оглавление: нажмите F9 для обновления") +
                                '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
                doc.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
            else:
                doc.body.append(para(inline(text), style=f"Heading{min(level if level > 1 else 1, 4)}"))
            i += 1
            continue
        # ---- линия
        if re.fullmatch(r"-{3,}|\*{3,}", stripped):
            flush_para()
            doc.body.append(para("", extra_ppr='<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="BFBFBF"/></w:pBdr>'))
            i += 1
            continue
        # ---- таблица
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            flush_para()
            rows = [split_row(stripped)]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            doc.table(rows)
            continue
        # ---- цитата
        if stripped.startswith(">"):
            flush_para()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            doc.body.append(para(inline(" ".join(quote)), style="Quote"))
            continue
        # ---- элемент списка
        m = re.match(r"(\s*)([*-]|\d+\.)\s+(.*)", line)
        if m:
            flush_para()
            indent = len(m.group(1).replace("\t", "    "))
            kind = "decimal" if m.group(2)[0].isdigit() else "bullet"
            start = int(m.group(2)[:-1]) if kind == "decimal" else 1     # «3.» начинает список с 3
            while list_stack and list_stack[-1][0] > indent:
                list_stack.pop()
            if not list_stack or list_stack[-1][0] < indent:
                list_stack.append((indent, kind, doc.new_num(kind, start)))
            elif list_stack[-1][1] != kind:
                list_stack[-1] = (indent, kind, doc.new_num(kind, start))
            text = m.group(3)
            text = re.sub(r"^\[ \]\s*", "☐ ", text)
            text = re.sub(r"^\[x\]\s*", "☑ ", text, flags=re.I)
            # продолжение элемента на следующих строках (с отступом, без маркера)
            j = i + 1
            while j < len(lines) and lines[j].strip() and lines[j].startswith(" ") \
                    and not re.match(r"\s*([*-]|\d+\.)\s", lines[j]) and not lines[j].strip().startswith(("```", "|")):
                text += " " + lines[j].strip()
                j += 1
            level = min(len(list_stack) - 1, 2)
            doc.body.append(para(inline(text), style="ListParagraph", num=(list_stack[-1][2], level)))
            i = j
            continue
        # ---- обычный абзац (строки до пустой склеиваются)
        list_stack = [] if not line.startswith(" ") else list_stack
        para_buf.append(line)
        i += 1
    flush_para()
    return doc


def convert_code(paths):
    """Исходный код Python: комментарии зелёным курсивом, строки кода — моноширинным шрифтом."""
    doc = Doc()
    doc.body.append(para(inline("Программы с комментарием к каждой строке"), style="Title"))
    doc.body.append(para(run("Код совпадает с anonymize.py и check.py (проверка: python tools/verify_same.py). "
                             "Комментарий стоит над строкой, которую он объясняет.", italic=True, color="595959")))
    for path in paths:
        doc.body.append(para(inline(f"Файл `{os.path.basename(path)}`"), style="Heading1"))
        with open(path, encoding="utf-8") as f:
            src = f.read().rstrip("\n").split("\n")
        for n, line in enumerate(src, 1):
            body = line.rstrip()
            s = body.lstrip()
            is_comment = s.startswith("#")
            number = run(f"{n:>4}  ", code=True, color="A6A6A6", size=16)
            if is_comment:
                text = run(body, code=True, color="2E7D32", size=17)
            else:
                text = run(body, code=True, size=17) if body else ""
            ppr = ('<w:spacing w:before="0" w:after="0" w:line="228" w:lineRule="auto"/>'
                   '<w:ind w:left="567" w:hanging="567"/>')
            doc.body.append(f'<w:p><w:pPr><w:pStyle w:val="Code"/>{ppr}</w:pPr>{number}{text}</w:p>')
    return doc


# --------------------------------------------------------------------------- упаковка .docx
STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{BODY_FONT}" w:hAnsi="{BODY_FONT}" w:cs="{BODY_FONT}" w:eastAsia="{BODY_FONT}"/>
<w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="ru-RU"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:before="0" w:after="240"/><w:pBdr><w:bottom w:val="single" w:sz="12" w:space="6" w:color="1F4E79"/></w:pBdr></w:pPr>
<w:rPr><w:rFonts w:ascii="{BODY_FONT}" w:hAnsi="{BODY_FONT}" w:cs="{BODY_FONT}"/><w:b/><w:color w:val="1F4E79"/><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="{BODY_FONT}" w:hAnsi="{BODY_FONT}" w:cs="{BODY_FONT}"/><w:b/><w:color w:val="1F4E79"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="280" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:rFonts w:ascii="{BODY_FONT}" w:hAnsi="{BODY_FONT}" w:cs="{BODY_FONT}"/><w:b/><w:color w:val="2E74B5"/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="200" w:after="80"/><w:outlineLvl w:val="2"/></w:pPr>
<w:rPr><w:rFonts w:ascii="{BODY_FONT}" w:hAnsi="{BODY_FONT}" w:cs="{BODY_FONT}"/><w:b/><w:color w:val="404040"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="160" w:after="60"/><w:outlineLvl w:val="3"/></w:pPr>
<w:rPr><w:rFonts w:ascii="{BODY_FONT}" w:hAnsi="{BODY_FONT}" w:cs="{BODY_FONT}"/><w:b/><w:i/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:before="0" w:after="60"/><w:contextualSpacing/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
<w:rPr><w:rFonts w:ascii="{CODE_FONT}" w:hAnsi="{CODE_FONT}" w:cs="{CODE_FONT}"/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/>
<w:pPr><w:ind w:left="340"/><w:pBdr><w:left w:val="single" w:sz="18" w:space="8" w:color="2E74B5"/></w:pBdr><w:shd w:val="clear" w:color="auto" w:fill="EEF3FA"/></w:pPr>
<w:rPr><w:i/><w:color w:val="404040"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="40"/></w:pPr><w:rPr><w:b/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TOC2"><w:name w:val="toc 2"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="20"/><w:ind w:left="284"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="1F5FBF"/><w:u w:val="single"/></w:rPr></w:style>
</w:styles>"""


def numbering_xml(nums):
    bullets = ["•", "◦", "▪"]
    abstract = ['<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>']
    for lvl in range(3):
        abstract.append(f'<w:lvl w:ilvl="{lvl}"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="{bullets[lvl]}"/>'
                        f'<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{360 + 360 * lvl}" w:hanging="283"/></w:pPr></w:lvl>')
    abstract.append('</w:abstractNum><w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>')
    for lvl in range(3):
        fmt = ["decimal", "lowerLetter", "lowerRoman"][lvl]
        abstract.append(f'<w:lvl w:ilvl="{lvl}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="%{lvl + 1}."/>'
                        f'<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{397 + 360 * lvl}" w:hanging="397"/></w:pPr></w:lvl>')
    abstract.append("</w:abstractNum>")
    inst = []
    for n, (kind, start) in enumerate(nums, 1):
        aid = 0 if kind == "bullet" else 1
        inst.append(f'<w:num w:numId="{n}"><w:abstractNumId w:val="{aid}"/>'
                    + (f'<w:lvlOverride w:ilvl="0"><w:startOverride w:val="{start}"/></w:lvlOverride>' if aid else "")
                    + "</w:num>")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            + "".join(abstract) + "".join(inst) + "</w:numbering>")


def save(doc, path, title):
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    sect = (f'<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/>'
            f'<w:pgSz w:w="{PAGE_W}" w:h="16838"/><w:pgMar w:top="1134" w:right="{MARGIN}" w:bottom="1134" w:left="{MARGIN}" '
            f'w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>'
                + "".join(doc.body) + sect + "</w:body></w:document>")
    footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {W}><w:p><w:pPr><w:pStyle w:val="Footer"/></w:pPr>'
              + run(f"{title} — стр. ") +
              '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
              '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
              "</w:p></w:ftr>")
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                     '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
                     '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
                     '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                     '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                     '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '</Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rIdNumbering" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
                '<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
                '</Relationships>')
    settings = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:defaultTabStop w:val="709"/><w:characterSpacingControl w:val="doNotCompress"/>'
                '<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>'
                '</w:settings>')
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{esc(title)}</dc:title><dc:language>ru-RU</dc:language>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/numbering.xml", numbering_xml(doc.nums))
        z.writestr("word/settings.xml", settings)
        z.writestr("word/footer1.xml", footer)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("docProps/core.xml", core)


# --------------------------------------------------------------------------- запуск
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = [  # (исходник, результат, заголовок для нижнего колонтитула)
    ("НОВИЧКУ.md", "1_Пошаговое_руководство_для_новичка.docx", "Руководство для новичка"),
    ("ИНСТРУКЦИЯ.md", "2_Инструкция_по_использованию.docx", "Инструкция по использованию"),
    ("РАЗРАБОТКА.md", "3_Как_разрабатывалось_решение.docx", "Как разрабатывалось решение"),
    ("README.md", "4_Обзор_решения.docx", "Обзор решения"),
]


PROJECT = os.path.dirname(ROOT)             # C:\MX — папка со всеми вариантами
PROJECT_DOCS = [  # документы шести вариантов: (исходник относительно C:\MX, результат, колонтитул)
    ("README.md", "0_Обзор_и_сравнение_вариантов.docx", "Обзор и сравнение вариантов"),
    ("v1_stream_hmac/README.md", "1_Вариант_1_Однопроходный_поток_HMAC.docx", "Вариант 1. Поток + HMAC"),
    ("v2_two_pass_vault/README.md", "2_Вариант_2_Два_прохода_и_vault.docx", "Вариант 2. Два прохода + vault"),
    ("v3_rules_engine/README.md", "3_Вариант_3_Движок_правил.docx", "Вариант 3. Движок правил"),
    ("v4_parallel_mapreduce/README.md", "4_Вариант_4_Параллельный_map-reduce.docx", "Вариант 4. Map-reduce"),
    ("v5_php_xmlreader/README.md", "5_Вариант_5_PHP_XMLReader.docx", "Вариант 5. PHP"),
    ("v6_sqlite_triplestore/README.md", "6_Вариант_6_SQLite_хранилище_триплетов.docx", "Вариант 6. SQLite"),
    ("_shared/README.md", "7_Общие_компоненты.docx", "Общие компоненты"),
    ("_shared/results.md", "8_Результаты_прогона_всех_вариантов.docx", "Результаты прогона"),
    ("v2_two_pass_vault/real_model/ИНСТРУКЦИЯ_НОВИЧКУ.md", "9_Вариант_2_подробная_инструкция_для_новичка.docx",
     "Вариант 2: инструкция для новичка"),
    ("v2_two_pass_vault/real_model/README.md", "10_Вариант_2_для_реальной_модели_обзор.docx",
     "Вариант 2 для реальной модели"),
]


def main():
    args = sys.argv[1:]
    if args == ["--project"]:                  # документы шести вариантов -> C:\MX\word
        out_dir = os.path.join(PROJECT, "word")
        os.makedirs(out_dir, exist_ok=True)
        for src, dst, title in PROJECT_DOCS:
            with open(os.path.join(PROJECT, src), encoding="utf-8") as f:
                save(convert_markdown(f.read()), os.path.join(out_dir, dst), title)
            print("готово:", dst)
        return
    if args and args[0] == "--code":
        doc = convert_code(args[1:-1])
        save(doc, args[-1], "Код с комментариями")
        print("готово:", args[-1])
        return
    if len(args) == 2:
        with open(args[0], encoding="utf-8") as f:
            save(convert_markdown(f.read()), args[1], os.path.splitext(os.path.basename(args[1]))[0])
        print("готово:", args[1])
        return
    out_dir = os.path.join(ROOT, "word")
    os.makedirs(out_dir, exist_ok=True)
    for src, dst, title in DOCS:
        with open(os.path.join(ROOT, src), encoding="utf-8") as f:
            save(convert_markdown(f.read()), os.path.join(out_dir, dst), title)
        print("готово:", dst)
    code = [os.path.join(ROOT, "anonymize_commented.py"), os.path.join(ROOT, "check_commented.py")]
    save(convert_code(code), os.path.join(out_dir, "5_Код_с_комментариями_к_каждой_строке.docx"), "Код с комментариями")
    print("готово: 5_Код_с_комментариями_к_каждой_строке.docx")


if __name__ == "__main__":
    main()
