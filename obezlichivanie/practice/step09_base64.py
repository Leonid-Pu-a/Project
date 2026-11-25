"""
Шаг 9. Вложения base64: раскодировать, заменить внутри, закодировать обратно. Плюс zip-архивы.
Запуск:   python practice/step09_base64.py
"""
import base64
import io
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

root = ET.parse("practice/mini_model.xml").getroot()
value = next(el.text for el in root.iter() if el.tag.endswith("ACLineSegment.sections"))
print("В модели хранится:", value[:60], "...")

raw = base64.b64decode(value)                          # base64 -> байты
print("Первые байты:", raw[:4], "(EF BB BF — метка BOM, дальше '<' — это XML-текст)")
text = raw.decode("utf-8-sig")                         # байты -> текст (utf-8-sig убирает BOM)
print("Внутри:", text)

new_text = text.replace("Тимошкино", "Яблочная")       # в программе здесь вызывается process_text
new_value = base64.b64encode(new_text.encode("utf-8")).decode("ascii")   # текст -> байты -> base64
print("\nПосле замены и кодирования:", new_value[:60], "...")
print("Проверка раскодированием:", base64.b64decode(new_value).decode("utf-8")[-60:])

# ---- zip-архив внутри base64 (так хранятся схемы подстанций)
buf = io.BytesIO()                                     # «файл» в памяти
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("diogen/diagram.xml", '<Diagram Description="КТП - 1618" uid="b2000000-0000-4000-8000-000000000001"/>')
zip_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
print("\nZip в base64 начинается так:", zip_b64[:12], "(после раскодирования байты начинаются с 'PK')")
with zipfile.ZipFile(io.BytesIO(base64.b64decode(zip_b64))) as z:
    for name in z.namelist():
        print("Файл в архиве:", name, "->", z.read(name).decode("utf-8"))
