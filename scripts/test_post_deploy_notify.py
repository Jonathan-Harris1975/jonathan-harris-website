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


    def test_payload_includes_versioned_site_shell_contract(self) -> None:
        context = notifier.NotificationContext(
            repository="owner/repo", branch="main", commit_sha="abc1234567", commit_message="test",
            actor="actor", workflow="wf", run_id="1", run_number="2", run_url="https://example.invalid/run",
            deployed_url="https://jonathan-harris.online",
        )
        payload = notifier.build_payload(context)
        self.assertEqual(payload["site_shell_release_sha"], "abc1234567")
        self.assertEqual(
            payload["site_shell_manifest_url"],
            "https://jonathan-harris.online/assets/site-shell/abc1234567/manifest.json",
        )

    def test_site_shell_sync_endpoint_can_be_derived_from_direct_aims_purge_url(self) -> None:
        self.assertEqual(
            notifier.derive_site_shell_sync_endpoint(
                "", "https://aims.example/cloudflare/purge"
            ),
            "https://aims.example/cloudflare/site-shell/sync",
        )
        self.assertEqual(
            notifier.derive_site_shell_sync_endpoint("", "https://hookdeck.example/random"),
            "",
        )

    def test_site_shell_sync_uses_release_specific_manifest(self) -> None:
        args = mock.Mock(
            site_shell_sync_endpoint="https://aims.example/cloudflare/site-shell/sync",
            cloudflare_purge_endpoint="",
            site_shell_sync_secret="secret",
            timeout_seconds=15.0,
            max_attempts=1,
            initial_backoff_seconds=0.0,
            max_backoff_seconds=0.0,
        )
        payload = {
            "site_shell_release_sha": "abc1234567",
            "site_shell_manifest_url": "https://jonathan-harris.online/assets/site-shell/abc1234567/manifest.json",
            "deployed_url": "https://jonathan-harris.online",
            "repository": "owner/repo",
        }
        with mock.patch.object(notifier, "deliver_with_retries") as deliver:
            notifier.maybe_deliver_site_shell_sync(args, payload)
        kwargs = deliver.call_args.kwargs
        self.assertEqual(kwargs["payload"]["release_sha"], "abc1234567")
        self.assertEqual(kwargs["headers"]["x-cloudflare-purge-secret"], "secret")

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
