"""Regression tests for optional post-deploy notification delivery."""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from scripts import post_deploy_notify as notifier


class PostDeployNotifyConfigurationTests(unittest.TestCase):
    def test_repository_contains_no_default_webhook_endpoint(self) -> None:
        self.assertEqual(notifier.DEFAULT_WEBHOOK_URL, "")

    def test_parse_args_skips_legacy_webhook_when_secret_is_absent(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(sys, "argv", ["post_deploy_notify.py"]):
            args = notifier.parse_args()
        self.assertEqual(args.webhook_url, "")

    def test_parse_args_uses_explicit_webhook_environment_value(self) -> None:
        with mock.patch.dict(
            os.environ,
            {notifier.POST_DEPLOY_WEBHOOK_URL_ENV: "https://example.invalid/post-deploy"},
            clear=True,
        ), mock.patch.object(sys, "argv", ["post_deploy_notify.py"]):
            args = notifier.parse_args()
        self.assertEqual(args.webhook_url, "https://example.invalid/post-deploy")

    def test_empty_webhook_configuration_does_not_make_a_network_request(self) -> None:
        args = mock.Mock(webhook_url="")
        with mock.patch.object(notifier, "deliver_with_retries") as deliver:
            notifier.maybe_deliver_legacy_webhook(args, {"status": "success"})
        deliver.assert_not_called()

    def test_cloudflare_purge_sequence_uses_initial_and_interval_delays(self) -> None:
        args = mock.Mock(
            cloudflare_purge_endpoint="https://example.invalid/purge",
            cloudflare_purge_secret="secret",
            cloudflare_purge_hosts="jonathan-harris.online",
            deployed_url="https://jonathan-harris.online",
            timeout_seconds=15.0,
            max_attempts=1,
            initial_backoff_seconds=0.0,
            max_backoff_seconds=0.0,
            purge_count=3,
            purge_initial_delay_seconds=300.0,
            purge_interval_seconds=300.0,
        )

        with mock.patch.object(notifier, "deliver_with_retries") as deliver, mock.patch.object(
            notifier.time, "sleep"
        ) as sleep:
            notifier.maybe_deliver_cloudflare_purge(args)

        self.assertEqual(deliver.call_count, 3)
        self.assertEqual(sleep.call_args_list, [mock.call(300.0), mock.call(300.0), mock.call(300.0)])

    def test_later_purges_still_run_when_an_earlier_pass_fails(self) -> None:
        args = mock.Mock(
            cloudflare_purge_endpoint="https://example.invalid/purge",
            cloudflare_purge_secret="",
            cloudflare_purge_hosts="jonathan-harris.online",
            deployed_url="https://jonathan-harris.online",
            timeout_seconds=15.0,
            max_attempts=1,
            initial_backoff_seconds=0.0,
            max_backoff_seconds=0.0,
            purge_count=3,
            purge_initial_delay_seconds=0.0,
            purge_interval_seconds=0.0,
        )
        first_failure = notifier.DeliveryFailure("temporary outage", transient=True)

        with mock.patch.object(
            notifier, "deliver_with_retries", side_effect=[first_failure, None, None]
        ) as deliver:
            with self.assertRaises(notifier.DeliveryFailure):
                notifier.maybe_deliver_cloudflare_purge(args)

        self.assertEqual(deliver.call_count, 3)

    def test_single_purge_has_no_schedule_sleep_by_default(self) -> None:
        args = mock.Mock(
            cloudflare_purge_endpoint="https://example.invalid/purge",
            cloudflare_purge_secret="",
            cloudflare_purge_hosts="jonathan-harris.online",
            deployed_url="https://jonathan-harris.online",
            timeout_seconds=15.0,
            max_attempts=1,
            initial_backoff_seconds=0.0,
            max_backoff_seconds=0.0,
            purge_count=1,
            purge_initial_delay_seconds=0.0,
            purge_interval_seconds=0.0,
        )

        with mock.patch.object(notifier, "deliver_with_retries") as deliver, mock.patch.object(
            notifier.time, "sleep"
        ) as sleep:
            notifier.maybe_deliver_cloudflare_purge(args)

        deliver.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
