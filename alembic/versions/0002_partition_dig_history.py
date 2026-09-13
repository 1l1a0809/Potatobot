"""Partition dig_history table by month"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP


revision = '0002_partition_dig_history'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create partitioned table
    op.execute("""
        CREATE TABLE dig_history_partitioned (
            dig_id BIGSERIAL,
            user_id INTEGER NOT NULL,
            kg REAL NOT NULL,
            timestamp REAL NOT NULL
        ) PARTITION BY RANGE (timestamp);
    """)

    # Create indexes on partitioned table
    op.execute("""
        CREATE INDEX idx_dig_history_partitioned_user_timestamp
        ON dig_history_partitioned (user_id, timestamp DESC);
    """)
    op.execute("""
        CREATE INDEX idx_dig_history_partitioned_timestamp
        ON dig_history_partitioned (timestamp);
    """)

    # Create partitions for 2024-2026 (adjust as needed)
    # Each partition covers one month
    partitions = [
        ("2024_01", 1704067200, 1706745600),  # Jan 2024
        ("2024_02", 1706745600, 1709251200),  # Feb 2024
        ("2024_03", 1709251200, 1711929600),  # Mar 2024
        ("2024_04", 1711929600, 1714521600),  # Apr 2024
        ("2024_05", 1714521600, 1717200000),  # May 2024
        ("2024_06", 1717200000, 1719792000),  # Jun 2024
        ("2024_07", 1719792000, 1722470400),  # Jul 2024
        ("2024_08", 1722470400, 1725148800),  # Aug 2024
        ("2024_09", 1725148800, 1727740800),  # Sep 2024
        ("2024_10", 1727740800, 1730419200),  # Oct 2024
        ("2024_11", 1730419200, 1733011200),  # Nov 2024
        ("2024_12", 1733011200, 1735689600),  # Dec 2024
        ("2025_01", 1735689600, 1738368000),  # Jan 2025
        ("2025_02", 1738368000, 1740787200),  # Feb 2025
        ("2025_03", 1740787200, 1743465600),  # Mar 2025
        ("2025_04", 1743465600, 1746057600),  # Apr 2025
        ("2025_05", 1746057600, 1748736000),  # May 2025
        ("2025_06", 1748736000, 1751328000),  # Jun 2025
        ("2025_07", 1751328000, 1754006400),  # Jul 2025
        ("2025_08", 1754006400, 1756684800),  # Aug 2025
        ("2025_09", 1756684800, 1759276800),  # Sep 2025
        ("2025_10", 1759276800, 1761955200),  # Oct 2025
        ("2025_11", 1761955200, 1764547200),  # Nov 2025
        ("2025_12", 1764547200, 1767225600),  # Dec 2025
        ("2026_01", 1767225600, 1769904000),  # Jan 2026
        ("2026_02", 1769904000, 1772323200),  # Feb 2026
        ("2026_03", 1772323200, 1775001600),  # Mar 2026
        ("2026_04", 1775001600, 1777593600),  # Apr 2026
        ("2026_05", 1777593600, 1780272000),  # May 2026
        ("2026_06", 1780272000, 1782864000),  # Jun 2026
        ("2026_07", 1782864000, 1785542400),  # Jul 2026
        ("2026_08", 1785542400, 1788220800),  # Aug 2026
        ("2026_09", 1788220800, 1790812800),  # Sep 2026
        ("2026_10", 1790812800, 1793491200),  # Oct 2026
        ("2026_11", 1793491200, 1796083200),  # Nov 2026
        ("2026_12", 1796083200, 1798761600),  # Dec 2026
    ]

    for name, start_ts, end_ts in partitions:
        op.execute(f"""
            CREATE TABLE dig_history_{name} PARTITION OF dig_history_partitioned
            FOR VALUES FROM ({start_ts}) TO ({end_ts});
        """)

    # Create default partition for future dates
    op.execute("""
        CREATE TABLE dig_history_future PARTITION OF dig_history_partitioned
        FOR VALUES FROM (1798761600) TO (MAXVALUE);
    """)

    # Migrate data from old table to partitioned table
    op.execute("""
        INSERT INTO dig_history_partitioned (dig_id, user_id, kg, timestamp)
        SELECT dig_id, user_id, kg, timestamp FROM dig_history;
    """)

    # Drop old table and rename
    op.execute("DROP TABLE dig_history;")
    op.execute("ALTER TABLE dig_history_partitioned RENAME TO dig_history;")

    # Recreate foreign key
    op.execute("""
        ALTER TABLE dig_history
        ADD CONSTRAINT dig_history_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;
    """)


def downgrade() -> None:
    # Recreate non-partitioned table
    op.execute("""
        CREATE TABLE dig_history_old (
            dig_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
            kg REAL NOT NULL,
            timestamp REAL NOT NULL
        );
    """)

    # Migrate data back
    op.execute("""
        INSERT INTO dig_history_old (dig_id, user_id, kg, timestamp)
        SELECT dig_id, user_id, kg, timestamp FROM dig_history;
    """)

    # Drop partitioned table and rename
    op.execute("DROP TABLE dig_history;")
    op.execute("ALTER TABLE dig_history_old RENAME TO dig_history;")

    # Recreate indexes
    op.execute("""
        CREATE INDEX idx_dig_history_user_timestamp
        ON dig_history (user_id, timestamp DESC);
    """)
    op.execute("""
        CREATE INDEX idx_dig_history_timestamp
        ON dig_history (timestamp);
    """)