"""Product versions are immutable once they leave DRAFT (invariant 21).

Rollback strategy: reverse SQL drops the trigger/function (schema only, no data loss)."""

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION product_version_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'DRAFT' THEN
      RAISE EXCEPTION 'non-draft product versions cannot be deleted'
        USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status <> 'DRAFT' AND (NEW.definition IS DISTINCT FROM OLD.definition
       OR NEW.definition_hash IS DISTINCT FROM OLD.definition_hash
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.product_id IS DISTINCT FROM OLD.product_id) THEN
    RAISE EXCEPTION 'product version % is immutable once submitted', OLD.id
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF OLD.status IN ('ACTIVE', 'SUPERSEDED', 'RETIRED')
     AND (NEW.approved_by IS DISTINCT FROM OLD.approved_by
          OR NEW.submitted_by IS DISTINCT FROM OLD.submitted_by
          OR NEW.created_by IS DISTINCT FROM OLD.created_by) THEN
    RAISE EXCEPTION 'approval evidence of product version % is immutable', OLD.id
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER product_version_guard
  BEFORE UPDATE OR DELETE ON product_version
  FOR EACH ROW EXECUTE FUNCTION product_version_guard();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS product_version_guard ON product_version;
DROP FUNCTION IF EXISTS product_version_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("products", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
