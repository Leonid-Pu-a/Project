"""
Перевести ВСЕ файлы папки «новый вариант» в Word (папка word/).

    python tools/make_word.py

* .md  (инструкции)       -> документ с оглавлением, таблицами, списками, блоками кода;
* .py  (программы)        -> текст программы с номерами строк, комментарии выделены зелёным;
* .xml (учебные модели)   -> текст модели с номерами строк;
* .tsv (справочники)      -> таблица;
* плюс 00_Список_всех_документов.docx — что в каком файле.

Использует конвертер tools/md_to_docx.py (стандартная библиотека Python, без установки пакетов).
После создания файлов откройте их в Word и нажмите F9 (или Ctrl+A, F9), чтобы обновить оглавления.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import md_to_docx as m          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "word")

# (номер, путь, описание) — порядок документов в папке word/
FILES = [
    (1, "ПОШАГОВАЯ_ИНСТРУКЦИЯ_КАК_СДЕЛАТЬ.md", "Пошаговая инструкция: как сделать задание самому, с нуля"),
    (2, "ИНСТРУКЦИЯ_НОВИЧКУ.md", "Инструкция: как пользоваться готовой программой"),
    (3, "README.md", "Краткое описание папки"),
    (10, "anonymize.py", "Программа обезличивания"),
    (11, "anonymize_commented.py", "Программа обезличивания с комментарием к каждой строке"),
    (12, "check.py", "Программа проверки результата"),
    (13, "check_commented.py", "Программа проверки с комментарием к каждой строке"),
    (20, "tools/explore.py", "Разведка модели: какие классы и поля в ней есть"),
    (21, "tools/show_words.py", "Просмотр словаря имён собственных, который соберёт программа"),
    (22, "tools/test_rules.py", "Быстрые тесты правил замены"),
    (23, "tools/verify_same.py", "Проверка, что файлы с комментариями совпадают с основными по коду"),
    (24, "tools/md_to_docx.py", "Конвертер Markdown -> Word"),
    (25, "tools/make_word.py", "Перевод всех файлов папки в Word (эта программа)"),
    (30, "practice/step01_read_xml.py", "Учебный шаг 1: прочитать XML"),
    (31, "practice/step02_stream.py", "Учебный шаг 2: потоковое чтение"),
    (32, "practice/step04_uuid.py", "Учебный шаг 4: замена UUID без поломки связей"),
    (33, "practice/step05_numbers.py", "Учебный шаг 5: номера той же длины без повторов"),
    (34, "practice/step06_persons.py", "Учебный шаг 6: ФИО из справочника имён"),
    (35, "practice/step07_words.py", "Учебный шаг 7: названия объектов, два прохода"),
    (36, "practice/step08_regex.py", "Учебный шаг 8: регулярные выражения"),
    (37, "practice/step09_base64.py", "Учебный шаг 9: вложения base64 и zip"),
    (38, "practice/mini_model.xml", "Учебная мини-модель (15 объектов)"),
    (39, "practice/mini_model_v2.xml", "Мини-модель с новыми объектами («следующая выгрузка»)"),
    (40, "dict/names.tsv", "Справочник мужских имён: имя -> фамилия, отчество, улица"),
    (41, "dict/female_names.tsv", "Справочник женских имён"),
    (42, "dict/fruits.tsv", "Справочник фруктов: фрукт -> прилагательное"),
]
TSV_HEADERS = {
    "names.tsv": ["Имя", "Фамилия", "Отчество (муж.)", "Отчество (жен.)", "Улица"],
    "female_names.tsv": ["Имя"],
    "fruits.tsv": ["Фрукт", "Прилагательное"],
}


def out_name(num, path):
    return f"{num:02d}_{path.replace('/', '_')}.docx"


def code_doc(path, title):
    """Текст программы или XML: номер строки + строка; комментарии Python — зелёным."""
    doc = m.Doc()
    doc.body.append(m.para(m.inline(f"`{path}`"), style="Title"))
    doc.body.append(m.para(m.run(title, italic=True, color="595959")))
    is_py = path.endswith(".py")
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        lines = f.read().rstrip("\n").split("\n")
    longest = max((len(l) for l in lines), default=0)
    size = 17 if longest <= 100 else max(12, 1700 // longest)        # длинные строки — шрифт мельче
    for n, line in enumerate(lines, 1):
        body = line.rstrip()
        number = m.run(f"{n:>4}  ", code=True, color="A6A6A6", size=min(size, 16))
        comment = is_py and body.lstrip().startswith("#")
        text = m.run(body, code=True, size=size, color="2E7D32" if comment else None) if body else ""
        ppr = ('<w:spacing w:before="0" w:after="0" w:line="228" w:lineRule="auto"/>'
               '<w:ind w:left="567" w:hanging="567"/>')
        doc.body.append(f'<w:p><w:pPr><w:pStyle w:val="Code"/>{ppr}</w:pPr>{number}{text}</w:p>')
    return doc


def tsv_doc(path, title):
    """Справочник: комментарии файла — абзацами, строки — таблицей."""
    doc = m.Doc()
    doc.body.append(m.para(m.inline(f"`{path}`"), style="Title"))
    doc.body.append(m.para(m.run(title, italic=True, color="595959")))
    rows = []
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#"):
                doc.body.append(m.para(m.run(line.lstrip("# "), color="404040")))
            elif line.strip():
                rows.append(line.split("\t"))
    header = TSV_HEADERS.get(os.path.basename(path), [f"Колонка {i + 1}" for i in range(len(rows[0]))])
    doc.body.append(m.para(m.run(f"Строк в справочнике: {len(rows)}. Колонки разделены табуляцией.", bold=True)))
    doc.table([["№"] + header] + [[str(i)] + r for i, r in enumerate(rows, 1)])
    return doc


def index_doc():
    doc = m.Doc()
    doc.body.append(m.para(m.inline("Новый вариант: список всех документов"), style="Title"))
    doc.body.append(m.para(m.run("Все файлы папки C:\\MX\\новый вариант в формате Word. Начните с документа 01 — "
                                 "пошаговой инструкции, как сделать задание самому.", italic=True, color="595959")))
    rows = [["Документ Word", "Исходный файл", "Что в нём"]]
    rows += [[out_name(num, path), f"`{path}`", title] for num, path, title in FILES]
    doc.table(rows)
    return doc


def main():
    os.makedirs(OUT, exist_ok=True)
    m.save(index_doc(), os.path.join(OUT, "00_Список_всех_документов.docx"), "Список всех документов")
    print("готово: 00_Список_всех_документов.docx")
    for num, path, title in FILES:
        src = os.path.join(ROOT, path)
        if path.endswith(".md"):
            with open(src, encoding="utf-8") as f:
                doc = m.convert_markdown(f.read())
        elif path.endswith(".tsv"):
            doc = tsv_doc(path, title)
        else:
            doc = code_doc(path, title)
        name = out_name(num, path)
        m.save(doc, os.path.join(OUT, name), title)
        print("готово:", name)


if __name__ == "__main__":
    main()
