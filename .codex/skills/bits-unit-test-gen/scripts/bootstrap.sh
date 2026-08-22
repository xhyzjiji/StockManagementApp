#!/usr/bin/env bash

set -e

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo-path)
                if [[ -z "${2:-}" ]]; then
                    REPO_PATH=""
                    shift
                    continue
                fi
                REPO_PATH="$2"
                shift 2
                ;;
            *)
                echo "Error: unknown argument: $1"
                exit 1
                ;;
        esac
    done

    REPO_PATH="${REPO_PATH:-}"
}

run_begin() {
    local target="$1"
    local -a begin_args
    begin_args=(begin)

    if [[ -n "$REPO_PATH" ]]; then
        begin_args+=(--repo-path "$REPO_PATH")
    fi

    if ! AGENT_SOURCE="${AGENT_SOURCE:-unknown}" MODEL_SOURCE="${MODEL_SOURCE:-unknown}" \
        "$target" "${begin_args[@]}"; then
        echo "Warning: utree begin failed; continuing with bootstrap"
    fi
}

ensure_utree_installed() {
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local target="$script_dir/utree"
    local cache_dir="$script_dir/.cache"

    # 检查目标二进制是否存在且有效
    if [[ -f "$target" && -x "$target" ]]; then
        echo "Info: utree already exists at $target"
        run_begin "$target"
        return 0
    fi

    # 根据系统和架构确定二进制名称
    local binary_name
    if [[ "$OSTYPE" == "darwin"* ]]; then
        binary_name="utree_darwin_arm64"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        binary_name="utree_linux_amd64"
    else
        echo "Error: unsupported OS ($OSTYPE)"
        exit 1
    fi

    echo "Info: fetching latest utree version..."
    local api_url="https://scm.byted.org/api/v2/versions/latest_version/?repo_id=536343&status=build_ok&type=online"
    local tar_url
    tar_url=$(curl -s "$api_url" | grep -o '"tar_url":"[^"]*"' | head -1 | sed 's/"tar_url":"//;s/"//')

    if [[ -z "$tar_url" ]]; then
        echo "Error: failed to get tar_url from API response"
        exit 1
    fi

    mkdir -p "$cache_dir"

    echo "Info: downloading utree from $tar_url..."
    curl -sL "$tar_url" | tar -xz -C "$cache_dir"

    # 找到下载的二进制并复制到脚本目录，重命名为 utree
    local downloaded_binary="$cache_dir/$binary_name"
    if [[ ! -f "$downloaded_binary" ]]; then
        # 尝试在 cache_dir 的子目录中查找
        downloaded_binary=$(find "$cache_dir" -name "$binary_name" -type f 2>/dev/null | head -1)
    fi

    if [[ -z "$downloaded_binary" || ! -f "$downloaded_binary" ]]; then
        echo "Error: $binary_name not found in downloaded package"
        rm -rf "$cache_dir"
        exit 1
    fi

    chmod +x "$downloaded_binary"
    cp -f "$downloaded_binary" "$target"
    rm -rf "$cache_dir"

    run_begin "$target"

    echo "Info: utree installed to $target"
}

parse_args "$@"
ensure_utree_installed
