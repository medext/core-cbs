"""Per-tenant-database account number sequence; closure & history protections.

- ``account_number_seq``: monotonic source for account numbers (mod-97 check digits added
  in code). Each tenant database owns its own sequence.
- accounts cannot be deleted; a CLOSED account cannot be reopened; status history is
  append-only (invariant 20).

Rollback strategy: reverse SQL drops triggers, functions and the sequence (no account data
is touched)."""

from django.db import migrations

FORWARD = r"""
CREATE SEQUENCE IF NOT EXISTS account_number_seq START 1000;

CREATE OR REPLACE FUNCTION account_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'accounts are never deleted (close them instead)'
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF OLD.status = 'CLOSED' AND NEW.status <> 'CLOSED' THEN
    RAISE EXCEPTION 'a closed account cannot be reopened' USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.principal_balance_id <> OLD.principal_balance_id
     OR NEW.interest_balance_id IS DISTINCT FROM OLD.interest_balance_id
     OR NEW.product_version_id <> OLD.product_version_id
     OR NEW.currency <> OLD.currency OR NEW.number <> OLD.number
     OR NEW.party_id <> OLD.party_id THEN
    RAISE EXCEPTION 'account identity, ledger mapping and product version are immutable'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER account_guard BEFORE UPDATE OR DELETE ON account
  FOR EACH ROW EXECUTE FUNCTION account_guard();

CREATE OR REPLACE FUNCTION account_history_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'account status history is append-only' USING ERRCODE = 'restrict_violation';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER account_history_append_only BEFORE UPDATE OR DELETE ON account_status_change
  FOR EACH ROW EXECUTE FUNCTION account_history_append_only();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS account_history_append_only ON account_status_change;
DROP FUNCTION IF EXISTS account_history_append_only();
DROP TRIGGER IF EXISTS account_guard ON account;
DROP FUNCTION IF EXISTS account_guard();
DROP SEQUENCE IF EXISTS account_number_seq;
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
