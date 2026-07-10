"""initial schema: users, verification_codes, posture_assessments

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-10

忠实反映 app.auth.models 和 app.posture.models 中的 Base.metadata：
- users
- verification_codes
- posture_assessments

使用 PostgreSQL UUID 和 JSONB 类型。
包含主键、外键、唯一索引（users.phone）、索引、nullable、字段长度和时间默认值。
downgrade 按依赖反序删除索引与表。

说明：ORM 的 User.phone 使用 unique=True + index=True，metadata 只生成唯一索引
``ix_users_phone``，没有独立的 UniqueConstraint。因此这里不生成 UNIQUE (phone) 约束，
仅创建唯一索引，以忠实反映模型。

说明：模型中 ``membership_level`` 和 ``used`` 使用 Python 端 default（ORM 层写入），
未声明 server_default，因此这里不为其生成 DDL DEFAULT，以忠实反映当前模型行为。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("nickname", sa.String(length=50), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("membership_level", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # users.phone 的唯一性由唯一索引 ix_users_phone 提供（对应 ORM unique=True+index=True），
    # 不额外生成表级 UniqueConstraint。
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)

    # --- verification_codes ---
    op.create_table(
        "verification_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_verification_codes_phone"),
        "verification_codes",
        ["phone"],
        unique=False,
    )

    # --- posture_assessments ---
    op.create_table(
        "posture_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", sa.String(length=20), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("self_test_answers", postgresql.JSONB(), nullable=True),
        sa.Column("ai_response", postgresql.JSONB(), nullable=True),
        sa.Column("photo_keys", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_posture_assessments_user_id"),
        "posture_assessments",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    # 按依赖反序删除：先删子表及其索引，再删父表。
    op.drop_index(
        op.f("ix_posture_assessments_user_id"),
        table_name="posture_assessments",
    )
    op.drop_table("posture_assessments")

    op.drop_index(
        op.f("ix_verification_codes_phone"),
        table_name="verification_codes",
    )
    op.drop_table("verification_codes")

    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_table("users")
