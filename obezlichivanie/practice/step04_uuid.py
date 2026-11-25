"""
Шаг 4. Заменить идентификаторы (UUID) так, чтобы связи не сломались, и записать новый файл.
Запуск:   python practice/step04_uuid.py
Результат: practice/out_step04.xml
"""
import hashlib
import re
import sys
import uuid
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
SECRET = "учебный-секрет"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def h(text):
    """Одинаковый текст -> одинаковое большое число. Без секрета число не угадать."""
    return int(hashlib.sha256((SECRET + "|" + text).encode("utf-8")).hexdigest(), 16)


def new_uuid(old):
    return str(uuid.UUID(int=h("uuid:" + old.lower()) % 2 ** 128, version=4))


def replace_uuids(text):
    return UUID_RE.sub(lambda m: new_uuid(m.group()), text)


# --- 1) Посмотрим на свойства функции
a = "b2000000-0000-4000-8000-000000000001"
print("new_uuid(a)          =", new_uuid(a))
print("ещё раз new_uuid(a)  =", new_uuid(a), " <- то же самое: детерминизм")
print("ссылка '#_' + a      =", replace_uuids("#_" + a), " <- UUID внутри строки заменён так же")

# --- 2) Применим ко всему файлу
namespaces = {}
for event, (prefix, uri) in ET.iterparse("practice/mini_model.xml", events=("start-ns",)):
    namespaces[prefix] = uri
    ET.register_namespace(prefix, uri)                  # иначе при записи будут ns0:, ns1: вместо cim:, rdf:

tree = ET.parse("practice/mini_model.xml")
for el in tree.getroot().iter():                        # все элементы файла
    for attr in (RDF + "about", RDF + "resource"):      # идентификатор объекта и ссылка
        if el.get(attr) is not None:
            el.set(attr, replace_uuids(el.get(attr)))
    if el.text and UUID_RE.fullmatch(el.text.strip()):  # поле mRID тоже содержит UUID
        el.text = replace_uuids(el.text)
tree.write("practice/out_step04.xml", encoding="utf-8", xml_declaration=True)

# --- 3) Проверим: каждая ссылка ведёт на существующий объект
root = ET.parse("practice/out_step04.xml").getroot()
ids = {obj.get(RDF + "about") for obj in root}
refs = [el.get(RDF + "resource") for el in root.iter() if (el.get(RDF + "resource") or "").startswith("#")]
broken = [r for r in refs if r not in ids]
print(f"\nОбъектов: {len(ids)}, внутренних ссылок: {len(refs)}, битых ссылок: {len(broken)}")
