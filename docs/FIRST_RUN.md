# 首次私人试运行

适用版本0.2.1。用户已有至少4GB的上海ECS、暂无域名。本指南先做管理员私下测试；微信家庭入口、HTTPS和发布条件后续完成。当前没有访问用户服务器，也未部署或连接真实模型。

## 1 先看服务器环境

在ECS终端分别执行下面五行，把输出反馈给开发者即可，不包含密钥：

```bash
cat /etc/os-release
python3 --version
docker --version
docker compose version
free -m
```

不因命令缺失就直接安装；先根据系统和既有项目确认安装方式。不要把ECS密码、SSH私钥、.env或模型API Key发到聊天。已有量化服务保持原有配置，育儿助手单独存放。

## 2 准备代码和密钥

将源码ZIP上传到ECS的独立目录并解压，进入family-parenting-agent目录。不要覆盖旧版.env或数据库。下面的部署工具只需Python标准库；本包构建前端的Docker步骤另需访问镜像及依赖源，具体在ECS验证。

默认使用阿里云百炼北京地域的qwen-plus普通业务API，Base URL为 `https://dashscope.aliyuncs.com/compatible-mode/v1`；官方仍兼容此地址，同时推荐业务空间专属地址。配置工具允许粘贴控制台给出的完整Base URL。百炼API Key和服务地址必须在对应地域，ECS在上海不表示百炼也选上海。模型可用性和费用以实际账号为准。

参考官方文档：
- [兼容接口与地域](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)
- [获取API Key](https://help.aliyun.com/zh/model-studio/get-api-key)
- [JSON结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output)

确认Docker与Compose可用后，在交互式终端执行：

```bash
python3 scripts/deploy.py configure --mode private
python3 scripts/deploy.py check
```

按提示输入密钥时屏幕不会显示字符；可以留空，先只试手工记录。配置工具不覆盖已有.env，不调用模型、不启动服务。默认端口18080、每天全家30次调用；端口占用时先确认是否本项目已运行，再决定是否另选端口。

`check`输出可发给开发者；.env内容不要截图或复制到聊天。它只检查运行条件，不验证模型凭证、证书、对外网络、ICP备案或微信体验。不要将.env当Shell脚本source执行。

## 3 构建并做一次模型测试

```bash
docker compose -p family-parenting-agent build
```

可选的真实模型连通测试会发起一次可能收费的合成样例请求，不读取宝宝资料，不计入应用内家庭每日次数。仅在需要且配置完整时执行：

```bash
docker compose -p family-parenting-agent run --rm --no-deps app python scripts/check_model.py --call-model
```

测试通过只证明HTTPS及JSON模式可用，不证明育儿场景质量。qwen-plus默认关闭思考模式；其他模型须核对是否支持该参数。结构化生成保留输出长度上限控制单次调用规模，若被截断则明确失败，不写记录或发布菜单；真实菜单验收时需检查1/3/7天长度。

然后启动此项目：

```bash
docker compose -p family-parenting-agent up -d
docker compose -p family-parenting-agent ps
```

本项目仅绑定主机127.0.0.1:18080，未开放公网安全组。健康检查成功不表示模型可用。以上命令尚未在用户ECS执行，镜像下载、依赖安装和运行结果以实际服务器为准。

## 4 无域名时从自己的电脑测试

在自己的电脑终端建立SSH隧道，把用户名和IP换成ECS现有登录信息：

```text
ssh -N -L 18080:127.0.0.1:18080 ECS用户名@ECS公网IP
```

保持该终端连接，在同一电脑浏览器打开 `http://127.0.0.1:18080`。这只通过现有SSH登录提供私人访问，不是微信中可给全家使用的网址，不新增公开Web端口。

在服务器私下查看.env里的初始化凭证，输入页面的“创建我的家庭”。不向其他人转发该凭证；完成后创建接口不能重复建立家庭。首次使用核实宝宝当前月龄和过敏情况，不沿用旧聊天中的历史月龄。

验证顺序：手工记一餐→刷新后仍在→第二浏览器独立加入→彼此看到同一记录→一句话整理后核对保存→生成一天菜单草稿→编辑并发布。录音仍只是兼容性测试。

## 5 给家人使用前

私人测试完成后，再配置稳定域名、HTTPS及部署所需手续，在.env中改为真实HTTPS PUBLIC_ORIGIN和COOKIE_SECURE=true，并让代理指向实际APP_PORT。修改模型或入口配置后用原项目名重新创建容器使配置生效。家人通过正式地址各自的邀请链接加入，做真实微信验证。

模型密钥失效时手工记录仍可用。数据在持久化卷，不能以删除卷方式修复问题。若已有旧部署，先确认原项目名、卷和端口并完成一致性备份，继续沿用原持久化数据；当前包不自动迁移到另一台服务器或另一个Compose项目。
