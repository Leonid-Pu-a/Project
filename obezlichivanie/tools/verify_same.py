"""
Доказывает, что версии «с комментариями» — это та же самая программа.

    python tools/verify_same.py

Python разбирает исходный код в синтаксическое дерево (AST). Комментарии в дерево не попадают,
поэтому если деревья двух файлов совпадают, то программы одинаковые, как бы ни отличались
комментарии и пустые строки.
"""
import ast                                   # модуль разбора кода Python в дерево
import os                                    # пути к файлам

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # папка simple_student
ok = True                                    # итог проверки
for plain, commented in (("anonymize.py", "anonymize_commented.py"), ("check.py", "check_commented.py")):
    trees = []                               # сюда положим два дерева
    for name in (plain, commented):          # читаем оба файла
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            trees.append(ast.dump(ast.parse(f.read())))   # текстовое представление дерева
    same = trees[0] == trees[1]              # деревья совпали?
    ok = ok and same                         # общий итог
    print(f"{plain} и {commented}: {'код одинаковый' if same else 'КОД РАЗЛИЧАЕТСЯ'}")
raise SystemExit(0 if ok else 1)             # код возврата: 0 — всё совпало
