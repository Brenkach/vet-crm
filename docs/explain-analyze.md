# EXPLAIN ANALYZE: плани запитів до і після оптимізації (ЛР №7)

Згенеровано: 2026-11-22 11:14 UTC, PostgreSQL 16.15, скрипт `python -m app.explain`.

Тестові дані (у транзакції, яку скасовано після аналізу): 2000 користувачів, 8000 тварин, 200000 записів на прийом, з них 10000 запланованих. Для кожного запиту наведено найкращий час із трьох прогонів.

## Підсумок

| Запит | ДО, мс | ПІСЛЯ, мс | Результат |
|---|---:|---:|---|
| Кількість запланованих прийомів (статистика адміна) | 6.43 | 1.32 | у 4.9 раза швидше |
| Уся статистика адміна (один запит із чотирма підзапитами) | 17.44 | 12.11 | у 1.4 раза швидше |
| `GET /pets` клієнта | 0.03 (2 запити) | 0.01 (1 запит) | зайвий запит прибрано |
| `GET /appointments` клієнта | 0.04 | 0.04 | вже оптимальний, змін не потребує |
| `GET /appointments` клієнта зі складеним індексом (pet_id, scheduled_at) | 0.04 | 0.04 | без суттєвої різниці — індекс відхилено |

## 1. Кількість запланованих прийомів: частковий індекс

Без індексу PostgreSQL переглядає всю таблицю (`Seq Scan`) і відкидає ~95% рядків фільтром. Частковий індекс `ix_appointments_scheduled` містить лише заплановані прийоми, тож запит читає тільки потрібні рядки (`Bitmap Index Scan`).

**ДО (без індексу)**

```sql
SELECT count(*) FROM appointments WHERE status = 'scheduled'
```

```
Aggregate  (cost=4395.77..4395.78 rows=1 width=8) (actual time=6.467..6.467 rows=1 loops=1)
  Buffers: shared hit=1870
  ->  Seq Scan on appointments  (cost=0.00..4370.00 rows=10307 width=0) (actual time=0.002..6.219 rows=10000 loops=1)
        Filter: ((status)::text = 'scheduled'::text)
        Rows Removed by Filter: 190000
        Buffers: shared hit=1870
Planning Time: 0.010 ms
Execution Time: 6.469 ms
```

**ПІСЛЯ (з індексом ix_appointments_scheduled)**

```sql
SELECT count(*) FROM appointments WHERE status = 'scheduled'
```

```
Aggregate  (cost=2120.24..2120.25 rows=1 width=8) (actual time=1.309..1.309 rows=1 loops=1)
  Buffers: shared hit=1881
  ->  Bitmap Heap Scan on appointments  (cost=100.64..2095.31 rows=9973 width=0) (actual time=0.328..1.079 rows=10000 loops=1)
        Recheck Cond: ((status)::text = 'scheduled'::text)
        Heap Blocks: exact=1870
        Buffers: shared hit=1881
        ->  Bitmap Index Scan on ix_appointments_scheduled  (cost=0.00..98.15 rows=9973 width=0) (actual time=0.245..0.245 rows=10000 loops=1)
              Buffers: shared hit=11
Planning Time: 0.011 ms
Execution Time: 1.325 ms
```

## 2. Статистика адміністратора одним запитом

**ДО (без індексу)**

```sql
SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM pets) AS pets, (SELECT count(*) FROM appointments) AS appointments, (SELECT count(*) FROM appointments WHERE status = 'scheduled') AS scheduled_appointments
```

```
Result  (cost=8964.81..8964.82 rows=1 width=32) (actual time=17.422..17.423 rows=1 loops=1)
  Buffers: shared hit=3814
  InitPlan 1 (returns $0)
    ->  Aggregate  (cost=48.00..48.01 rows=1 width=8) (actual time=0.109..0.109 rows=1 loops=1)
          Buffers: shared hit=23
          ->  Seq Scan on users  (cost=0.00..43.00 rows=2000 width=0) (actual time=0.001..0.063 rows=2000 loops=1)
                Buffers: shared hit=23
  InitPlan 2 (returns $1)
    ->  Aggregate  (cost=151.00..151.01 rows=1 width=8) (actual time=0.413..0.413 rows=1 loops=1)
          Buffers: shared hit=51
          ->  Seq Scan on pets  (cost=0.00..131.00 rows=8000 width=0) (actual time=0.001..0.230 rows=8000 loops=1)
                Buffers: shared hit=51
  InitPlan 3 (returns $2)
    ->  Aggregate  (cost=4370.00..4370.01 rows=1 width=8) (actual time=10.483..10.484 rows=1 loops=1)
          Buffers: shared hit=1870
          ->  Seq Scan on appointments  (cost=0.00..3870.00 rows=200000 width=0) (actual time=0.001..5.964 rows=200000 loops=1)
                Buffers: shared hit=1870
  InitPlan 4 (returns $3)
    ->  Aggregate  (cost=4395.77..4395.78 rows=1 width=8) (actual time=6.416..6.416 rows=1 loops=1)
          Buffers: shared hit=1870
          ->  Seq Scan on appointments appointments_1  (cost=0.00..4370.00 rows=10307 width=0) (actual time=0.002..6.160 rows=10000 loops=1)
                Filter: ((status)::text = 'scheduled'::text)
                Rows Removed by Filter: 190000
                Buffers: shared hit=1870
Planning Time: 0.020 ms
Execution Time: 17.437 ms
```

**ПІСЛЯ (з індексом)**

```sql
SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM pets) AS pets, (SELECT count(*) FROM appointments) AS appointments, (SELECT count(*) FROM appointments WHERE status = 'scheduled') AS scheduled_appointments
```

```
Result  (cost=6689.28..6689.29 rows=1 width=32) (actual time=12.082..12.083 rows=1 loops=1)
  Buffers: shared hit=3825
  InitPlan 1 (returns $0)
    ->  Aggregate  (cost=48.00..48.01 rows=1 width=8) (actual time=0.106..0.106 rows=1 loops=1)
          Buffers: shared hit=23
          ->  Seq Scan on users  (cost=0.00..43.00 rows=2000 width=0) (actual time=0.001..0.064 rows=2000 loops=1)
                Buffers: shared hit=23
  InitPlan 2 (returns $1)
    ->  Aggregate  (cost=151.00..151.01 rows=1 width=8) (actual time=0.422..0.422 rows=1 loops=1)
          Buffers: shared hit=51
          ->  Seq Scan on pets  (cost=0.00..131.00 rows=8000 width=0) (actual time=0.001..0.242 rows=8000 loops=1)
                Buffers: shared hit=51
  InitPlan 3 (returns $2)
    ->  Aggregate  (cost=4370.00..4370.01 rows=1 width=8) (actual time=10.276..10.276 rows=1 loops=1)
          Buffers: shared hit=1870
          ->  Seq Scan on appointments  (cost=0.00..3870.00 rows=200000 width=0) (actual time=0.001..6.029 rows=200000 loops=1)
                Buffers: shared hit=1870
  InitPlan 4 (returns $3)
    ->  Aggregate  (cost=2120.24..2120.25 rows=1 width=8) (actual time=1.277..1.277 rows=1 loops=1)
          Buffers: shared hit=1881
          ->  Bitmap Heap Scan on appointments appointments_1  (cost=100.64..2095.31 rows=9973 width=0) (actual time=0.298..1.054 rows=10000 loops=1)
                Recheck Cond: ((status)::text = 'scheduled'::text)
                Heap Blocks: exact=1870
                Buffers: shared hit=1881
                ->  Bitmap Index Scan on ix_appointments_scheduled  (cost=0.00..98.15 rows=9973 width=0) (actual time=0.232..0.232 rows=10000 loops=1)
                      Buffers: shared hit=11
Planning Time: 0.028 ms
Execution Time: 12.110 ms
```

## 3. `GET /pets`: зайвий запит, який генерувало `lazy="selectin"`

До ЛР №7 кожне завантаження тварин автоматично тягнуло всі їхні записи на прийом, хоча відповідь API їх не містить. Нижче — цей зайвий запит. Після оптимізації він не виконується взагалі.

**Запит, що виконується (і до, і після)**

```sql
SELECT pets.* FROM pets WHERE pets.owner_id = :owner ORDER BY pets.id
```

```
Sort  (cost=8.39..8.40 rows=4 width=243) (actual time=0.006..0.006 rows=4 loops=1)
  Sort Key: id
  Sort Method: quicksort  Memory: 25kB
  Buffers: shared hit=3
  ->  Index Scan using ix_pets_owner_id on pets  (cost=0.28..8.35 rows=4 width=243) (actual time=0.003..0.003 rows=4 loops=1)
        Index Cond: (owner_id = 1000)
        Buffers: shared hit=3
Planning Time: 0.008 ms
Execution Time: 0.010 ms
```

**Зайвий запит, що виконувався лише ДО оптимізації**

```sql
SELECT appointments.* FROM appointments WHERE appointments.pet_id IN (SELECT id FROM pets WHERE owner_id = :owner)
```

```
Nested Loop  (cost=0.58..44.28 rows=100 width=45) (actual time=0.010..0.021 rows=100 loops=1)
  Buffers: shared hit=16
  ->  Index Scan using ix_pets_owner_id on pets  (cost=0.28..8.35 rows=4 width=4) (actual time=0.003..0.003 rows=4 loops=1)
        Index Cond: (owner_id = 1000)
        Buffers: shared hit=3
  ->  Index Scan using ix_appointments_pet_id on appointments  (cost=0.29..8.73 rows=25 width=45) (actual time=0.002..0.003 rows=25 loops=4)
        Index Cond: (pet_id = pets.id)
        Buffers: shared hit=13
Planning:
  Buffers: shared hit=12
Planning Time: 0.046 ms
Execution Time: 0.027 ms
```

## 4. `GET /appointments`: перевірений, але відхилений індекс

Запит уже використовує наявні індекси `ix_pets_owner_id` і `ix_appointments_pet_id` (`Nested Loop` з `Index Scan`). Складений індекс `(pet_id, scheduled_at)` перевірено, але він не дає виграшу, а кожен індекс уповільнює вставку, тому його не додано.

**Поточний план**

```sql
SELECT appointments.* FROM appointments JOIN pets ON pets.id = appointments.pet_id WHERE pets.owner_id = :owner ORDER BY appointments.scheduled_at
```

```
Sort  (cost=47.60..47.85 rows=100 width=45) (actual time=0.026..0.028 rows=100 loops=1)
  Sort Key: appointments.scheduled_at
  Sort Method: quicksort  Memory: 32kB
  Buffers: shared hit=16
  ->  Nested Loop  (cost=0.58..44.28 rows=100 width=45) (actual time=0.006..0.017 rows=100 loops=1)
        Buffers: shared hit=16
        ->  Index Scan using ix_pets_owner_id on pets  (cost=0.28..8.35 rows=4 width=4) (actual time=0.003..0.003 rows=4 loops=1)
              Index Cond: (owner_id = 1000)
              Buffers: shared hit=3
        ->  Index Scan using ix_appointments_pet_id on appointments  (cost=0.29..8.73 rows=25 width=45) (actual time=0.001..0.002 rows=25 loops=4)
              Index Cond: (pet_id = pets.id)
              Buffers: shared hit=13
Planning:
  Buffers: shared hit=12
Planning Time: 0.051 ms
Execution Time: 0.036 ms
```

**Зі складеним індексом (pet_id, scheduled_at)**

```sql
SELECT appointments.* FROM appointments JOIN pets ON pets.id = appointments.pet_id WHERE pets.owner_id = :owner ORDER BY appointments.scheduled_at
```

```
Sort  (cost=47.60..47.85 rows=100 width=45) (actual time=0.031..0.033 rows=100 loops=1)
  Sort Key: appointments.scheduled_at
  Sort Method: quicksort  Memory: 32kB
  Buffers: shared hit=16
  ->  Nested Loop  (cost=0.58..44.28 rows=100 width=45) (actual time=0.007..0.019 rows=100 loops=1)
        Buffers: shared hit=16
        ->  Index Scan using ix_pets_owner_id on pets  (cost=0.28..8.35 rows=4 width=4) (actual time=0.003..0.004 rows=4 loops=1)
              Index Cond: (owner_id = 1000)
              Buffers: shared hit=3
        ->  Index Scan using ix_appointments_pet_id on appointments  (cost=0.29..8.73 rows=25 width=45) (actual time=0.001..0.002 rows=25 loops=4)
              Index Cond: (pet_id = pets.id)
              Buffers: shared hit=13
Planning:
  Buffers: shared hit=14
Planning Time: 0.076 ms
Execution Time: 0.043 ms
```
