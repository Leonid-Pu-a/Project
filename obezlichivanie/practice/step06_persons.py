"""
Шаг 6. ФИО: синтетические из справочника имён (имя -> фамилия, отчество, улица).
Запуск:   python practice/step06_persons.py
"""
import hashlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
SECRET = "учебный-секрет"


def h(text):
    return int(hashlib.sha256((SECRET + "|" + text).encode("utf-8")).hexdigest(), 16)


def pick(items, text):
    return items[h(text) % len(items)]


def load_tsv(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip().split("\t") for line in f if line.strip() and not line.startswith("#")]


MALE = load_tsv("dict/names.tsv")           # [Имя, Фамилия, Отчество_м, Отчество_ж, Улица]
FEMALE = load_tsv("dict/female_names.tsv")  # [Имя]
print("Одна строка справочника:", MALE[22])  # из имени «Пётр» получаются Петров, Петрович, Петровна, Петровская

TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o",
                     "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


def translit(text):
    return "".join((TRANSLIT.get(c.lower(), c).capitalize() if c.isupper() else TRANSLIT.get(c, c)) for c in text)


def fake_person(full_name):
    parts = full_name.split()
    female = parts[0].lower().endswith(("a", "а"))               # пол — по окончанию фамилии
    surname = pick(MALE, "surname:" + parts[0])[1] + ("а" if female else "")
    result = [surname]
    if len(parts) > 1:
        result.append(pick(FEMALE if female else MALE, "first:" + parts[1])[0])
    if len(parts) > 2:
        result.append(pick(MALE, "middle:" + parts[2])[3 if female else 2])
    text = " ".join(result)
    if not any("а" <= c.lower() <= "я" or c in "ёЁ" for c in full_name):
        text = translit(text)                                    # исходник латиницей -> результат латиницей
    return text.upper() if full_name.isupper() else text         # регистр как в исходнике


for name in ["Nikitin Vitaliy Artemov", "Tamarina Alyonina Kirillov", "ALYONINA DENIS ANTONINA",
             "Иванов Иван Иванович", "Смирнова Ольга Петровна"]:
    print(f"{name:30} -> {fake_person(name)}")
print("\nУлица из того же справочника: Djikoroni ->", translit(pick(MALE, "street:Djikoroni")[4]))
