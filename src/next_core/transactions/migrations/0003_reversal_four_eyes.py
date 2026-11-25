"""Four-eyes backstop for reversals (security review H1): a REVERSAL transaction must be
initiated by a different principal than the transaction it reverses.

Rollback strategy: reverse SQL drops the trigger/function (schema only)."""

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION txn_reversal_four_eyes() RETURNS trigger AS $$
DECLARE
  original_initiator text;
BEGIN
  IF NEW.reversal_of_id IS NOT NULL THEN
    SELECT initiated_by INTO original_initiator FROM business_transaction
      WHERE id = NEW.reversal_of_id;
    IF original_initiator = NEW.initiated_by THEN
      RAISE EXCEPTION 'the initiator of a transaction cannot reverse it'
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER business_transaction_reversal_four_eyes
  BEFORE INSERT OR UPDATE OF reversal_of_id, initiated_by ON business_transaction
  FOR EACH ROW EXECUTE FUNCTION txn_reversal_four_eyes();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS business_transaction_reversal_four_eyes ON business_transaction;
DROP FUNCTION IF EXISTS txn_reversal_four_eyes();
"""


class Migration(migrations.Migration):
    dependencies = [("transactions", "0002_history_guards")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
