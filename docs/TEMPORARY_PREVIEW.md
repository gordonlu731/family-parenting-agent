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

# 当前选择：先试用，不购买域名

2026年11月16日，用户在访问路线选择中明确选择“先试用，不买域名”。本阶段目标是先用虚构数据评估操作体验及家人普通微信网络可达性；不以购买域名作为该阶段的先决条件，不把试用说成正式长期家庭服务。

当前没有测试URL，未启用Funnel、未修改Tailscale权限/系统/公网、未切正式家庭，真实验证账本8/8保持。这是用户选择及下一执行任务，不是入口已部署。

## 先解释清楚

- 不必自己注册域名：提供服务的平台也可以分配HTTPS地址，这个地址依然有域名，只是不由用户单独购买。
- 技术上存在IP访问和IP证书，但沿用现有中国内地ECS时，阿里云明确要求IP对外网站也备案，且其代备案系统不支持IP备案；不能靠IP、换端口或临时隧道宣称免除要求。
- 临时平台地址能否在家人当前普通移动网络和微信中打开，必须实际验证。不能把Codex/VPN内可达当作家人可达。
- 现有入口为回环服务，发127.0.0.1或Tailscale私有IP给家人不能直接当作公网分享网址。

## 已连family-dev的Codex立即执行

1. 同步部署分支并核对STATUS/HANDOFF。沿用当前0.3.5服务、Key、已有虚构库、备份和定时器；不重配SSH/Docker，不开正式家庭，不发模型请求。
2. 优先只读评估现有Tailscale的测试分享能力：服务版本、当前节点是否允许操作、MagicDNS/HTTPS/Funnel条件、现有Serve/Funnel配置是否占用。完整节点清单/账号/策略留服务器私密，不上传公开Git。不要假定SSH已通就表示Funnel已开启或当前用户有权配置。
3. 候选Funnel可提供平台分配的https://<node>.<tailnet>.ts.net地址，接收方通常不需安装Tailscale；它是本次评估候选，未证明适合本项目或国内微信。先核实服务条款、接入商/地区适用发布条件与现有权限，不将其作为备案绕过方案。
4. 若具备适用条件，准备仅指向现有虚构育儿应用的具体配置、PUBLIC_ORIGIN/安全Cookie修改、原配置备份及回退。不要公开其他端口、Tailscale管理接口、宿主Docker或量化服务；不要用reset覆盖其他既有分享配置。
5. 需要控制台开关或管理员操作时，先完成只读评估和候选配置，再给用户一个具体、最小范围动作；用户此前选择试用不等于批准扩大整个tailnet权限或改系统策略。不要求购买域名，不新建付费资源。
6. 如果不具备公开测试条件，准确说明具体原因并保留运行服务。可提供仅本人使用的SSH隧道/私有Tailscale Serve预览作为可选回退；Serve需要访问者加入tailnet，不得说成无需安装的普通公开分享。涉及家人安装软件先说明影响，不默认要求老人安装。
7. 实际测试入口就绪后，以严格CA验证、health、静态页面、匿名拒绝和私人邀请登录检查；从服务器外验证，再让用户用普通手机网络/微信确认。不调用AI、不新增2次真实模型额度、不改8/8账本。临时网址不表示已完成真实换餐或正式家庭验收。

试用只使用已核实的虚构数据和家人各自身份，统一首页网址不直接授予家庭记录访问。保留现有鉴权、CSRF/Origin与安全Cookie。不得让用户关闭证书验证、关闭身份校验或粘贴Key/邀请到公开渠道。

## 最终只交回这些信息

- 试用入口是否实际建成、具体网址/私有访问办法及验证结果；没有就明确“尚无URL”，不编造地址。
- 家人是否无需安装额外软件；国内微信可达性是已实测还是待用户确认。
- 用户下一步最多需要做的具体账号/管理员/手机动作；平台不适合时给出原因，避免无休止更换隧道。
- 如何撤销试用入口、恢复原应用配置和保留既有数据；未完成的正式HTTPS/备案条件、异机加密和真实模型验收继续分别记录。

## 官方依据（2026-11-16核对）

- Tailscale测试分享：https://tailscale.com/docs/use-cases/application-testing/share-local-dev-server-with-internet
- Funnel条件与限制：https://tailscale.com/docs/features/tailscale-funnel
- 阿里云内地服务器/IP/HTTP/HTTPS备案说明：https://help.aliyun.com/zh/icp-filing/basic-icp-service/product-overview/icp-filing-requirements-for-a-regular-website
- IP证书技术能力：https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability

以上来源说明技术能力或接入商要求，不证明当前账号已具备权限、当前服务已可分享或国内微信一定可用。
