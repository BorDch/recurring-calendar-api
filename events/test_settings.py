import os
import subprocess
import sys
from unittest import TestCase


class ProductionBooleanSettingsTests(TestCase):
    def settings_result(self, **values):
        env = os.environ.copy()
        env.update(
            {
                "CALENDAR_PROFILE": "production",
                "SECRET_KEY": "settings-test-key",
                "ALLOWED_HOSTS": "localhost",
                "CSRF_TRUSTED_ORIGINS": "https://localhost",
                "POSTGRES_DB": "unused",
                "POSTGRES_USER": "unused",
                "POSTGRES_PASSWORD": "unused",
                "POSTGRES_HOST": "localhost",
            }
        )
        for name in ("CALENDAR_HTTPS_ENABLED", "CALENDAR_TRUST_PROXY_HTTPS"):
            env.pop(name, None)
        env.update(values)
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "from django.conf import settings; print(settings.SECURE_SSL_REDIRECT, "
                'settings.SECURE_PROXY_SSL_HEADER if hasattr(settings, "SECURE_PROXY_SSL_HEADER") else None)',
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_defaults_and_binary_values(self):
        for values, expected in (
            ({}, "True None"),
            ({"CALENDAR_HTTPS_ENABLED": "0"}, "False None"),
            ({"CALENDAR_HTTPS_ENABLED": "1"}, "True None"),
            ({"CALENDAR_TRUST_PROXY_HTTPS": "0"}, "True None"),
            ({"CALENDAR_TRUST_PROXY_HTTPS": "1"}, "True ('HTTP_X_FORWARDED_PROTO', 'https')"),
        ):
            with self.subTest(values=values):
                result = self.settings_result(**values)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_invalid_values_name_the_variable_without_echoing_value(self):
        for name in ("CALENDAR_HTTPS_ENABLED", "CALENDAR_TRUST_PROXY_HTTPS"):
            for value in ("", "treu"):
                with self.subTest(name=name, value=value):
                    result = self.settings_result(**{name: value})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(name, result.stderr)
                    self.assertIn("must be 0 or 1", result.stderr)
                    self.assertNotIn("treu", result.stderr)
