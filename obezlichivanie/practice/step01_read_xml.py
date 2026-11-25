"""
Шаг 1. Прочитать XML-файл и увидеть его устройство.
Запуск (из папки simple_student):   python practice/step01_read_xml.py
"""
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")              # чтобы русские буквы печатались правильно

RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"   # так ElementTree записывает префикс rdf:


def local(tag):
    """'{http://...cim16#}Substation' -> 'Substation' (отрезаем пространство имён)."""
    return tag.rsplit("}", 1)[-1]


tree = ET.parse("practice/mini_model.xml")             # читаем ВЕСЬ файл в память (для маленького — можно)
root = tree.getroot()                                   # корень <rdf:RDF>
print("Корень:", local(root.tag), "| объектов внутри:", len(root))

for obj in root:                                        # каждый ребёнок корня — объект модели
    print(f"\nОбъект класса {local(obj.tag)}, идентификатор {obj.get(RDF + 'about')}")
    for field in obj:                                   # поля объекта
        ref = field.get(RDF + "resource")               # если есть rdf:resource — это ссылка
        if ref is not None:
            print(f"   {local(field.tag)} -> ссылка на {ref}")
        elif len(field):                                # есть вложенные элементы (адрес)
            print(f"   {local(field.tag)} -> вложенная структура")
        else:
            print(f"   {local(field.tag)} = {field.text[:60]!r}")
