# DeepSeek官方接口：已配置，后续不要重新录入

更新2026年11月16日。本项目已接入DeepSeek官方API并部署应用0.3.5 / f919554cc2e9462f34ac7e75baf261b5531e9d6b。Key已通过服务器隐藏输入存入权限600的私密配置，鉴权与JSON连通成功；不在聊天、Git、命令行或公开日志展示，不再次要求输入。

## 已验证的非秘密配置

```dotenv
MODEL_BASE_URL=https://api.deepseek.com
MODEL_ID=deepseek-flash
MODEL_ENABLE_THINKING=false
```

实际请求使用thinking.type=disabled，response_format=json_object。不要改回千问enable_thinking；不以模型名称猜第三方平台参数。四条核心真实场景r01/r03/m01/p01最终通过，r01数量/名称重复问题已在0.3.5修复并复测。

## 当前验证额度与限制

本轮账本共8次官方请求：models1、Chat7，含失败场景和复测，已全部使用。此为本轮验证请求限制，不是账户余额或应用每天的调用次数。没有新的明确额度前不追加真实验证、不重置账本、不无限重试；本次整理不访问账户或查询余额。

最后一次真实换餐虽然HTTP200，但后续两人流程机器断言失败，具体位置未定位且回复正文未保存。先按HANDOFF增强私密步骤诊断并离线复放，不把另一份m01菜单的离线成功当作该次真实换餐通过。输出语义、菜单多样性和宝宝适用仍需家长人审。

## 后续执行者

- 在现有family-dev/native-user-service上工作，保留配置、数据、备份和原私密账本，不重建家庭。
- 新发布/迁移时用当前user_service.environment安全加载本项目配置，不source .env，不复制其他项目凭据。密钥已经存在时不要运行首次configure覆盖配置。
- 先做不收费的离线诊断和测试；需要新真实调用时先列明确验证目标及最少次数，取得新增额度后再执行。报告保存私密，GitHub只保留去敏结果。
- 正式HTTPS与微信未完成，域名不阻塞离线业务工作；不能把model_ready=true等同所有业务/营养质量验收通过。

## 已核对的官方依据

- 接口与模型：https://api-docs.deepseek.com/
- 思考参数：https://api-docs.deepseek.com/api/create-chat-completion/
- JSON输出：https://api-docs.deepseek.com/guides/json_mode/
- 账号模型列表：https://api-docs.deepseek.com/api/list-models/

2026年11月15日接入时核对。配置和真实测试详细过程保留在VERIFICATION历史，包括Key尚未录入的早期状态；不得用早期状态覆盖本页当前事实。
