"""stage3 conversations orders agent runs

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02 11:17:39.360455
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('conversations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('shop_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('guest_session_id', sa.String(length=64), nullable=True),
    sa.Column('language', sa.String(length=16), nullable=True),
    sa.Column('script', sa.String(length=16), nullable=True),
    sa.Column('status', sa.Enum('open', 'closed', name='conversation_status'), server_default='open', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversations_customer_id'), 'conversations', ['customer_id'], unique=False)
    op.create_index(op.f('ix_conversations_guest_session_id'), 'conversations', ['guest_session_id'], unique=False)
    op.create_index(op.f('ix_conversations_shop_id'), 'conversations', ['shop_id'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=False),
    sa.Column('sender', sa.Enum('customer', 'bot', 'shopkeeper', 'system', name='message_sender'), nullable=False),
    sa.Column('type', sa.Enum('text', 'audio', 'image', 'system', 'bill', name='message_type'), server_default='text', nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('media_url', sa.Text(), nullable=True),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_messages_conversation_id_id', 'messages', ['conversation_id', 'id'], unique=False)
    op.create_table('orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('shop_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('conversation_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('draft', 'needs_clarification', 'awaiting_confirmation', 'confirmed', 'packing', 'out_for_delivery', 'delivered', 'cancelled', name='order_status'), server_default='draft', nullable=False),
    sa.Column('requires_reapproval', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('address_id', sa.Integer(), nullable=True),
    sa.Column('delivery_address_text', sa.Text(), nullable=True),
    sa.Column('delivery_lat', sa.Float(), nullable=True),
    sa.Column('delivery_lng', sa.Float(), nullable=True),
    sa.Column('distance_km', sa.Numeric(precision=6, scale=2), nullable=True),
    sa.Column('requested_delivery_text', sa.Text(), nullable=True),
    sa.Column('requested_delivery_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('subtotal', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
    sa.Column('discount', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
    sa.Column('delivery_fee', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
    sa.Column('total', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
    sa.Column('payment_method', sa.Enum('cod', 'upi', 'razorpay', name='payment_method'), nullable=True),
    sa.Column('payment_status', sa.Enum('pending', 'paid', 'cod', name='payment_status'), nullable=True),
    sa.Column('quoted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['address_id'], ['customer_addresses.id'], ),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_conversation_id'), 'orders', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_orders_shop_id'), 'orders', ['shop_id'], unique=False)
    op.create_table('agent_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('message_id', sa.Integer(), nullable=True),
    sa.Column('agent', sa.Enum('intake', 'parser', 'matcher', 'inventory', 'clarifier', 'billing', 'messaging', 'stt', 'ocr', 'explainer', name='agent_name'), nullable=False),
    sa.Column('status', sa.Enum('running', 'success', 'error', 'skipped', name='agent_status'), nullable=False),
    sa.Column('input', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_agent_runs_conversation_id_id', 'agent_runs', ['conversation_id', 'id'], unique=False)
    op.create_table('order_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('name_guess', sa.String(length=160), nullable=False),
    sa.Column('quantity_value', sa.Numeric(precision=10, scale=3), nullable=True),
    sa.Column('unit', sa.String(length=16), nullable=True),
    sa.Column('normalized_qty', sa.Numeric(precision=10, scale=3), nullable=True),
    sa.Column('product_qty', sa.Numeric(precision=10, scale=3), nullable=True),
    sa.Column('unit_price_snapshot', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('line_total', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('confidence', sa.Numeric(precision=3, scale=2), server_default='0', nullable=False),
    sa.Column('status', sa.Enum('matched', 'ambiguous', 'out_of_stock', 'unmatched', 'vague_qty', 'removed', 'substituted', 'pending_amendment', name='order_item_status'), nullable=False),
    sa.Column('candidates', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_span', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_table('clarifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('order_item_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('ambiguous_product', 'pack_size', 'out_of_stock', 'unmatched', 'vague_qty', 'unusual_qty', 'price_change', name='clarification_kind'), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clarifications_order_id'), 'clarifications', ['order_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_clarifications_order_id'), table_name='clarifications')
    op.drop_table('clarifications')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index('ix_agent_runs_conversation_id_id', table_name='agent_runs')
    op.drop_table('agent_runs')
    op.drop_index(op.f('ix_orders_shop_id'), table_name='orders')
    op.drop_index(op.f('ix_orders_conversation_id'), table_name='orders')
    op.drop_table('orders')
    op.drop_index('ix_messages_conversation_id_id', table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_conversations_shop_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_guest_session_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_customer_id'), table_name='conversations')
    op.drop_table('conversations')
    # ### end Alembic commands ###
    for enum_name in ('clarification_kind', 'order_item_status', 'agent_status', 'agent_name', 'payment_status',
                      'payment_method', 'order_status', 'message_type', 'message_sender', 'conversation_status'):
        op.execute(f'DROP TYPE IF EXISTS {enum_name}')
