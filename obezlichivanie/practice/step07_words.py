"""
Шаг 7. Названия объектов: ДВА прохода — собрать имена собственные, затем заменить их везде.
Запуск:   python practice/step07_words.py
"""
import hashlib
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
SECRET = "учебный-секрет"
WORD_RE = re.compile(r"[^\W\d_]+")                    # слово = подряд идущие буквы
KEY_CLASSES = {"Substation", "Line"}                    # где искать настоящие названия
STOP_WORDS = {"sub", "ohl", "kv", "line"}               # технические слова (в нижнем регистре)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def h(text):
    return int(hashlib.sha256((SECRET + "|" + text).encode("utf-8")).hexdigest(), 16)


def proper_words(text):
    """Слово с заглавной буквы, от 3 букв, не техническое и не аббревиатура до 4 букв."""
    return {w for w in WORD_RE.findall(text)
            if len(w) >= 3 and w[0].isupper() and w.lower() not in STOP_WORDS and not (w.isupper() and len(w) <= 4)}


FRUITS = [line.split("\t")[1].strip() for line in open("dict/fruits.tsv", encoding="utf-8")
          if line.strip() and not line.startswith("#")]
root = ET.parse("practice/mini_model.xml").getroot()

# ---- ПРОХОД 1: собираем имена собственные из названий подстанций и линий
words = set()
for obj in root:
    if local(obj.tag) in KEY_CLASSES:
        for field in obj:
            if local(field.tag) == "IdentifiedObject.name":
                words |= proper_words(field.text)
print("Найдены имена собственные:", sorted(words))

# ---- Строим словарь замен: каждому слову — своё прилагательное (порядок задаёт хеш с секретом)
word_map = {}
for i, w in enumerate(sorted(words, key=lambda w: h("word:" + w))):
    word_map[w] = FRUITS[i]                             # для учебного примера слов меньше 100
print("Словарь замен:", word_map, "\n")

# ---- ПРОХОД 2: заменяем эти слова во ВСЕХ текстах, не только в названиях подстанций
for obj in root:
    for field in obj.iter():
        if field.text and field.text.strip() and len(field) == 0:
            new = WORD_RE.sub(lambda m: word_map.get(m.group(), m.group()), field.text)
            if new != field.text:
                print(f"{local(obj.tag):28} {field.text!r}\n{'':28} -> {new!r}")
