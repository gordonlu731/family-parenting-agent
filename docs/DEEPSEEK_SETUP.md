## 2026-11-15 DeepSeek已接入并部署0.3.5

当前实际服务为0.3.5 / f919554cc2e9462f34ac7e75baf261b5531e9d6b，native-user-service active/enabled、仅127.0.0.1:18080，health200，model_ready=true。用户Key已通过服务器隐藏输入录入，600配置；原初始化凭证、Cookie、限额和数据位置保持。不得再次索要或输出Key。

官方/models鉴权成功，账号返回deepseek-flash、deepseek-v4-pro；实际选择deepseek-flash，thinking.type=disabled、response_format=json_object。固定JSON连通通过；r03/m01/p01真实核心场景通过。r01首次将“半碗米饭”混为名称，已在0.3.5分离提示/schema并增加服务器拒绝，复测r01通过。现有家庭库未用于评测，全部事实写入只在临时虚构库。

预算已耗尽并持久化：共8次官方请求（/models1、Chat7；其中包含首次失败场景及复测），所有HTTP200且Chat finish_reason=stop，没有自动重试。返回使用量合计prompt4900、completion1343、total6243 tokens；费用未核实，不编人民币金额。后续会话不得重置计数或继续收费请求。

最后一次真实换餐返回200，但两人流程中的机器断言失败，具体断言尚未定位；没有保存该回复正文，不能宣称真实换餐完整验收通过。随后仅用已保存的m01菜单在新临时实例离线复放：私人草稿、明确确认、采购不扣库、照护者买后总量、计划与实际不同、两日回看通过，供应商请求0。该复放不替代真实换餐验收。下一步先增强私密逐步诊断，若需新真实请求，须取得新的明确额度。菜单三餐较重复，菜品质量与营养适用仍需人审，机器通过不是质量认证。

本地/ECS构建及115项模拟测试通过；[Verify43732056092](https://github.com/gordonlu731/family-parenting-agent/actions/runs/43732056092)构建、桌面/手机browser、container均success。新增回归重现数量混入名称并确认无草稿/事实写入。发布前在线备份/恢复通过，原有10份有效备份另存私密校验副本保全；原源码/venv/unit/配置和库保留。发布后业务摘要不变、所服务静态资源与构建一致、用户backup/check任务成功且timer继续开启。未重新初始化、未写真实档案、未改公网或量化项目。

HTTPS/微信与异机加密仍待外部条件；域名不阻塞此次服务器内真实API验证。以下为此前历史。

## 2026-11-15 本次连接与隐藏录入准备

已同步源码2d63d1821654e56aab7036ae606edb1cd15c965f，实机仍为0.3.3/86f3f29，专属SSH核对服务运行且配置600、Key为空。已暂存新版源码并准备服务器私密隐藏输入工具；以虚构值验证仅改四个模型字段、原配置保留、600权限及重复执行不再提示输入。此检查不是用户Key或API连通验收。

用户在本会话给出的既有ECS终端命令隐藏输入一次后，Key只写入新版暂存配置；原运行版配置保持，避免旧适配器直接启用DeepSeek。工具保留私密配置备份及全轮8次预算状态，不重置已有计数。当前真实Chat请求仍0次，未发/models请求、不重启服务、不改库。下一步只检查录入状态，再用新适配器读取账号模型列表、执行1次连通及核心评测；不要让用户再次贴Key或将配置内容上传Git。

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
