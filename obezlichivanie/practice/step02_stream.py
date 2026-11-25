"""
Шаг 2. Читать файл ПОТОКОМ — по одному объекту, не загружая весь файл в память.
Запуск:   python practice/step02_stream.py practice/mini_model.xml
          python practice/step02_stream.py C:\\Users\\Admin\\Downloads\\input.xml   (около 40 секунд)
"""
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")


def local(tag):
    return tag.rsplit("}", 1)[-1]


def read_objects(path):
    """Генератор: отдаёт объекты модели по одному и сразу удаляет их из памяти."""
    depth = 0                                           # глубина: 1 = корень, 2 = объект, 3+ = поля
    root = None
    for event, elem in ET.iterparse(path, events=("start", "end")):
        if event == "start":
            depth += 1
            if depth == 1:
                root = elem                             # запомнили корень <rdf:RDF>
        else:
            depth -= 1
            if depth == 1:                              # закончился объект (ребёнок корня)
                yield elem                              # отдаём его наружу
                root.remove(elem)                       # и выбрасываем из памяти


start = time.time()
classes = Counter()                                     # класс -> сколько объектов
for obj in read_objects(sys.argv[1]):
    classes[local(obj.tag)] += 1
print(f"Объектов: {sum(classes.values())}, классов: {len(classes)}, время: {time.time() - start:.1f} с")
for cls, n in classes.most_common(10):                 # 10 самых частых классов
    print(f"{n:>8}  {cls}")
