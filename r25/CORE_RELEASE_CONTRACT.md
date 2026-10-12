# R25 Core 发布第一版：待安装

这是待审查、待 CI 和现场验收的实现。本轮不安装或切换生产；当前服务器继续使用原控制器。磁盘扩容、主机公钥绑定和上线窗口完成后，才打开 R25_DEPLOY_ENABLED。候选构建成功不代表生产已发布。

## 明确的首版范围

现场当前后端为 60c5b95529e027ec2cd3634cc6fe190fe43b42c48eb402e2d9ba0f1ce7caaecb，来源 commit 98af96843760f7a44627a7284cdb9ffccaf02aa2。2026-10-10 的 GitHub compare 确认该来源是 main 的祖先，后续 13 个文件变化仅协作、CI、文档和工具；src/main 与 pom.xml 未变。

首版要求**全部运行 payload 相同**：JAR 的 class、资源、依赖、额外条目和有效 launcher manifest 属性都与精确现场 JAR 对比。只忽略 ZIP 时间、四个构建描述标签、本项目 Maven 描述文件。它支持这次相同业务源码重新构建和工具/协作版本更新，尚不是可发布任意业务修改的通用发布系统。业务类、依赖或运行 profile 改变时明确拒绝；后续必须通过 PR 更新能力契约并补真实集成回归，不靠修改一条摘要绕过。

payload 相同不等于完整回归。上线前后另检查 PostgreSQL V001–V013、国画保留对象和12个媒体根、三类活动工作、本机匿名gallery、受保护详情的401边界和公开asset的JSON404。SecurityConfig明确要求详情认证，不能把401当故障，也不能把匿名200当通过。只读SQL可统计非公开字段样本，但未使用生产用户凭据，认证后的详情字段投影明确记录NOT_EXERCISED_NO_TEST_CREDENTIAL。当前这部分靠完整payload等价及已有PaintingQueryService单测约束；未来业务变更必须补隔离认证集成回归。验收只发GET，不登录、不创建任务、不触发提供商、不写数据库。

## 文件和实际接口

- core_release_guard.py：固定根下 root 私有 POLICY/CURRENT/ACTIVE/record 授权；重新解析实际 JAR。只有与60c5运行payload等价，才调用原 huaniao_recovery_guard 的既有能力检查。原有限 guard 文件不改。
- control_overlay.py：只接受已审计 lifecycle/launcher 的完整原摘要，用单次精确匹配增加 registry 接口；其余 PID/ticks、ownership、preview、端口、lease 检查保留。可选 AI guard 缺失时保留原 Critic 固定摘要。
- r25_storage.py：Linux 目录FD逐层 O_NOFOLLOW、精确owner/mode、原子持久化、已有摘要CAS。未知文件、失败临时文件不清理或覆盖。
- publisher_transaction.py、core_runtime.py：真实固定R25接口、共享lease、完整快照、停止owned Java/watchdog、再次查任务、安装、真实验收、CURRENT CAS以及失败恢复。
- core_publish.py：prepare-incoming、stage、publish、status、recover、rollback CLI。外部expected SHA/run/attempt独立绑定；不执行候选脚本。
- core-release-candidate.py、verify-r25-artifact.py：部署 bundle 内的受信校验器。服务器副本用私有文件读取和源码字节编译加载 sibling verifier，候选 JSON 格式与 Core CI 相同；不从上传候选导入任何 Python 模块。
- install_core_controller.py：一次性安装和recover-install。现有60c5 Java保持运行，仅暂停/重启owned watchdog。准备前持久化PREPARING；中断后只复用完全相同私有副本。
- fixtures/*.snapshot：CI实际输入保真证据，不能直接作为安装文件执行。

固定共享锁：/root/autodl-tmp/auralink-web-deploy/runtime/frontend-deployment.lock。Core/AI非终态ACTIVE journal会阻止新的Core变更，先显式恢复。

固定生产根：
/root/autodl-tmp/artlive-r25-native-pg16/handoff-production-20260923T062101Z

## 安装前置

先通过CI中的Linux filesystem fixtures、代码审查及现场只读preflight_core_live.py。刷新确认双JAR、handoff、MANIFEST、控制器仍是本次精确摘要；漂移必须重新审计，不手改固定摘要让安装器通过。凭据、模型、媒体、数据库不进入制品或Git。

将审核后的本目录Python模块及其完整文件摘要清单安装到固定生产根的 operations/r25-publisher/，目录root:root0700、Python文件root私有。测试、fixture、文档不作为生产控制器安装。Core候选包无权更新Deploy控制器。

新增受信动态加载路径从已核验摘要的源码字节直接 compile/exec，保留模块注册并记录实际编译摘要，避免 Python 在 -B 下仍读取已有 .pyc。该修复覆盖 Core runtime、旧 guard 的受信入口，以及新生命周期/launcher 的 Core/AI guard 加载；原 fixture 字节保持不变。原 guard 内部固定 PostgreSQL helper 的旧加载接口保留，因此进入新 guard 前若发现该 helper 的相邻 .pyc/.pyo、__pycache__ 或当前 pycache_prefix 缓存，明确拒绝 legacy_postgres_bytecode_cache。安装前还必须逐一检查既有 selector、tunnel 等 helper 的现场缓存；控制器不会删除现场缓存。其他原有 legacy helper 的加载实现未在本轮重写，不能将此项描述为所有历史控制脚本的加载审计已完成。

使用可信Python执行固定路径下 install_core_controller.py install，然后 core_publish.py status。脚本不接受自选生产根。PREPARING/PREPARED准备中断可用同一bundle重试；进入停watchdog或替换控制器后中断先执行 install_core_controller.py recover-install。RESTORED后同bundle允许重试。未知内容保留且拒绝，不删除文件来跳过检查。

## Actions与启用

Core release push先构建和上传候选。production job使用既有SERVER_HOST、SERVER_PORT、SERVER_USER、SERVER_SSH_KEY四个Secrets。公开变量SERVER_HOST_KEY是经可信服务器终端读取的单条ssh-ed25519公钥；workflow结合Secret主机/端口生成known_hosts，始终StrictHostKeyChecking=yes。

仅R25_DEPLOY_ENABLED精确为true才运行生产job。关闭时summary明确NOT_DEPLOYED，候选继续构建。开启后缺controller、凭据或主机公钥会失败。workflow拒绝过期排队SHA，先prepare-incoming，再SCP固定三个文件至commit-run-attempt私有目录，最后publish。不会恢复原已暂停deploy-core.sh deploy通道。

普通publish先验证当前运行版本、候选payload、数据兼容、组件终态及空闲工作，备份固定文件集合。停止owned watchdog/Java后再次检查，再安装JAR pair/MANIFEST/handoff；应用配置原样备份，未改变模型、AI/Web代码。真实HTTP/PG验收及PID/ticks通过后才CAS提交CURRENT。抓取旧CURRENT内容和执行替换使用同一个摘要，不能重新观察并接纳漂移。

发布job有界超时；SIGTERM转为受控异常，若处于事务中会尝试恢复。强制终止或无法安全恢复时journal保持可恢复状态，不能声称自动回滚成功；需要core_publish.py recover --transaction <32位hex>。成功发布后的显式回退用rollback同参数，只允许CURRENT仍为该候选且前版仍兼容。PREPARED recover只在原文件、运行版本未变时无停机终止。

完整恢复拒绝任何外来文件漂移；停候选后再次核对旧版数据资格和任务，恢复文件并启动验收，最后恢复CURRENT。失败保持RECOVERY_REQUIRED及私有诊断。这不是历史迁移writer的f00a恢复接口。

## 验证边界

运行：python -B -m unittest discover -s r25 -p 'test_*.py' -v

Windows跳过Linux owner/fd/fsync fixtures；其余测试覆盖真实overlay源保真、JAR能力变化拒绝、HTTP/隐藏字段、实际adapter固定文件/CAS、安装准备/切换多边界故障与安全重试。模拟进程/PG不是现场验收，候选测试不是生产部署成功。本轮交付可审查实施与CI证据；安装、真实版本切换和回退仍待执行。
