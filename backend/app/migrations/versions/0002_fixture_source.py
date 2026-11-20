"""Add provider identity to fixtures."""
from alembic import op
import sqlalchemy as sa

revision = "0002_fixture_source"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("fixtures")}
    if "source" not in columns:
        op.add_column("fixtures", sa.Column("source", sa.String(length=40), nullable=False, server_default="manual"))
    if "external_id" not in columns:
        op.add_column("fixtures", sa.Column("external_id", sa.String(length=80), nullable=True))
    constraints = {item["name"] for item in sa.inspect(bind).get_unique_constraints("fixtures")}
    if "uq_fixture_source_external_id" not in constraints:
        op.create_unique_constraint("uq_fixture_source_external_id", "fixtures", ["source", "external_id"])

def downgrade():
    constraints = {item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints("fixtures")}
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("fixtures")}
    if "uq_fixture_source_external_id" in constraints:
        op.drop_constraint("uq_fixture_source_external_id", "fixtures", type_="unique")
    if "external_id" in columns:
        op.drop_column("fixtures", "external_id")
    if "source" in columns:
        op.drop_column("fixtures", "source")
