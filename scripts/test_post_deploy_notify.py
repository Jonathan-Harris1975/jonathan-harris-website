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


if __name__ == "__main__":
    unittest.main()
