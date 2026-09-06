"""
多机（多角色）设备槽位 —— 与 multi_device_feature.md 约定一致。

- Markdown 步骤/断言中通过 ${richText_<uuid>:<设备枚举名>} 标明操作或观测主体
- RichText 结构与工具不同：mentionType=33，pluginData 仅含平台 id
- 嘉宾、管理员在设备维度与「非主播」一致，差异由步骤语义体现

## 设备角色映射按「空间（space_id）」分区

同一个设备枚举（如 `TT-主播设备-1`）在不同 bits 空间下，对应的平台插件实例 id
（`pluginData.id`）不同。因此设备角色映射按 **空间** 分区：

- **设备枚举 uuid**（`${richText_<uuid>:<名称>}` 中的 uuid）跨空间保持稳定，
  保证生成的 Markdown 占位符与空间无关；
- 只有 **pluginData.id**（平台插件实例 id）随空间切换，体现在 richtext 注册表里。

调用方在「涉及使用设备」时应先通过 `set_active_space(space_id)` 指定空间；
若用户未指定空间 id，skill 层必须反问用户后再设置（见 SKILL.md）。
未设置时回退到 `default` 分区（历史默认映射）。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# 设备枚举顺序 + 跨空间稳定的设备 uuid（用于 ${richText_<uuid>:<名称>} 占位符）。
_DEVICE_UUIDS: List[Tuple[str, str]] = [
    ("TT-主播设备-1", "690001010101"),
    ("TT-主播设备-2", "690001010102"),
    ("TT-主播设备-3", "690001010103"),
    ("TT-主播设备-4", "690001010104"),
    ("TT-非主播设备-1", "691001010101"),
    ("TT-非主播设备-2", "691001010102"),
    ("TT-非主播设备-3", "691001010103"),
    ("TT-非主播设备-4", "691001010104"),
    ("TT-非主播设备-5", "691001010105"),
    ("TT-非主播设备-6", "691001010106"),
    ("TT-非主播设备-7", "691001010107"),
]

# 各空间下「设备枚举名 → 平台插件实例 id（pluginData.id）」的分区表。
# 分区键为 bits space_id；`default` 为默认映射（未指定/未知空间时回退）。
# 这些 id 是快照，平台重建角色后会漂移；上传前由 upload_cases.check_device_roles 对
# `test_case/role/list` 校验，对不上会直接报错，不要在这里凭印象加分区。
_DEVICE_PLUGIN_ID_BY_SPACE: Dict[str, Dict[str, str]] = {
    "default": {
        "TT-主播设备-1": "69aec5d7a38946403f615e56",
        "TT-主播设备-2": "69aec632b781879e8ae3bb4c",
        "TT-主播设备-3": "69aec639b781879e8ae3bb4d",
        "TT-主播设备-4": "69aec63fb781879e8ae3bb4e",
        "TT-非主播设备-1": "69aec654b781879e8ae3bb4f",
        "TT-非主播设备-2": "69aec658b781879e8ae3bb50",
        "TT-非主播设备-3": "69aec78cb781879e8ae3bb51",
        "TT-非主播设备-4": "69afd88bb781879e8ae3bb7f",
        "TT-非主播设备-5": "69afd88eb781879e8ae3bb80",
        "TT-非主播设备-6": "69afd891b781879e8ae3bb81",
        "TT-非主播设备-7": "69afd896b781879e8ae3bb82",
    },
}

# 部分空间使用「project/dir 子分区 id」作为别名指向同一映射，方便调用方直接用 dir/project id 切换。
_SPACE_ALIASES: Dict[str, str] = {}

_DEFAULT_SPACE = "default"

# 当前生效空间（模块级状态，由 CLI / 渲染入口在「涉及设备」前设置）。
_active_space = {"id": _DEFAULT_SPACE}


def set_active_space(space_id: str = "") -> str:
    """设置当前生效的设备空间分区。返回实际生效的分区键。

    传入的 space_id 支持 space_id 本身或其 project/dir 别名（见 _SPACE_ALIASES）；
    未知或空值回退到 default 分区。
    """
    raw = (space_id or "").strip()
    resolved = _SPACE_ALIASES.get(raw, raw)
    if resolved in _DEVICE_PLUGIN_ID_BY_SPACE:
        _active_space["id"] = resolved
    else:
        _active_space["id"] = _DEFAULT_SPACE
    return _active_space["id"]


def get_active_space() -> str:
    return _active_space["id"]


def list_known_spaces() -> List[str]:
    """返回所有可选空间分区键（含 default）。"""
    return list(_DEVICE_PLUGIN_ID_BY_SPACE.keys())


def _current_plugin_map() -> Dict[str, str]:
    return _DEVICE_PLUGIN_ID_BY_SPACE.get(
        _active_space["id"], _DEVICE_PLUGIN_ID_BY_SPACE[_DEFAULT_SPACE]
    )


def get_device_role_spec(space_id: str = "") -> List[Tuple[str, str, str]]:
    """返回 [(设备名, 设备uuid, pluginData.id)] 三元组列表。

    space_id 为空时使用当前生效空间（见 set_active_space）。
    """
    if space_id:
        resolved = _SPACE_ALIASES.get(space_id.strip(), space_id.strip())
        plugin_map = _DEVICE_PLUGIN_ID_BY_SPACE.get(
            resolved, _DEVICE_PLUGIN_ID_BY_SPACE[_DEFAULT_SPACE]
        )
    else:
        plugin_map = _current_plugin_map()
    default_map = _DEVICE_PLUGIN_ID_BY_SPACE[_DEFAULT_SPACE]
    return [
        (name, uid, plugin_map.get(name, default_map.get(name, "")))
        for name, uid in _DEVICE_UUIDS
    ]


_BUSINESS_ROLE_DEFAULT_DEVICE = """
文档角色与设备槽对应（缺省时按序使用同类型空槽）：
- 主播、Host、开播方 → TT-主播设备-1（多主播场景可依次用 TT-主播设备-2…）
- 观众、Viewer、观众侧 → TT-非主播设备-1
- 管理员、Moderator → TT-非主播设备-2（或与文档「管理员1」对应槽位）
- 嘉宾、连麦嘉宾 → TT-非主播设备-3（或与文档「嘉宾1」对应槽位）
管理员、嘉宾与观众共用「非主播」设备枚举，通过步骤描述区分行为。
"""

_BUSINESS_ALIAS_TO_DEVICE: List[Tuple[List[str], str]] = [
    (["主播", "Host", "开播方", "主播端", "主播侧"], "TT-主播设备-1"),
    (["观众", "Viewer", "观众侧", "观众端"], "TT-非主播设备-1"),
    (["管理员", "Moderator", "管理员端"], "TT-非主播设备-2"),
    (["嘉宾", "连麦嘉宾", "嘉宾端"], "TT-非主播设备-3"),
]


def role_richtext_struct(display_name: str, uuid: str, plugin_id: str) -> Dict:
    return {
        "type": 2,
        "text": display_name,
        "token": "33",
        "id": uuid,
        "mentionType": 33,
        "uuid": uuid,
        "pluginData": {"id": plugin_id},
    }


def role_richtext_registry() -> Dict[str, Dict]:
    """uuid → RichText，供 SSE 与工具 registry 合并（按当前生效空间取 plugin id）。"""
    return {
        uid: role_richtext_struct(name, uid, pid)
        for name, uid, pid in get_device_role_spec()
    }


def all_name_to_richtext_tag() -> Dict[str, str]:
    """所有角色名/别名 → ${richText_<uuid>:<设备枚举名>} 映射，按名称长度降序排列。

    占位符仅依赖跨空间稳定的设备 uuid，因此与当前生效空间无关。
    """
    mapping: Dict[str, str] = {}
    device_lookup: Dict[str, str] = {}
    for name, uid in _DEVICE_UUIDS:
        tag = f"${{richText_{uid}:{name}}}"
        mapping[name] = tag
        device_lookup[name] = tag
    for aliases, device_name in _BUSINESS_ALIAS_TO_DEVICE:
        if device_name in device_lookup:
            for alias in aliases:
                mapping[alias] = device_lookup[device_name]
    return dict(sorted(mapping.items(), key=lambda x: -len(x[0])))


def list_role_display_names() -> List[str]:
    return [name for name, _ in _DEVICE_UUIDS]


def roles_prompt_context() -> str:
    """注入 prompt：枚举占位 + 书写规则。"""
    lines = [
        "**关于多机/多角色（设备槽位）的强制要求：**",
        "- 业务背景：直播场景需区分**主播端**与**非主播端**（观众/管理员/嘉宾共用非主播设备枚举，步骤文案体现差异）。",
        "- **每一条**操作步骤（`step` 字段）必须以**设备占位符**开头，再写具体操作；禁止无角色前缀的裸步骤。",
        "- **预期结果**若描述某一端 UI/状态，该条 `expected` 字符串也应以**对应设备占位符**开头。",
        "- 占位符格式：`${richText_<uuid>:<设备枚举名>}`，须与下列**完全一致**。",
        "",
        "可用设备占位（请直接复制使用，勿改 uuid 与名称）：",
    ]
    for name, uid, _ in get_device_role_spec():
        lines.append(f'  - `${{richText_{uid}:{name}}}`')
    lines.append("")
    lines.append(_BUSINESS_ROLE_DEFAULT_DEVICE.strip())
    lines.append("")
    lines.append(
        "若文档中出现「主要角色」「参与角色要求」「主播1/观众1/管理员1」等，"
        "须按上表映射到具体 TT-主播设备-n / TT-非主播设备-n，并在步骤中一贯使用同一槽位。"
    )
    return "\n".join(lines)


def roles_prompt_context_short() -> str:
    """RAG Bug 分析等短提示。"""
    return (
        "若涉及多端/多角色：每条 step 与（必要时）expected 须以设备占位开头，例如 "
        "`${richText_690001010101:TT-主播设备-1}`、`${richText_691001010101:TT-非主播设备-1}`；"
        "主播用 TT-主播设备-n，观众/管理员/嘉宾用 TT-非主播设备-n。"
    )
