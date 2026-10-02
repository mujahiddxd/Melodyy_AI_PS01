"""stage4 order status events

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-02 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

# the enum already exists (created with `orders`): reuse it, never create it again
order_status = postgresql.ENUM(name='order_status', create_type=False)


def upgrade() -> None:
    op.create_table('order_status_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('from_status', order_status, nullable=True),
    sa.Column('to_status', order_status, nullable=False),
    sa.Column('actor', sa.Enum('customer', 'shopkeeper', 'system', name='status_actor'), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_status_events_order_id'), 'order_status_events', ['order_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_order_status_events_order_id'), table_name='order_status_events')
    op.drop_table('order_status_events')
    sa.Enum(name='status_actor').drop(op.get_bind(), checkfirst=True)
