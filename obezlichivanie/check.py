"""
Проверка результата обезличивания (работает потоком, подходит для больших файлов).

Запуск:
    python check.py исходный.xml обезличенный.xml

Файлы читаются ОДНОВРЕМЕННО, объект за объектом (порядок объектов при обезличивании не меняется).
Проверяем:
  1. Структура: те же объекты, те же классы, те же поля в каждом объекте.
  2. Идентификаторы: все изменены, новые не повторяются.
  3. Связи: каждая ссылка указывает на «тот же» объект, что и раньше
     (граф после обезличивания совпадает с исходным с точностью до переименования).
  4. Числовые параметры (сопротивления, длины, мощности, даты, флаги) не изменились.
  5. Статистика: число объектов каждого класса, число ссылок каждого типа.
  6. Утечки: ФИО абонентов, номера счётчиков и точек учёта не встречаются в результате;
     показываем, какие слова из названий подстанций и линий остались без изменений.
"""
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter

RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
NUMBER = re.compile(r"[-+]?\d*[.,]?\d+([eE][-+]?\d+)?|true|false|\d{4}-\d\d-\d\d.*")


def local(tag):
    return tag.rsplit("}", 1)[-1]


def read_objects(path):
    depth = 0
    root = None
    for event, elem in ET.iterparse(path, events=("start", "end")):
        if event == "start":
            depth += 1
            if depth == 1:
                root = elem
            continue
        depth -= 1
        if depth == 1:
            yield elem
            root.remove(elem)


def object_id(obj):
    v = obj.get(RDF + "about") or obj.get(RDF + "ID") or ""
    return v.lstrip("#")


def pairs(a, b):
    """Пары (исходный объект, обезличенный объект)."""
    ga, gb = read_objects(a), read_objects(b)
    for x, y in zip(ga, gb):
        yield x, y
    if next(ga, None) is not None or next(gb, None) is not None:
        raise SystemExit("ОШИБКА: в файлах разное число объектов")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    a, b = sys.argv[1], sys.argv[2]
    t0 = time.time()
    problems = Counter()
    examples = {}
    id_map = {}
    new_ids = set()
    classes = Counter()
    unchanged_ids = 0
    changed_names = Counter()
    secret_values = set()          # то, чего не должно остаться: ФИО абонентов, номера счётчиков
    out_values = set()
    key_words = Counter()          # слова из названий ПС и линий
    out_words = set()

    def problem(kind, text):
        problems[kind] += 1
        examples.setdefault(kind, text)

    # ---------- проход 1: структура, идентификаторы, числа, утечки
    for x, y in pairs(a, b):
        cls = local(x.tag)
        classes[cls] += 1
        if x.tag != y.tag:
            problem("класс объекта изменился", f"{x.tag} -> {y.tag}")
        old, new = object_id(x), object_id(y)
        id_map[old] = new
        if new in new_ids:
            problem("новый идентификатор повторяется", new)
        new_ids.add(new)
        unchanged_ids += old == new
        xs, ys = list(x.iter()), list(y.iter())
        if [e.tag for e in xs] != [e.tag for e in ys]:
            problem("состав полей объекта изменился", f"{cls} {old}")
            continue
        for ex, ey in zip(xs[1:], ys[1:]):
            field = local(ex.tag)
            vx, vy = (ex.text or "").strip(), (ey.text or "").strip()
            if len(ex) or not vx:
                continue
            if field == "IdentifiedObject.name" and vx != vy:
                changed_names[cls] += 1
            is_id_field = field in ("IdentifiedObject.name", "Asset.serialNumber", "Meter.meteringPointCode")
            if NUMBER.fullmatch(vx) and not is_id_field and vx != vy:
                problem("изменился числовой параметр", f"{cls}.{field}: {vx} -> {vy}")
            if cls in ("Customer", "Meter", "UsagePoint") and field in ("IdentifiedObject.name", "Asset.serialNumber"):
                # секретом считаем ФИО (три слова с заглавной) и всё, где есть номер из 3+ цифр;
                # «Technical Metering (CES)» или «б/н» — не персональные данные
                if re.search(r"\d{3}", vx) or re.fullmatch(r"([A-ZА-ЯЁ][^\W\d_]+\s+){2}[A-ZА-ЯЁ][^\W\d_]+", vx):
                    secret_values.add(vx)
                out_values.add(vy)
            if cls in ("Substation", "Line") and field == "IdentifiedObject.name":
                key_words.update(w for w in re.findall(r"[^\W\d_]{4,}", vx) if w[0].isupper())
            if field == "IdentifiedObject.name":
                out_words.update(re.findall(r"[^\W\d_]{4,}", vy))
    t1 = time.time()

    # ---------- проход 2: связи (теперь известно соответствие всех идентификаторов)
    edges_a, edges_b = Counter(), Counter()
    refs = 0
    for x, y in pairs(a, b):
        for ex, ey in zip(x.iter(), y.iter()):
            rx, ry = ex.get(RDF + "resource"), ey.get(RDF + "resource")
            if rx is None:
                continue
            refs += 1
            edges_a[(local(x.tag), local(ex.tag))] += 1
            edges_b[(local(y.tag), local(ey.tag))] += 1
            if rx.startswith("#"):
                target = rx[1:]
                expected = "#" + id_map[target] if target in id_map else None
                if expected is None:
                    if rx == ry:
                        problem("ссылка на объект вне файла не изменилась", rx)
                elif ry != expected:
                    problem("ссылка указывает не на тот объект", f"{rx} -> {ry}, ожидалось {expected}")
            elif rx != ry:
                problem("изменилась внешняя ссылка (перечисление)", f"{rx} -> {ry}")
    t2 = time.time()

    # ---------- отчёт
    leaked = secret_values & out_values
    if leaked:
        problem("ФИО/номер абонента или счётчика остался в результате", next(iter(leaked)))
    kept = [(w, n) for w, n in key_words.most_common() if w in out_words]
    print(f"Объектов: {sum(classes.values())}, классов: {len(classes)}, ссылок: {refs}")
    print(f"Идентификаторов не изменено: {unchanged_ids}")
    print(f"Статистика по классам и типам ссылок совпадает: {'да' if edges_a == edges_b else 'НЕТ'}")
    print("Изменено названий (топ классов):",
          ", ".join(f"{c} {n}" for c, n in changed_names.most_common(8)))
    print(f"Проверено ФИО/номеров абонентов, счётчиков, точек учёта: {len(secret_values)}, осталось в результате: {len(leaked)}")
    print(f"Слова из названий ПС и линий, оставшиеся как есть: {len(kept)} из {len(key_words)}"
          + (f" — например: {', '.join(w for w, _ in kept[:15])}" if kept else ""))
    if problems:
        print("\nПРОБЛЕМЫ:")
        for kind, n in problems.items():
            print(f"  {kind}: {n} (пример: {examples[kind]})")
    else:
        print("\nПроблем не найдено.")
    print(f"Время: {t2 - t0:.0f} с")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
