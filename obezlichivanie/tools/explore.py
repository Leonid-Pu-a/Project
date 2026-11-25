"""
Шаг 1 разработки: «разведка» модели — какие классы и поля в ней есть и что в них лежит.

    python tools/explore.py input.xml > explore_report.txt

Читает файл потоком (как anonymize.py) и печатает:
  * сколько объектов каждого класса;
  * для каждого текстового поля: сколько значений, сколько ссылок, 3 примера значений.
По этому отчёту решают, какие поля содержат персональные данные и имена собственные.
"""
import sys                                   # аргументы командной строки, кодировка вывода
import xml.etree.ElementTree as ET           # потоковый XML-парсер
from collections import Counter, defaultdict # счётчики

sys.stdout.reconfigure(encoding="utf-8")     # чтобы кириллица правильно печаталась в любой консоли
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"


def local(tag):                              # имя тега без пространства имён
    return tag.rsplit("}", 1)[-1]


classes = Counter()                          # класс -> число объектов
fields = defaultdict(lambda: {"values": 0, "refs": 0, "examples": []})   # (класс, поле) -> статистика
depth, root = 0, None                        # глубина вложенности и корень
for event, elem in ET.iterparse(sys.argv[1], events=("start", "end")):
    if event == "start":                     # начало тега
        depth += 1
        if depth == 1:
            root = elem                      # корень rdf:RDF
        continue
    depth -= 1                               # конец тега
    if depth != 1:                           # нас интересуют только целые объекты модели
        continue
    cls = local(elem.tag)
    classes[cls] += 1
    for el in elem.iter():                   # все вложенные элементы объекта
        if el is elem:
            continue
        info = fields[(cls, local(el.tag))]
        if el.get(RDF + "resource") is not None:
            info["refs"] += 1                # это ссылка на другой объект
        elif el.text and el.text.strip() and len(el) == 0:
            info["values"] += 1              # это текстовое значение
            if len(info["examples"]) < 3 and el.text not in info["examples"]:
                info["examples"].append(el.text.strip()[:80])
    root.remove(elem)                        # освобождаем память

print(f"Объектов: {sum(classes.values())}, классов: {len(classes)}\n")
print("=== Классы (по убыванию числа объектов) ===")
for cls, n in classes.most_common():
    print(f"{n:>9}  {cls}")
print("\n=== Текстовые поля: класс / поле — значений, ссылок, примеры ===")
for (cls, field), info in sorted(fields.items()):
    if info["values"]:                       # поля только со ссылками не печатаем
        print(f"{cls} / {field} — {info['values']} знач., {info['refs']} ссыл.: {info['examples']}")
