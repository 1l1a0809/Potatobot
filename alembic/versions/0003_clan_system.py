"""Add clan system tables"""

from alembic import op
import sqlalchemy as sa


revision = '0003_clan_system'
down_revision = '0002_partition_dig_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clans table
    op.create_table(
        'clans',
        sa.Column('clan_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('tag', sa.Text(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('total_kg', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('member_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('clan_id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('tag'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.user_id'], ondelete='CASCADE'),
    )
    op.create_index('idx_clans_total_kg', 'clans', ['total_kg'], unique=False)

    # Clan members table
    op.create_table(
        'clan_members',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('clan_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False, server_default='member'),
        sa.Column('joined_at', sa.Float(), nullable=False),
        sa.Column('contributed_kg', sa.Float(), nullable=False, server_default='0.0'),
        sa.PrimaryKeyConstraint('user_id', 'clan_id'),
        sa.ForeignKeyConstraint(['clan_id'], ['clans.clan_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.CheckConstraint("role IN ('owner', 'officer', 'member')", name='valid_role'),
    )
    op.create_index('idx_clan_members_clan_id', 'clan_members', ['clan_id'], unique=False)

    # Clan invites table
    op.create_table(
        'clan_invites',
        sa.Column('invite_id', sa.Text(), nullable=False),
        sa.Column('clan_id', sa.Integer(), nullable=False),
        sa.Column('inviter_id', sa.Integer(), nullable=False),
        sa.Column('invitee_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('invite_id'),
        sa.ForeignKeyConstraint(['clan_id'], ['clans.clan_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['inviter_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invitee_id'], ['users.user_id'], ondelete='CASCADE'),
    )
    op.create_index('idx_clan_invites_invitee', 'clan_invites', ['invitee_id'], unique=False)
    op.create_index('idx_clan_invites_expires', 'clan_invites', ['expires_at'], unique=False)

    # Add clan_id to users table
    op.add_column('users', sa.Column('clan_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_users_clan_id', 'users', 'clans', ['clan_id'], ['clan_id'], ondelete='SET NULL')
    op.create_index('idx_users_clan_id', 'users', ['clan_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_users_clan_id', table_name='users')
    op.drop_constraint('fk_users_clan_id', 'users', type_='foreignkey')
    op.drop_column('users', 'clan_id')

    op.drop_index('idx_clan_invites_expires', table_name='clan_invites')
    op.drop_index('idx_clan_invites_invitee', table_name='clan_invites')
    op.drop_table('clan_invites')

    op.drop_index('idx_clan_members_clan_id', table_name='clan_members')
    op.drop_table('clan_members')

    op.drop_index('idx_clans_total_kg', table_name='clans')
    op.drop_table('clans')