#!/usr/bin/env bash
set -euo pipefail

# 每次运行创建全新绝对 runtime；退出时只删除本脚本创建的精确目录。
task_tmp_base="${TMPDIR:-/tmp}"
task_tmp_base="${task_tmp_base%/}"
task_runtime_root="$(mktemp -d "${task_tmp_base}/findoc-e2e-runtime.XXXXXX")"

cleanup_runtime() {
  case "${task_runtime_root}" in
    "${task_tmp_base}"/findoc-e2e-runtime.*)
      rm -rf -- "${task_runtime_root}"
      ;;
    *)
      echo "拒绝清理非预期 E2E runtime：${task_runtime_root}" >&2
      ;;
  esac
}

trap cleanup_runtime EXIT INT TERM
export FINDOC_CONTROLLED_RUNTIME_ROOT="${task_runtime_root}"

"$(dirname "$0")/../node_modules/.bin/playwright" test "$@"
