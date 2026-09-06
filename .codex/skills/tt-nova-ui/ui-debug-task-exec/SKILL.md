---
name: ui-debug-task-exec
description: "Use when TT Nova UI automation needs ByTest/Bits cloud intelligent debugging execution, debug task creation for an existing case_set_id, package-url based case-set execution, or nil deviceOs scheduler failure investigation."
---

# UI Debug Task Exec

## Overview

Create Nova/Bits remote intelligent-debug tasks through official CLI/API channels. Do not use browser recording, DevTools scraping, or Playwright capture for this workflow.

This is the execution stage after `ui-xmind-case-upload` / `ui-md-case-upload`, and it can also run standalone when the user already has `project_id`, `case_set_id`, and either install package URLs or TTAT app shortcut parameters.

## Required Inputs

| Input | Required | Notes |
| --- | --- | --- |
| `--project_id` / `--project-id` | yes | Bits/Nova project or space id. |
| `--case_set_id` / `--case-set-id` | yes | ByTest case set id. |
| TTP App shortcut | preferred | For normal TT Nova runs, ask the user for platform (`Android` or `iOS`) and optional version. The runner defaults to `product=musically` and `category=ttp`. |
| `--app_platform` | required for app shortcut | No default. Confirm with the user before resolving app config, for example `Android` or `iOS`. |
| `--app_conf_version` / `--version` | no | First fetch `ui/get_app_conf_list`, then filter by this version. If omitted, use the first package entry returned. |
| `--package_type` / `--package-type` | yes only for manual package URL mode | `android`, `ios`, `windows`, or `web`; Android maps to trigger `platform=1`. |
| `--package_url` / `--package-url` | yes only for manual package URL mode | Escape hatch for a specific package URL; if the user says `app_url`, pass it here. |
| `--app_product`, `--app_category` | no | Advanced override only. Defaults are `musically` and `ttp`; do not ask for these in the normal TTP flow. |
| `--ttat_base` | no | Controls only the TTAT app-conf lookup endpoint. Defaults to office-network `https://ttat-openapi-sg.tiktok-row.net`. |
| `--ttat_header` | no | Extra TTAT lookup header as `KEY=VALUE`; repeat only when a temporary lane explicitly needs headers. No lane header is hardcoded. |
| `--skip_layout_lookup` | no | Skip `ui/get_layout`; by default the runner tries it with the app-conf `job_id`, but auth failures do not block package resolution. |
| `--mapping_url`, `--resource_mapping_url`, `--class_mapping_url` | no | Use when supplied with the package. |
| `--role_id`, `--extra_role`, `--device_group_id` | no | Provide when known; otherwise run preflight discovery first. |
| `--tmp_dir` or `--manifest_path` | recommended | Writes `*_debug_task_manifest.json` under the TT Nova temp path. |
| `--trigger_url` or `--use_default_trigger_url` | live trigger only | Required with `--execute` unless `--preflight_only` is set. |

Default mode is dry-run. It prints and optionally writes a non-secret request plan; it does not create a task.

## TT Nova Path Contract

Write debug manifests under:

```text
<repo_root>/tt-nova/ui/tmp/{vc}/{module}/ui-debug-task-exec/{ui_path}_debug_task_manifest.json
```

Use `--vc`, `--module`, `--ui_path`, and `--tmp_dir` so downstream agents can find the execution evidence.

## Workflow

1. If endpoint contracts are uncertain, read `references/api.md`.
2. Run `scripts/bam_schema_probe.py --endpoint-id 2810306` and `--endpoint-id 3926617` when BAM schema confirmation is needed.
3. Prefer the TTP App shortcut instead of asking for package URLs. Confirm only the platform (`--app_platform Android` or `iOS`) and optional version; the runner defaults to `musically` + `ttp`, calls TTAT office-network `ui/get_app_conf_list`, then best-effort `ui/get_layout`.
4. Run `scripts/nova_bits_exec.py --dry-run ...` first and inspect the manifest.
5. Run `--execute --preflight_only --auto_jwt ...` to call only prerequisite query endpoints.
6. Create a live task only when the user explicitly asks for execution and the command includes `--trigger_url` or `--use_default_trigger_url`.

## Quick Start

Run from this skill directory:

```bash
python3 scripts/nova_bits_exec.py \
  --project_id 1499051266 \
  --case_set_id 13835709 \
  --case_select_mode 1 \
  --package_type android \
  --package_url '<apk_url>' \
  --mapping_url '<mapping_url>' \
  --resource_mapping_url '<resource_mapping_url>' \
  --class_mapping_url '<class_mapping_url>' \
  --app_id '' \
  --app_name 'TikTok-M' \
  --package_name 'com.zhiliaoapp.musically' \
  --version '44.9.0' \
  --role_id 69aec5d7a38946403f615e56 \
  --extra_role '69aec632b781879e8ae3bb4c:TT-主播设备-2:0:0::autox_ios' \
  --device_group_id 4414 \
  --timeout_seconds 72000 \
  --timeout_option 0 \
  --use_default_trigger_url \
  --vc '<vc>' \
  --module '<module>' \
  --ui_path '<ui_path>' \
  --tmp_dir '<repo_root>/tt-nova/ui/tmp/<vc>/<module>/ui-debug-task-exec' \
  --dry-run
```

App shortcut dry-run:

```bash
python3 scripts/nova_bits_exec.py \
  --project_id 1499051266 \
  --case_set_id '<case_set_id>' \
  --app_platform Android \
  --vc '<vc>' \
  --module '<module>' \
  --ui_path '<ui_path>' \
  --tmp_dir '<repo_root>/tt-nova/ui/tmp/<vc>/<module>/ui-debug-task-exec' \
  --dry-run
```

If the user provides a specific app version, add `--version '<version>'`. Only fall back to `--package_url` / mapping URLs when the user needs a non-TTP package, a one-off package, or TTAT app-conf lookup is unavailable.

Live execution:

```bash
python3 scripts/nova_bits_exec.py ... --execute --auto_jwt --use_default_trigger_url
```

## Verified Demo Defaults

- `TT-主播设备-1`: `role_id=69aec5d7a38946403f615e56`, `role_type=1`, `DeviceType=2`, `PrivacyGroupId=4414`, `pipeline_sum_uniq_name=autox_android`.
- `TT-主播设备-2`: `role_id=69aec632b781879e8ae3bb4c`, `role_type=0`, `DeviceType=0`, `pipeline_sum_uniq_name=autox_ios`.
- Optional app metadata: `app_id=1233`, `app_name=TikTok-M`, `package_name=com.zhiliaoapp.musically`, `version=44.9.0`.

## Expected Trigger Shape

Before live execution, confirm the dry-run manifest has:

- `platform=1` for Android packages.
- When app shortcut parameters are used, `app_conf_resolution` records the TTAT source, version, job id, and whether layout lookup ran/succeeded. Layout auth failures are recorded there and do not block package resolution.
- `old_device_filters` with `DeviceType`; Android simulator also has `PrivacyGroupId`.
- Per-role `run_param_map.pipeline_sum_uniq_name`, usually `autox_android` and `autox_ios`.
- `device_app_and_filter_configs[].device_filters` as an empty list when `old_device_filters` is used.
- `case_set_debug_config_list` and `device_role_configs` describing the same roles.

## Common Mistakes

- Missing `DeviceType` / `old_device_filters` can surface as scheduler error `param: nil deviceOs`.
- Do not paste JWT, cookies, or browser-captured headers. Use `X_JWT_TOKEN`, `BYTEST_JWT_TOKEN`, or `--auto_jwt`.
- Do not assume upload produced a `case_set_id`; if the upload response does not expose one, ask for the Bits case-set URL or explicit `case_set_id`.

## References

- `references/api.md` contains endpoint notes, known role defaults, and CLI PATH hints.
- `scripts/nova_bits_exec.py` is the deterministic runner.
- `scripts/bam_schema_probe.py` is the BAM schema probe.
