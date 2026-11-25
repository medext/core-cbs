"""created_txid cannot be supplied by the client: a BEFORE INSERT trigger forces it to the
inserting transaction's id (ledger review S-a). Rollback: drop trigger/function."""

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION ledger_entry_force_txid() RETURNS trigger AS $$
BEGIN
  NEW.created_txid := txid_current();
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_entry_force_txid
  BEFORE INSERT ON ledger_journal_entry
  FOR EACH ROW EXECUTE FUNCTION ledger_entry_force_txid();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS ledger_entry_force_txid ON ledger_journal_entry;
DROP FUNCTION IF EXISTS ledger_entry_force_txid();
"""


class Migration(migrations.Migration):
    dependencies = [("ledger", "0003_entry_txid_guard")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
