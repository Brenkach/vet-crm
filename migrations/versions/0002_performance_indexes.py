"""ЛР №7: частковий індекс для запланованих прийомів.

Статистика адміністратора рахує записи зі статусом 'scheduled'. Без індексу PostgreSQL
переглядає всю таблицю appointments (Seq Scan). Частковий індекс містить лише ~5% рядків
(заплановані прийоми), тому він маленький і дешевий в оновленні. Обґрунтування і плани
EXPLAIN ANALYZE до/після — у docs/performance.md і docs/explain-analyze.md.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WHERE = "status = 'scheduled'"


def upgrade() -> None:
    op.create_index(
        "ix_appointments_scheduled",
        "appointments",
        ["scheduled_at"],
        postgresql_where=sa.text(WHERE),
        sqlite_where=sa.text(WHERE),
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_scheduled", table_name="appointments")
