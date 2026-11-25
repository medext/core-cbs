"""Postings may only be added to a journal entry inside the database transaction that created
it (ledger review C2: no appending a balanced pair to an already-committed entry).

``created_txid`` records txid_current() — the top-level transaction id, identical inside
savepoints — and the posting-shape trigger compares it with the inserting transaction.
Rollback strategy: reverse SQL restores the 0002 trigger function and drops the column
(the column carries no financial value; dropping it loses only the guard)."""

from django.db import migrations

FORWARD = r"""
ALTER TABLE ledger_journal_entry
  ADD COLUMN IF NOT EXISTS created_txid bigint NOT NULL DEFAULT txid_current();

CREATE OR REPLACE FUNCTION ledger_posting_shape() RETURNS trigger AS $$
DECLARE
  b_currency char(3);
  b_tenant uuid;
  e_tenant uuid;
  e_txid bigint;
BEGIN
  SELECT currency, tenant_id INTO b_currency, b_tenant FROM ledger_balance WHERE id = NEW.balance_id;
  SELECT tenant_id, created_txid INTO e_tenant, e_txid FROM ledger_journal_entry WHERE id = NEW.entry_id;
  IF b_currency IS DISTINCT FROM NEW.currency THEN
    RAISE EXCEPTION 'posting currency % does not match balance currency %', NEW.currency, b_currency
      USING ERRCODE = 'check_violation';
  END IF;
  IF b_tenant IS DISTINCT FROM NEW.tenant_id OR e_tenant IS DISTINCT FROM NEW.tenant_id THEN
    RAISE EXCEPTION 'posting tenant does not match its entry/balance tenant'
      USING ERRCODE = 'check_violation';
  END IF;
  IF e_txid IS DISTINCT FROM txid_current() THEN
    RAISE EXCEPTION 'postings can only be added to an entry within the transaction that created it'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
"""

REVERSE = r"""
CREATE OR REPLACE FUNCTION ledger_posting_shape() RETURNS trigger AS $$
DECLARE
  b_currency char(3);
  b_tenant uuid;
  e_tenant uuid;
BEGIN
  SELECT currency, tenant_id INTO b_currency, b_tenant FROM ledger_balance WHERE id = NEW.balance_id;
  SELECT tenant_id INTO e_tenant FROM ledger_journal_entry WHERE id = NEW.entry_id;
  IF b_currency IS DISTINCT FROM NEW.currency THEN
    RAISE EXCEPTION 'posting currency % does not match balance currency %', NEW.currency, b_currency
      USING ERRCODE = 'check_violation';
  END IF;
  IF b_tenant IS DISTINCT FROM NEW.tenant_id OR e_tenant IS DISTINCT FROM NEW.tenant_id THEN
    RAISE EXCEPTION 'posting tenant does not match its entry/balance tenant'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
ALTER TABLE ledger_journal_entry DROP COLUMN IF EXISTS created_txid;
"""


class Migration(migrations.Migration):
    dependencies = [("ledger", "0002_ledger_db_enforcement")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
