# 审计输入，不作为安装文件

两份 snapshot 是 2026-10-10 从 R25 既有 operations 只读取得的原字节。它们只用于 CI 验证 control_overlay 的输入摘要和逐字保真，不能作为独立启动或恢复指令执行。

- lifecycle_adapter.py.snapshot：b89b0abbf127d8a2f0b959646c6eeff6ca986a8fac5e626349efae74a75b28cb
- r25-production-java-launch.py.snapshot：26daa88555f928079ac59b5374bd1ba2c9fd144cb6d944ca8e0e56fc8f8a462c

文件仅含控制代码、固定运行路径和摘要，没有环境文件内容或提供商凭据。安装器读取并验证现场当前文件后才渲染新控制器；不会从 fixture 直接覆盖现场。
