# 仓库与云端开发

源码仓库：https://github.com/gordonlu731/family-parenting-agent。维护者明确选择Public，只公开源码和虚构演示数据，家庭记录、凭证和部署配置不提交Git。项目与量化仓库分开。

本批次将0.2.1源码接到GitHub初始化提交之后。生成物dist不提交Git，由npm run build生成。新环境先读取AGENTS.md、README.md、docs/STATUS.md和docs/HANDOFF.md。

## 云端开发环境

使用Python 3.12、Node 24，安装命令：

```bash
python3 -m pip install -r requirements.lock
npm ci --ignore-scripts
npm run build
npm test
```

开发启动命令为npm run dev，仅用于隔离演示环境；真实家庭部署见FIRST_RUN.md。默认不配置模型密钥，自动检查不会产生模型费用。

仓库中包含AGENTS.md，记录权限、共享数据与私人草稿的规则和真实验证限制。开启后续开发任务时先读AGENTS.md、README.md、docs/STATUS.md、docs/HANDOFF.md。

## 当前下一任务

代码入库后，核实ECS系统及Docker/Compose状态，按FIRST_RUN.md建立私人试运行。接入真实国内模型前确认API Key和服务地域，密钥只在服务器终端隐藏输入，不在聊天中发送。随后评测实际记录抽取与菜单生成，再完成微信真机测试。当前代码未部署，48项后台测试采用模拟模型回复。
