# Tailscale虚构数据试用：最小操作包（尚未启用）

## 2026-11-16 实机评估

Tailscale1.104.5、状态Running、MagicDNS开启；本节点DNS名称存在。Serve/Funnel配置均为空，无已有分享需要覆盖。当前CertDomains为空，Self.CapMap未含Funnel能力；不能据此声称HTTPS/Funnel已启用。OperatorUser未配置，family-dev非root，不能擅自修改daemon/策略。完整节点/账号状态只在服务器家庭用户私密目录，不进入公开Git。

**尚无可用测试URL。** 有节点DNS名不等于Funnel公网DNS和证书已部署；普通手机/微信可达性尚未测试。

## 一次集中需要用户处理的事项

1. 由现有tailnet Owner/Admin在控制台DNS设置核实/开启HTTPS Certificates；保持MagicDNS和其他配置。启用HTTPS是tailnet级功能，签发公开证书可能公开节点/tailnet DNS名称，先确认接受该影响。
2. 在Access controls中合并**仅本ECS Tailscale IP**的`funnel` nodeAttrs，保留原规则；本节点专用JSON片段已保存在服务器私密操作包。不要点击默认的全体autogroup:member授权，不改节点标签/所有权/SSH/ACL，不授予family-dev整个daemon的operator权限。策略编辑器须校验通过，再由执行者只读确认本节点能力已下发。
3. 当前后端仍在中国内地ECS。阿里云文档要求内地服务器网站公开访问前满足接入备案条件，Tailscale条款也要求遵守适用规则。平台分配地址不是自动豁免；在未有明确适用证据时，向接入商确认该“仅虚构数据、临时应用测试、通过Tailscale Funnel中继分配HTTPS地址”的分享方式是否允许，再授权现有ECS管理员执行下面唯一映射。若条件不允许，保留私有预览，不反复更换隧道。

可直接使用的接入商问题：
> 本ECS仅运行虚构数据应用，监听127.0.0.1:18080，拟通过出站Tailscale Funnel中继用平台ts.net HTTPS地址临时给家人测试；不开放ECS公网18080、不录入真实家庭资料。请确认该方式是否允许用于本账号当前实例的临时公网测试，若有前置条件请明确说明。

不需要购买域名、不申请新云资源；控制台变更和root映射需要一次明确确认，用户选择“先试用”未授权扩大整个tailnet。

## 已准备的应用配置（未应用）

preview_config.py prepare已生成服务器600权限候选.env及原配置备份、哈希计划，只改PUBLIC_ORIGIN为节点HTTPS origin、COOKIE_SECURE=true、MODEL_API_KEY为空。

禁用Key确保家人点击AI按钮也不会增加真实调用；不是更改原Key或每日额度。原初始化凭证、数据库路径、家庭身份、限额均保留，DEMO_MODE仍false。新/原配置均私密；不要cat完整.env到聊天或日志。

申请控制台/管理员动作前仅prepare，不apply、不重启应用。控制台能力及接入条件确认后，执行者用现有family-dev运行apply，并检查健康200/model_ready=false，再让现有root管理员运行映射。不是新审批执行器，不增加sudo或operator。

## 管理员唯一映射（确认条件后执行，目前不要运行）

先确认状态仍Running、CertDomains含本节点、已下发Funnel能力，Serve/Funnel仍空。发生并发已有映射即停止，不reset。

```bash
tailscale funnel --bg --https=443 http://127.0.0.1:18080
tailscale funnel status --json
```

只能这一项HTTPS443→现有育儿18080；不用--tcp、不分享文件/目录、不代理其他端口、不修改安全组或sshd，不触碰量化项目。禁止接受CLI可能提出的默认全体成员授权；条件不足直接停止。私密操作包中包含不变性预检和精确节点信息。

配置成功后才从真实命令结果取得URL。执行者从服务器外严格CA验证、health、静态页面、匿名导出401、未登录拒绝、邀请/登录Secure/HttpOnly/SameSite和CSRF/Origin；应用model_ready必须false。Funnel未承诺提供HTTP80跳转，不能把普通Caddy探测中的HTTP跳转要求直接套用并因此修改ECS入站。

## 撤销和回退

管理员仅撤同一映射，不reset，不动其他节点：

```bash
tailscale funnel --bg --https=443 http://127.0.0.1:18080 off
```

先确认此443映射仍只指向本项目，若别人已改动则停止，由管理员处理。执行者再以family-dev用preview_config.py restore恢复原.env和原回环origin/cookie/Key，仅重启本项目并核对health；不回滚、删除或覆盖数据库/备份。控制台仅移除本次单节点funnel条目，是否撤HTTPS功能先核实其他节点是否在用，不整体关停或覆盖原策略。

## 可选私有回退

已有SSH本地转发可供本人电脑访问http://127.0.0.1:18080；不改现有连接和host pin，不绑定0.0.0.0。Tailscale Serve若另行批准可在tailnet内预览，但访问者需要Tailscale/tailnet权限，不能称作普通微信公开网址，不默认要求老人安装。

## 成功后的手机一步

入口建成且外部验证通过后，用户使用普通移动网络、关闭Tailscale，分别在系统浏览器和微信打开统一URL；使用私发单次邀请进入虚构家庭。记录成功/失败及页面提示，不发Key/邀请截图。界面只测试手工文字、共享、历史复用、回看，不录入真实宝宝资料，不调用AI；国内微信真实可达性以此结果为准。

## 官方依据

- https://tailscale.com/docs/features/tailscale-funnel （版本、MagicDNS、HTTPS、nodeAttrs及公开接收方无需Tailscale）
- https://tailscale.com/docs/reference/targets-and-selectors （IP可作为nodeAttr target，限制到本节点）
- https://tailscale.com/docs/reference/tailscale-cli/funnel （443及精确off撤销，不reset）
- https://tailscale.com/terms （2.5适用规则）
- https://help.aliyun.com/zh/icp-filing/basic-icp-service/product-overview/icp-filing-requirements-for-a-regular-website （内地托管、IP及HTTP/HTTPS接入要求；不宣称临时中继豁免）
