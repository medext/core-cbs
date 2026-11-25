"""Database-level enforcement of the ledger invariants (the authority; app checks come first).

Invariants backed here: 1/2 (balanced per currency, deferred constraint trigger),
5/6 (append-only entries & postings), 8 (projection writes only through the posting-service
session flag; identity columns immutable; monotonic totals; version increments),
16 (posting currency == balance currency), 18 (available-funds floor backstop),
24 (integrity does not depend solely on application code).

Session flags (transaction-local, set with set_config(..., true)):
- ``next_core.ledger_writer = 'on'``  — set only by ledger.application.posting for the
  duration of a posting-service call; required for INSERT on entries/postings and UPDATE
  on balances. Any other write path fails loudly.
- ``next_core.allow_overdraw = 'on'`` — set by the posting service only for explicitly
  forced operations (reversals, policy changes); otherwise the funds floor applies.

Rollback strategy: reverse SQL drops the triggers/functions (schema-only; no data loss).
"""

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION ledger_require_writer() RETURNS trigger AS $$
BEGIN
  IF coalesce(current_setting('next_core.ledger_writer', true), '') <> 'on' THEN
    RAISE EXCEPTION 'ledger table % may only be written by the posting service', TG_TABLE_NAME
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION ledger_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'ledger table % is append-only (% refused)', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'restrict_violation';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_journal_entry_append_only
  BEFORE UPDATE OR DELETE ON ledger_journal_entry
  FOR EACH ROW EXECUTE FUNCTION ledger_append_only();
CREATE TRIGGER ledger_posting_append_only
  BEFORE UPDATE OR DELETE ON ledger_posting
  FOR EACH ROW EXECUTE FUNCTION ledger_append_only();
CREATE TRIGGER ledger_journal_entry_writer
  BEFORE INSERT ON ledger_journal_entry
  FOR EACH ROW EXECUTE FUNCTION ledger_require_writer();
CREATE TRIGGER ledger_posting_writer
  BEFORE INSERT ON ledger_posting
  FOR EACH ROW EXECUTE FUNCTION ledger_require_writer();

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

CREATE TRIGGER ledger_posting_currency
  BEFORE INSERT ON ledger_posting
  FOR EACH ROW EXECUTE FUNCTION ledger_posting_shape();

CREATE OR REPLACE FUNCTION ledger_check_entry_balanced() RETURNS trigger AS $$
DECLARE
  eid uuid;
  n integer;
  r record;
BEGIN
  IF TG_TABLE_NAME = 'ledger_posting' THEN
    eid := NEW.entry_id;
  ELSE
    eid := NEW.id;
  END IF;
  SELECT count(*) INTO n FROM ledger_posting WHERE entry_id = eid;
  IF n < 2 THEN
    RAISE EXCEPTION 'journal entry % has % posting(s); at least 2 are required', eid, n
      USING ERRCODE = 'check_violation';
  END IF;
  FOR r IN
    SELECT currency,
           sum(CASE WHEN direction = 'DEBIT' THEN amount ELSE 0 END) AS debits,
           sum(CASE WHEN direction = 'CREDIT' THEN amount ELSE 0 END) AS credits
      FROM ledger_posting WHERE entry_id = eid GROUP BY currency
  LOOP
    IF r.debits <> r.credits THEN
      RAISE EXCEPTION 'journal entry % unbalanced in %: debits % <> credits %',
        eid, r.currency, r.debits, r.credits USING ERRCODE = 'check_violation';
    END IF;
  END LOOP;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER ledger_entry_balanced_posting
  AFTER INSERT ON ledger_posting DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION ledger_check_entry_balanced();
CREATE CONSTRAINT TRIGGER ledger_entry_balanced_entry
  AFTER INSERT ON ledger_journal_entry DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION ledger_check_entry_balanced();

CREATE OR REPLACE FUNCTION ledger_balance_guard() RETURNS trigger AS $$
DECLARE
  old_avail bigint;
  new_avail bigint;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'ledger balances cannot be deleted' USING ERRCODE = 'restrict_violation';
  END IF;
  IF coalesce(current_setting('next_core.ledger_writer', true), '') <> 'on' THEN
    RAISE EXCEPTION 'ledger balances may only be written by the posting service'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id
     OR NEW.gl_account_id <> OLD.gl_account_id OR NEW.currency <> OLD.currency
     OR NEW.normal_side <> OLD.normal_side OR NEW.owner_type <> OLD.owner_type
     OR NEW.owner_id IS DISTINCT FROM OLD.owner_id OR NEW.purpose <> OLD.purpose THEN
    RAISE EXCEPTION 'ledger balance identity columns are immutable'
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.debit_total < OLD.debit_total OR NEW.credit_total < OLD.credit_total THEN
    RAISE EXCEPTION 'ledger balance totals are monotonic' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.version <> OLD.version + 1 THEN
    RAISE EXCEPTION 'ledger balance version must increment by exactly 1'
      USING ERRCODE = 'serialization_failure';
  END IF;
  IF NEW.funds_enforced THEN
    new_avail := NEW.book_balance - NEW.held_amount - NEW.pending_debit + NEW.overdraft_limit;
    old_avail := OLD.book_balance - OLD.held_amount - OLD.pending_debit + OLD.overdraft_limit;
    IF new_avail < 0 AND new_avail < old_avail
       AND coalesce(current_setting('next_core.allow_overdraw', true), '') <> 'on' THEN
      RAISE EXCEPTION 'available funds floor violated on balance %', NEW.id
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_balance_guard
  BEFORE UPDATE OR DELETE ON ledger_balance
  FOR EACH ROW EXECUTE FUNCTION ledger_balance_guard();

-- A balance is born empty: value can only arrive through postings.
CREATE OR REPLACE FUNCTION ledger_balance_born_empty() RETURNS trigger AS $$
BEGIN
  IF NEW.debit_total <> 0 OR NEW.credit_total <> 0 OR NEW.book_balance <> 0
     OR NEW.held_amount <> 0 OR NEW.pending_debit <> 0 OR NEW.pending_credit <> 0
     OR NEW.version <> 0 OR NEW.last_entry_seq <> 0 THEN
    RAISE EXCEPTION 'ledger balances must be created empty' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_balance_born_empty
  BEFORE INSERT ON ledger_balance
  FOR EACH ROW EXECUTE FUNCTION ledger_balance_born_empty();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS ledger_balance_born_empty ON ledger_balance;
DROP FUNCTION IF EXISTS ledger_balance_born_empty();
DROP TRIGGER IF EXISTS ledger_balance_guard ON ledger_balance;
DROP TRIGGER IF EXISTS ledger_entry_balanced_entry ON ledger_journal_entry;
DROP TRIGGER IF EXISTS ledger_entry_balanced_posting ON ledger_posting;
DROP TRIGGER IF EXISTS ledger_posting_currency ON ledger_posting;
DROP TRIGGER IF EXISTS ledger_posting_writer ON ledger_posting;
DROP TRIGGER IF EXISTS ledger_journal_entry_writer ON ledger_journal_entry;
DROP TRIGGER IF EXISTS ledger_posting_append_only ON ledger_posting;
DROP TRIGGER IF EXISTS ledger_journal_entry_append_only ON ledger_journal_entry;
DROP FUNCTION IF EXISTS ledger_balance_guard();
DROP FUNCTION IF EXISTS ledger_check_entry_balanced();
DROP FUNCTION IF EXISTS ledger_posting_shape();
DROP FUNCTION IF EXISTS ledger_append_only();
DROP FUNCTION IF EXISTS ledger_require_writer();
"""


class Migration(migrations.Migration):
    dependencies = [("ledger", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
