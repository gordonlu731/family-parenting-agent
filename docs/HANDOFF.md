## 2026-11-16 临时试用评估与准备完成（尚无URL）

已按用户“先试用、不买域名”执行，只使用已核实虚构数据。Tailscale1.104.5/Running、MagicDNS开启，Serve/Funnel均为空；当前HTTPS证书域名和Funnel能力未下发，operator未配置，family-dev无现成配置授权。完整节点/账号信息仅保存在ECS私密目录。

仅准备、未启用：单节点IP的funnel策略片段、实际节点HTTPS origin的600候选配置、原配置备份/哈希、已有root Workbench审阅块和精确撤销命令。候选仅改origin/Secure Cookie并清空模型Key，保留原初始化凭证、数据、身份和限额；当前应用配置未改、未重启，health200。管理员块先验证证书/能力/原空配置及已知虚构业务摘要，不reset、不换节点身份，不授operator；只代理HTTPS443→育儿127.0.0.1:18080。原Key留在600备份，不公开、不删除。

预览工具2027fdc0a4815c88a9b864e7d90d40e007b431b7已暂存到ECS；最终构建和133项测试通过（含候选apply/restore的模拟服务验证及HTTPS-only严格TLS探测），[Verify43866974293](https://github.com/gordonlu731/family-parenting-agent/actions/runs/43866974293)成功。实际apply/restore、Serve/Funnel、控制台、root块均未执行；不能把模拟或bash语法检查称为管理员实机生效。

当前状态仍是“尚无URL”。需要Owner/Admin核实/开启HTTPS Certificates、仅对本节点添加Funnel能力，避免默认全成员授权；需确认内地ECS该临时公开方式的接入条件，并审核执行唯一root映射。具体控制台、接入商问题、操作次序和回退见[TAILSCALE_PREVIEW_ACTIONS](TAILSCALE_PREVIEW_ACTIONS.md)。这个试用不要求买域名，不要求新增模型额度或异机备份配置；长期正式服务事项另记。

若后续Funnel建成，接收方按平台设计不需Tailscale；但国内普通手机网络/微信仍待真实验证。Serve/SSH只属私人回退，不得冒充公开微信分享。本轮未生成公开地址或私发登录邀请；真实模型新增0，账本8/8不变。

## 2026-11-16 现有Tailscale只读评估结果

当前Tailscale1.104.5/Running、MagicDNS开启，节点DNS名存在；Serve/Funnel配置均为空。CertDomains为空、Self未下发Funnel能力、OperatorUser为空，family-dev不能自行更改daemon/策略。尚无URL，未启用分享或重启应用，真实预算仍8/8。

已准备仅本节点IP的Funnel策略片段、只指向18080的443映射、HTTPS/Secure Cookie且禁用模型的私密配置候选及原配置回退。需要控制台Owner/Admin核实HTTPS Certificates并仅授权本节点；既有root执行精确映射，不给family-dev operator，不用全体成员授权、不改节点标签、不开ECS公网18080。

Funnel官方文档说明接收方可不安装Tailscale，但当前条件不足且国内微信未实测；接入商对本实例临时公网测试方式的适用条件仍需确认，不能将中继作为备案豁免。控制台和管理员最小动作、接入商问题、撤销和私有回退见[TAILSCALE_PREVIEW_ACTIONS](TAILSCALE_PREVIEW_ACTIONS.md)。以上是实机评估及准备，不是测试入口已启用。

# 总交付接续

## 当前优先选择（2026-11-16）

用户已选“先试用，不买域名”。先按[TEMPORARY_PREVIEW](TEMPORARY_PREVIEW.md)只读评估既有Tailscale测试入口及实际发布条件，不再重复要求用户先买域名。没有测试URL或权限证据；若须管理员开关，先准备最小动作再集中交回。此选择未增加真实模型预算，未切正式家庭，后文正式域名交付包留长期阶段。

当前结论和精确源码见STATUS；执行NEXT_CODEX_TASK的完整目标，不从SSH/Key重配开始。

本轮已在ECS部署并执行f306a26交付工具，130测试、全量mock/回放和明确重建m01的两人p10回放通过；原真实失败仍无回复和栈，不能伪造诊断。当前应用仍f919554（0.3.5），健康且未重启；工具与应用backend/frontend内容核对相同。

正式候选私密配置/独立初始化凭证、空正式目录、应用/备份/监测候选unit、原5个unit回退副本已准备在ECS。本项目trial-ready计划文件记录具体位置，不能公开其凭据或把虚构管理员当真家人。域名未定，所以候选仍是private origin；域名确认后保留该凭证，只更新候选origin/cookie并重生成候选，不再次建家。

长期正式交付仍有外部条件（不阻塞本次零模型虚构试用）：新增最多2次Chat的明确授权（原8/8不重置）、域名/DNS/一次HTTPS管理员操作范围、异机存储/加密公钥与恢复保管。具体步骤/止损/回退见DELIVERY_CHECKPOINT。没有这些输入时不要继续付费请求、开公网、买资源、填真实档案。

取得2次授权后执行新工具p10 --capture-responses --max-calls 2，回复先fsync到私密报告，31具名检查；首个错误停止，无自动重试。单独记录新授权额度和旧账本的关联，不能直接绕开旧worker的预算守卫。HTTP200不等于业务通过。

入口与证书就绪再做check_https严格系统CA探测、真实浏览器登录/邀请/原身份恢复/撤销、Cookie/Origin/CSRF。切正式unit前备份并保留旧目录，切换同步正式备份/监测路径；家长首次建家后才能运行正式库备份与启用其timer。两机微信和菜单质量需真实家长参与。不得把本轮mock或跨日期重建回放当成这些实证。
