# -*- coding: utf-8 -*-
"""
Восстановление схемы процесса обработки заявок на закупку по журналу событий.

Запуск:
    pip install pandas
    python analysis.py students.csv

Скрипт:
  1. группирует журнал по ProcessInstanceId и сортирует по числовому EventIndex;
  2. строит цепочку ActivityName для каждого экземпляра;
  3. извлекает все пары соседних активностей (переходы) и считает их частоты;
  4. строит таблицу полных вариантов (уникальные маршруты) с частотами и долями;
  5. проверяет гипотезу о пороге Amount для "Дополнительное согласование";
  6. проверяет строгое соответствие Result -> следующая активность;
  7. сохраняет student_transitions.csv и variants.csv.

Все выводы в отчёте report.md опираются на результаты именно этого скрипта.
"""
import sys
from collections import Counter
import pandas as pd


def load_log(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    # Внутри экземпляра сортируем строго по числовому EventIndex (не лексикографически)
    df = df.sort_values(["ProcessInstanceId", "EventIndex"]).reset_index(drop=True)
    return df


def build_chains(df: pd.DataFrame) -> pd.Series:
    return df.groupby("ProcessInstanceId")["ActivityName"].apply(list)


def extract_transitions(chains: pd.Series) -> Counter:
    trans = Counter()
    for seq in chains:
        for a, b in zip(seq, seq[1:]):
            trans[(a, b)] += 1
    return trans


def build_variants(chains: pd.Series) -> pd.DataFrame:
    total = len(chains)
    routes = chains.apply(lambda s: " > ".join(s))
    vc = routes.value_counts()
    rows = []
    for i, (route, cnt) in enumerate(vc.items(), 1):
        rows.append({"Variant": f"V{i}", "Route": route,
                      "NumberOfCases": cnt, "Share": round(cnt / total, 3)})
    return pd.DataFrame(rows)


def check_amount_threshold(df: pd.DataFrame):
    """Проверка: 'Дополнительное согласование' встречается <=> Amount >= 150000,
    среди экземпляров, дошедших до 'Проверка бюджета'."""
    amt = df.groupby("ProcessInstanceId")["Amount"].first()
    acts = df.groupby("ProcessInstanceId")["ActivityName"].apply(set)
    reached_budget = acts.apply(lambda s: "Проверка бюджета" in s)
    has_extra = acts.apply(lambda s: "Дополнительное согласование" in s)
    res = pd.DataFrame({"amount": amt, "has_extra": has_extra})[reached_budget]
    below = res[res.amount < 150000]["has_extra"]
    above = res[res.amount >= 150000]["has_extra"]
    assert below.sum() == 0, "Найдены случаи доп. согласования при Amount < 150000"
    assert (~above).sum() == 0, "Найдены случаи БЕЗ доп. согласования при Amount >= 150000"
    print(f"Порог подтверждён: ниже 150000 ({len(below)} случаев) — "
          f"доп. согласования нет; от 150000 и выше ({len(above)} случаев) — всегда есть.")


def check_result_routing(df: pd.DataFrame):
    """Проверка строгого соответствия Result -> следующая активность
    для 'Первичная проверка' и 'Согласование руководителем'."""
    g = df.groupby("ProcessInstanceId")
    mapping_manager = {"accept": "Проверка бюджета", "return": "Доработка заявки",
                        "reject": "Заявка отклонена", "cancel": "Заявка отменена"}
    for pid, d in g:
        d = d.reset_index(drop=True)
        sr = d[d.ActivityName == "Согласование руководителем"]
        for _, row in sr.iterrows():
            nxt = d[d.EventIndex == row.EventIndex + 1]
            if len(nxt) == 0:
                continue
            expected = mapping_manager[row["Result"]]
            actual = nxt.iloc[0]["ActivityName"]
            assert actual == expected, (pid, row["Result"], actual)
        pv = d[d.ActivityName == "Первичная проверка"]
        if (pv["Result"] == "reject").any():
            rej_idx = pv[pv.Result == "reject"]["EventIndex"].max()
            nxt = d[d.EventIndex == rej_idx + 1]
            assert nxt.iloc[0]["ActivityName"] == "Заявка отклонена"
    print("Соответствие Result -> следующая активность подтверждено на всех 1000 экземплярах.")


def main(path: str):
    df = load_log(path)
    chains = build_chains(df)
    print(f"Экземпляров: {len(chains)}, событий: {len(df)}")

    trans = extract_transitions(chains)
    print("\nПереходы (отсортированы по частоте):")
    for (a, b), c in sorted(trans.items(), key=lambda kv: -kv[1]):
        print(f"  {c:5d}  {a} -> {b}")

    variants = build_variants(chains)
    print(f"\nУникальных вариантов маршрута: {len(variants)} "
          f"(покрывают {variants.NumberOfCases.sum()} из {len(chains)} экземпляров)")

    check_amount_threshold(df)
    check_result_routing(df)

    order = ["Регистрация заявки", "Первичная проверка", "Согласование руководителем",
             "Доработка заявки", "Проверка бюджета", "Дополнительное согласование",
             "Исполнение закупки", "Заявка выполнена", "Заявка отклонена", "Заявка отменена"]
    rows = sorted(trans.items(), key=lambda kv: (order.index(kv[0][0]), order.index(kv[0][1])))
    with open("student_transitions.csv", "w", encoding="utf-8", newline="") as f:
        f.write("SourceActivity,TargetActivity\n")
        for (a, b), _ in rows:
            f.write(f'"{a}","{b}"\n')

    variants.to_csv("variants.csv", index=False, encoding="utf-8")
    print("\nСохранено: student_transitions.csv, variants.csv")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "students.csv"
    main(path)
