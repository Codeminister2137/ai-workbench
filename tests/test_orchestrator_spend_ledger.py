"""Spend-ledger prototype: P5 spend order, reserve/settle, grant files."""

from __future__ import annotations

import json

import pytest
from ai_orchestrator.spend_ledger import (
    Allowance,
    AllowanceKind,
    PolicyRule,
    SpendLedger,
    allowance_fingerprint,
    allowance_from_file,
    policy_from_file,
)


def _ledger(
    clock_value: float = 1_700_000_000.0, rules: list[PolicyRule] | None = None
) -> SpendLedger:
    return SpendLedger(clock=lambda: clock_value, rules=rules)


def _allowance(
    allowance_id: str = "a1",
    kind: str = "allowance_expiring",
    granted_cents: int = 500,
    *,
    provider: str = "meta",
    expires_at: float | None = 1_800_000_000.0,
) -> Allowance:
    return Allowance(
        id=allowance_id,
        provider=provider,
        kind=kind,  # type: ignore[arg-type]
        balance_cents=granted_cents,
        granted_cents=granted_cents,
        granted_at=1_700_000_000.0,
        expires_at=expires_at,
    )


class TestSpendOrder:
    def test_free_bucket_spent_before_expiring(self):
        ledger = _ledger()
        ledger.add_allowance(_allowance("free", kind="free_daily"))
        ledger.add_allowance(_allowance("exp", kind="allowance_expiring"))
        admission = ledger.admit(
            task_id="t1", task_class="eval", estimated_cents=100, provider="meta"
        )
        assert admission.decision == "admitted"
        assert admission.allowance_id == "free"
        assert ledger.get_allowance("free").balance_cents == 400
        assert ledger.get_allowance("exp").balance_cents == 500

    def test_expiring_fifo_by_earliest_expiry(self):
        ledger = _ledger()
        ledger.add_allowance(_allowance("late", expires_at=1_900_000_000.0))
        ledger.add_allowance(_allowance("soon", expires_at=1_700_000_100.0))
        admission = ledger.admit(
            task_id="t1", task_class="eval", estimated_cents=100, provider="meta"
        )
        assert admission.decision == "admitted"
        assert admission.allowance_id == "soon"

    def test_prepaid_blocked_by_default(self):
        ledger = _ledger()
        ledger.add_allowance(_allowance("pp", kind="prepaid", expires_at=None))
        admission = ledger.admit(
            task_id="t1", task_class="eval", estimated_cents=100, provider="meta"
        )
        assert admission.decision == "deferred"
        assert admission.reason == "awaiting_prepaid_permission"

    def test_prepaid_admitted_with_explicit_rule(self):
        ledger = _ledger(rules=[PolicyRule(prepaid_allowed=True)])
        ledger.add_allowance(_allowance("pp", kind="prepaid", expires_at=None))
        admission = ledger.admit(
            task_id="t1", task_class="eval", estimated_cents=100, provider="meta"
        )
        assert admission.decision == "admitted"
        assert admission.allowance_id == "pp"

    def test_expired_allowance_is_skipped(self):
        ledger = _ledger(clock_value=1_900_000_000.0)
        ledger.add_allowance(_allowance("old", expires_at=1_800_000_000.0))
        admission = ledger.admit(
            task_id="t1", task_class="eval", estimated_cents=100, provider="meta"
        )
        assert admission.decision == "rejected"

    def test_zero_cost_local_call_needs_no_grant(self):
        ledger = _ledger()
        admission = ledger.admit(
            task_id="t1", task_class="local_run", estimated_cents=0, provider="ollama"
        )
        assert admission.decision == "admitted"
        assert admission.reservation is None
        record = ledger.settle_local(task_id="t1", task_class="local_run")
        assert record.actual_cents == 0
        assert len(ledger.records()) == 1


class TestReserveSettle:
    def test_settle_refunds_delta(self):
        ledger = _ledger()
        ledger.add_allowance(_allowance("exp"))
        admission = ledger.admit(
            task_id="t1", task_class="eval", estimated_cents=100, provider="meta"
        )
        assert admission.reservation is not None
        record = ledger.settle(
            admission.reservation.id, actual_cents=30, model_id="m1", duration_ms=5
        )
        assert record.estimated_cents == 100
        assert record.actual_cents == 30
        assert ledger.get_allowance("exp").balance_cents == 470

    def test_cancel_restores_full_estimate(self):
        ledger = _ledger()
        ledger.add_allowance(_allowance("exp"))
        admission = ledger.admit(
            task_id="t1", task_class="eval", estimated_cents=100, provider="meta"
        )
        assert admission.reservation is not None
        ledger.refund(admission.reservation.id)
        assert ledger.get_allowance("exp").balance_cents == 500

    def test_single_call_single_bucket_no_split(self):
        ledger = _ledger()
        ledger.add_allowance(_allowance("small", granted_cents=60))
        ledger.add_allowance(_allowance("big", granted_cents=500))
        admission = ledger.admit(
            task_id="t1", task_class="eval", estimated_cents=100, provider="meta"
        )
        assert admission.decision == "admitted"
        assert admission.allowance_id == "big"
        assert ledger.get_allowance("small").balance_cents == 60

    def test_settle_refuses_changed_grant(self):
        ledger = _ledger()
        ledger.add_allowance(_allowance("exp"))
        admission = ledger.admit(
            task_id="t1", task_class="eval", estimated_cents=100, provider="meta"
        )
        assert admission.reservation is not None
        tampered = _allowance("exp", granted_cents=999)
        object.__setattr__(ledger.get_allowance("exp"), "granted_cents", 999)
        assert allowance_fingerprint(tampered) != admission.reservation.allowance_fingerprint
        with pytest.raises(ValueError, match="Grant changed"):
            ledger.settle(admission.reservation.id, actual_cents=30)


class TestGrantFiles:
    def test_round_trip_explicit_grant(self, tmp_path):
        path = tmp_path / "grant.json"
        path.write_text(
            json.dumps(
                {
                    "allowance_id": "nov-evals",
                    "provider": "meta",
                    "kind": "allowance_expiring",
                    "granted_cents": 15000,
                    "expires_at": 1_800_000_000.0,
                    "local_spending_limit_accepted": True,
                }
            ),
            encoding="utf-8",
        )
        allowance = allowance_from_file(path)
        assert allowance.id == "nov-evals"
        assert allowance.balance_cents == 15000

    def test_legacy_grant_refused(self, tmp_path):
        path = tmp_path / "grant.json"
        path.write_text(json.dumps({"provider_spend_cap_verified": True}), encoding="utf-8")
        with pytest.raises(ValueError, match="Legacy"):
            allowance_from_file(path)

    def test_missing_acceptance_refused(self, tmp_path):
        path = tmp_path / "grant.json"
        path.write_text(
            json.dumps(
                {
                    "allowance_id": "x",
                    "provider": "meta",
                    "kind": "prepaid",
                    "granted_cents": 100,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="explicit acceptance"):
            allowance_from_file(path)

    def test_oversize_grant_refused(self, tmp_path):
        path = tmp_path / "grant.json"
        path.write_text(json.dumps({"blob": "x" * 9000}), encoding="utf-8")
        with pytest.raises(ValueError, match="exceeds 8192"):
            allowance_from_file(path)


def test_status_reports_spend_by_operation():
    ledger = _ledger()
    ledger.add_allowance(_allowance("exp", granted_cents=500))
    for task_id, task_class, estimate, actual in [
        ("s1", "stt:audio", 1, 1),
        ("s2", "stt:audio", 1, 1),
        ("e1", "eval", 100, 90),
    ]:
        admission = ledger.admit(
            task_id=task_id, task_class=task_class, estimated_cents=estimate, provider="meta"
        )
        assert admission.decision == "admitted"
        assert admission.reservation is not None
        ledger.settle(admission.reservation.id, actual_cents=actual)
    view = ledger.status()
    assert view["by_operation"] == {
        "stt:audio": {"calls": 2, "actual_cents": 2},
        "eval": {"calls": 1, "actual_cents": 90},
    }


class TestPolicyFiles:
    def test_round_trip_rules(self, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "scope": "global",
                            "prepaid_allowed": False,
                        },
                        {
                            "scope": "meta",
                            "prepaid_allowed": True,
                            "max_prepaid_cents_per_day": 500,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        rules = policy_from_file(path)
        assert [rule.scope for rule in rules] == ["global", "meta"]
        assert rules[1].max_prepaid_cents_per_day == 500

    def test_unknown_keys_refused(self, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(json.dumps({"rules": [], "typo": 1}), encoding="utf-8")
        with pytest.raises(ValueError, match="Unknown spend policy keys"):
            policy_from_file(path)

    def test_unknown_rule_keys_refused(self, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(
            json.dumps({"rules": [{"scope": "meta", "prepaid": True}]}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unknown keys"):
            policy_from_file(path)

    def test_non_boolean_permission_refused(self, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(
            json.dumps({"rules": [{"scope": "meta", "prepaid_allowed": "yes"}]}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="must be boolean"):
            policy_from_file(path)

    def test_file_rules_permit_prepaid(self, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(
            json.dumps(
                {"rules": [{"scope": "meta", "prepaid_allowed": True}]},
            ),
            encoding="utf-8",
        )
        ledger = SpendLedger(clock=lambda: 1_700_000_000.0, rules=policy_from_file(path))
        ledger.add_allowance(
            Allowance(
                id="pp",
                provider="meta",
                kind=AllowanceKind.PREPAID,
                balance_cents=1000,
                granted_cents=1000,
                granted_at=1_600_000_000.0,
                expires_at=None,
            )
        )
        admission = ledger.admit(
            task_id="t1",
            task_class="eval",
            estimated_cents=100,
            provider="meta",
        )
        assert admission.decision == "admitted"

    def test_status_reports_policy_and_order(self):
        ledger = SpendLedger(clock=lambda: 1_700_000_000.0)
        view = ledger.status()
        policy = view["policy"]
        assert isinstance(policy, dict)
        assert policy["spend_order"][0] == "free_daily"
        assert policy["rules"] == [
            {
                "scope": "global",
                "prepaid_allowed": False,
                "max_prepaid_cents_per_day": None,
            }
        ]
        assert policy["prepaid_spent_today_cents"] == 0
