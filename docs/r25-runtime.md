# R25 运行映射

以下是 2026-10-10 的现场核验基线，用于接通协作发布；它不是新的生产发布回执。
后续发布必须重新核验实际版本，不能只依据本说明中的快照。

| 组件 | 代码归属 | 当前内部端口 | 运行形式 |
| --- | --- | --- | --- |
| Web | `auralink-web` | 19083 | Next.js standalone，由现有 Web 发布器管理 |
| Core | `auralink-core-api` | 19080 | Java 17 JAR，R25 生命周期管理 |
| Guide | `auralink-ai-service` 的 `guide_service/` | 19084 | Python 3.10 Flask，独立环境 |
| Critic | `auralink-ai-service` 的 `critic-service/` | 19085 | Python 3.10 FastAPI/Uvicorn，独立环境 |
| 数据库 | 运行数据 | 使用服务器受控配置 | PostgreSQL 16，常规代码发布不迁移数据 |

旧 MusicGen、Vision、VMM 的 8000、5002、5001 端口在该次核验中没有监听者。
保留其源码和模型，并不在国画发布中启动它们。

## 已核验的来源

- Web 原运行提交：`520ad0ae78608bc2f154c0b9fbb242e070812fd2`。
- Core 两份运行 JAR 摘要一致：`60c5b95529e027ec2cd3634cc6fe190fe43b42c48eb402e2d9ba0f1ce7caaecb`；大小均为 69,590,578 字节。MANIFEST、handoff 和运行 Java 进程指向同一版本。
- Guide/Critic 已从实际运行目录导出 22 个源码、依赖声明和说明文件；其中 19 个代码与依赖文件摘要和独立现场清单一致。源码导入 AI 仓库前逐文件核验，未携带 `.env`、凭据、用户数据或模型。
- 公开首页与画廊正常呈现；画廊基线为 9,553 幅，已加载的推荐及首屏图片来自 `https://api.artlive.top`。这只证明该次核验时的版本，不替代下一次发布验收。
- 只读预检通过：数据库 V001–V013、两份 JAR、国画保留对象及媒体根符合当前基线，检查时活动生成任务为零。匿名画廊返回 200，要求认证的详情返回 401，未知公开媒体返回 JSON 404。未使用生产用户凭据，认证后的详情投影明确未验收。

## 发布边界

Web 继续调用经过摘要绑定的现有发布器。Core 原入口只允许特定历史迁移，不能
用于任意新 JAR；常规 Core 发布实现和验收要求见
[Core 发布契约](../r25/CORE_RELEASE_CONTRACT.md)。新控制器通过审查和故障验证并安装后，
才可接入生产执行步骤。

Guide/Critic 的运行源码受到 R25 生命周期摘要约束。AI 仓库合并成功只表示源码
已纳管，更新运行版本还必须同时更新经过校验的 R25 绑定并完成服务验收。
不能直接覆盖目录后执行未经协调的重启。

共享发布锁位于 `/root/autodl-tmp/auralink-web-deploy/runtime/frontend-deployment.lock`。
发布前后记录 Web、Core、Guide、Critic 的版本或源码摘要；未改动的组件保持同一身份。

扩盘完成后应重新核验数据盘可用空间。Web 现有发布器要求至少 4 GiB，
不通过降低门槛或删除模型、用户数据来绕过检查。
