#!/usr/bin/env python3
"""Tests for nova_bits_exec app-conf argument resolution."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import unittest


SCRIPT_PATH = pathlib.Path(__file__).with_name("nova_bits_exec.py")


def load_module():
    spec = importlib.util.spec_from_file_location("nova_bits_exec", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AppConfResolutionTest(unittest.TestCase):
    def test_app_conf_args_resolve_package_and_layout(self) -> None:
        module = load_module()

        calls: list[tuple[str, dict]] = []

        def fake_post_json(url, body, headers, timeout, verify_tls):
            calls.append((url, body))
            if url.endswith("/ui/get_app_conf_list"):
                return {
                    "data": {
                        "app_conf_list": [
                            {
                                "pkg_url": "https://example.test/tiktok.apk",
                                "version": "45.0.0",
                                "job_id": "layout-job-1",
                            }
                        ]
                    }
                }
            if url.endswith("/ui/get_layout"):
                return {
                    "data": {
                        "mapping_url": "https://example.test/layout-mapping.txt",
                        "layout_mapping_url": "https://example.test/layout-class-mapping.txt",
                    }
                }
            raise AssertionError(f"unexpected url: {url}")

        module.post_json_anonymous = fake_post_json
        args = module.parse_args(
            [
                "--project_id",
                "1499051266",
                "--case_set_id",
                "14485061",
                "--app_product",
                "musically",
                "--app_category",
                "ttp",
                "--app_platform",
                "Android",
                "--dry-run",
            ]
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = module.run(args)

        self.assertEqual(code, 0)
        output = json.loads(stdout.getvalue())
        package = output["config"]["package"]
        self.assertEqual(package["package_type"], "android")
        self.assertEqual(package["package_url"], "https://example.test/tiktok.apk")
        self.assertEqual(package["mapping_url"], "https://example.test/layout-mapping.txt")
        self.assertEqual(package["class_mapping_url"], "https://example.test/layout-class-mapping.txt")
        self.assertEqual(package["version"], "45.0.0")
        self.assertEqual(package["app_id"], "1233")
        self.assertEqual(package["app_name"], "TikTok-M")
        self.assertEqual(package["package_name"], "com.zhiliaoapp.musically")
        self.assertTrue(output["app_conf_resolution"]["layout_lookup"])
        self.assertEqual(calls[0][1], {"product": "musically", "category": "ttp", "platform": "Android"})
        self.assertEqual(calls[1][1], {"job_id": "layout-job-1"})

    def test_app_conf_defaults_product_category_and_filters_version(self) -> None:
        module = load_module()

        calls: list[tuple[str, dict]] = []

        def fake_post_json(url, body, headers, timeout, verify_tls):
            calls.append((url, body))
            if url.endswith("/ui/get_app_conf_list"):
                return {
                    "data": {
                        "app_conf_list": [
                            {
                                "pkg_url": "https://example.test/old.apk",
                                "version": "44.9.0",
                                "job_id": "old-job",
                            },
                            {
                                "pkg_url": "https://example.test/new.apk",
                                "version": "45.0.0",
                                "job_id": "new-job",
                            },
                        ]
                    }
                }
            if url.endswith("/ui/get_layout"):
                return {
                    "data": {
                        "mapping_url": "https://example.test/new-mapping.txt",
                        "layout_mapping_url": "https://example.test/new-layout.txt",
                    }
                }
            raise AssertionError(f"unexpected url: {url}")

        module.post_json_anonymous = fake_post_json
        args = module.parse_args(
            [
                "--project_id",
                "1499051266",
                "--case_set_id",
                "14485061",
                "--app_platform",
                "Android",
                "--version",
                "45.0.0",
                "--dry-run",
            ]
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = module.run(args)

        self.assertEqual(code, 0)
        output = json.loads(stdout.getvalue())
        package = output["config"]["package"]
        self.assertEqual(package["package_url"], "https://example.test/new.apk")
        self.assertEqual(package["mapping_url"], "https://example.test/new-mapping.txt")
        self.assertEqual(package["class_mapping_url"], "https://example.test/new-layout.txt")
        self.assertEqual(package["version"], "45.0.0")
        self.assertEqual(output["app_conf_resolution"]["job_id"], "new-job")
        self.assertEqual(calls[0][1], {"product": "musically", "category": "ttp", "platform": "Android"})
        self.assertEqual(calls[1][1], {"job_id": "new-job"})

    def test_missing_package_and_platform_requires_platform_confirmation(self) -> None:
        module = load_module()
        args = module.parse_args(
            [
                "--project_id",
                "1499051266",
                "--case_set_id",
                "14485061",
                "--dry-run",
            ]
        )

        with self.assertRaisesRegex(ValueError, "--app-platform"):
            module.run(args)

    def test_office_base_does_not_bind_default_lane_headers(self) -> None:
        module = load_module()

        headers_seen: list[dict] = []
        urls_seen: list[str] = []

        def fake_post_json(url, body, headers, timeout, verify_tls):
            urls_seen.append(url)
            headers_seen.append(headers)
            if url.endswith("/ui/get_app_conf_list"):
                return {
                    "data": {
                        "app_conf_list": [
                            {
                                "pkg_url": "https://example.test/tiktok.apk",
                                "version": "45.0.0",
                                "job_id": "layout-job-1",
                            }
                        ]
                    }
                }
            if url.endswith("/ui/get_layout"):
                return {"data": {"mapping_url": "", "layout_mapping_url": ""}}
            raise AssertionError(f"unexpected url: {url}")

        module.post_json_anonymous = fake_post_json
        args = module.parse_args(
            [
                "--project_id",
                "1499051266",
                "--case_set_id",
                "14485061",
                "--app_platform",
                "Android",
                "--dry-run",
            ]
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = module.run(args)

        self.assertEqual(code, 0)
        self.assertEqual(headers_seen, [{}, {}])
        self.assertTrue(all(url.startswith("https://ttat-openapi-sg.tiktok-row.net/") for url in urls_seen))

    def test_ttat_header_is_explicitly_forwarded(self) -> None:
        module = load_module()

        headers_seen: list[dict] = []

        def fake_post_json(url, body, headers, timeout, verify_tls):
            headers_seen.append(headers)
            if url.endswith("/ui/get_app_conf_list"):
                return {
                    "data": {
                        "app_conf_list": [
                            {
                                "pkg_url": "https://example.test/tiktok.apk",
                                "version": "45.0.0",
                                "job_id": "layout-job-1",
                            }
                        ]
                    }
                }
            if url.endswith("/ui/get_layout"):
                return {"data": {"mapping_url": "", "layout_mapping_url": ""}}
            raise AssertionError(f"unexpected url: {url}")

        module.post_json_anonymous = fake_post_json
        args = module.parse_args(
            [
                "--project_id",
                "1499051266",
                "--case_set_id",
                "14485061",
                "--app_platform",
                "Android",
                "--ttat_header",
                "x-temp-lane=lane-a",
                "--dry-run",
            ]
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = module.run(args)

        self.assertEqual(code, 0)
        self.assertEqual(headers_seen, [{"x-temp-lane": "lane-a"}, {"x-temp-lane": "lane-a"}])

    def test_layout_lookup_auth_failure_does_not_block_package_resolution(self) -> None:
        module = load_module()

        def fake_post_json(url, body, headers, timeout, verify_tls):
            if url.endswith("/ui/get_app_conf_list"):
                return {
                    "app_conf_list": [
                        {
                            "pkg_url": "https://example.test/tiktok.apk",
                            "version": "45.0.0",
                            "job_id": "layout-job-1",
                            "mapping_url": "https://example.test/mapping.txt",
                            "resource_mapping_url": "https://example.test/resource-mapping.txt",
                        }
                    ]
                }
            if url.endswith("/ui/get_layout"):
                return {"ok": False, "status": 401, "error": {"status_msg": "auth token not exists"}}
            raise AssertionError(f"unexpected url: {url}")

        module.post_json_anonymous = fake_post_json
        args = module.parse_args(
            [
                "--project_id",
                "1499051266",
                "--case_set_id",
                "14485061",
                "--app_platform",
                "Android",
                "--dry-run",
            ]
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = module.run(args)

        self.assertEqual(code, 0)
        output = json.loads(stdout.getvalue())
        package = output["config"]["package"]
        self.assertEqual(package["package_url"], "https://example.test/tiktok.apk")
        self.assertEqual(package["mapping_url"], "https://example.test/mapping.txt")
        self.assertEqual(package["resource_mapping_url"], "https://example.test/resource-mapping.txt")
        self.assertIsNone(package["class_mapping_url"])
        self.assertTrue(output["app_conf_resolution"]["layout_lookup"])
        self.assertFalse(output["app_conf_resolution"]["layout_lookup_ok"])
        self.assertEqual(
            output["app_conf_resolution"]["layout_lookup_error"],
            {"status_msg": "auth token not exists"},
        )


if __name__ == "__main__":
    unittest.main()
