# Nova/Bits Remote Debug API Notes

Source document: `https://bytedance.larkoffice.com/wiki/Lo9swRVW2ivJhpkNFODcmtFYnrd`, title `云上执行调试任务`.

## Official Sources

- Read doc through `lark-cli wiki +node-get` and `lark-cli docs +fetch --api-version v2`.
- Download doc images through `lark-cli docs +media-download`.
- Resolve JWT through `byte-cli login --control-plane cn get-jwt`.
- Resolve BAM endpoint schemas through `bitscli-bam` after official login:
  - Trigger debug task: endpoint id `2810306`
  - Case role information before debug execution: endpoint id `3926617`

If `bitscli-bam` returns the legacy error text `please login : skills login --region cn`, first ensure AgentBuddy is on PATH, then run `agentbuddy login --region cn` or `agentbuddy get-jwt --region cn`. Keep `/opt/homebrew/bin` on PATH as well because related ByteDance CLIs can live there.

## Known Endpoint Chain

### Case Set Variables

```http
GET https://bytest.bytedance.net/autox-case/api/v1/case_set_variable/list?case_set_id={case_set_id}
X-Jwt-Token: <token>
Accept: application/json, text/plain, */*
```

### Device Groups

The doc says to query this three times with `device_type` values `0`, `1`, and `2`.

```http
POST https://bytest.bytedance.net/oplatform/inner/v1/device-filter/user_group
X-Jwt-Token: <token>
Content-Type: application/json

{
  "service_id": 2,
  "template_id": 282771,
  "biz": 66666866,
  "email": "guofeng.gf@bytedance.com",
  "device_type": [0],
  "device_region": "cn"
}
```

### Roles

Official role query endpoint from BAM endpoint `3926617`:

```http
POST https://bytest.bytedance.net/autox/test_service/api/v1/autox_case/role/query
X-Jwt-Token: <token>
Content-Type: application/json

{
  "filter_test_case_mind_by_condition_group": "",
  "case_filters": [
    {
      "case_set_id": 13835709,
      "case_select_mode": 1,
      "run_mode": 0,
      "case_set_data": "",
      "bits_space_id": 1499051266
    }
  ]
}
```

The repository has an existing Bits role client and the live preflight confirmed the fallback role-list flow:

```http
POST https://bits-cn-gw.bytedance.net/test_case/role/list
domain: bits_test_management_api;v1
X-Jwt-Token: <token>

{
  "bits_space_id": <bits_space_id>
}
```

With `project_id=1499051266`, the endpoint returned role aliases such as `TT-主播设备-1`, `TT-主播设备-2`, `TT-非主播设备-1`, and related backup roles.

For the verified demo data, `autox_case/batch_preview` selected no cases with `case_select_mode=0`, and selected 3 cases with `case_select_mode=1`. The runner defaults to `--case-select-mode 1`, with `--run-mode 0`.

The demo case set references both:

- `TT-主播设备-1`: `role_id=69aec5d7a38946403f615e56`, `role_type=1`
- `TT-主播设备-2`: `role_id=69aec632b781879e8ae3bb4c`, `role_type=0`

Pass additional roles with `--extra-role ROLE_ID:ALIAS:ROLE_TYPE[:DEVICE_TYPE[:PRIVACY_GROUP_ID[:PIPELINE]]]`.

The UI capture showed role-specific device scheduling params. Do not rely on the newer `device_filters.device_condition` form for this workflow; the unified scheduler requires the old filter shape:

```json
{
  "old_device_filters": [
    {
      "number": 0,
      "device_number_adj_mode": 1,
      "and_conditions": [
        {
          "or_conditions": [
            {"field_name": "DeviceType", "field_values": ["2"], "operation": "="}
          ]
        },
        {
          "or_conditions": [
            {"field_name": "PrivacyGroupId", "field_values": ["4414"], "operation": "IN"}
          ]
        }
      ],
      "is_required": false
    }
  ]
}
```

Role `TT-主播设备-1` uses `DeviceType=2`, `PrivacyGroupId=4414`, and `pipeline_sum_uniq_name=autox_android`.

Role `TT-主播设备-2` uses `DeviceType=0` and `pipeline_sum_uniq_name=autox_ios`.

The trigger body should also include per-role `run_param_map` JSON strings containing `case_need_dispatch=true`, `use_pipe_line=true`, `need_repack=true`, and `device_max_re_dispatch_times=3`.

### App Info

The task create endpoint requires app metadata in addition to the direct package URL. Query:

```http
GET https://bytest.bytedance.net/autox/test_service/api/v1/autox_test_app_info/list
X-Jwt-Token: <token>
```

For the verified demo package, use:

- `app_id=1233`
- `app_name=TikTok-M`
- `package_name=com.zhiliaoapp.musically`
- `version=44.9.0`

The UI capture sends `app_id` as an empty string while still supplying the direct package URL. The runner supports either explicit app metadata or the captured empty `app_id` form.

### Trigger Debug Task

BAM endpoint `2810306`:

```http
POST https://bytest.bytedance.net/autox/test_service/api/v2/debug/task/create
X-Jwt-Token: <token>
Content-Type: application/json
```

Method: `CreateAutoxDebugTaskV2`

Response body includes `task_id` and `BaseResp`.

## UI Defaults From The Document Images

- package type: `android`
- device schedule timeout: `420` seconds
- runtime: Python 3
- install app: yes
- uninstall app before install: yes
- screen tap feedback: yes
- smart install: no
- notifications: start and finish checked

## Verified Demo Preflight

Using `byte-cli login --control-plane cn get-jwt` through the `bytedance-jwt` skill, the preflight succeeded for:

- case variables: `case_set_variables` was empty for `case_set_id=13835709`
- role list: returned roles for `bits_space_id=1499051266`
- device groups: `device_type` values `0`, `1`, and `2` all returned success
- live trigger: `POST /autox/test_service/api/v2/debug/task/create` returned a `task_id`
- UI-compatible live trigger with `old_device_filters` returned a `task_id`

After adding `/opt/homebrew/bin` to PATH, BAM endpoint `2810306` schema was resolved. The runner still requires `--use-default-trigger-url` or `--trigger-url` before live creation.

## CLI PATH Notes

`byte-cli` installed by `uv tool install` is normally at `~/.local/bin/byte-cli`. Codex login shells need `~/.local/bin` on PATH; if `command -v byte-cli` fails, check `~/.zprofile` for:

```bash
. "$HOME/.local/bin/env"
```

`agentbuddy`, `bytedcli`, and `bitscli` can live under `/opt/homebrew/bin`; `bitscli-bam` may still print the legacy error text `please login : skills login --region cn`. If so, confirm AgentBuddy is on PATH, then run `agentbuddy login --region cn` or `agentbuddy get-jwt --region cn`.
