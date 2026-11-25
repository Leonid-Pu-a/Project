"""
Шаг настройки: показать словарь, который соберёт проход 1, — и проверить его глазами.

    python tools/show_words.py input.xml > words.txt

Выводит: имена собственные с заменами, улицы, защищённые слова (районы).
Если в списке «имён собственных» видны технические слова (Protection, Отключены, Резерв) —
добавьте их в STOP_WORDS в anonymize.py и запустите снова. Так и подбирался стоп-список.
"""
import os                                    # пути
import sys                                   # аргументы и кодировка вывода

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # чтобы найти anonymize.py
import anonymize                             # noqa: E402  (импорт после настройки пути)

if len(sys.argv) > 2:                        # необязательный второй аргумент — секрет
    anonymize.SECRET = sys.argv[2]
n = anonymize.collect(sys.argv[1])           # запускаем только проход 1
print(f"Объектов: {n}")
print(f"\n=== Имена собственные ({len(anonymize.word_map)}): слово -> замена ===")
for word in sorted(anonymize.word_map):      # по алфавиту — так удобнее искать глазами
    print(f"{word} -> {anonymize.word_map[word]}")
print(f"\n=== Улицы ({len(anonymize.street_map)}) ===")
for word in sorted(anonymize.street_map):
    print(f"{word} -> {anonymize.street_map[word]}")
print(f"\n=== Защищённые слова — районы, регионы ({len(anonymize.protected)}) ===")
print(", ".join(sorted(anonymize.protected)))
