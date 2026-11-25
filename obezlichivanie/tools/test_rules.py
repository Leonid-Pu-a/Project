"""
Проверка правил замены на коротких строках — без запуска на большом файле (1 секунда).

    python tools/test_rules.py

Каждый тест: (класс, поле, исходное значение, условие на результат, что проверяем).
Именно так проверялись правила во время разработки, прежде чем запускать обработку 900 МБ.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import anonymize as a                        # noqa: E402

# Маленький «словарь» вместо прохода 1: как будто эти слова нашлись в модели
a.build_word_map({"Kangaba", "Тимошкино", "Faladie", "Tonga", "Часовая", "МРСК", "Урала", "KOLRABIEVY", "Niarèkoto"})
a.build_street_map({"Djikoroni"})
a.protected.update({"Koulikoro", "District", "Mali", "Center"})

TESTS = [
    ("Substation", "IdentifiedObject.name", "Sub 138 kV Kangaba",
     lambda r: r.startswith("Sub 138 kV ") and "Kangaba" not in r, "напряжение сохранено, имя заменено"),
    ("Substation", "IdentifiedObject.name", "Sub - 2303",
     lambda r: r.startswith("Sub - ") and r != "Sub - 2303" and len(r) == len("Sub - 2303"), "номер ПС заменён, длина та же"),
    ("Discrete", "IdentifiedObject.description", "Sub - 2303, рядом Sub 0,4 kV",
     lambda r: "2303" not in r and r.endswith(", рядом Sub 0,4 kV"), "номер перед запятой заменён, «0,4 kV» нет"),
    ("ServiceLocation", "StreetDetail.name", "Djikoroni Street",
     lambda r: r.endswith(" Street") and "Djikoroni" not in r, "слово «Street» сохранено"),
    ("Substation", "IdentifiedObject.name", "Sub 110/35/6 kV №53 Faladie",
     lambda r: r.startswith("Sub 110/35/6 kV №53 ") and "Faladie" not in r, "«110/35/6 kV» не тронуто"),
    ("ACLineSegment", "IdentifiedObject.name", "OHL 10 kV f.05 Sub Niarèkoto main line, 189-200",
     lambda r: r.startswith("OHL 10 kV f.05 Sub ") and "Niarèkoto" not in r, "тип OHL сохранён"),
    ("AnalogMeasurementExpression", "Expression.formula", "abs(ПС_Часовая_2_P_Ф_02)",
     lambda r: r.startswith("abs(ПС_") and "Часовая" not in r and r.endswith("_2_P_Ф_02)"), "формула согласована"),
    ("DjRecordTemplate", "DjRecordTemplate.text", 'В филиале СЭ (ОАО "МРСК Урала") отменен ОРР',
     lambda r: "МРСК" not in r and "Урала" not in r and 'ОАО "' in r, "организация в кавычках"),
    ("ServiceLocation", "IdentifiedObject.name", "Mali,  Koulikoro District, Center, Djikoroni Street, h.№ 61",
     lambda r: "Koulikoro District" in r and "Djikoroni" not in r, "район сохранён, улица заменена"),
    ("Customer", "IdentifiedObject.name", "Tamarina Alyonina Kirillov",
     lambda r: r.split()[0].endswith("a") and "Tamarina" not in r, "ФИО заменено, женский род сохранён"),
    ("Customer", "IdentifiedObject.name", "IP ALYONINA DENIS ANTONINA",
     lambda r: r.startswith("IP ") and r.isupper() and "ALYONINA" not in r, "ИП: префикс и регистр сохранены"),
    ("Customer", "IdentifiedObject.name", "LLC UK DOM KOLRABIEVY",
     lambda r: r.startswith("LLC UK DOM ") and "KOLRABIEVY" not in r and r.isupper(), "организация-абонент"),
    ("Meter", "IdentifiedObject.name", "52073867",
     lambda r: r.isdigit() and len(r) == 8 and r != "52073867", "номер счётчика той же длины"),
    ("Meter", "IdentifiedObject.mRIDStr", "meter_52073867",
     lambda r: r == "meter_" + a.new_number("52073867"), "тот же номер в коде — та же замена"),
    ("Pole", "Asset.serialNumber", "ПРДУСТ112481",
     lambda r: r.startswith("ПРДУСТ") and r != "ПРДУСТ112481", "серийный номер опоры"),
    ("CableInfo", "IdentifiedObject.name", "AAB 3x185-10",
     lambda r: r == "AAB 3x185-10", "марка кабеля не тронута"),
    ("CurrentTransformer", "IdentifiedObject.name", "CT10 Bay f. 19 300/5",
     lambda r: r == "CT10 Bay f. 19 300/5", "коэффициент ТТ не тронут"),
    ("ACLineSegment", "ACLineSegment.r", "0.123",
     lambda r: r == "0.123", "физический параметр не тронут"),
    ("Line", "IdentifiedObject.mRID", "3ca10967-b797-4d15-9a44-cdea3015ad63",
     lambda r: r == a.new_uuid("3ca10967-b797-4d15-9a44-cdea3015ad63"), "UUID в тексте = UUID в ссылке"),
    ("X", "IdentifiedObject.description", "тел. +7 (912) 345-67-89",
     lambda r: r.startswith("тел. +7 (") and r != "тел. +7 (912) 345-67-89", "телефон: формат сохранён"),
]

failed = 0
for cls, field, value, check, what in TESTS:
    result = a.process_value(cls, field, value, None)    # та же функция, что работает в проходе 2
    good = check(result)
    failed += not good
    print(f"[{'OK' if good else 'ОШИБКА'}] {what}\n      {value!r}\n   -> {result!r}")
print(f"\nТестов: {len(TESTS)}, ошибок: {failed}")
raise SystemExit(1 if failed else 0)
