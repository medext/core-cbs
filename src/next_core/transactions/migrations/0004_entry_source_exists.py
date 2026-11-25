"""Invariant 15 at the database level (ledger review C1): a journal entry whose source_type is
TRANSACTION must reference an existing business transaction in the same tenant database.

The ledger kernel stays independent of this context (no ORM FK from ledger to
transactions); the coupling lives here, in the context that owns business transactions.
Rollback strategy: reverse SQL drops the trigger/function (schema only)."""

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION ledger_entry_source_exists() RETURNS trigger AS $$
BEGIN
  IF NEW.source_type = 'TRANSACTION' AND NOT EXISTS (
       SELECT 1 FROM business_transaction WHERE id = NEW.source_id AND tenant_id = NEW.tenant_id
     ) THEN
    RAISE EXCEPTION 'journal entry source transaction % does not exist', NEW.source_id
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_entry_source_exists
  BEFORE INSERT ON ledger_journal_entry
  FOR EACH ROW EXECUTE FUNCTION ledger_entry_source_exists();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS ledger_entry_source_exists ON ledger_journal_entry;
DROP FUNCTION IF EXISTS ledger_entry_source_exists();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("transactions", "0003_reversal_four_eyes"),
        ("ledger", "0003_entry_txid_guard"),
    ]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
