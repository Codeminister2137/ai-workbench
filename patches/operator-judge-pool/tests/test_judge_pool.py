"""Judge pool slice: required amount, disabled-until-grant, shared ledger."""

import inspect
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

from remote_operator.judge_pool import (
    JudgePool,
    JudgePoolConfig,
    PoolDisabled,
    pool_config_from_mapping,
)
from remote_operator.store import Store

MODEL = "muse-spark-fixture"


def config(**overrides):
    params = {
        "grant_id": "judge-pool-fixture",
        "model": MODEL,
        "expires_at": time.time() + 600,
        "max_requests": 4,
        "approved_usd": "2.00",
    }
    params.update(overrides)
    return JudgePoolConfig(**params)


class PoolConfigTests(unittest.TestCase):
    def test_every_field_is_required_with_no_defaults(self):
        names = [name for name in inspect.signature(JudgePoolConfig).parameters]
        self.assertEqual(names, ["grant_id", "model", "expires_at", "max_requests", "approved_usd"])
        for name, parameter in inspect.signature(JudgePoolConfig).parameters.items():
            self.assertIs(
                parameter.default,
                inspect.Parameter.empty,
                f"{name} must have no default amount",
            )
        with self.assertRaises(TypeError):
            JudgePoolConfig(grant_id="pool", model=MODEL, expires_at=time.time() + 60)

    def test_amount_must_be_positive_finite_decimal_string(self):
        for bad in ("0", "0.00", "-1.50", "nan", "Infinity", "not-money", "", 2, None):
            with self.assertRaises(ValueError, msg=f"approved_usd={bad!r}"):
                config(approved_usd=bad).check()

    def test_max_requests_is_bounded_integer(self):
        for bad in (0, 101, -1, True, 2.0, "4", None):
            with self.assertRaises(ValueError, msg=f"max_requests={bad!r}"):
                config(max_requests=bad).check()

    def test_model_grant_and_expiry_are_validated(self):
        with self.assertRaises(ValueError):
            config(model="gpt-fixture").check()
        with self.assertRaises(ValueError):
            config(model="muse-contributor-fixture").check()
        with self.assertRaises(ValueError):
            config(grant_id="has spaces").check()
        with self.assertRaises(ValueError):
            config(expires_at=time.time() - 1).check()
        with self.assertRaises(ValueError):
            config(expires_at=float("inf")).check()

    def test_mapping_parser_names_missing_fields_and_reads_no_defaults(self):
        with self.assertRaises(ValueError) as missing:
            pool_config_from_mapping({"grant_id": "pool"})
        message = str(missing.exception)
        for name in ("model", "expires_at", "max_requests", "approved_usd"):
            self.assertIn(name, message)
        with self.assertRaises(TypeError):
            pool_config_from_mapping(None)
        with self.assertRaises(ValueError):
            pool_config_from_mapping({**config().__dict__, "approved_usd": "-1"})
        parsed = pool_config_from_mapping(
            {
                "grant_id": "pool-1",
                "model": MODEL,
                "expires_at": time.time() + 60,
                "max_requests": 2,
                "approved_usd": "1.00",
            }
        )
        self.assertEqual(parsed.grant_id, "pool-1")


class PoolAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.pool = JudgePool(Store(Path(self.directory.name) / "pool.sqlite3"))

    def tearDown(self):
        self.directory.cleanup()

    def test_disabled_until_a_grant_exists(self):
        self.assertIsNone(self.pool.effective("judge-ada"))
        self.assertIsNone(self.pool.effective("visitor-x"))
        with self.assertRaises(PoolDisabled):
            self.pool.reserve("judge-ada", "0.10")
        status = self.pool.status()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["scope"], "judge_pool")

    def test_only_judge_subjects_are_admitted(self):
        self.pool.attach_grant(config())
        self.assertIsNotNone(self.pool.effective("judge-ada"))
        self.assertIsNone(self.pool.effective("visitor-x"))
        self.assertIsNone(self.pool.effective(""))
        with self.assertRaises(PoolDisabled):
            self.pool.reserve("visitor-x", "0.10")

    def test_expired_grant_reads_as_absent(self):
        live = config(expires_at=time.time() + 600)
        self.pool.attach_grant(live)
        self.assertIsNotNone(self.pool.effective("judge-ada"))
        self.assertIsNone(self.pool.effective("judge-ada", now=time.time() + 601))
        with self.assertRaises(ValueError):
            self.pool.attach_grant(config(expires_at=time.time() - 1))

    def test_consumed_pool_settings_cannot_change(self):
        live = config()
        self.pool.attach_grant(live)
        self.pool.reserve("judge-ada", "0.10")
        with self.assertRaises(ValueError):
            self.pool.attach_grant(config(approved_usd="9.99"))
        # Re-attaching identical settings is a harmless no-op.
        self.pool.attach_grant(live)
        self.assertIsNotNone(self.pool.effective("judge-ada"))


class PoolLedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.pool = JudgePool(Store(Path(self.directory.name) / "pool.sqlite3"))
        self.grant = config(max_requests=2, approved_usd="1.00")
        self.pool.attach_grant(self.grant)

    def tearDown(self):
        self.directory.cleanup()

    def test_reservations_are_shared_across_judges(self):
        first = self.pool.reserve("judge-ada", "0.30")
        self.assertEqual(first["requests_used"], 1)
        self.assertEqual(first["requests_limit"], 2)
        second = self.pool.reserve("judge-bob", "0.20")
        self.assertEqual(second["requests_used"], 2)
        self.assertEqual(Decimal(second["reserved_usd_estimate"]), Decimal("0.50"))
        self.assertEqual(Decimal(second["remaining_usd_estimate"]), Decimal("0.50"))

    def test_exhaustion_refuses_without_consuming(self):
        self.pool.reserve("judge-ada", "0.60")
        with self.assertRaises(ValueError):
            self.pool.reserve("judge-bob", "0.50")
        status = self.pool.status()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["requests_used"], 1)
        self.pool.reserve("judge-bob", "0.10")
        with self.assertRaises(ValueError):
            self.pool.reserve("judge-ada", "0.01")

    def test_status_reports_shared_usage_without_consuming(self):
        self.pool.reserve("judge-ada", "0.25")
        status = self.pool.status()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["model"], MODEL)
        self.assertEqual(status["requests_used"], 1)
        self.assertEqual(status["requests_limit"], 2)
        self.assertEqual(self.pool.status()["requests_used"], 1)

    def test_ledger_survives_reopen_with_same_grant(self):
        path = Path(self.directory.name) / "pool.sqlite3"
        self.pool.reserve("judge-ada", "0.25")
        reopened = JudgePool(Store(path))
        reopened.attach_grant(self.grant)
        self.assertEqual(reopened.status()["requests_used"], 1)
        tampered = JudgePool(Store(path))
        tampered.attach_grant(self.grant)
        tampered._grant = config(max_requests=2, approved_usd="5.00")
        with self.assertRaises(ValueError):
            tampered.reserve("judge-ada", "0.01")


if __name__ == "__main__":
    unittest.main()
