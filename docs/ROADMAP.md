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

## 当前用户优先选择：先试用，不买域名

执行TEMPORARY_PREVIEW进行已有平台测试入口的只读评估和具体动作准备，先用虚构数据验证体验。当前未建立URL，Funnel未获可用证据，不承诺国内微信畅通；不把临时地址当备案替代或正式家庭交付，不新增模型请求/付费资源。长期交付项继续保留，不因暂缺自购域名停止试用评估。

# 总交付进度

| 工作 | 当前结果 |
| --- | --- |
| 原失败诊断 | 已读取ECS旧脚本/摘要；回复和栈丢失，仍无法定位。新工具已部署并实机验证，原失败不冒称修复 |
| 两身份文字闭环 | 130回归、30条mock/30条零网络回放通过；重建m01的p10通过；真实换餐需一次最多2次新验证额度 |
| 稳定入口 | HTTPS项目准备工具、严格TLS只读探测、管理员变更/验证/回退材料完成；缺实际域名/DNS与管理员范围确认 |
| 正式家庭 | 独立600配置和新初始化凭证、700空目录、5候选unit已准备并校验；未建家、未切换、未填真实档案 |
| 运行保障 | 原备份/监测定时运行成功；新一致性备份/隔离恢复通过；正式路径候选和5个旧unit回退材料齐全；异机加密缺专属条件 |
| 发布/交接 | 工具f306a26已部署，运行f919554未变，PR保持Draft；STATUS/VERIFICATION/DELIVERY_CHECKPOINT共同维护 |

结论是外部条件阻塞，尚非“可供微信家庭试用”。真正外部输入集中见STATUS；继续任务不得重新索要Key、重置8/8、回退到main旧代码或扩建审批执行器。
