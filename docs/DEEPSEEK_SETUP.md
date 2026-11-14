# DeepSeek官方接入：下一条可执行任务

2026年11月15日，用户确认密钥来自DeepSeek官方平台。源码0.3.4已准备适配，实际ECS仍为0.3.3/86f3f29；Key尚未注入，真实请求尚未执行。不要要求用户另外开百炼账号。

## 非秘密配置

```dotenv
MODEL_BASE_URL=https://api.deepseek.com
MODEL_ID=deepseek-flash
MODEL_ENABLE_THINKING=false
```

MODEL_API_KEY使用用户自己的DeepSeek官方Key，不能放在本文、聊天、Git、命令行参数或公开日志。API Key属于账号，不应根据旧聊天猜某个历史模型仍可用；实际可用ID先用账号/models列表核实。当前官方文档列出deepseek-flash和deepseek-v4-pro，本任务默认先用前者。

现有后台使用/chat/completions和response_format=json_object。DeepSeek思考参数是thinking.type=disabled/enabled，不能发送千问enable_thinking。0.3.4按官方host转换MODEL_ENABLE_THINKING，留空也默认非思考；其他供应商保持原参数。不要只改.env而继续运行缺少适配的旧代码。模型Base URL不要包含末尾/chat/completions。

## 交给已连接family-dev的Codex执行

1. 同步部署分支并读取STATUS、HANDOFF、VERIFICATION和本文件；保留旧源码、私密配置、unit、运行库与备份。读取当前用户unit确认实际发布/数据路径，不拿旧文档中的示例路径覆盖现有配置。
2. 给用户准备一次可实际操作的隐藏输入Key方式，用户只需输入一次。如果已有可用的本项目安全凭据绑定，则直接使用，不要求再粘贴。缺少绑定时由用户在私密配置/终端隐藏输入，不能索要聊天发送。不要以Key为脚本参数、环境完整输出或截图；先留存权限600的原配置，再仅更新四个MODEL字段，保留初始化凭证、库路径、Cookie、每日限额等。
3. 先把安全配置加载到新的已验证源码/venv子进程，读取模型列表核实选型，再运行check_model.py --call-model的1次固定合成JSON请求；使用user_service.environment加载本项目.env，不source文件，不读取量化凭据。没有正确Key或网络失败时留存去敏原因，不自动无限重试。
4. 继续evaluate.py四条核心场景r01/r03/m01/p01并按需要复核短菜单。全轮真实Chat调用最多8次，包含连通、失败和重试，不因新会话而重置；当前0次。检查输出长度/finish_reason、空白内容、JSON结构及原话依据。空白JSON明确失败，不当作成功，不自动重试加费。
5. 真实评测始终使用工具的隔离虚构数据库；报告私密保存，不写入现有家庭事实。读写业务仍人工确认。先核实配置、做适用测试并备份，再发布固定代码SHA；只重启本项目，更新原生备份/监测路径并单次验证。不因为接模型而改公网、换数据库、重新建家或重配SSH。
6. GitHub仅回传模型ID、参数、合成检查结果、调用次数、延迟、实际使用量和待人审项。无可核实费率时不编人民币费用。成功后继续既有文字闭环和HTTPS准备，域名未定不阻塞服务器内模型验收。

## 官方依据（2026年11月15日核对）

- 接口与模型：https://api-docs.deepseek.com/
- 思考参数：https://api-docs.deepseek.com/api/create-chat-completion/
- JSON输出：https://api-docs.deepseek.com/guides/json_mode/
- 账号模型列表：https://api-docs.deepseek.com/api/list-models/

文档要求JSON提示、合理max_tokens，并指出返回可能只有空白。合成测试只能证明协议与业务规则，不替代真实菜品质量或微信验收。这里没有声称已获得用户Key、账号余额、可用模型或真实连通证据。
