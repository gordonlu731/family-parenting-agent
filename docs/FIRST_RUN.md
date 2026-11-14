# 首次私人试运行

适用版本0.3.2；更新2026年11月14日。用户已确认ECS连接打通并授权部署。执行者在已有SSH环境按DEPLOYMENT_PLAN自主操作，只有缺账号、入口或真实设备时再找用户。当前会话未挂载SSH身份，以下仍未在用户ECS执行。

## 先核实已有服务器

通过现有SSH配置检查当前用户、系统/Python、内存磁盘、Docker/Compose权限、已有服务及18080端口。用户已提供Docker/Compose安装成功记录，不要求重复安装或重新上传私钥。不读取量化业务资料，不改动其容器、端口、目录和数据。

## 固定代码与首次配置

在独立目录检出本次已确认完整SHA，检查对应Verify结果。已有.env或数据库必须保留；不拿旧ZIP覆盖现有Git版本。

无人值守首次生成私人配置：

```bash
python3 scripts/deploy.py configure --non-interactive --mode private
python3 scripts/deploy.py check
```

这只在.env不存在时成功；权限600、生成新的随机初始化凭证，默认绑定回环18080、关闭演示，每日全家30次模型尝试。没有MODEL_API_KEY也可先部署手工记录，不会调用模型。生产模式另需已验证HTTPS入口；选定变量及说明见DEPLOYMENT_PLAN，不把.env当Shell脚本source执行。

如果由用户在服务器私下输入配置，也保留原交互入口：

```bash
python3 scripts/deploy.py configure --mode private
```

交互输入密钥隐藏显示，可留空；现有.env拒绝覆盖。不要把密钥、初始化凭证、.env或SSH私钥粘贴到聊天或公开Git。模型默认百炼北京兼容地址和qwen-plus，仅为已有可配置默认值；实际地域、权限和模型能力必须在真实接入时验证，不能根据ECS地域推断API地域。

## 构建和启动

在预检通过且确认没有覆盖现有部署后：

```bash
docker compose -p family-parenting-agent build
docker compose -p family-parenting-agent up -d
docker compose -p family-parenting-agent ps
curl --fail --silent --show-error http://127.0.0.1:18080/api/health
```

本项目只绑定主机127.0.0.1:18080，数据使用独立持久卷；没有公网家庭网址。确认实际容器健康，核实重启策略及卷，不能将CI容器测试记成ECS启动成功。已有部署先按OPERATIONS完成备份和隔离恢复，不重复创建卷或删除旧配置。

## 模型与私人浏览器验证

配置完整时，执行1次合成JSON连通测试；然后按DEPLOYMENT_PLAN运行少量隔离评测，遇错误先修复，不自动连续重试收费请求。

```bash
docker compose -p family-parenting-agent run --rm --no-deps app python scripts/check_model.py --call-model
```

只证明HTTPS与JSON模式连通，不证明菜单质量。模型验收不打开实际家庭数据库，不计入应用内每日次数；记录请求数和使用量，不能宣称人民币硬封顶。

暂时没有域名时，通过现有SSH连接建立到回环18080的私人隧道。隧道客户端可打开http://127.0.0.1:18080；这只供私人测试，不是微信家庭入口。隔离测试使用虚构资料，正式家庭由家长核实当前月龄和过敏后再初始化，不从历史聊天自动导入。

## 给家人使用前

核实可复用的稳定HTTPS入口并配置PUBLIC_ORIGIN、COOKIE_SECURE=true；没有入口则保留私人运行并报告缺口，不临时把明文HTTP开放公网代替。入口改变后用原项目名和卷重新创建容器使配置生效。

创建并实际校验备份/恢复/监测，再按部署路径核对并安装本项目定时模板。异机加密状态单独记录，详情见OPERATIONS。至少两部微信设备完成身份、邀请/恢复、刷新保持、共享、输入和保存；录音仍只是兼容测试，ASR/TTS尚未实现。

给用户私密交付初始化办法与家庭统一入口；初始化凭证不进公开回执。管理员确认真实档案后邀请家人，不在验收中自动发布真实菜单。模型失效时保留手工记录，不能以删除持久卷方式修复问题。
