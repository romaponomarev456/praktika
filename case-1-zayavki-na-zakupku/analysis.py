"""
Воспроизводимый анализ аномалий в журнале заявок на закупку.
Запуск: python3 analysis.py  (students.csv должен лежать рядом)
Печатает сводки, на основе которых сформирован anomalies.csv.
Зависимости: pandas
"""
import pandas as pd

df = pd.read_csv('students.csv', encoding='utf-8-sig')
df['ts'] = pd.to_datetime(df.Timestamp)

# --- 1. Целостность данных ---
assert df.EventId.duplicated().sum() == 0, "есть дублирующиеся EventId"
for pid, g in df.groupby('ProcessInstanceId'):
    assert g.sort_values('EventIndex').ts.is_monotonic_increasing

# --- 2. Длительность заданий по (этап, тип заявки) ---
created = df[df.EventType == 'task_created'][
    ['ProcessInstanceId', 'TaskId', 'ActivityName', 'ts', 'RequestType']
].rename(columns={'ts': 'created_ts'})
completed = df[df.EventType == 'task_completed'][
    ['TaskId', 'ts', 'Role', 'Result']
].rename(columns={'ts': 'completed_ts'})
tasks = created.merge(completed, on='TaskId', how='left')
tasks['dur_min'] = (tasks.completed_ts - tasks.created_ts).dt.total_seconds() / 60
print(tasks.groupby(['ActivityName', 'RequestType']).dur_min.describe())

# --- 3. Роль vs этап ---
tc = df[df.EventType == 'task_completed']
print(pd.crosstab(tc.ActivityName, tc.Role))

# --- 4. Маршруты процессов ---
def route_str(g):
    g = g.sort_values('EventIndex')
    parts = []
    for _, r in g.iterrows():
        tag = r.ActivityName
        if r.EventType == 'task_completed':
            tag += f"[{r.Result}]"
        parts.append(tag)
    return ' > '.join(parts)

routes = df.sort_values(['ProcessInstanceId', 'EventIndex']) \
    .groupby('ProcessInstanceId').apply(route_str)
print('Уникальных маршрутов:', routes.nunique())
print(routes.value_counts())

# --- 5. Открытые процессы и их "зависание" ---
cutoff = pd.Timestamp('2026-07-01T00:00:00+03:00')
has_complete = set(df[df.EventType == 'process_completed'].ProcessInstanceId)
open_procs = set(df.ProcessInstanceId) - has_complete
last_rows = df.loc[df.groupby('ProcessInstanceId').ts.idxmax()]
stuck = last_rows[last_rows.ProcessInstanceId.isin(open_procs)].copy()
stuck['idle_days'] = (cutoff - stuck.ts).dt.total_seconds() / 86400
print(stuck[['ProcessInstanceId', 'ActivityName', 'idle_days']].sort_values('idle_days', ascending=False))

# Конкретные выборки (роль-несоответствие, пропуск этапа, порядок, циклы доработки,
# повтор проверки, быстрый маршрут) см. в пошаговых запросах отчёта report.md —
# логика идентична блокам выше, примененным с дополнительной фильтрацией.
