# 协作与验证

本仓库管理部署配置和跨仓库协作说明。先从最新 `main` 创建功能分支，完成修改后向 `main` 提交 Pull Request。代码审查及 CI 通过后合并；阶段成果通过本仓库 `main` 到 `release` 的 Pull Request 汇总。请勿把真实凭据或运行数据提交到 Git。

## 当前适用范围

当前 `docker-compose.yml` 仍是旧 Docker 模板：Core API 使用 SQLite，容器端口为 5000，Web 容器端口为 3000。这与现有 R25 PostgreSQL 生产运行方式不同。`.env.example` 中的镜像与目录也只是模板配置，不能据此判断当前服务器的实际版本或路径。

新增 CI 只检查 Shell 语法和 Compose 配置能否正确解析、合并。它不拉取镜像、不启动容器，也不会执行 `scripts/start.sh`、`scripts/stop.sh` 或切换 R25 生产服务。`release` 合并目前也不会触发本仓库的生产部署；R25 接通工作及跨组件发布要求见 [协作说明](docs/collaboration.md)。配置验证通过不代表生产部署通过。

## 提交步骤

1. 更新本地 `main`，新建 `feat/`、`fix/`、`docs/` 或 `codex/` 分支。
2. 一次 PR 处理一个明确问题。跨仓库改动应在描述中关联其他 PR，并注明依赖顺序。
3. 使用示例环境文件执行下列配置验证。只运行验证命令，不执行启动或停止脚本。
4. 按 PR 模板填写实际验证结果，再向 `main` 提交。
5. 由负责人审核，CI 通过后合并。需要发布阶段成果时，单独提交 `main` 到 `release` 的 PR。

## 本地验证

需要 Bash、Docker CLI 和支持 GPU `gpus` 字段的 Docker Compose 插件。`config --quiet` 只验证配置，不需要启动 Docker 服务或容器。必须验证基础文件和 GPU 合并后的文件；缺少 Compose 时应先安装，不能把跳过当成通过。

```bash
set -Eeuo pipefail
while IFS= read -r -d '' script; do
  bash -n "$script"
done < <(find scripts -type f -name '*.sh' -print0)

temporary_dir="$(mktemp -d)"
trap 'rm -f "$temporary_dir/.env"; rmdir "$temporary_dir"' EXIT
cp .env.example "$temporary_dir/.env"
docker compose --env-file "$temporary_dir/.env" \
  -f docker-compose.yml config --quiet
docker compose --env-file "$temporary_dir/.env" \
  -f docker-compose.yml -f docker-compose.gpu.yml config --quiet
```

这里使用的是示例值，临时文件在退出时删除。CI 不读取生产环境文件，也不输出展开后的环境变量值。仓库原有 `scripts/validate.sh` 在工具缺失时可能跳过部分检查，因此本次 CI 直接调用上述强制检查。

## 仓库规则需要单独配置

`CODEOWNERS` 指定 `@Hang-666-star` 为负责人，但文件本身不会强制审核。仓库管理员还需启用 main/release 的 PR 审核规则、Code Owner 审核和必需状态检查。建议 `main` 要求 `Validate deployment configuration`；`release` 还要要求 `Verify main-to-release promotion`。禁止直接推送、强制推送和删除这两个分支。管理员绕过规则的能力需要单独评估，不能当作已实现的“仅本人 PR 免审”。
