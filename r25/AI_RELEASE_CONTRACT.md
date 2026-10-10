# R25 Guide / Critic 发布契约

本目录提供候选验证、可信源码登记、19 个生产文件的事务切换和显式恢复。生产主机安装与运行验收尚未执行。本轮保持 `R25_DEPLOY_ENABLED` 关闭，不修改生产服务。源码恢复 PR 的通过及相同源码登记均不能证明任意 AI 更新已在生产运行。

## 仓库和版本

AI 仓库负责 `guide_service/` 与 `critic-service/app/` 的业务源码；旧 MusicGen、Vision、VMM 保留但不进入 R25 候选包。Deploy 负责固定主机控制器及发布约束。两仓库均使用功能分支 → `main` → `release`；只有 AI `release` push 或在 `release` 手动运行才生成候选。

候选包含完整 40 位 Git commit、Actions run ID / attempt、19 个文件的 SHA-256 和字节数、两个 requirements 文件摘要、统一源码树摘要，以及确定性 `ai-source.zip`。创建器核验 checkout HEAD 和每个文件对应的 Git blob；接收器用工作流独立传入的 commit/run/attempt 重新验证，不接受候选自行批准生产或指定部署命令。候选不含环境文件、令牌、模型、数据、媒体、缓存或旧音乐服务。

初始生产源码摘要为 `97cf196216ae8a9e1a4f8e15f1e6cac6fb338787a6663eb9789cecf0ba3f576a`，逐文件证据见 `ai-baseline.json`。它对应恢复源码的 AI main commit `c41c2435d6498c9f1177ae7faea329a799d72535`；初始登记不编造旧生产的 Actions run。

## 安装顺序和开关

1. 先安装同目录的 Core 控制器；共享 lifecycle overlay 已包含可选 AI hook。固定可信 bundle 目录为 R25 根目录下 `operations/r25-publisher/`，root:root、0700；Python 模块为 root:root、0600。只允许审核后的 Deploy bundle，不能从候选包执行部署代码。
2. 在同一个可信 bundle 中运行 `/root/miniconda3/bin/python3 -B install_ai_controller.py install`。它核验实际 19 文件、现有 Core、Guide、Critic、PG 空闲状态和健康状态，登记初始版本，再安装 `operations/ai_release_guard.py` 和 handoff 的 path/hash/policy 绑定。仅短暂暂停已有 watchdog；不重启 Java/AI，不替换业务源码，不安装依赖。
3. 核验 `/root/miniconda3/bin/python3 -B ai_publish.py status`。检查现有树是否含 `.pyc`、`.pyo`、`.so`、`.pyd`、额外 Python 模块或符号链接；它们会被拒绝，控制器不会静默删除。`-B` 仍可能读取旧字节码，所以发布不能忽略这些文件。
4. 配置 GitHub `production` environment 的 `SERVER_HOST`、`SERVER_PORT`、`SERVER_USER=root`、`SERVER_SSH_KEY` secrets，以及 `SERVER_HOST_KEY` 变量。host key 必须是一条不带主机名或注释的 `ssh-ed25519 <base64>` 公钥；工作流据主机/端口生成 known_hosts 并强制校验。
5. 完成生产安装、演练与验收后，才把仓库变量 `R25_DEPLOY_ENABLED` 设为字符串 `true`。目前不设置。关闭时工作流只上传候选，summary 明确显示 `NOT_DEPLOYED`。

安装过程中断后使用 `install_ai_controller.py recover-install` 恢复原 handoff 绑定。该操作仅适用于尚未发布其他 AI 版本的初始登记；成功的业务源码升级不能通过撤销 hook 绕过版本核验。

## 一次实际发布

服务器共享锁仍为 Web / Core 使用的 `frontend-deployment.lock`，贯穿准备、停机、切换、验收和必要的恢复。AI 与 Core 分别保留自己的 CURRENT、ACTIVE 和不可变 accepted records；任何组件存在未完成事务时，另一组件必须先完成显式恢复。

1. 核验可信控制器、接受记录、现有 19 文件、原 Core 版本、进程 PID/start ticks、监听端口、健康和 PG 活跃任务数量。验证依赖摘要仍为初始审核值，并预留源码备份与 64 MiB 余量。
2. 保存 19 文件的完整私有备份、原 CURRENT、对应 Core 三元身份和不变角色 PID；先写 durable journal，再暂停 owned watchdog 和 Java，阻止新任务。再次确认已有任务为空。
3. 只停止源码有变化的 Guide 或 Critic；PID/start ticks/用户/可执行文件/进程组/端口不符合原 lifecycle 所有权规则时拒绝，绝不强杀或接管外来进程。
4. 逐文件以原摘要作比较并原子替换，保留 1000:1000、0600。Guard 只在允许启动的事务阶段接受完整的新 19 文件摘要；中间混合状态不能启动。
5. 使用原 Python、私有配置与启动方式恢复改动角色。Guide 必须为 UP 且 provider/model 已配置；Critic 必须为 ok、vision/model 已配置，且带原内部令牌访问 readiness 为 available、configured-provider；不带令牌须返回 401。这些请求不调用模型提供商。
6. 恢复相同 Core 版本，核验公开图库、鉴权边界、JSON 错误响应、原图库数量下限和 owned Java。受保护详情没有提供测试凭据，记录 `authenticated_detail_projection=NOT_EXERCISED_NO_TEST_CREDENTIAL`，不声称已完成认证详情或隐私投影验收。Web/Tunnel 仅查询状态。恢复 watchdog 后写 acceptance，再提交 AI CURRENT。

依赖文件变化当前明确拒绝：没有在运行中的 Python 环境执行 `pip install`。如需改依赖，应另行审核独立环境构建、进程可执行路径和回滚契约。新增运行模块也必须先更新明确的文件清单与审核规则。

源码相同则只执行健康核验和来源登记，结果为 `AI_IDENTICAL_SOURCE_REGISTERED`。发生实际源码切换才返回 `AI_SOURCE_PUBLISHED`。两种结果都不能代替模型真实调用的业务验收，本流程刻意不产生付费提供商请求。

## 失败、恢复和记录

源文件替换、启动或验收失败时，控制器保留原始失败类别并在同一锁下恢复旧文件、旧 AI CURRENT、原 Core 版本及 watchdog。恢复也失败时登记 `RECOVERY_REQUIRED`（若 journal 写入本身失败则保留最后的 intent），阻止后续发布及混合源码启动，不宣称成功。远端发布上限 480 秒，SIGTERM 转为异常进入事务恢复；再超过 60 秒被强制终止或连接中断时只能依据 journal 显式恢复，不能宣称已自动回退。传输前和发布前均核对 GitHub 当前 release SHA，拒绝过期排队版本。

在可信 bundle 中运行以下命令；transaction 必须来自控制器输出的完整 32 位 ID：

```bash
/root/miniconda3/bin/python3 -B ai_publish.py recover --transaction <transaction-id>
/root/miniconda3/bin/python3 -B ai_publish.py rollback --transaction <committed-transaction-id>
/root/miniconda3/bin/python3 -B ai_publish.py status
```

`recover` 用于未完成事务；`rollback` 用于最近仍为 ACTIVE 的已完成发布。若 AI/Core CURRENT、文件摘要或不变角色的进程身份已漂移，拒绝自动覆盖，需要先调查现场。`PREPARED` 阶段的撤销和已 `RESTORED` 的重复核验都要求旧源码、旧 CURRENT、对应 Core、Guide/Critic/Java 进程、HTTP 健康和 watchdog 完整有效；只检查，不重启或改源，任一缺失就拒绝报告恢复成功。

AI `runtime/ai-publications/` 留存候选、文件副本、accepted record、snapshot、journal、HTTP acceptance。跨组件版本记录包含 AI commit + 源码树摘要 + accepted record 摘要以及 Core commit + JAR 摘要 + accepted record 摘要。记录不包含 provider key、数据库口令、令牌或完整进程环境。

## 验证范围

`test_ai_runtime.py` 运行真实适配器与临时文件操作，以受控进程/HTTP边界验证顺序、每个 intent 后故障、部分替换、健康失败、恢复失败、外来 PID、源码漂移、依赖变化、跨组件互斥、真实候选解包以及控制器 handoff 安装/撤销。`r25_storage.py` 的 Linux 测试负责 descriptor、owner/mode、原子替换和持久化边界。AI 仓库另外验证真实 Flask/FastAPI 服务的离线契约和候选包完整性。

当前本地结果不能冒充生产进程启动、生产磁盘条件或真实模型调用已验收。服务器空间、首次安装、SSH环境配置、实际发布及恢复演练均在启用开关前完成并记录。
