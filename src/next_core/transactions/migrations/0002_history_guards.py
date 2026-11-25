"""Append-only transition history; transactions/holds/idempotency records never deleted;
terminal transaction states are final (no transition out — lifecycle spec principle 4).

Rollback strategy: reverse SQL drops triggers/functions (schema only)."""

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION txn_no_delete() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% rows are never deleted', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER txn_transition_append_only BEFORE UPDATE OR DELETE ON txn_state_transition
  FOR EACH ROW EXECUTE FUNCTION txn_no_delete();
CREATE TRIGGER business_transaction_no_delete BEFORE DELETE ON business_transaction
  FOR EACH ROW EXECUTE FUNCTION txn_no_delete();
CREATE TRIGGER txn_hold_no_delete BEFORE DELETE ON txn_hold
  FOR EACH ROW EXECUTE FUNCTION txn_no_delete();
CREATE TRIGGER idempotency_record_no_delete BEFORE DELETE ON idempotency_record
  FOR EACH ROW EXECUTE FUNCTION txn_no_delete();

CREATE OR REPLACE FUNCTION txn_terminal_guard() RETURNS trigger AS $$
BEGIN
  IF OLD.state IN ('REJECTED', 'SETTLED', 'REVERSED', 'VOIDED', 'FAILED')
     AND NEW.state <> OLD.state THEN
    RAISE EXCEPTION 'transaction % is in terminal state %', OLD.id, OLD.state
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.amount_minor <> OLD.amount_minor OR NEW.currency <> OLD.currency
     OR NEW.type <> OLD.type THEN
    RAISE EXCEPTION 'transaction amount, currency and type are immutable'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER business_transaction_terminal_guard BEFORE UPDATE ON business_transaction
  FOR EACH ROW EXECUTE FUNCTION txn_terminal_guard();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS business_transaction_terminal_guard ON business_transaction;
DROP FUNCTION IF EXISTS txn_terminal_guard();
DROP TRIGGER IF EXISTS idempotency_record_no_delete ON idempotency_record;
DROP TRIGGER IF EXISTS txn_hold_no_delete ON txn_hold;
DROP TRIGGER IF EXISTS business_transaction_no_delete ON business_transaction;
DROP TRIGGER IF EXISTS txn_transition_append_only ON txn_state_transition;
DROP FUNCTION IF EXISTS txn_no_delete();
"""


class Migration(migrations.Migration):
    dependencies = [("transactions", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
