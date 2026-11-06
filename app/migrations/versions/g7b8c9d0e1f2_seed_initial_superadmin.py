"""Historical revision retained without automatic credential provisioning.

Use python -m app.scripts.create_superadmin for explicit operator provisioning.
The production-readiness migration disables any unrotated legacy seeded account.
"""

revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
