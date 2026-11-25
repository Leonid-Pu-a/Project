"""
Шаг 5. Номера: другой номер той же длины, одинаковый для одинаковых, разный для разных.
Запуск:   python practice/step05_numbers.py
"""
import hashlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
SECRET = "учебный-секрет"
number_map = {}                     # старый номер -> новый (память о сделанных заменах)
used_numbers = set()                # какие новые номера уже выданы


def h(text):
    return int(hashlib.sha256((SECRET + "|" + text).encode("utf-8")).hexdigest(), 16)


def new_number(old):
    if old in number_map:                                   # уже заменяли — та же замена
        return number_map[old]
    attempt = 0
    while True:
        new = str(h(f"num:{old}:{attempt}") % 10 ** len(old)).zfill(len(old))   # кандидат той же длины
        same_kind = (new[0] == "0") == (old[0] == "0")      # ведущий ноль сохраняем как был
        if same_kind and new != old and new not in used_numbers:
            break                                           # кандидат подходит
        attempt += 1                                        # иначе — следующая попытка
    number_map[old] = new
    used_numbers.add(new)
    return new


for n in ["52073867", "52073867", "75164594", "2303", "0123", "126", "5000339959"]:
    print(f"{n:>12} -> {new_number(n)}")

# Проверка уникальности на всех трёхзначных номерах: 900 разных номеров -> 900 разных замен
olds = [str(i) for i in range(100, 1000)]
news = [new_number(x) for x in olds]
print(f"\nТрёхзначных номеров: {len(olds)}, разных замен: {len(set(news))}, "
      f"все длиной 3: {all(len(x) == 3 for x in news)}")
