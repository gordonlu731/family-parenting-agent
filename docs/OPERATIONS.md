# 备份、监测与升级回滚准备

更新：2026年11月14日，应用0.3.2。用户已授权部署；当前会话缺少SSH身份，仍未连接ECS、安装定时器或启用通知。执行顺序见DEPLOYMENT_PLAN。

## 一致性备份

部署后可在应用容器内运行：

```bash
python scripts/operations.py backup --source /data/family.sqlite3 --destination /data/backups --keep 14
```

本工具独立于应用启动，不导入backend.app、不执行迁移；源文件不存在直接失败，不能创建空数据库冒充备份。源连接使用SQLite只读模式，在线备份包含已提交WAL内容，不使用忽略WAL的immutable模式。

备份目录必须由运行用户拥有、权限700，文件和清单权限600；拒绝符号链接源及不安全目录。每次生成独立命名文件，验证数据库/外键、写入SHA-256清单并同步落盘。并发备份使用目录锁；新备份成功后才保留最近14份，仅清理本工具命名、格式、校验均有效的完整文件对。未知文件和无效文件不会被当作过期备份删除；清理失败保留本次完整新备份并报告失败。

每个应用实例用独立备份目录，不与量化项目混用。/data/backups与数据库仍在同一个持久卷，**只是本机明文备份**，不是异机或加密备份，也不能防止整台ECS或磁盘丢失。异机存储、加密接收方、访问权限及保留/删除策略需在正式家庭试用前另外配置并验证。

## 只读监测

```bash
python scripts/operations.py check --source /data/family.sqlite3 --backup-dir /data/backups --max-age-hours 36 --min-free-mb 256
```

检查数据库可读性、quick_check、外键与迁移版本、可用磁盘、最近备份完整性和新旧。输出去敏JSON：正常退出0，缺备份、陈旧、损坏或空间不足等退出1；不返回家庭记录或密钥。

/api/health另外检查应用数据库是否存在且迁移表可读，异常返回503与固定unavailable，不创建缺失数据库或回显服务器路径。它是轻量存活/就绪信号，不能替代备份或完整性监测；健康检查不会自动恢复数据库，也不重启其他项目。

ops/包含未激活的service/timer示例：备份按上海时间03:15加最多5分钟随机延迟，监测在启动15分钟后及每小时运行。安装前核对项目目录、Docker权限、Compose项目名和持久卷。模板不含告警接收人，也不会向任何人发消息；失败可在部署后的systemd状态/journal中观察，通知渠道另行配置。日历表达式已在开发环境解析，不代表ECS服务已验证。

## 隔离恢复检查

对本工具生成、带清单的备份执行：

```bash
python scripts/operations.py restore-check --backup /data/backups/family-backup-YYYYMMDDTHHMMSSZ-HEX.sqlite3
```

验证命名/权限、清单、SHA-256、数据库完整性和外键，再恢复到临时目录检查。命令绝不覆盖当前数据库。检测通过后仍须在目标部署环境完成一次实际恢复演练；原manage.py产生的无清单旧备份不能直接冒充本工具备份。

## 升级与回滚步骤（待部署时执行）

1. 固定并记录当前Git提交、镜像和schema版本；确认独立项目名、目录和数据卷，不操作量化服务。
2. 先创建并验证一致性备份及隔离恢复，保留当前版本镜像；部署时再次核对迁移文件，旧迁移不可修改。
3. 在隔离实例应用新版本，检查/API、家庭身份、原记录、食材和采购结果，再安排正式升级窗口。
4. 更新失败先停应用和相关定时任务，保留失败后的数据库/WAL/SHM及日志副本。没有进程持有数据库后，按匹配版本恢复到新目录/卷并核验，再切换运行；不在运行中覆盖文件，不使用down -v。
5. 仅当schema兼容时才单独回退代码。0.3.1和0.3.2无新迁移，但退到0.3.0时其镜像没有新运维脚本，定时任务也要匹配或暂停；不能只换镜像而留下失配任务。
6. 恢复后验证health、数据完整性和关键业务，记录实际提交、备份及回执。备份明文与异机加密副本按既定策略管理，不自动公开或删除。

参考：Python 3.12 SQLite在线备份 https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup ，systemd时间与时区 https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html 。
