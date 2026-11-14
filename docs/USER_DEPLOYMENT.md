# 非root开发身份的私人部署

2026-11-14实机更新：已用native-user-service完成私人回环部署与虚构持久化/重启/备份恢复验收，
固定代码e1a499296952cd86e94a8cd34a5aa10aac8430b5；完整证据与限制见VERIFICATION。
首次unit被真实systemd拒绝，现移除引号WorkingDirectory，由run启动器切换目录；真实解析器回归通过。
已部署环境须保留配置/数据库/备份，不再执行首次建家。本文件后文的“尚无ECS证据”为部署前历史。

用户已选定独立Cloud环境和非root项目身份。管理员初始化另行集中审核，当前没有ECS安装/SSH验收证据。
本仓库只保存通用育儿应用工具；不保存服务器地址、其他项目方案、真实家庭信息或密钥。

管理员初始化完成后，日常Git/Shell/Python/Node、依赖安装、测试、项目部署/日志/备份可自主执行。
不使用宿主机Docker组/socket、不执行sudo、不改变其他项目服务。仍只用127.0.0.1:18080。

## 部署选择

优先使用属于当前用户的Rootless Docker；`docker info`必须包含rootless，
`DOCKER_HOST`为`unix:///run/user/$(id -u)/docker.sock`。不得为修复连接而改用/var/run/docker.sock。
原compose.yaml、项目名family-parenting-agent和持久卷保持；先按DEPLOYMENT_PLAN实查资源/卷/端口。
Rootless不具备条件时，可以使用下面原生systemd用户服务；两种模式不能同时占用18080。

原生模式与容器模式是独立数据位置，不自动搬迁或混用。若已有部署或数据库，先识别模式和备份，
不得通过切换模式绕过升级/覆盖保护。没有现有部署时，新建独立发布目录和数据目录即可。

## 原生模式（当前非root用户执行）

进入核实过的固定源码SHA目录。Python3.12、Node22.12+/24由当前用户使用或安装，不要求新增root权限。
这不是要求用户逐条运行；由具有新SSH身份的Codex执行并收集真实证据。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm ci --ignore-scripts
npm run build
# 仅首次没有.env时；已有配置必须保留。
.venv/bin/python scripts/deploy.py configure --non-interactive --mode private
.venv/bin/python scripts/user_service.py install --data-dir "$HOME/data/family-parenting-agent"
systemctl --user is-active family-parenting-agent.service
curl --fail --silent --show-error http://127.0.0.1:18080/api/health
```

运行时只读取本项目私有.env，显式允许的字段进入后端，容器内APP_DB=/data/...不会用于宿主机。
真实DB固定在指定私有目录family.sqlite3。unit不含模型Key或初始化令牌，日志不含访问日志；
读取日志仍应在ECS分析，只向GitHub回传去敏摘要。配置私有权限/符号链接异常立即拒绝。
install只写当前用户的systemd unit，更新会保留旧unit并restart本项目；不写系统unit或调用root服务。

root初始化需已启用当前用户manager/linger和资源/凭据隔离；这些不是本工具的普通安装权限。
若未具备，停止部署并记录具体缺口，不sudo、加Docker组或修改认证。

## 验收与备份

实际SSH身份、metadata访问拒绝、系统与其他用户文件不可读、正确用户cgroup、模型凭据私有、
回环监听、/api/health、虚构数据持久化和隔离恢复均须实测。Rootless模式还需容器路径隔离验收；
不能将HTTP403、连接超时或CI绿当成IMDS阻断证明。

```bash
.venv/bin/python scripts/operations.py backup --source "$HOME/data/family-parenting-agent/family.sqlite3" --destination "$HOME/backups/family-parenting-agent"
.venv/bin/python scripts/operations.py check --source "$HOME/data/family-parenting-agent/family.sqlite3" --backup-dir "$HOME/backups/family-parenting-agent"
```

restore-check按OPERATIONS.md选择实际新备份，绝不恢复覆盖运行库。正常备份和保留为本项目常规操作，
不可逆删除数据/所有备份仍需批准。没有正式库或备份时报告缺失，不伪造通过。

回滚代码时先备份、停止本用户unit、回到兼容的固定源码/venv重新install；保留数据目录、旧unit与失败日志。
不原地回滚schema、不删除容器卷。真实模型、稳定HTTPS、微信真机仍按DEPLOYMENT_PLAN后续阶段验收。

本轮只新增部署工具和合成测试，应用/API版本仍0.3.2；当前ECS部署、模型和微信结果均未取得。
