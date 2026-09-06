#!/usr/bin/env python3
"""Official-channel runner for Nova/Bits remote debug task setup."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


DEFAULT_BYTEST_BASE = "https://bytest.bytedance.net"
DEFAULT_BITS_BASE = "https://bits-cn-gw.bytedance.net"
DEFAULT_TRIGGER_PATH = "/autox/test_service/api/v2/debug/task/create"
DEFAULT_BIZ = 66666866
DEFAULT_TEMPLATE_ID = 282771
DEFAULT_SERVICE_ID = 2
DEFAULT_EMAIL = "guofeng.gf@bytedance.com"
DEFAULT_APP_PRODUCT = "musically"
DEFAULT_APP_CATEGORY = "ttp"
DEFAULT_TTAT_BASE = "https://ttat-openapi-sg.tiktok-row.net"

APP_METADATA_DEFAULTS = {
    ("musically", "android"): {
        "app_id": "1233",
        "app_name": "TikTok-M",
        "package_name": "com.zhiliaoapp.musically",
    },
}


@dataclass
class PackageConfig:
    package_type: str
    package_url: str
    mapping_url: str | None
    resource_mapping_url: str | None
    class_mapping_url: str | None
    app_id: str
    app_name: str
    package_name: str
    version: str


@dataclass
class RoleConfig:
    role_id: str
    alias: str
    role_type: int
    device_type: int | None = None
    privacy_group_id: int | None = None
    pipeline_sum_uniq_name: str | None = None


@dataclass
class ExecutionConfig:
    project_id: int
    case_set_id: int
    case_select_mode: int
    run_mode: int
    case_set_data: str
    biz: int
    email: str
    service_id: int
    template_id: int
    device_region: str
    device_types: list[int]
    selected_device_type: int
    device_group_name: str
    device_group_id: int | None
    role_alias: str
    role_id: str
    role_type: int
    extra_roles: list[RoleConfig]
    timeout_seconds: int
    install_app: bool
    uninstall_before_install: bool
    tap_feedback: bool
    smart_install: bool
    runtime: str
    package: PackageConfig


class HttpClient:
    def __init__(self, jwt_token: str, timeout: float = 30.0, verify_tls: bool = True) -> None:
        self.jwt_token = jwt_token
        self.timeout = timeout
        self.context = None if verify_tls else ssl._create_unverified_context()

    def request(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("Accept", "application/json, text/plain, */*")
        req.add_header("X-Jwt-Token", self.jwt_token)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        if body is not None:
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.context) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return {
                    "ok": 200 <= resp.status < 300,
                    "status": resp.status,
                    "url": url,
                    "data": parse_json_or_text(text),
                }
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return {
                "ok": False,
                "status": exc.code,
                "url": url,
                "error": parse_json_or_text(text),
            }
        except urllib.error.URLError as exc:
            return {"ok": False, "status": None, "url": url, "error": str(exc)}


def parse_json_or_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def bool_arg(value: str) -> bool:
    value = value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid bool value: {value}")


def normalize_package_type(value: str | None) -> str:
    value = (value or "").strip().lower()
    aliases = {
        "android": "android",
        "ios": "ios",
        "iphone": "ios",
        "windows": "windows",
        "win": "windows",
        "web": "web",
    }
    if value in aliases:
        return aliases[value]
    raise ValueError(f"unsupported package/app platform: {value}")


def post_json_anonymous(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    verify_tls: bool,
) -> dict[str, Any]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    context = None if verify_tls else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return parse_json_or_text(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "url": url, "error": parse_json_or_text(text)}
    except urllib.error.URLError as exc:
        return {"ok": False, "status": None, "url": url, "error": str(exc)}


def ttat_base_and_headers(args: argparse.Namespace) -> tuple[str, dict[str, str]]:
    base = (args.ttat_base or DEFAULT_TTAT_BASE).rstrip("/")
    headers: dict[str, str] = {}
    for item in args.ttat_header:
        if "=" not in item:
            raise ValueError("--ttat-header must be KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("--ttat-header key must not be empty")
        headers[key] = value.strip()
    return base, headers


def response_error(payload: Any) -> Any:
    if isinstance(payload, dict) and payload.get("ok") is False:
        return payload.get("error") or {"status": payload.get("status"), "url": payload.get("url")}
    return None


def payload_get(payload: Any, key: str) -> Any:
    if not isinstance(payload, dict):
        return None
    if key in payload:
        return payload.get(key)
    data = payload.get("data")
    if isinstance(data, dict):
        if key in data:
            return data.get(key)
        resp_body_json = data.get("resp_body_json")
        if isinstance(resp_body_json, dict) and key in resp_body_json:
            return resp_body_json.get(key)
    resp_body_json = payload.get("resp_body_json")
    if isinstance(resp_body_json, dict) and key in resp_body_json:
        return resp_body_json.get(key)
    return None


def first_present(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def select_app_conf(app_conf_list: list[dict[str, Any]], version: str | None) -> dict[str, Any]:
    candidates = [
        item
        for item in app_conf_list
        if isinstance(item, dict) and first_present(item, ["pkg_url", "pkgUrl", "package_url", "url"])
    ]
    if not candidates:
        raise ValueError("ui/get_app_conf_list returned no package for the requested app platform")
    if version:
        for item in candidates:
            if first_present(item, ["version"]) == version:
                return item
        raise ValueError(f"ui/get_app_conf_list returned no package version={version}")
    return candidates[0]


def fill_arg_if_empty(args: argparse.Namespace, name: str, value: Any) -> None:
    if value is None:
        return
    if getattr(args, name, None):
        return
    setattr(args, name, value)


def should_resolve_app_conf(args: argparse.Namespace) -> bool:
    has_app_hint = any([args.app_product, args.app_category, args.app_platform, args.app_conf_version])
    return has_app_hint or not args.package_url


def resolve_app_conf_args(args: argparse.Namespace) -> None:
    if not should_resolve_app_conf(args):
        return

    product = args.app_product or DEFAULT_APP_PRODUCT
    category = args.app_category or DEFAULT_APP_CATEGORY
    platform = args.app_platform or args.package_type
    if not platform:
        raise ValueError(
            "--app-platform must be confirmed when package URL is omitted; "
            f"default app product/category are {DEFAULT_APP_PRODUCT}/{DEFAULT_APP_CATEGORY}"
        )

    package_type = normalize_package_type(platform)
    fill_arg_if_empty(args, "package_type", package_type)

    base, headers = ttat_base_and_headers(args)
    app_conf_body = {
        "product": product,
        "category": category,
        "platform": platform,
    }
    app_conf_payload = post_json_anonymous(
        f"{base}/ui/get_app_conf_list",
        app_conf_body,
        headers,
        args.http_timeout,
        not args.insecure_skip_tls_verify,
    )
    app_conf_error = response_error(app_conf_payload)
    if app_conf_error:
        raise ValueError(f"ui/get_app_conf_list failed: {app_conf_error}")
    app_conf_list = payload_get(app_conf_payload, "app_conf_list") or payload_get(app_conf_payload, "appConfList")
    if not isinstance(app_conf_list, list):
        raise ValueError("ui/get_app_conf_list response missing app_conf_list")

    app_conf = select_app_conf(app_conf_list, args.app_conf_version or args.version or None)
    job_id = first_present(app_conf, ["job_id", "jobId"])
    layout_payload: dict[str, Any] = {}
    layout_lookup = bool(job_id and not args.skip_layout_lookup)
    layout_lookup_ok = False
    layout_lookup_error: Any = None
    if job_id and not args.skip_layout_lookup:
        raw_layout_payload = post_json_anonymous(
            f"{base}/ui/get_layout",
            {"job_id": job_id},
            headers,
            args.http_timeout,
            not args.insecure_skip_tls_verify,
        )
        layout_lookup_error = response_error(raw_layout_payload)
        if layout_lookup_error:
            layout_payload = {}
        elif isinstance(raw_layout_payload, dict):
            layout_payload = raw_layout_payload
            layout_lookup_ok = True

    fill_arg_if_empty(args, "package_url", first_present(app_conf, ["pkg_url", "pkgUrl", "package_url", "url"]))
    fill_arg_if_empty(
        args,
        "mapping_url",
        payload_get(layout_payload, "mapping_url")
        or payload_get(layout_payload, "mappingUrl")
        or first_present(app_conf, ["mapping_url", "mappingUrl"]),
    )
    fill_arg_if_empty(
        args,
        "resource_mapping_url",
        first_present(app_conf, ["resource_mapping_url", "resourceMappingUrl"]),
    )
    fill_arg_if_empty(
        args,
        "class_mapping_url",
        payload_get(layout_payload, "layout_mapping_url")
        or payload_get(layout_payload, "layoutMappingUrl")
        or first_present(app_conf, ["class_mapping_url", "classMappingUrl", "layout_mapping_url", "layoutMappingUrl"]),
    )
    fill_arg_if_empty(args, "version", first_present(app_conf, ["version"]))

    defaults = APP_METADATA_DEFAULTS.get((product.lower(), normalize_package_type(args.package_type)))
    if defaults:
        fill_arg_if_empty(args, "app_id", defaults.get("app_id"))
        fill_arg_if_empty(args, "app_name", defaults.get("app_name"))
        fill_arg_if_empty(args, "package_name", defaults.get("package_name"))

    args._app_conf_resolution = {
        "source": "ttat",
        "ttat_base": base,
        "product": product,
        "category": category,
        "platform": platform,
        "version": first_present(app_conf, ["version"]),
        "job_id": job_id,
        "layout_lookup": layout_lookup,
        "layout_lookup_ok": layout_lookup_ok,
        "layout_lookup_error": layout_lookup_error,
    }


def validate_execution_args(args: argparse.Namespace) -> None:
    if not args.package_type:
        raise ValueError("--package-type is required unless --app-platform is provided")
    args.package_type = normalize_package_type(args.package_type)
    if not args.package_url:
        raise ValueError("--package-url is required unless --app-product/--app-category/--app-platform resolve it")


def get_jwt(auto_jwt: bool) -> str | None:
    token = os.environ.get("X_JWT_TOKEN") or os.environ.get("BYTEST_JWT_TOKEN")
    if token:
        return token

    if not auto_jwt:
        return None

    byte_cli = shutil.which("byte-cli")
    if not byte_cli:
        local_byte_cli = os.path.expanduser("~/.local/bin/byte-cli")
        if os.path.exists(local_byte_cli):
            byte_cli = local_byte_cli
    if not byte_cli:
        return None

    proc = subprocess.run(
        [byte_cli, "login", "--control-plane", "cn", "get-jwt"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return None
    payload = parse_json_or_text(proc.stdout)
    if isinstance(payload, dict) and payload.get("success"):
        data = payload.get("data") or {}
        jwt = data.get("jwt")
        if isinstance(jwt, str) and jwt:
            return jwt
    return None


def build_config(args: argparse.Namespace) -> ExecutionConfig:
    return ExecutionConfig(
        project_id=args.project_id,
        case_set_id=args.case_set_id,
        case_select_mode=args.case_select_mode,
        run_mode=args.run_mode,
        case_set_data=args.case_set_data,
        biz=args.biz,
        email=args.email,
        service_id=args.service_id,
        template_id=args.template_id,
        device_region=args.device_region,
        device_types=args.device_types,
        selected_device_type=args.selected_device_type,
        device_group_name=args.device_group_name,
        device_group_id=args.device_group_id,
        role_alias=args.role_alias,
        role_id=args.role_id,
        role_type=args.role_type,
        extra_roles=parse_extra_roles(args.extra_role),
        timeout_seconds=args.timeout_seconds,
        install_app=args.install_app,
        uninstall_before_install=args.uninstall_before_install,
        tap_feedback=args.tap_feedback,
        smart_install=args.smart_install,
        runtime=args.runtime,
        package=PackageConfig(
            package_type=args.package_type,
            package_url=args.package_url,
            mapping_url=args.mapping_url,
            resource_mapping_url=args.resource_mapping_url,
            class_mapping_url=args.class_mapping_url,
            app_id=args.app_id,
            app_name=args.app_name,
            package_name=args.package_name,
            version=args.version,
        ),
    )


def planned_requests(args: argparse.Namespace, config: ExecutionConfig) -> list[dict[str, Any]]:
    base = args.bytest_base.rstrip("/")
    bits_base = args.bits_base.rstrip("/")
    requests: list[dict[str, Any]] = [
        {
            "name": "case_set_variables",
            "method": "GET",
            "url": f"{base}/autox-case/api/v1/case_set_variable/list?case_set_id={config.case_set_id}",
        },
        {
            "name": "case_role_query",
            "method": "POST",
            "url": f"{base}/autox/test_service/api/v1/autox_case/role/query",
            "body": {
                "filter_test_case_mind_by_condition_group": "",
                "case_filters": [build_case_filter(config)],
            },
        },
        {
            "name": "bits_role_list_fallback",
            "method": "POST",
            "url": f"{bits_base}/test_case/role/list",
            "headers": {"domain": "bits_test_management_api;v1"},
            "body": {"bits_space_id": config.project_id},
            "note": "Fallback role source when case_role_query returns empty.",
        },
    ]
    for device_type in config.device_types:
        requests.append(
            {
                "name": f"device_user_group_{device_type}",
                "method": "POST",
                "url": f"{base}/oplatform/inner/v1/device-filter/user_group",
                "body": {
                    "service_id": config.service_id,
                    "template_id": config.template_id,
                    "biz": config.biz,
                    "email": config.email,
                    "device_type": [device_type],
                    "device_region": config.device_region,
                },
            }
        )
    trigger_url = args.trigger_url
    if args.use_default_trigger_url:
        trigger_url = f"{base}{DEFAULT_TRIGGER_PATH}"
    if trigger_url:
        requests.append(
            {
                "name": "trigger_debug_task",
                "method": "POST",
                "url": trigger_url,
                "headers": {
                    "accept-language": "zh",
                    "origin": "https://bits.bytedance.net",
                    "referer": "https://bits.bytedance.net/",
                    "x-onesite-space-id": str(config.project_id),
                    "x-template-id": str(config.template_id),
                    "x-trigger-source": "bits",
                    "x-user-email": config.email,
                },
                "body": build_trigger_body(args, config),
                "note": "BAM endpoint 2810306: CreateAutoxDebugTaskV2.",
            }
        )
    return requests


def build_case_filter(config: ExecutionConfig) -> dict[str, Any]:
    return {
        "case_set_id": config.case_set_id,
        "case_select_mode": config.case_select_mode,
        "run_mode": config.run_mode,
        "case_set_data": config.case_set_data,
        "bits_space_id": config.project_id,
    }


def build_trigger_body(args: argparse.Namespace, config: ExecutionConfig) -> dict[str, Any]:
    if args.trigger_body_json:
        with open(args.trigger_body_json, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("--trigger-body-json must contain a JSON object")
        return data

    platform = {"android": 1, "ios": 2, "windows": 3, "web": 7}.get(config.package.package_type, 1)
    install_app_switch = 1 if config.install_app else 0
    device_group_ids = [config.device_group_id] if config.device_group_id else []
    role_specs = build_role_specs(config)
    debug_config = {
        "case_set_id": config.case_set_id,
        "app_url": config.package.package_url,
        "mapping_url": config.package.mapping_url or "",
        "res_mapping_url": config.package.resource_mapping_url or "",
        "clazz_mapping_url": config.package.class_mapping_url or "",
        "package_name": config.package.package_name,
        "version": config.package.version,
        "app_name": config.package.app_name,
        "app_id": config.package.app_id,
        "platform": platform,
        "product_id": config.biz,
        "biz": config.biz,
        "bits_space_id": None,
        "template_id": config.template_id,
        "role_id": config.role_id,
        "request_headers": {},
        "headless_browser_region": config.device_region,
        "install_app_switch": install_app_switch,
        "timeout": args.timeout_seconds,
        "timeout_option": args.timeout_option,
        "environ_map": {},
        "user_param_map": "{}",
        "run_param_map": "{}",
        "explore_option": {"wait_user_prepare_case": False, "knowledge_url": ""},
        "tool_plugins": [],
        "tools": [],
    }
    debug_config_list = []
    device_role_configs = []
    for role_spec in role_specs:
        per_role_debug_config = dict(debug_config)
        per_role_debug_config["role_id"] = role_spec.role_id
        per_role_debug_config["old_device_filters"] = build_old_device_filters(role_spec)
        per_role_debug_config["run_param_map"] = json.dumps(build_run_param_map(role_spec), separators=(",", ":"))
        debug_config_list.append(per_role_debug_config)
        device_role_configs.append(build_device_role_config(config, role_spec, platform, install_app_switch, device_group_ids))

    return {
        "case_set_id": config.case_set_id,
        "autox_case_filter": build_case_filter(config),
        "case_set_debug_config_list": debug_config_list,
        "case_set_debug_config": debug_config,
        "lark_notify_config": {
            "task_begin_switch": 1,
            "task_end_switch": 1,
            "group_ids": [],
            "user_emails": [config.email],
        },
        "device_role_configs": device_role_configs,
        "case_set_variables": [],
        "run_param_map": "",
        "user_param_map": "",
        "test_target_type": 0,
    }


def build_role_specs(config: ExecutionConfig) -> list[RoleConfig]:
    specs: list[RoleConfig] = []
    if config.role_id:
        specs.append(
            RoleConfig(
                config.role_id,
                config.role_alias,
                config.role_type,
                device_type=config.selected_device_type,
                privacy_group_id=config.device_group_id,
                pipeline_sum_uniq_name=pipeline_for_device_type(config.selected_device_type),
            )
        )
    specs.extend(config.extra_roles)
    if not specs:
        specs.append(
            RoleConfig(
                "",
                config.role_alias,
                config.role_type,
                device_type=config.selected_device_type,
                privacy_group_id=config.device_group_id,
                pipeline_sum_uniq_name=pipeline_for_device_type(config.selected_device_type),
            )
        )
    return specs


def build_device_role_config(
    config: ExecutionConfig,
    role_spec: RoleConfig,
    platform: int,
    install_app_switch: int,
    device_group_ids: list[int],
) -> dict[str, Any]:
    return {
        "test_case_role": {
            "RoleID": role_spec.role_id,
            "Alias": role_spec.alias,
            "Avatar": "",
            "ExtraAliasList": [],
            "ProductID": config.biz,
            "RoleType": role_spec.role_type,
        },
        "old_device_filters": build_old_device_filters(role_spec),
        "device_app_and_filter_configs": [
            {
                "install_app_infos": [
                    {
                        "app_url": config.package.package_url,
                        "mapping_url": config.package.mapping_url or "",
                        "res_mapping_url": config.package.resource_mapping_url or "",
                        "clazz_mapping_url": config.package.class_mapping_url or "",
                        "platform": platform,
                        "install_app_switch": install_app_switch,
                        "package_name": config.package.package_name,
                        "outer_version": config.package.version,
                        "app_id": config.package.app_id,
                        "app_select_req": "",
                    }
                ],
                "device_filters": [],
            }
        ],
    }


def build_old_device_filters(role_spec: RoleConfig) -> list[dict[str, Any]]:
    device_type = role_spec.device_type
    if device_type is None:
        return []
    and_conditions: list[dict[str, Any]] = [
        {
            "or_conditions": [
                {"field_name": "DeviceType", "field_values": [str(device_type)], "operation": "="}
            ]
        }
    ]
    if role_spec.privacy_group_id:
        and_conditions.append(
            {
                "or_conditions": [
                    {
                        "field_name": "PrivacyGroupId",
                        "field_values": [str(role_spec.privacy_group_id)],
                        "operation": "IN",
                    }
                ]
            }
        )
    return [
        {
            "number": 0,
            "device_number_adj_mode": 1,
            "and_conditions": and_conditions,
            "is_required": False,
        }
    ]


def pipeline_for_device_type(device_type: int | None) -> str:
    if device_type == 0:
        return "autox_ios"
    if device_type == 2:
        return "autox_android"
    return "autox"


def build_run_param_map(role_spec: RoleConfig) -> dict[str, Any]:
    return {
        "device_max_re_dispatch_times": 3,
        "block_clean_up_before_install": False,
        "svc_uniq_name": "autox",
        "pipeline_sum_uniq_name": role_spec.pipeline_sum_uniq_name or pipeline_for_device_type(role_spec.device_type),
        "is_analyzer_enabled": False,
        "case_execute_times": 1,
        "case_need_dispatch": True,
        "is_assertor_enabled": False,
        "block_clean_up": False,
        "block_device_init": False,
        "need_screen_recording": True,
        "need_intelligent_case_analysis": True,
        "case_remote_retry_times": 1,
        "autox_case_filters": [],
        "assertor_configs_str": "[]",
        "block_creator_lark": False,
        "need_all_device_pass": False,
        "block_install": False,
        "use_pipe_line": True,
        "plugin_urls": [],
        "need_repack": True,
        "need_origin_screen_recording": False,
        "shoots_step_capture": True,
    }


def parse_extra_roles(values: list[str]) -> list[RoleConfig]:
    roles: list[RoleConfig] = []
    for value in values:
        parts = value.split(":")
        if len(parts) not in {3, 4, 5, 6}:
            raise argparse.ArgumentTypeError("--extra-role must be ROLE_ID:ALIAS:ROLE_TYPE[:DEVICE_TYPE[:PRIVACY_GROUP_ID[:PIPELINE]]]")
        role_id, alias, role_type_text = parts[:3]
        try:
            role_type = int(role_type_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("--extra-role ROLE_TYPE must be an integer") from exc
        device_type = int(parts[3]) if len(parts) >= 4 and parts[3] else None
        privacy_group_id = int(parts[4]) if len(parts) >= 5 and parts[4] else None
        pipeline = parts[5] if len(parts) >= 6 and parts[5] else pipeline_for_device_type(device_type)
        roles.append(
            RoleConfig(
                role_id=role_id,
                alias=alias,
                role_type=role_type,
                device_type=device_type,
                privacy_group_id=privacy_group_id,
                pipeline_sum_uniq_name=pipeline,
            )
        )
    return roles


def resolve_manifest_path(args: argparse.Namespace) -> str | None:
    if args.manifest_path:
        return args.manifest_path
    target_dir = args.tmp_dir or args.out_dir
    if not target_dir:
        return None
    stem = args.ui_path or f"case_set_{args.case_set_id}"
    return os.path.join(target_dir, f"{stem}_debug_task_manifest.json")


def write_manifest(args: argparse.Namespace, output: dict[str, Any]) -> None:
    manifest_path = resolve_manifest_path(args)
    if not manifest_path:
        return
    output["manifest_path"] = manifest_path
    manifest = {
        "skill_name": "ui-debug-task-exec",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "vc": args.vc,
        "module": args.module,
        "ui_path": args.ui_path,
        "mode": output.get("mode"),
        "ok": output.get("ok"),
        "auth": output.get("auth"),
        "config": output.get("config"),
        "requests": output.get("requests", []),
        "results": output.get("results", []),
        "app_conf_resolution": output.get("app_conf_resolution"),
        "error": output.get("error"),
    }
    parent = os.path.dirname(os.path.abspath(manifest_path))
    os.makedirs(parent, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def finish(args: argparse.Namespace, output: dict[str, Any], code: int) -> int:
    write_manifest(args, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return code


def run(args: argparse.Namespace) -> int:
    resolve_app_conf_args(args)
    validate_execution_args(args)
    config = build_config(args)
    plan = planned_requests(args, config)
    token = get_jwt(args.auto_jwt)

    output: dict[str, Any] = {
        "ok": True,
        "mode": "execute" if args.execute else "dry-run",
        "auth": {
            "jwt_available": bool(token),
            "source": "env_or_byte_cli" if token else None,
        },
        "config": asdict(config),
        "requests": plan,
    }
    if hasattr(args, "_app_conf_resolution"):
        output["app_conf_resolution"] = args._app_conf_resolution

    if not args.execute:
        return finish(args, output, 0)

    if not token:
        output["ok"] = False
        output["error"] = "Missing auth. Set X_JWT_TOKEN/BYTEST_JWT_TOKEN or install/login byte-cli, then retry."
        return finish(args, output, 2)

    if not (args.trigger_url or args.use_default_trigger_url) and not args.preflight_only:
        output["ok"] = False
        output["error"] = "Refusing live execution without --trigger-url or --use-default-trigger-url."
        return finish(args, output, 2)

    client = HttpClient(token, timeout=args.http_timeout, verify_tls=not args.insecure_skip_tls_verify)
    results: list[dict[str, Any]] = []
    for request in plan:
        if args.preflight_only and request["name"] == "trigger_debug_task":
            continue
        method = request["method"]
        url = request["url"]
        body = request.get("body")
        result = client.request(method, url, body, request.get("headers"))
        results.append({"name": request["name"], **result})
        if not result["ok"] and args.stop_on_error:
            break
        time.sleep(args.request_interval)

    output["results"] = results
    output["ok"] = all(item.get("ok") for item in results)
    return finish(args, output, 0 if output["ok"] else 1)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", "--project_id", dest="project_id", type=int, required=True)
    parser.add_argument("--case-set-id", "--case_set_id", dest="case_set_id", type=int, required=True)
    parser.add_argument("--case-select-mode", "--case_select_mode", dest="case_select_mode", type=int, default=1, help="ByTest case selection mode. Demo case_set 13835709 previews cases with mode 1.")
    parser.add_argument("--run-mode", "--run_mode", dest="run_mode", type=int, default=0)
    parser.add_argument("--case-set-data", "--case_set_data", dest="case_set_data", default="")
    parser.add_argument("--package-type", "--package_type", dest="package_type", choices=["android", "ios", "windows", "web"])
    parser.add_argument("--package-url", "--package_url", dest="package_url")
    parser.add_argument("--mapping-url", "--mapping_url", dest="mapping_url")
    parser.add_argument("--resource-mapping-url", "--resource_mapping_url", dest="resource_mapping_url")
    parser.add_argument("--class-mapping-url", "--class_mapping_url", dest="class_mapping_url")
    parser.add_argument("--app-id", "--app_id", dest="app_id", default="")
    parser.add_argument("--app-name", "--app_name", dest="app_name", default="")
    parser.add_argument("--package-name", "--package_name", dest="package_name", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--app-product", "--app_product", dest="app_product", help=f"Resolve package config through TTAT ui/get_app_conf_list. Defaults to {DEFAULT_APP_PRODUCT}.")
    parser.add_argument("--app-category", "--app_category", dest="app_category", help=f"Resolve package config through TTAT ui/get_app_conf_list. Defaults to {DEFAULT_APP_CATEGORY}.")
    parser.add_argument("--app-platform", "--app_platform", dest="app_platform", help="Resolve package config platform, e.g. Android. No default; confirm this with the user.")
    parser.add_argument("--app-conf-version", "--app_conf_version", dest="app_conf_version", help="Pick a specific app version from ui/get_app_conf_list.")
    parser.add_argument("--ttat-base", "--ttat_base", dest="ttat_base", help=f"Override TTAT app-conf base URL. Defaults to office-network {DEFAULT_TTAT_BASE}.")
    parser.add_argument("--ttat-header", "--ttat_header", dest="ttat_header", action="append", default=[], help="Extra TTAT app-conf lookup header as KEY=VALUE. Repeat when a temporary lane requires explicit headers.")
    parser.add_argument("--skip-layout-lookup", "--skip_layout_lookup", dest="skip_layout_lookup", action="store_true", help="Do not call ui/get_layout for layout/mapping artifacts.")
    parser.add_argument("--biz", type=int, default=DEFAULT_BIZ)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--service-id", "--service_id", dest="service_id", type=int, default=DEFAULT_SERVICE_ID)
    parser.add_argument("--template-id", "--template_id", dest="template_id", type=int, default=DEFAULT_TEMPLATE_ID)
    parser.add_argument("--device-region", "--device_region", dest="device_region", default="cn")
    parser.add_argument("--device-types", "--device_types", dest="device_types", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--selected-device-type", "--selected_device_type", dest="selected_device_type", type=int, default=2)
    parser.add_argument("--device-group-name", "--device_group_name", dest="device_group_name", default="UI-Most-直播钱包专用-Emulator-Android")
    parser.add_argument("--device-group-id", "--device_group_id", dest="device_group_id", type=int)
    parser.add_argument("--role-alias", "--role_alias", dest="role_alias", default="TT-主播设备-1")
    parser.add_argument("--role-id", "--role_id", dest="role_id", default="")
    parser.add_argument("--role-type", "--role_type", dest="role_type", type=int, default=1)
    parser.add_argument(
        "--extra-role",
        "--extra_role",
        dest="extra_role",
        action="append",
        default=[],
        help="Additional role as ROLE_ID:ALIAS:ROLE_TYPE[:DEVICE_TYPE[:PRIVACY_GROUP_ID[:PIPELINE]]]. Repeat for multi-role case sets.",
    )
    parser.add_argument("--timeout-seconds", "--timeout_seconds", dest="timeout_seconds", type=int, default=420)
    parser.add_argument("--timeout-option", "--timeout_option", dest="timeout_option", type=int, default=0)
    parser.add_argument("--runtime", default="Python 3")
    parser.add_argument("--install-app", "--install_app", dest="install_app", type=bool_arg, default=True)
    parser.add_argument("--uninstall-before-install", "--uninstall_before_install", dest="uninstall_before_install", type=bool_arg, default=True)
    parser.add_argument("--tap-feedback", "--tap_feedback", dest="tap_feedback", type=bool_arg, default=True)
    parser.add_argument("--smart-install", "--smart_install", dest="smart_install", type=bool_arg, default=False)
    parser.add_argument("--bytest-base", "--bytest_base", dest="bytest_base", default=DEFAULT_BYTEST_BASE)
    parser.add_argument("--bits-base", "--bits_base", dest="bits_base", default=DEFAULT_BITS_BASE)
    parser.add_argument("--trigger-url", "--trigger_url", dest="trigger_url")
    parser.add_argument("--use-default-trigger-url", "--use_default_trigger_url", dest="use_default_trigger_url", action="store_true", help=f"Use {DEFAULT_BYTEST_BASE}{DEFAULT_TRIGGER_PATH} for the final task trigger.")
    parser.add_argument("--trigger-body-json", "--trigger_body_json", dest="trigger_body_json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--preflight-only", "--preflight_only", dest="preflight_only", action="store_true", help="With --execute, call only prerequisite query endpoints and skip task trigger.")
    parser.add_argument("--dry-run", action="store_true", help="Accepted for readability; dry-run is the default.")
    parser.add_argument("--auto-jwt", "--auto_jwt", dest="auto_jwt", action="store_true", help="Try byte-cli login --control-plane cn get-jwt if env token is absent.")
    parser.add_argument("--http-timeout", "--http_timeout", dest="http_timeout", type=float, default=30.0)
    parser.add_argument("--insecure-skip-tls-verify", "--insecure_skip_tls_verify", dest="insecure_skip_tls_verify", action="store_true", help="Allow internal self-signed TLS chains. Use only on trusted ByteDance endpoints.")
    parser.add_argument("--request-interval", "--request_interval", dest="request_interval", type=float, default=0.2)
    parser.add_argument("--stop-on-error", "--stop_on_error", dest="stop_on_error", action="store_true", default=False)
    parser.add_argument("--vc", default="")
    parser.add_argument("--module", default="")
    parser.add_argument("--ui-path", "--ui_path", dest="ui_path", default="")
    parser.add_argument("--out-dir", "--out_dir", dest="out_dir", default="", help="Optional TT Nova output directory for debug task manifest.")
    parser.add_argument("--tmp-dir", "--tmp_dir", dest="tmp_dir", default="", help="Optional TT Nova temp directory; defaults to --out-dir for manifest output.")
    parser.add_argument("--manifest-path", "--manifest_path", dest="manifest_path", default="", help="Optional exact path for debug task manifest JSON.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
