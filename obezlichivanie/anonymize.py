"""
Обезличивание CIM-модели энергосистемы (RDF/XML) — простое решение.

Запуск:
    python anonymize.py входной.xml выходной.xml [секретное_слово]

Идея в двух проходах по файлу:
  ПРОХОД 1 — «составляем словарь»: читаем модель и собираем настоящие имена собственные
             (названия подстанций, линий, организаций), названия улиц и районы.
  ПРОХОД 2 — «заменяем»: читаем модель ещё раз, в каждом значении заменяем
             UUID, имена собственные, ФИО, номера — и сразу пишем результат.

Почему это работает на файлах в десятки гигабайт:
  файл читается ПОТОКОМ (xml.etree.ElementTree.iterparse) — в памяти одновременно
  находится только ОДИН объект модели, а не весь файл.

Почему результат одинаковый при каждом запуске (детерминизм):
  все замены вычисляются из хеша SHA-256 от «секретное слово + исходное значение»,
  а не из случайных чисел. Без секретного слова исходные данные по хешу не восстановить.

Почему не ломаются связи между объектами:
  ссылка rdf:resource="#_<UUID>" и сам объект rdf:about="#_<UUID>" проходят через одну и
  ту же функцию new_uuid(), поэтому получают один и тот же новый UUID.
"""
import base64
import hashlib
import io
import os
import re
import sys
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SECRET = "secret"                        # меняется третьим аргументом командной строки

RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
NAMESPACES = {}                          # префикс -> URI (заполняется при чтении файла)


# =====================================================================================
# 1. Справочники
# =====================================================================================
def load_tsv(name):
    """Читает файл справочника: строки, разделённые табуляцией; '#' — комментарий."""
    rows = []
    with open(os.path.join(HERE, "dict", name), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                rows.append(line.split("\t"))
    return rows


MALE = load_tsv("names.tsv")             # [Имя, Фамилия, Отчество_м, Отчество_ж, Улица]
FEMALE = load_tsv("female_names.tsv")    # [Имя]
FRUITS = [row[1] for row in load_tsv("fruits.tsv")]   # прилагательные: «Яблочная», ...

TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o",
                     "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


def translit(text):
    """Кириллица -> латиница: «Яблочная» -> «Yablochnaya»."""
    out = ""
    for ch in text:
        lat = TRANSLIT.get(ch.lower(), ch)
        out += lat.capitalize() if ch.isupper() else lat
    return out


def is_cyrillic(text):
    return re.search("[А-Яа-яЁё]", text) is not None


# =====================================================================================
# 2. Детерминированный «случайный» выбор
# =====================================================================================
def h(text):
    """Большое целое число из SHA-256(секрет + текст). Одинаковый текст -> одинаковое число."""
    return int(hashlib.sha256((SECRET + "|" + text).encode("utf-8")).hexdigest(), 16)


def pick(items, text):
    """Выбрать элемент списка по хешу текста."""
    return items[h(text) % len(items)]


# =====================================================================================
# 3. Правила замены значений
# =====================================================================================

# --- 3.1 UUID (идентификаторы объектов) -------------------------------------------
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def new_uuid(old):
    """Новый UUID из старого. Регистр букв сохраняем (в схемах бывают ЗАГЛАВНЫЕ UUID)."""
    new = str(uuid.UUID(int=h("uuid:" + old.lower()) % 2 ** 128, version=4))
    return new.upper() if old.isupper() else new


def replace_uuids(text):
    return UUID_RE.sub(lambda m: new_uuid(m.group()), text)


# --- 3.2 Номера (той же длины, без повторов) --------------------------------------
number_map = {}          # старый номер -> новый
used_numbers = set()     # уже выданные новые номера (чтобы два разных номера не совпали)


def new_number(old):
    if old in number_map:
        return number_map[old]
    attempt = 0
    while True:
        new = str(h(f"num:{old}:{attempt}") % 10 ** len(old)).zfill(len(old))
        same_kind = (new[0] == "0") == (old[0] == "0")       # «0123» -> «0xxx», «123» -> не «0xx»
        if same_kind and new != old and new not in used_numbers:
            break
        attempt += 1
    number_map[old] = new
    used_numbers.add(new)
    return new


# --- 3.3 Имена собственные -> прилагательные от названий фруктов -----------------
word_map = {}            # «Kangaba» -> «Yablochnaya», «Тимошкино» -> «Грушевая», ...
street_map = {}          # «Djikoroni» -> «Petrovskaya»
protected = set()        # районы и регионы: по заданию их сохраняем


def build_word_map(words):
    """
    Каждому слову — своё прилагательное. Слова сортируем и нумеруем:
      0..99    -> «Яблочная»
      100..    -> «Яблочно-грушевая» (две РАЗНЫЕ части), так хватит на 100 + 100*99 = 10 000 слов.
    Номера у слов разные => и замены разные (уникальность новых наименований).
    Сортируем НЕ по алфавиту, а по хешу с секретом: иначе по номеру прилагательного можно было бы
    угадать алфавитное место настоящего названия. Порядок всё равно одинаковый при каждом запуске.
    """
    words = sorted(words, key=lambda w: (h("word:" + w), w))
    n = len(FRUITS)
    if len(words) > n + n * (n - 1):
        raise SystemExit("Слишком много имён собственных — добавьте фруктов в dict/fruits.tsv")
    for i, word in enumerate(words):
        if i < n:
            adjective = FRUITS[i]                           # «Яблочная»
        else:
            first, second = divmod(i - n, n - 1)            # номер пары (first, second), first != second
            if second >= first:
                second += 1
            prefix = FRUITS[first][:-2] + "о"               # «Яблочная» -> «Яблочно»
            adjective = prefix + "-" + FRUITS[second].lower()
        if not is_cyrillic(word):
            adjective = translit(adjective)
        if word.isupper() and len(word) > 1:
            adjective = adjective.upper()
        word_map[word] = adjective


def build_street_map(words):
    for word in words:
        street = pick(MALE, "street:" + word)[4]               # «Петровская»
        street_map[word] = street if is_cyrillic(word) else translit(street)


# --- 3.4 ФИО ----------------------------------------------------------------------
def fake_person(full_name):
    """
    «Nikitin Vitaliy Artemov» -> «Petrov Kirill Romanovich».
    Фамилия, имя и отчество берутся из справочника по хешу соответствующей части,
    пол определяется по окончанию фамилии, алфавит и РЕГИСТР — как в исходной строке.
    """
    parts = full_name.split()
    if not parts:
        return full_name
    female = parts[0].lower().endswith(("a", "а"))
    surname = pick(MALE, "surname:" + parts[0])[1]
    if female:
        surname += "а"
    result = [surname]
    if len(parts) > 1:
        result.append(pick(FEMALE if female else MALE, "first:" + parts[1])[0])
    if len(parts) > 2:
        result.append(pick(MALE, "middle:" + parts[2])[3 if female else 2])
    text = " ".join(result)
    if not is_cyrillic(full_name):
        text = translit(text)
    return text.upper() if full_name.isupper() else text


def looks_like_person(name):
    """Три слова, каждое с заглавной буквы и только из букв — похоже на ФИО."""
    parts = name.split()
    return len(parts) == 3 and all(p.isalpha() and p[0].isupper() and not p.isupper() for p in parts)


def fake_email(email):
    """Адрес строится из синтетического имени: «ivanov@mail.ru» -> «pyotr.petrov17@example.com»."""
    surname = translit(pick(MALE, "e-surname:" + email)[1]).lower()
    first = translit(pick(MALE, "e-first:" + email)[0]).lower()
    return f"{first}.{surname}{h(email) % 100}@example.com"


def fake_phone(phone):
    """Последние 10 цифр телефона заменяем, формат записи (+7 (912) 345-67-89) сохраняем."""
    digits = re.sub(r"\D", "", phone)
    new = digits[:-10] + new_number(digits[-10:])
    position = iter(new)
    return re.sub(r"\d", lambda m: next(position), phone)


# --- 3.5 Замена внутри произвольного текста ---------------------------------------
# Номер после «типа объекта»: «Sub - 2303», «TS 1230-2», «РП 843», «pol.126», «№ 1234».
# Но «Sub 138 kV» и «Sub 110/35 kV» — это напряжение, его НЕ трогаем (проверка «(?!...)» после числа).
MARKERS = r"Sub|ПС|TS|ТП|KTP|КТП|STP|СТП|RP|РП|pol|оп|Оп|feeder|No|№"
UNITS = r"kV|кВ|kv|KV|kVA|кВА|MVA|МВА|MW|МВт|V\b|В\b"
TOKEN = re.compile(r"""
     (?P<uuid>""" + UUID_RE.pattern + r""")
   | (?P<email>[\w.+-]+@[\w-]+\.[\w.-]+)
   | (?P<phone>(?<![\d+])(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d))
   | (?P<marker>(?<![A-Za-zА-Яа-яЁё])(?:""" + MARKERS + r""")[\s.\-–_№]*)(?P<mnum>\d{3,})(?![\d/]|[.,]\d|\s*(?:""" + UNITS + r"""))
   | (?P<num>\d+)
   | (?P<word>[^\W\d_]+)
""", re.VERBOSE)


def process_text(text, id_field=False, long_numbers=True):
    """
    Один проход регулярным выражением по тексту. Для каждого найденного куска решаем:
      UUID           -> новый UUID
      e-mail/телефон -> синтетические
      «Sub 2303»     -> номер объекта заменяем
      число          -> заменяем, если это поле-идентификатор (номер счётчика и т.п.)
                        или число длинное (6+ цифр: ИНН, лицевой счёт, код из учётной системы)
      слово          -> по словарям (имя собственное / улица); остальные слова не трогаем
    Каждый кусок текста заменяется ровно один раз.
    """
    def replace(m):
        kind = m.lastgroup
        t = m.group()
        if kind == "uuid":
            return new_uuid(t)
        if kind == "email":
            return fake_email(t)
        if kind == "phone":
            return fake_phone(t)
        if kind == "mnum":
            return m.group("marker") + new_number(m.group("mnum"))
        if kind == "num":
            if (id_field and len(t) >= 3) or (long_numbers and len(t) >= 6):
                return new_number(t)
            return t
        if t in protected:
            return t
        if t in street_map:
            return street_map[t]
        return word_map.get(t, t)
    return TOKEN.sub(replace, text)


# --- 3.6 base64: вложенные XML-документы, zip-архивы схем -----------------------
BASE64_RE = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")


def decode_base64(value):
    """Возвращает байты, если значение похоже на base64, иначе None."""
    if len(value) % 4 or not BASE64_RE.fullmatch(value):
        return None
    try:
        return base64.b64decode(value, validate=True)
    except ValueError:
        return None


def base64_texts(raw):
    """Все тексты внутри base64: сам текст или XML-файлы из zip. Картинки/звук — пропускаем."""
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            return [z.read(n).decode("utf-8-sig", "ignore") for n in z.namelist() if n.endswith(".xml")]
    try:
        return [raw.decode("utf-8-sig")]
    except UnicodeDecodeError:
        return []


def process_base64(value, raw):
    def fix(data):                                  # обработать текст, сохранив BOM, если был
        bom = data.startswith(b"\xef\xbb\xbf")
        text = process_text(data.decode("utf-8-sig"), long_numbers=False)  # координаты схем не трогаем
        return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")

    if raw[:2] == b"PK":                            # zip-архив (схема подстанции)
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as zin, zipfile.ZipFile(out, "w") as zout:
            for info in zin.infolist():
                data = zin.read(info)
                zout.writestr(info, fix(data) if info.filename.endswith(".xml") else data)
        return base64.b64encode(out.getvalue()).decode("ascii")
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return value                                # двоичные данные (картинка, звук, график)
    return base64.b64encode(fix(raw)).decode("ascii")


# =====================================================================================
# 4. Какие поля как обрабатывать
# =====================================================================================
NAME_FIELDS = {"IdentifiedObject.name", "IdentifiedObject.aliasName", "IdentifiedObject.description", "Name.name"}

# Классы, в названиях которых — настоящие имена собственные (подстанции, линии, организации)
KEY_CLASSES = {"Substation", "Line", "Plant", "CogenerationPlant", "HydroPowerPlant", "ControlArea",
               "ControlAreaOperator", "HostControlArea", "ConnectDisconnectFunction", "WeatherStation",
               "ReportingGroup", "Customer", "Organisation"}

# Районы и регионы — по заданию сохраняются
REGION_CLASSES = {"GeographicalRegion", "SubGeographicalRegion", "NetworkView"}

# Поля-идентификаторы: в них заменяем все номера от 3 цифр
ID_FIELDS = {"Asset.serialNumber", "Meter.meteringPointCode", "IdentifiedObject.mRIDStr",
             "PowerSystemResource.ccsCode", "StreetDetail.buildingName", "StreetDetail.number",
             "StreetDetail.suiteNumber"}

PERSON_FIELDS = {"Location.inChargeFullName"}

# Как в модели может начинаться название индивидуального предпринимателя (дальше идёт ФИО)
IP_PREFIXES = ("Individual Entrepreneur ", "IP ", "Индивидуальный предприниматель ", "ИП ")

# Классы, у которых название — это номер (счётчик, точка учёта, опора, лицевой счёт абонента)
NUMBER_NAME_CLASSES = {"Meter", "UsagePoint", "Pole", "Customer", "EndDevice"}

# Технические слова, которые НЕ являются именами собственными (не заменяем)
STOP_WORDS = {w.lower() for w in {
    "Sub", "Substation", "Line", "Lines", "CableLine", "Plant", "Park", "Area", "Areas", "Balancing", "Main",
    "Aux", "Interconnection", "Office", "Dispatching", "Regional", "Centre", "Center", "South", "West",
    "North", "East", "System", "Control", "Backup", "Network", "Company", "United", "District", "Extract",
    "Social", "Domestic", "Load", "Management", "Nuclear", "Power", "HydroPlant", "Hydro", "Jet", "Technical",
    "Metering", "Individual", "Entrepreneur", "Grid", "Base", "Weather", "Station", "Group", "Reporting",
    "Equivalent", "Equivalents", "Global", "Objects", "Local", "Neighbouring", "Pump", "Plant", "Electrical",
    "Networks", "Reserve", "Elevator", "Mean", "Interest", "Technological", "Information", "Consumer",
    "Society", "Village", "Church", "The", "And", "Center", "Объекты", "Подстанция", "Линия", "Управление",
    "Региональное", "Диспетчерское", "Диспетческое", "Филиал", "Сети", "Электрические", "Района",
    # общие слова, найденные при просмотре словаря на реальной модели (технические, а не имена)
    "Active", "Biological", "Dispatch", "Enterprise", "Facilities", "Factory", "International", "Light",
    "Mining", "New", "Off", "Oil", "Processing", "Project", "Protection", "Railway", "Railways", "Sea", "State",
    "Temperature", "Treatment", "University", "Middle", "Central", "Combine", "Compound", "Dairy", "Feed",
    "Infeed", "Meat", "Pool", "Rack", "Ring", "Rotor", "Sky", "Plus", "Russian", "Swt", "SCADA", "Planer",
    "Замечаний", "Инструктаж", "Исполнительный", "Окончены", "Отключалась", "Отключены", "Отпайка", "Передано",
    "Полностью", "Проверить", "Проведён", "Разрешаю", "Резерв", "Установлено", "Установлены", "Вывешены",
    "Выслана", "Смена", "Город", "Городская", "Предприятие", "Объединенное", "Системного", "Средней", "Центра",
    "Востока", "Запада", "Сибири", "Волги", "Промзона",
    # слова-типы улиц: заменяем название улицы, а не слово «улица»
    "Street", "St", "Avenue", "Ave", "Road", "Rue", "Lane", "Boulevard", "Square", "Улица", "Переулок",
    "Проспект", "Проезд", "Бульвар", "Шоссе", "Площадь", "Набережная", "Тупик", "Микрорайон",
    # типы объектов и формы собственности — их сохраняем всегда (тип объекта не должен меняться)
    "OHL", "OHCL", "CL", "TS", "KTP", "STP", "RP", "ВЛ", "КЛ", "ПС", "ТП", "КТП", "СТП", "РП", "ЛЭП",
    "LLC", "JSC", "PJSC", "OJSC", "CJSC", "OOO", "ZAO", "PAO", "NGDU", "ООО", "ОАО", "ЗАО", "ПАО", "АО", "МУП",
}}   # храним в нижнем регистре: «CONTROL», «Control», «control» — одно и то же техническое слово

# Слово сразу после типа объекта — почти всегда имя собственное: «Sub Kangaba», «ПС_Часовая», «ВЛ Тимошкино»
LINE_MARKER_RE = re.compile(r"(?<![A-Za-zА-Яа-яЁё])(?:Sub|ПС|OHL|CL|ВЛ|КЛ|ТП|КТП|РП)[\s._\-]+([A-ZА-ЯЁ][^\W\d_]{2,})")
# Название организации в кавычках после формы собственности: ОАО "МРСК Урала", LLC 'Ukropnyy Tomatnyy'
ORG_RE = re.compile(r"(?<![A-Za-zА-Яа-яЁё])(?:ООО|ОАО|ЗАО|ПАО|АО|МУП|OOO|ZAO|PAO|LLC|JSC|PJSC|OJSC|CJSC)\s*"
                    r"[\"'«„]+([^\"'»“]{2,60})[\"'»“]")
WORD_RE = re.compile(r"[^\W\d_]+")


def proper_words(text):
    """Слова, похожие на имена собственные: с заглавной буквы, от 3 букв, не технические.
    Короткие аббревиатуры из заглавных (JSC, LLC, OHL, РДУ) — тоже технические."""
    return {w for w in WORD_RE.findall(text)
            if len(w) >= 3 and w[0].isupper() and w.lower() not in STOP_WORDS and not (w.isupper() and len(w) <= 4)}


def org_words(text):
    """Все слова с заглавной буквы внутри кавычек названия организации (включая аббревиатуры: «ЕЭСК»)."""
    return {w for name in ORG_RE.findall(text) for w in WORD_RE.findall(name)
            if len(w) >= 2 and w[0].isupper() and w.lower() not in STOP_WORDS}


def local(tag):
    return tag.rsplit("}", 1)[-1]


# =====================================================================================
# 5. Чтение файла потоком
# =====================================================================================
def read_objects(path):
    """Отдаёт объекты верхнего уровня (дочерние элементы rdf:RDF) по одному."""
    depth = 0
    root = None
    for event, elem in ET.iterparse(path, events=("start", "end", "start-ns")):
        if event == "start-ns":
            prefix, uri = elem
            NAMESPACES[prefix] = uri
            ET.register_namespace(prefix, uri)        # чтобы при записи остались cim:, me:, rdf:
        elif event == "start":
            depth += 1
            if depth == 1:
                root = elem
        else:
            depth -= 1
            if depth == 1:
                yield elem
                root.remove(elem)                     # освобождаем память


def leaf_values(obj):
    """Все текстовые значения объекта (включая вложенные, например адрес): (элемент, поле)."""
    for el in obj.iter():
        if el is not obj and len(el) == 0 and el.text and el.text.strip():
            yield el, local(el.tag)


# =====================================================================================
# 6. ПРОХОД 1: собираем словари
# =====================================================================================
def collect(path):
    words, streets = set(), set()
    count = 0
    for obj in read_objects(path):
        count += 1
        cls = local(obj.tag)
        for el, field in leaf_values(obj):
            value = el.text
            texts = [value]
            raw = decode_base64(value)
            if raw is not None:
                texts = base64_texts(raw)
            for text in texts:
                if (cls in REGION_CLASSES and field in NAME_FIELDS) or field.startswith("TownDetail."):
                    protected.update(WORD_RE.findall(text))
                elif field == "StreetDetail.name":
                    streets.update(proper_words(text))
                elif cls in KEY_CLASSES and field in NAME_FIELDS:
                    if not (cls == "Customer" and (looks_like_person(text) or text.startswith(IP_PREFIXES))):
                        words.update(proper_words(text))
                elif field == "Expression.formula":
                    words.update(proper_words(text))
                words.update(proper_words(" ".join(LINE_MARKER_RE.findall(text))))  # «ПС Тимошкино», «Sub Kangaba»
                words.update(org_words(text))                # ОАО "МРСК Урала"
    words = {w for w in words if w.lower() not in STOP_WORDS}
    words -= protected
    streets -= protected
    build_word_map(words - streets)
    build_street_map(streets)
    return count


# =====================================================================================
# 7. ПРОХОД 2: заменяем и записываем
# =====================================================================================
stats = {"objects": 0, "persons": 0, "base64": 0}


def process_value(cls, field, value, person):
    if cls == "Person" and field in ("IdentifiedObject.name", "Person.lastName", "Person.firstName", "Person.mName"):
        stats["persons"] += 1
        sur, first, middle = person
        return {"Person.lastName": sur, "Person.firstName": first, "Person.mName": middle}.get(
            field, f"{sur} {first} {middle}")

    if field in PERSON_FIELDS:                                         # «ответственный» в адресе
        stats["persons"] += 1
        return fake_person(value)

    if cls == "Customer" and field == "IdentifiedObject.name":
        if looks_like_person(value):                                   # физлицо
            stats["persons"] += 1
            return fake_person(value)
        for prefix in IP_PREFIXES:                                     # индивидуальный предприниматель
            if value.startswith(prefix):
                stats["persons"] += 1
                return prefix + fake_person(value[len(prefix):])

    raw = decode_base64(value)
    if raw is not None:
        stats["base64"] += 1
        return process_base64(value, raw)

    if re.fullmatch(r"[-+]?\d*[.,]?\d+([eE][-+]?\d+)?|true|false|\d{4}-\d\d-\d\d.*", value) \
            and field not in ID_FIELDS and field not in NAME_FIELDS:
        return value                                                   # числа, даты, флаги — физика модели

    number_name = cls in NUMBER_NAME_CLASSES and field == "IdentifiedObject.name"   # «52073867» — номер счётчика
    return process_text(value, id_field=field in ID_FIELDS or number_name)


def process_object(obj):
    cls = local(obj.tag)
    for attr in (RDF + "about", RDF + "ID"):
        if obj.get(attr) is not None:
            obj.set(attr, replace_uuids(obj.get(attr)))
    # Сотрудник (cim:Person): вместо логина «ck11user5» — синтетическое ФИО, одно на объект,
    # чтобы поля name, lastName, firstName одного сотрудника были согласованы.
    person = None
    if cls == "Person":
        key = obj.get(RDF + "about") or ""
        person = (translit(pick(MALE, "p-surname:" + key)[1]),
                  translit(pick(MALE, "p-first:" + key)[0]),
                  translit(pick(MALE, "p-middle:" + key)[2]))
    for el in obj.iter():
        res = el.get(RDF + "resource")
        if res is not None:
            el.set(RDF + "resource", replace_uuids(res))   # внешние ссылки (перечисления) без UUID не меняются
    for el, field in leaf_values(obj):
        el.text = process_value(cls, field, el.text, person)


def anonymize(src, dst):
    with open(src, "rb") as f:                         # заголовок файла (<?xml ...?>, <rdf:RDF ...>) — как был
        head = f.read(1 << 20)
    m = re.search(rb"<(\w+:)?RDF\b[^>]*>", head)
    root_close = b"</" + (m.group(1) or b"") + b"RDF>\n"
    declarations = None
    with open(dst, "wb") as out:
        out.write(head[:m.end()] + b"\n")
        for obj in read_objects(src):
            if declarations is None:                   # xmlns-атрибуты, которые ElementTree добавит в каждый объект
                declarations = [f' xmlns:{p}="{u}"' for p, u in NAMESPACES.items()]
            process_object(obj)
            obj.tail = None
            text = ET.tostring(obj, encoding="unicode")
            for d in declarations:
                text = text.replace(d, "")             # они уже объявлены на корне
            out.write(b"  " + text.encode("utf-8") + b"\n")
            stats["objects"] += 1
        out.write(root_close)


def main():
    global SECRET
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    if len(sys.argv) > 3:
        SECRET = sys.argv[3]
    t0 = time.time()
    n = collect(src)
    t1 = time.time()
    print(f"Проход 1: объектов {n}, имён собственных {len(word_map)}, улиц {len(street_map)}, "
          f"защищённых слов (районы) {len(protected)} — {t1 - t0:.0f} с")
    anonymize(src, dst)
    t2 = time.time()
    print(f"Проход 2: объектов {stats['objects']}, ФИО {stats['persons']}, base64-вложений {stats['base64']}, "
          f"заменённых номеров {len(number_map)} — {t2 - t1:.0f} с")
    print(f"Готово: {dst} ({os.path.getsize(dst) / 2 ** 20:.0f} МБ) за {t2 - t0:.0f} с")


if __name__ == "__main__":
    main()
