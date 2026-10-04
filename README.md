# preset: scrape —— Web 采集与逆向

油猴脚本（UserScript）/ 网站接口逆向 / 数据采集与自动化开发用的 DSH agent preset，
外加一套 mitmproxy 抓包分析工具（`scrape-toolkit`）。

> 本文里的占位符：`<仓库根>` = 你 clone 的这份仓库；`<profile>` = 你的 DSH profile 目录
> （本机实测是 `C:\Users\<用户名>\.dsh\profiles\desktop`）；`<PKG>` = 装进 profile 后的那份
> 包副本 `<profile>\node_modules\@emo-bird\dsh-preset-scrape`。

## 目录结构

```
<仓库根>\
├─ package.json            ← DSH bundle 清单（dsh.bundle.patch 指向 cordis.patch.yml）
├─ index.js                ← ⚠️ 占位入口，别删（见下节「为什么有个空的 index.js」）
├─ cordis.patch.yml        ← preset 声明 + persona 全文
├─ lean-agent.js           ← 本 preset 专用的 lean_agent 工具插件（零依赖）
├─ README.md               ← 本文件
├─ skills\                 ← 只在本 preset 会话里可见的技能目录
│   ├─ scrape-toolkit\
│   │   └─ SKILL.md        ← 脚本说明书（技能发现认的标准布局）
│   └─ subagent-brief\
│       └─ SKILL.md        ← 给「被委派的子代理」（尤其本地小模型）的环境手册
├─ tools\                  ← Python 抓包分析脚本
│   ├─ flow_probe.py       ① 体检：能不能读、多少条、哪些域名
│   ├─ flow_index.py       ② 请求总表（idx/method/status/体积/host/path）
│   ├─ flow_slice.py       ③ 按 (host, 路径首段) 分片，每片约 24KB，喂本地模型
│   ├─ flow_extract.py     ④ 单条请求导出成精简 JSON
│   └─ flow_replay.py      ⑤ 复现请求（默认 dry-run，加 --send 才真发）
├─ _selftest\
│   ├─ load_test.mjs       ← 预检：模块能否加载 + schema 是否被真校验器接受
│   └─ preset_acceptance_prompt.md  ← 新会话验收用的提示词模板
```

**仓库根就是包根**（`package.json` 在根上），所以既能本地装、也能直接从
GitHub 当 git 依赖装。

`skills\` 只在装了本 preset 的会话里生效，靠 preset 里 `skill-filesystem` 那一行的
`config.customSkillDirs` 指过来；该行用 `!!js` 按**包名**解析出包目录再拼 `skills`，
所以本地装 / GitHub 装 / link 装都自动指向同一份包。其他会话看不到 `scrape-toolkit`，
也不用往 `$DSH_HOME\skills\` 塞指针。用户级的 `local-llm-offload` 不受影响。

### 为什么有个空的 `index.js`（别删）

它不是死代码，**删掉会重新弄坏市场里的「更新」按钮**。

本包是 **bundle**：loader 从来不 import 包的根，真正干活的是 `dsh.bundle.patch` 指向的
`cordis.patch.yml`，而 patch 里唯一 import 本包的地方是子路径
`@emo-bird/dsh-preset-scrape/lean-agent.js`。所以从「能不能跑」的角度，`index.js`
确实可以不存在 —— 本仓库长期就是那样，而且工作正常。

但插件市场（`dshmarket`）在**安装和更新**时会先过一道
`hasLoadableEntry()`（`dshmarket/lib/profile.js` 的 `entryArtifactExists`），它只看
`package.json` 的 `main` / `exports`，两者都没有时**兜底去找 `index.js`**；三个都没有
就判定「这个包没有可加载的入口」，于是**自动回滚这次更新**并报：

> `@emo-bird/dsh-preset-scrape 更新后缺少入口文件（package.json 的 main/exports 指向的文件不存在），且未能验证恢复原版本文件；请先检查该 profile，再重新启动。`

实测判据（用 `dshmarket` 真实的 `hasLoadableEntry` 跑）:

| 包根内容 | `hasLoadableEntry` |
| --- | --- |
| 无 `main` / `exports` / `index.js`（本仓库旧状态） | **`false`** → 更新被回滚 |
| 带 `index.js`（现状） | **`true`** → 更新正常 |

注意它**不影响手动装**：手动 `install_bundle` 或 `pnpm add` 后能正常启动，因为 loader
走的是 patch，不查入口文件。所以症状是「包能用，但那颗更新按钮一点就失败」。
把包删了重装能临时绕过（这也是为什么之前「删除重装」能成功）—— 本文件才是根治。

## 安装

> 下面说的 `plugin_manager` 是**宿主平面**的工具，**不在本 preset 的工具表里**
> （preset 自己关掉了 `tool-plugin-manager`）。所以「安装 / 重装」这一步要在
> **别的 preset 会话**（例如 `standard`）里做，或者用 GUI 的设置界面。

### 本地装 / 重装

用 `plugin_manager` 工具，`action: install_bundle`，`target` 填**仓库根目录的绝对路径**：

```
<仓库根>
```

### 从 GitHub 装

`target` 填仓库地址，三种写法都认：

```
https://github.com/emo-bird/dsh-scrape-preset.git
github:emo-bird/dsh-scrape-preset
https://github.com/emo-bird/dsh-scrape-preset.git#<tag 或 commit>
```

`customSkillDirs` 按**包名**动态解析（见 `cordis.patch.yml` 里 `skill-filesystem` 那一行），
所以无论本地装、GitHub 装还是 link 装，技能目录都自动指向「当前真正生效的那份包」，
**不需要手工改路径**。

它会自己跑包安装并写入 profile 的 bundle 列表，**不要**手动改 profile 的
`package.json` 或 `cordis.patch.yml`。

⚠️ **复制安装，不是链接。** 实测 `<PKG>`（`<profile>\node_modules\@emo-bird\dsh-preset-scrape`）
是**实体目录**（`LinkType` / `Target` 均为空，`Attributes: Directory`），所以它是
**安装那一刻的快照** —— 改了仓库不重装，profile 里跑的还是旧版，**而且不会报错**。
详见下面「已知限制」。

装完在 Web GUI 新建会话时选「**Web 采集与逆向**」即可。

## 这个 preset 和 standard 的差别

保留：`pwsh` / 文件工具 / `jobs` / `skill` / `ask_user_question` / `todo_write` /
`web_search`+`web_fetch` / `present` / plan mode / 上下文压缩 / `workflow`。

不挂（`disabled: true`）：

| row | 为什么 |
|---|---|
| `tool-subagent` / `tool-subagent-fork` | 委派首选 `lean_agent`，多阶段编排走 `workflow` 的 `agent()` |
| `tool-subagent-control` / `tool-subagent-list-agents` | 同上 |
| `command-goal` / `tool-goal` | goal 是「自动续轮、无人值守」，与「每个决策点都要用户拍板」冲突 |
| `tool-plugin-manager` | preset 装好之后它自己不需要改插件 |
| `tool-ralph` | 自动迭代循环，同上 |

**注意**：`subagents` 注册表和 `spawn` provider 在**宿主平面**，preset 只挑「工具」。
所以不挂 `tool-subagent` **不影响** `workflow-ptc` 的 `provider: spawn`。

⚠️ **这只关掉 preset 自己那棵树。** 如果 profile 层的其它 bundle 也注册了同名工具行，
它们照旧会出现在根平面、所有 preset 都能看见 —— 本 preset 管不了。
（曾经踩过这个坑：profile 自己的 `cordis.patch.yml` 里有一大段机器生成的
`- id: X` / `disabled: false`，把根平面重新打开，于是工具数从 32 涨到 43。
判据很简单：**顶层新建会话里数工具**，本 preset 的预期是 32 个左右。）

## persona 里固化了什么

见 `cordis.patch.yml` 的 `persona.config.prefix`（约 7500 字符）。要点：

> **上下文纪律（最高优先级·硬规则，显式覆盖一切「自行判断」）** —— persona 里单列一节，
> 与该文件其它条文的宽松表述冲突时，一律以它为准：
>
> 1. 预计超过 **4K tokens** 的单次输出（HAR / `.flow` / HTML 全文 / 长文档 / 构建与测试全量输出 /
>    用户粘贴的日志与探针输出）**一律先落盘到 `local/`**，再交 `lean_agent` 摘成 **≤400 字**
>    （只回：结论 + 关键字段 + 文件行号 + 疑点），主代理只读这份摘要。
>    能预判的大输出直接 `... > local/x.txt` 重定向，根本不让它进上下文。
> 2. **项目文档禁止整份读**（需求 / 开发 / 交接 / 手测清单）：先 `grep` 定位，再用 `read` 的
>    `offset`/`limit` 只读命中段落；同一份文档每会话最多整段读一次。
> 3. 每轮手测反馈处理完（改完 + commit + 汇报）**立刻 compress** 该轮全部工具输出；摘要必须含
>    真因、改动文件与函数签名、验证数字（用例数/构建号/字节行数）、提交 hash、未决项。
> 4. 手测清单 / 文档草稿 / commit message / 日志聚类 / HTML 与选择器结构分析 / 正则与样板代码
>    —— 默认先由 `lean_agent` 起草，主代理只核对与 patch。
> 5. 用户粘贴的长文本先落盘，再按第 1 条走；**同一份原文不得在上下文里出现第二次**。
> 6. **任何文件都不得整份读入**：先 `grep` 定位，再 `read` 的 `offset`/`limit` 分段读，
>    单次 **≤200 行**。压缩 HTML / 单行 JSON / `*.min.js` 这类「单行很长」的文件按行分页没意义，
>    先用 `pwsh` 把长行切开落盘成小文件再读。
> 7. **同一动作失败两次即停**：原样回报错误全文，不许换写法试第三次（换引号 / 换参数顺序 /
>    换等价工具 / 包 `try/catch` / 拆成两条命令都算第三次）。
> 8. **复读自检**：同一句话出现第三次即视为复读 —— 立即停止并回报「已复读，最后一次有效结论
>    是什么」。换词重说同一个结论也算。

1. **开场协议**：检查 `docs/开发文档.md`、`docs/环境文档.md`、`docs/交接文档.md`；
   缺环境文档就自行探测（node/python/mitmproxy/端口/Edge/LM Studio），只问探测不到的。
2. **交互铁律**：用户不拍板不动手；每个决策点给 2~3 个方案；出现任何非预期情况
   （接口对不上、结构不符、依赖装不上、抓包被拦）**立即停下上报**，严禁自己绕过。
3. **git**：新功能必须开分支；任何修改都要 commit。
4. **测试**：档1 纯函数冒烟（node assert）/ 档2 接口契约冒烟 / 档3 UI 由用户手测；
   风险接口不做自动化测试。
5. **省 token**（原则层；具体阈值与强制动作见上面那节「上下文纪律」）：抓网页用 `pwsh` 落盘而非 `web_fetch`；抓包绝不整份读入，先 index 再 slice；
   高 token 低难度活儿在 preset 会话里走 `lean_agent`（provider/model 已配好，**不用再传**），
   需要多阶段编排（pipeline / 子代理串联 / 脚本里循环）时才用 `workflow` 的 `agent()`，
   且那时要显式写 `provider` / `model`。
   ⚠️ persona 里还写死了一条：**`agent()` 的 `schema` 在本机恒返回 null**（本地 9B 不会主动调用
   `structured_output`，driver 于是把 `completed` 改判成 `error`）—— 要结构化输出走 `lean_agent`
   的 `schema`，或干脆在 prompt 里要求「只回 JSON 文本」自己 parse。
6. **隐私**：抓包可能含真实姓名/手机号，只喂本地模型，绝不喂云端。
7. **委派**：首选 `lean_agent`；用 `agent()` 时必须让子代理先加载 `subagent-brief` 技能；
   不用 subagent 工具、不用 Agent Teams、不用 ssh、不开 computer use。

## 子代理环境手册（`subagent-brief`）

`skills\subagent-brief\SKILL.md` 是写给**子代理**（尤其 9B 本地模型）的手册：Windows 受限沙箱
哪些能碰哪些碰不得、pwsh 5.1 没有 `&&`、`.NET` 调用会被拦且**可能不报错只给空结果**、
只读沙箱里写文件必被拒、`read_image` 读不了抓包、以及「抓包别手搓，直接调 `tools\` 里的脚本」。
它还写明子代理自己的**运行预算（上下文 64K / 单次回复上限 5120 tokens）**、读文件的 200 行上限、
「同一动作失败两次即停」与「复读自检」这三条硬规矩。

它有两条投递路径：

| 委派方式 | 子代理怎么拿到手册 |
|---|---|
| `lean_agent` | **自动**。`lean-agent.js` 在注册时读取同包的 `skills/subagent-brief/SKILL.md`，去掉 frontmatter、把 `<TOOLS>` 替换成绝对路径，然后追加到每个子代理的 persona 后面。子代理不需要调用 `skill` 工具。设 `config.brief: false` 可关闭。 |
| `workflow` 的 `agent()` | **不自动**。`agent()` 只认 prompt/provider/model/schema，注入不了任何东西。所以 persona 里写死了硬规则：用 `agent()` 委派时，prompt 第一行必须写「先用 skill 工具加载 `subagent-brief` 技能，并严格遵守它」。 |

两条路的**实测差异**（这决定了什么时候必须走 `lean_agent`）：

| | `lean_agent` 子代理 | `workflow` 的 `agent()` 子代理 |
|---|---|---|
| persona | 一句英文短句（**覆盖**父 preset 的） | **整套中文 persona 原样继承**（约 9000 字符） |
| 环境手册 | **自动注入** | **不注入**，要在 prompt 里让它自己加载 |
| 工具表 | 调用方点名（纯文本变换活儿 **0 个**；上下文工具也**默认不给**） | **全部 32 个**，含 `lean_agent` + `workflow` |
| 能否继续委派 | **不能** | **能**（递归深度上限未测） |
| 撞上单次回复上限时 | 回传**部分输出** + `⚠️ ... TRUNCATED (stopReason=max-tokens)` 标记 | 整轮报错失败 |

### 子代理的上下文工具（**默认不给**，要就点名）

`billion-context` 提供 5 个工具：`compress` / `decompress` / `search_context` / `acp_status` /
`acp_cache`。**默认不放进子代理的白名单**（preset 的 `tool-lean-agent` config 里写死了
`contextTools: false`）。

- **为什么不默认给**（实测，2026-10-05）：本地 9B 不认识这几个工具。一旦无条件放行，它会把
  有限的步数耗在反复调 `acp_status`（无参、返回 `{}`）和 `acp_cache` 上，真正该读的文件反而
  没读——委派直接白费。**放行 ≠ 会自动压缩**：`lean-agent.js` 里没有任何按阈值自动调
  `compress` 的代码，profile 的 billion-context 也写着 `compaction-basic: config: {auto: false}`。
- **怎么点名放行**：这 5 个工具注册在**根平面（global 层）**，属于 `restrict()` 认可的
  「继承层」名字集合，因此可以写进 `tools:[...]`。这与 `structured_output` 正好相反 ——
  后者由 driver 注册进子代理自己的层，写进 `allow` 会让整次运行抛 `unknown global tool`。
- **点名时必须配触发条件**：光放行没用，prompt 里要写清什么时候压，例如「读满 20 个文件后
  先 `compress` 再继续」。否则 9B 要么不用，要么乱用。
- 实现上 `lean-agent.js` 仍保留探测（只有父作用域 `tools.get(name)` 真解析得到才可能放行，
  代理没起来就退化成不给），只是 `contextTools: false` 把这条通道整体关掉了。改成 `true`
  即可恢复自动放行。

**token 超限的真正病根是单次委派切太大（输入侧）**，不是输出上限太小。一次最多让子代理读
2~3 个文件，并在 prompt 里写死输出上限（「只回 400 字」）。想一次读十几个文件再产出一份长
清单，必然撞上限。

⚠️ 实测记录（2026-10-04）：任务中 `compress` 曾连续报
`bili proxy tool compress failed (409): outbound tool witness does not match conversationId`，
当时代理进程内是 0.1.183 而磁盘已是 0.1.184（`GET <proxy>/__bili/status` → `status.version` /
`diskVersion` / `stale: true`）。billion-context 0.1.184 的更新说明点明 #2082（升级后 bili 工具
会消失直到重启）、#2101、**#2072 调用错路由** —— 遇到这类 409 先重启代理（或重启 DSH）再试，
不要靠换写法硬试。

手册正文里脚本目录写成 `<TOOLS>` 这种说明性写法，`lean-agent.js` 在注入时把它替换成包内
`tools\` 的绝对路径。**不要在手册正文里写出占位符的字面量** —— 替换是朴素全文替换，
写出来会连「解释占位符的那句话」一起被换掉，子代理会读到自相矛盾的说明（这一条是实测踩出来的）。

## 工具脚本用法

见 [skills/scrape-toolkit/SKILL.md](./skills/scrape-toolkit/SKILL.md)。常用：

```powershell
$T = "<本包根>\tools"      # 装到 profile 后是 <profile>\node_modules\@emo-bird\dsh-preset-scrape\tools
python "$T\flow_probe.py"   capture\xxx.flow
python "$T\flow_index.py"   capture\xxx.flow --only-api -o docs\抓包总表.md
python "$T\flow_slice.py"   capture\xxx.flow -o capture\slices --only-api
python "$T\flow_extract.py" capture\xxx.flow --idx 13
python "$T\flow_replay.py"  capture\xxx.flow --idx 13            # dry-run
```

脚本已做的安全处理：

- `flow_slice.py` / `flow_extract.py` 输出的 `Authorization` 一律截断为
  `Bearer eyJhbGc...<redacted>`，`x-token` / `x-sign` / `x-signature` / `x-api-key`
  截前 8 字符；cookie 默认只留名字。**这些脱敏与 `--cookie-mode` 无关，`full` 也拿不到。**
- `flow_replay.py` 默认 dry-run；dry-run 输出里 cookie 只显示名字、
  `Authorization` 只显示前 14 字符。⚠️ **但它不脱敏 `x-sign` 这类自定义头**，
  dry-run 输出照样含敏感信息，别贴进云端对话。
- 所有脚本只读抓包文件，不修改它。

## 已知依赖

### 宿主环境

- **Python 3.14.7**（`python` 在 PATH）。已经实测确认过。
- **mitmproxy 12.2.3**，作为库使用（`python -m pip install mitmproxy`）。已经实测确认过。
- **Node ≥ 22**（`lean-agent.js` 用了 `node:fs` / `node:url` 与 `import.meta.url`），
  开发机实测 Node v24.19.0。**（推断，非实测）**
- 本 preset 的 `lean_agent` 默认指向 `local-llm` provider，它由 profile 里
  `dsh-llm-gate` / `dsh-llm-pi-ai` 那几行定义（baseURL `http://localhost:1234/v1`）。
  **那是 profile 层的东西，不是本仓库的**；换 profile 就得自己再配一遍，
  否则 `lean_agent` 会因为找不到 provider 而失败（**推断**）。
- **LM Studio 侧的两个设置要跟 profile 对齐**（都是**手工**在 LM Studio 界面里改，本仓库管不着）：
  - **Limit Response Length ≥ 5120**：profile 里该模型的 `maxTokens` 就是按这个值写的
    （2026-10-05 从 2000 提到 5120）。设小了，子代理的单次回复会被服务端提前截断，
    然后触发 `lean_agent` 的 `TRUNCATED` 标记。
  - **Context Overflow → `Truncate Middle`**（实测确认这个选择是对的）：`Rolling Window`
    会优先丢系统提示（正好是 persona + `subagent-brief`），还可能把
    `tool_call` / `tool_result` 拆散；`Stop at Limit` 直接让整轮作废。
  - 思考预算 `thinking` 保持 8000。**`maxTokens` 与 LM Studio 上限不一致时以服务端为准。**
- 抓包侧（用户手工）：`mitmweb --listen-port 8080 --web-port 8081` + Edge 的 ZeroOmega。

## 已知限制

- `scrape-toolkit` 只在装了本 preset 的会话里可见（靠 `skill-filesystem` 的
  `customSkillDirs` 指向 `skills\`）。**preset 未安装时技能不激活**——已实测确认：
  未装时该行解析不到包，技能列表里没有 `scrape-toolkit`。
- ⚠️ **重装最快的方式（实测有效，比改 profile 安全）**：在**别的 preset 会话**里（例如
  `standard`，因为 `plugin_manager` 不在本 preset 工具表里）调
  `plugin_manager` → `install_bundle` → `target` 填仓库根绝对路径。它会重新复制并
  **自动重启 DSH**（上一次实测：装完 GUI 端口从 43114 变成 54417）。
- **`install_bundle` 是复制安装，不是链接。** 实测 `<PKG>`（
  `<profile>\node_modules\@emo-bird\dsh-preset-scrape`）是**实体目录**：`LinkType` 空、`Target` 空、
  `Attributes: Directory`、`dir /a` 显示普通 `<DIR>`。所以 profile 里跑的那份是**安装那一刻的
  快照**，本地仓库改完**必须重跑 `install_bundle`** 才会进 `<PKG>`。
  **没有任何文件是「立即生效」的** —— 包括 `skills\` 下的 `SKILL.md`。
  （技能 watcher 监听的是 `<PKG>\skills\` 那个根，不是你的仓库目录；改仓库不动 `<PKG>` 就没用。）
- 改动 → 生效路径速查：

  | 改了 | 怎么才能生效 |
  |---|---|
  | `cordis.patch.yml`（含技能根、工具开关、persona） | commit + push + 重装（或重跑 `install_bundle`）+ **重启 DSH** |
  | `lean-agent.js` | 同上（bundle 加载时读取） |
  | `skills\subagent-brief\SKILL.md` | 同上（`lean-agent.js` 在注册时读它，不是每次调用读） |
  | `tools\*.py` | 重装（脚本在包内，`<PKG>\tools\`） |
  | `skills\scrape-toolkit\SKILL.md` | 重装后会生效；它是**技能**，由技能 watcher 监听 `<PKG>\skills\` |

  注：**profile 自己的** `cordis.patch.yml`（`<profile>\cordis.patch.yml`）是例外 ——
  它被 DSH 监视，**保存即热重载**，不需要重启。
- ⚠️ **`<PKG>` 不是你的仓库。** `<PKG>` 是 profile `node_modules` 里那份，仓库是你 clone
  下来的那份。两者是**两份不同的目录**。验收经验：**改了仓库不重装，测出来的全是旧版行为**，
  而且不会有任何报错。改完先做这一步自检（把两个路径替换成你机器上的实际位置）：

  ```powershell
  $pkg = "<profile>\node_modules\@emo-bird\dsh-preset-scrape"
  $repo = "<仓库根>"
  foreach ($f in "lean-agent.js", "cordis.patch.yml", "README.md",
                 "skills\scrape-toolkit\SKILL.md", "skills\subagent-brief\SKILL.md") {
    $a = (Get-FileHash "$pkg\$f" -Algorithm SHA256).Hash
    $b = (Get-FileHash "$repo\$f" -Algorithm SHA256).Hash
    "{0,-40} {1}" -f $f, $(if ($a -eq $b) { "SAME" } else { "DIFF" })
  }
  ```

  出现 `DIFF` = 没重装（或没 push、或没重启 DSH）。
  （`README.md` 这类纯文档不一致不影响功能，但说明 `<PKG>` 确实落后了。）
- `lean-agent.js` **必须保持零依赖**。它只用 `node:` 内置模块（`node:fs` / `node:url`），
  不 import 任何**包**，工具注册走 `ctx.tools.register` 的原始对象形式；
  而安装到 profile 后的那份副本解析不到 `@deepseek-ai/*`（包未声明 `dependencies`）。
  一旦给它加包 `import`，就会在 profile 里直接加载失败。同理，`subagent-brief/SKILL.md`
  必须与 `lean-agent.js` 一起打进包里 —— 仓库根就是包根，`skills\` 本来就在包内。