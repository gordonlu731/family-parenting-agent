# 页面与真实模型验收

更新：2026年11月13日，应用0.3.1。工具就绪不代表真实模型、微信或部署已通过。

## 浏览器回归

GitHub Verify的browser作业在独立Ubuntu环境安装requirements-browser.lock，构建真实前端并运行scripts/browser_check.py。覆盖1440×1000桌面和390×844手机尺寸，使用临时虚构家庭、两个独立浏览器身份、实际ASGI接口与合成模型响应。

已观察到[运行43460550470](https://github.com/gordonlu731/family-parenting-agent/actions/runs/43460550470)通过：食材确认、菜单草稿核对后发布、买后库存与采购刷新、计划/实际分开回看、邀请加入及刷新登录保持、共享记录、无横向溢出。首次运行发现下拉框隐式标签定位问题，已补明确aria-label。后续每次变更仍需看对应提交结果，不能沿用旧运行作为新提交的证明。

该测试把浏览器同源请求桥接到TestClient，不启动公网服务、不验证HTTPS代理或微信内核。浏览器依赖不进入生产镜像。本地Chromium仍因socket权限无法启动，使用独立CI；不通过调整权限绕过限制。

CI将仅含虚构资料的截图和result.json保存为synthetic-browser-results，保留7天。截图可以发现排版问题，自动断言只覆盖脚本声明的步骤；不是全量可访问性认证。微信录音、实际输入法、来电/后台、真实设备Cookie策略等仍须真机验收。

## 可执行模型场景

默认只列场景并检查配置是否齐全，不导入应用、不打开数据库、不访问供应商：

```bash
python scripts/evaluate.py --all
```

只验证评测工具自身，可在没有真实密钥时执行：

```bash
python scripts/evaluate.py --mock-model --all
```

经安全运行配置注入MODEL_API_KEY、MODEL_BASE_URL、MODEL_ID及适用的思考模式后，显式开启少量真实请求：

```bash
python scripts/evaluate.py --call-model --cases r01,r03,m01,p01 --max-calls 5
```

--call-model可能计费；--max-calls限制供应商请求次数，不是金额封顶。默认5次，最大30次；七天菜单单次输出较长，应先少量验证。只有显式--all才选全部场景。缺配置、非法URL、已存在或不安全的报告路径在付费请求前拒绝。

每个场景使用独立临时数据库和虚构档案，强制替换APP_DB，不读取或写入已配置的家庭数据库。草稿确认、冲突和采购场景里的写入仅发生在这些测试数据库。故障场景使用注入错误并单独标记，不冒充真实供应商故障测量。

报告默认保存在数据库目录旁的evaluations/（本地通常是忽略的data/evaluations/，容器为/data/evaluations/；可用EVAL_REPORT_DIR指定），文件权限600、不覆盖既有文件；也可指定仓库外的新路径。报告在请求前创建，逐场景保存进度；包含模式、日期/时区、模型标识、供应商主机名、延迟、返回使用量、调用次数、去身份ID后的提案和机器检查结果，不输出API Key、登录令牌或供应商原始错误正文。不要把报告提交公开Git。

机器通过只证明对应结构和行为断言，不证明菜品、营养、过敏别名或中文语义全部正确。human_review保持pending，quality_certified为false；人工核对原话、提案、配料和处理方式后，在私有评测记录中补结论。evals/family-scenarios.json仍是验收定义，不由工具自动改成已通过。--mock-model的成功不能填成真实模型通过。

## 后续验收门槛

1. 安全配置实际国内模型，先连通及少量场景，再扩大到30条；失败不得只以HTTP 200为通过依据。
2. 模型结果与机器断言分别检查，记录人工发现及成本；明显问题修复后重跑相关场景。
3. 待ECS连接和HTTPS入口就绪，在隔离部署中用家人实际微信验证登录、共享、输入、保存与重新进入。
4. 满足运维准备与恢复演练后才正式试用。ECS手动部署仍暂停，不要求用户重复安装Docker。

参考：Playwright官方CI说明 https://playwright.dev/python/docs/ci 。依赖按本项目固定版本验证，不以“最新版本”宣传兼容性。
