"""Initial migration"""

from alembic import op
import sqlalchemy as sa


revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tg_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('total_kg', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('last_dig_time', sa.Float(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False, server_default=sa.text('EXTRACT(EPOCH FROM NOW())')),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('tg_id'),
    )
    op.create_table(
        'dig_history',
        sa.Column('dig_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kg', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('dig_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    )
    op.create_index('idx_dig_history_user_timestamp', 'dig_history', ['user_id', sa.text('timestamp DESC')], unique=False)
    op.create_index('idx_dig_history_timestamp', 'dig_history', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_dig_history_timestamp', table_name='dig_history')
    op.drop_index('idx_dig_history_user_timestamp', table_name='dig_history')
    op.drop_table('dig_history')
    op.drop_table('users')