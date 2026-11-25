"""
Шаг 8. Одно регулярное выражение для всего текста: UUID, телефон, «тип + номер», число, слово.
Запуск:   python practice/step08_regex.py
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

# 8.1 Простые примеры регулярных выражений
print(re.findall(r"\d+", "Sub - 2303, pol.126, 35 kV"))                  # все числа
print(re.findall(r"[^\W\d_]+", "ПС_Ngolona_P_Ф_01"))                      # все слова (буквы без цифр и _)
print(re.findall(r"(?:Sub|pol)[\s.\-]*(\d{3,})", "Sub - 2303, pol.126, Sub 35 kV"))  # номер после типа

# 8.2 Номер после «Sub», но НЕ напряжение: после числа не должно быть цифры, «/», дробной части, «kV»
rx = re.compile(r"(Sub[\s\-]*)(\d{3,})(?![\d/]|[.,]\d|\s*kV)")
for s in ["Sub - 2303", "Sub - 2303, рядом", "Sub 138 kV Kangaba", "Sub 110/35 kV"]:
    print(f"{s!r:22} -> найдено: {rx.findall(s)}")

# 8.3 Одно выражение с ИМЕНОВАННЫМИ вариантами; m.lastgroup говорит, какой вариант сработал
TOKEN = re.compile(r"""
     (?P<phone>(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]?\d{2}[\s-]?\d{2})
   | (?P<marker>(?:Sub|pol)[\s.\-]*)(?P<mnum>\d{3,})(?![\d/]|[.,]\d|\s*kV)
   | (?P<num>\d+)
   | (?P<word>[^\W\d_]+)
""", re.VERBOSE)

text = "Sub - 2303, pol.126, Sub 35 kV Ngolona, тел. +7 (912) 345-67-89"
for m in TOKEN.finditer(text):
    print(f"   {m.lastgroup:6} {m.group()!r}")


def replace(m):
    """Решаем, на что заменить кусок. Каждый кусок заменяется ровно один раз."""
    if m.lastgroup == "phone":
        return "<ТЕЛЕФОН>"
    if m.lastgroup == "mnum":
        return m.group("marker") + "<НОМЕР>"
    if m.lastgroup == "word" and m.group() == "Ngolona":
        return "Яблочная"
    return m.group()                                  # остальное как есть


print("\nБыло:  ", text)
print("Стало: ", TOKEN.sub(replace, text))
