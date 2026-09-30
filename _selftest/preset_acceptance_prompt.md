# scrape preset 验收会话模板

> 用法：新建会话，agent preset 选「**Web 采集与逆向**」，把下面「提示词」整段粘进去。
> 被测对象是 preset 本身，不是业务开发。

---

## 提示词

本次任务是**验收刚装好的 scrape preset 本身**，不是做业务开发。

跳过项目开场协议：不要去找 `docs/开发文档.md` / `docs/环境文档.md` / `docs/交接文档.md`，
不要建 git 分支，不要读抓包文件，不要碰 `tools\*.py`。

### 背景

preset `scrape`（显示名「Web 采集与逆向」）已通过 `plugin_manager install_bundle` 安装。
它带来的东西在真实会话里需要实测：

1. `skills\scrape-toolkit\SKILL.md` —— 靠 preset 里 `skill-filesystem` 那一行的
   `config.customSkillDirs` 指过来，期望**只在本 preset 的会话里**可见。
2. `skills\subagent-brief\SKILL.md` —— 写给**子代理**的环境手册，同样在该目录下，也应当可见。
3. `lean-agent.js` —— 注册 `lean_agent` 工具，补齐 `workflow` 的 `agent()` 传不了的
   `persona` 与 `toolFilter`。期望子代理换成**一句极短 persona、工具集由调用方指定**，
   并且**自动附加 `subagent-brief` 的正文**（去掉 frontmatter、`<TOOLS>` 换成绝对路径）。

**先自行确定包的实际安装位置**，再开始验证：

```
# 从 profile 里找这个包的链接目标
Get-Item "C:\Users\一门鸽鸽\.dsh\profiles\desktop\node_modules\@emo-bird\dsh-preset-scrape" -Force |
  Select-Object FullName, LinkType, Target
```

把解析出来的真实根目录记下来，记为 `<PKG>`（后续用它，不要硬编码）。若解析不到，**第 0 步就停下报告**。

### 总规矩（先读，再动手）

- **全程只读为主。** 要写、改、删任何文件（包括最后清理 `_selftest`）**先问我**。
- **一条一条来**，每条都要给出**可核对的原始证据**：命令 + 完整输出 / 工具返回值 / 文件片段。
  「应该没问题」「看起来正常」不算证据。
- **任何一条与预期不符，立即停下告诉我**，不要自己想办法绕过、不要「顺手修一下」、不要改代码。
- 下面标了「**实测**」的预期是上一轮量过的；其余是**从源码推的**。凡是从源码推的，不符就当成
  「我的推断错了」来报，别当成小毛病略过。
- **不要臆造**。拿不到的东西（比如某个文件不存在）就写「取不到 + 原因」，不要补一个看起来合理的值。
- 每条给一个明确结论：**通过 / 不通过 / 无法判定**（无法判定要写清卡在哪）。

### 第 0 步：前置条件

1. 解析出 `<PKG>`（见上）。
2. 本地模型服务在 `http://localhost:1234/v1` 是否可达？（`lean_agent` 默认指向它）
   用只读方式探测，例如：

   ```powershell
   try { (Invoke-WebRequest http://localhost:1234/v1/models -TimeoutSec 5).StatusCode }
   catch { $_.Exception.Message }
   ```

   不可达就**停下告诉我**，第 3/4/5 条做不了（第 1、2 条仍可做，先把它们做完）。

3. **先确认装上去的是新版**。这一轮刚改过 `lean-agent.js`、新增了 `skills\subagent-brief\`，
   还补了一个**占位入口文件 `index.js`**，如果重装没生效，第 3 条会必然失败，那就白测了。
   逐项核对：

   ```powershell
   # a) 新技能文件在不在包里
   Test-Path "<PKG>\skills\subagent-brief\SKILL.md"
   # b) 占位入口文件在不在（缺了它市场的「更新」按钮会失败）
   Test-Path "<PKG>\index.js"
   # c) lean-agent.js 里有没有注入代码与占位符常量
   Select-String -Path "<PKG>\lean-agent.js" -Pattern "subagent-brief|loadBrief|personaFor|TOOLS_PLACEHOLDER" |
     Select-Object LineNumber, Line
   # d) 和仓库那份对比，SHA256 应完全一致
   Get-FileHash "<PKG>\lean-agent.js", "<仓库根>\lean-agent.js" -Algorithm SHA256 |
     Select-Object Hash, Path
   ```

   （`<仓库根>` = 本仓库在你机器上的位置；验收时问用户，或从他的会话工作目录推。）

   任一不符 → **停下告诉我「重装没生效」**，不要继续往下测（测出来的都是旧版行为）。
   ⚠️ `install_bundle` 是**复制安装**（`<PKG>` 是实体目录，不是 junction），所以「改了仓库」
   不等于「改了 `<PKG>`」。上一轮就踩过：仓库改完没重装，测出来全是旧版行为，**且不会报错**。

4. **顺手做一次回归检查**（这是上一轮修掉的东西）。读
   `C:\Users\一门鸽鸽\.dsh\profiles\desktop\cordis.patch.yml`，确认文件里**没有**重新出现
   一整段 `- id: <某工具名>` / `  disabled: false` 的机器生成列表（上一轮删掉了 73 行这种东西）。
   若又出现了，说明某个界面操作（例如 GUI 的 preset 编辑器保存）会重写这个文件 —— 立即告诉我。

5. **验证市场的「更新」按钮不再失败**（这一轮新修的）。`@emo-bird/dsh-preset-scrape`
   过去一旦点更新就会报「更新后缺少入口文件…且未能验证恢复原版本文件」，然后被自动回滚；
   根因是包根没有 `main`/`exports`/`index.js`，市场的 `hasLoadableEntry()` 判它没有入口。
   现在补了 `index.js`。复现这个判据（只读，不改任何东西）：

   ```powershell
   node -e "import('file:///C:/Program Files/DSH NEXT/resources/app/node_modules/dshmarket/lib/profile.js').then(m => console.log(m.hasLoadableEntry('C:/Users/一门鸽鸽/.dsh/profiles/desktop', '@emo-bird/dsh-preset-scrape')))"
   ```

   - **通过**：输出 `true`。
   - **失败**：输出 `false` → `<PKG>` 里缺 `index.js`（回到第 0 步第 3b 项），或仓库那份没 push。

   ⚠️ 这条**不要**真的去点 GUI 的更新按钮来自测（会触发真实重装）。上面这个调用就是市场内部用的
   同一个函数，等价且无副作用。

### 第 1 条：preset 本身

你现在这个会话就是 scrape preset。确认你的工具表里：

⚠️ 要看的是这次**新建的顶层会话**，不是被委派的子会话。上一轮的报告里「子会话工具表 43 个」与
「顶层应该干净」互相矛盾，根因是 profile 层的工具覆盖把根平面重新打开了 —— 那一层已经删掉，
所以现在顶层和子会话都应该是干净的。

- **有** `lean_agent`、**有** `workflow`、**有** `skill`、**有** `pwsh`（配置里 pwsh 是启用的）
- **没有**：`bash`（Windows 上被平台表达式关掉，**这不算失败**）、`subagent`、
  `subagent_fork`、`spawn_teammate`、`get_goal` / `create_goal` / `update_goal`、`ralph`、
  任何 ssh 相关工具、`plugin_manager`

⚠️ **两处例外 / 易误判点，都先看清楚再下结论**：

1. `task_board_*` 与 `acp_cache` / `acp_status` / `compress` / `decompress` / `search_context`
   来自 profile 里**其它第三方 bundle**（`@linxin666/dsh-web-all` 与 `billion-context`），
   它们在**全 profile 共享的根平面**注册工具行，preset 关不掉。除非改 profile 的 bundle 列表，
   否则它们一直会在。**不算失败。**
2. 几条容易误判的：
   - **`bash` 缺失是预期**：根平面 `tool-bash` 的 `disabled` 是
     `!!js process.platform === 'win32'`，且 preset 自己也声明了同一表达式。上一轮这段被
     profile 的覆盖块强行改成启用，才让「43 个工具」出现；那一层已删除，现在恢复成 Windows 上禁用。
   - **`todo_write` 应当在**：preset 自己声明了 `- id: tool-todo`
     （`config.allowParallelInProgress: true`）。（上一版模板写「多半不在」，实测证明是错的。）
   - **`compress` / `decompress` / `search_context` / `acp_cache` / `acp_status` 在**：
     属于第 1 条例外，来自 `billion-context`。
   - **`web_fetch` / `web_search` 在**：来自 preset 自己声明的 `tool-web` 行。

**怎么取完整清单**：`cordis_inspect_query` 这个工具**不存在**，不要去找它。可行的取证方式是
读当前会话的日志文件（`C:\Users\一门鸽鸽\.dsh\sessions\` 下按修改时间找最新的），
看首条请求的 `data.header.tools` 数组 —— 这是**上一轮验证过、可复核**的硬证据；
同时以「我这个会话实际能调用的工具」为准逐个列。**在报告里说明你用的是哪种方式**。
不要因为拿不到某个工具就停下，也不要为了它去改任何配置。

### 第 2 条：两个技能都可见

用 `skill` 工具分别加载 `scrape-toolkit` 和 `subagent-brief`。

- **通过**：`scrape-toolkit` 能加载，且内容讲的是 `flow_probe` / `flow_index` / `flow_slice` /
  `flow_extract` / `flow_replay`；`subagent-brief` 能加载，内容是「给子代理的环境手册」
  （讲 pwsh 没有 `&&`、`[System.IO.File]::` 被拦、只读沙箱、抓包要走脚本）。
  贴出两者加载到的开头 20 行。
- **失败就报告**，**不要**自己往 `.dsh\skills\` 里塞指针、不要改 `customSkillDirs`。

### 第 3 条：lean_agent 真能跑，且子代理是「瘦」的（核心）

调一次 `lean_agent`，`prompt` 用这个探针（**原样传，不要改写**）：

```
不要做任何实际工作，只回答两件事：
(1) 逐字引用你系统提示词的前两句话；
(2) 列出你能调用的每一个工具的确切名字，一个不漏；一个都没有就说 none。
```

调用参数：`prompt` = 上面那段；`description` = `probe`；
`provider` 和 `model` **都留空**（走配置默认 `local-llm`）；`tools` 留空。
把子代理的**原始返回**贴给我，不要概括。

**判断标准**（这条是本次改动的核心价值）：

- **通过**：
  - (1) 开头回的是 `You are a focused worker. Do exactly the task...` 这句英文
    （`lean_agent` 会在这句**之后**追加 `subagent-brief` 的正文，所以后面出现
    「# subagent-brief — 被委派子代理的环境手册」以及一串中文规矩是**预期行为**，不算失败）；
  - (2) 回 `none`，或（只在传了 `schema` 时）只有 `structured_output`。
  - (3) **加分项**：让子代理照着手册做一件它以前会做错的事 —— 例如让它用 pwsh 打印
    `flow_probe.py` 是否存在。预期它用 `& python "<绝对路径>\flow_probe.py" --help` 或
    `Test-Path` 这类手册里教过的写法，且**不出现 `&&` 语句分隔符报错**。
- **失败**：
  - (1) 开头就是一段**中文的**、关于「用户不拍板不动手 / 渐进式确认 / git 分支」的长文
    —— 说明同名 section 覆盖**没生效**，子代理仍在整套继承父 preset 的长 persona；
  - (1b) persona 换成了英文短句，但**完全没有** `subagent-brief` 的正文
    —— 说明 brief 注入没生效（检查安装副本里 `skills\subagent-brief\SKILL.md` 是否存在）；
  - (1c) brief 正文里还留着 `{{TOOLS_DIR}}` 或 `<TOOLS>` 字面量 —— 说明占位符替换失败。
    （注意：手册**源文件**里就是写 `<TOOLS>` 的，所以判据是「注入后的正文里一个都不剩」。）
  - (2) 列出了 `pwsh` / `read` / `write` / `workflow` / `skill` / `todo_write` 等
    —— 说明 `toolFilter` 没生效。

⚠️ **对 (2) 的预期要放宽**（这是上一轮的**实测**结论，不是源码推断）：`lean_agent` 不传 `tools` 时，
子代理拿到的工具数是 **0 个**；只有在**同时传了 `schema`** 时才会多出驱动注册的
`structured_output`，也就是 1 个。所以：

- 不传 `tools`、不传 `schema` → 预期 **0 个**；
- 不传 `tools`、传 `schema` → 预期**恰好 1 个**，名字是 `structured_output`。

子代理把读过的系统提示词里出现过的工具名（比如手册里提到的 `read` / `grep`）一起报出来，
是 9B 常见的**幻觉**，不算 `toolFilter` 失效。判断 `toolFilter` 是否真失效，要看**硬证据路线**
（去子会话文件里数 `header.tools` / 读首条 system prompt），不要只看模型自述。

**如果拿不准，走硬证据路线互相印证**：调用后去 `C:\Users\一门鸽鸽\.dsh\sessions\` 下按修改时间
找最新的**子会话**文件，读出它首条请求的 system prompt 与 provider/model，和子代理自述对比。
**两条对不上，以文件为准**，并明确说明哪里对不上。

### 第 4 条：子代理确实跑在本地模型上

接第 3 条，从子会话文件 / request header 里确认 `provider` 是 `local-llm`、
`model` 是 `ornith-1.5-9b-dsh-agentic-gpt-5.6-sol-distill`。

**只看「没报错」不算通过。** 要贴出含这两个字段的原始片段。

### 第 5 条：`structured_output` 不会被工具白名单挡掉

再调一次 `lean_agent`，这次带 `schema`：

```json
{"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":false}
```

`prompt` 让它返回一个简单结果（例如「回答 ok」）。

**先把预期说清楚，别拿「没报错」当通过**（这是上一轮的实测结论）：

- 本地 9B 模型**不会**主动调用驱动为它注册的 `structured_output` 工具。driver 发现「给了 schema
  但没捕获到 structured」时会把 `stopReason` 从 `completed` 强改成 `error`，于是 `lean_agent`
  抛一条 `lean_agent run failed`。
- 所以**两种结果都算「行为符合源码」**，请如实记录是哪一种：
  - **A**：返回里有 `structured` 字段且值是符合 schema 的对象 → 模型这次调用了 `structured_output`；
  - **B**：返回一条 `lean_agent run failed` 错误 → 模型没调用它。**这不是白名单问题**，是模型能力问题。
- **不通过**：报 `unknown global tool "structured_output"`（说明它被写进了 `tools` 白名单，是 bug）；
  或**成功返回但 `structured` 为空/缺失**（说明 render 漏了 structured）。

顺便记录这次**有没有**在 `tools` 里写 `structured_output`（预期：**没写**，也**不该写**）。

### 第 6 条：子代理无法递归

第 3 条的 (2) 已经覆盖：若子代理的工具列表里**没有** `lean_agent`、也**没有** `workflow`，
即为通过。请显式引用第 3 条 (2) 的原文作为证据，不要重新推断。

⚠️ **这一条只对 `lean_agent` 成立。** 上一轮实测发现：走 `workflow` 的 `agent()` 起的子代理
拿到的是**全部 32 个工具**（含 `lean_agent` 和 `workflow`），所以**它是能继续委派的**，
递归深度上限**没有测过**。所以第 6 条的结论请写成「`lean_agent` 子代理不能递归：通过；
`workflow` 的 `agent()` 子代理可递归，深度上限未知」。

### 收尾

1. 全部跑完后给我**一张表**：`第 0~6 条 / 实际结果 / 通过与否 / 证据在哪`。
   证据要写清是「命令 + 输出片段」「工具返回值」还是「某个文件的第 N 行」。
2. 表下面另起一段「**我的推断错在哪**」：凡是实际结果与预期不符的，逐条写清楚
   我原来的预期是什么、实际是什么、最可能的原因是什么（只做归因，**不要动代码**）。
3. `<PKG>\_selftest\` 下有一个加载测试脚本，是我上一轮留下的。
   **不要自行删除**——先问我，我说删你再删。
   顺带一提：它可以用 `node <PKG>\_selftest\load_test.mjs <PKG>\lean-agent.js` 直接跑，
   预期最后打印 `LOAD TEST OK`。**这不是本次验收的必查项**，跑不跑都行；
   跑的话把最后几行贴出来即可。

4. **额外做一次对照实验**（上次没测，两条空白）：用 `workflow` 的 `agent()` 起一个子代理，
   让它只回答「你有哪些工具、叫什么名字」，然后去子会话文件里读 `data.header.tools`。
   要回答两件事：
   - `agent()` 起的子代理到底拿到几个工具、有没有 `lean_agent` 和 `workflow`（预期：全部 32 个，都有）；
   - `agent()` **不写 `provider` / `model`** 时，子会话 header 里的 provider/model 是什么
     （上次没做这个对照组）。

4. 最后**额外输出一份「功能自述」**（见下节）。

---

## 功能自述（第 3 步的交付物）

全部验证跑完后，在**不参考我这份提示词**的前提下（也就是说：只依据你刚才实测到的行为
和你在会话里读到的 preset 实际内容），另起一节输出：

### `# 功能自述：scrape preset`

用**给下一个使用者看**的口吻写，必须包含：

1. **一句话定位** —— 这个 preset 是干什么用的、适合什么任务。
2. **提供的东西** —— 逐项列，每项写清「是什么 / 怎么用 / 一句话示例」：
   - `lean_agent` 工具的定位与和 `workflow` 的分工，`tools` / `schema` / `persona` /
     `provider` / `model` 各参数怎么用，**默认行为**是什么（不传 `tools` 会怎样、
     不传 `provider` 会走哪）。
   - `scrape-toolkit` 技能覆盖的能力（五个脚本各自解决什么问题、什么场景该用哪个）。
   - `subagent-brief` 技能是**给子代理**的环境手册，以及它两条投递路径的差别
     （`lean_agent` 自动注入 vs `agent()` 要自己在 prompt 里要求加载）。
   - 其他你实测确认存在的工具（`workflow` 等）。
3. **明确不提供的** —— 有意砍掉的能力（子代理类工具、goal/ralph、Agent Teams、ssh 等），
   并说明**砍掉的理由**（理由要来自你在会话/preset 里真实读到的内容，不要编）。
4. **边界与限制** —— 至少覆盖：
   - `lean_agent` 的子代理**不能再委派**（但 `workflow` 的 `agent()` 子代理**可以**）；
   - 子代理**不共享上下文**，prompt 必须自包含；
   - 走本地模型的**隐私考虑**（哪些内容不该发出去）；
   - 安装方式对 `customSkillDirs` 的影响（本地绝对路径 vs 从 GitHub 装进 `node_modules`）；
   - **`install_bundle` 是复制安装**：改了仓库不重装，测出来全是旧版行为且不报错；
     逐项说明「改了哪个文件 → 需要重装 / 需要重启 / 保存即热重载」。
5. **验收状态** —— 直接引用你这次测出的结果：哪些**已实测通过**、哪些**没测到**、
   哪些**测出与文档不符**。**没测到的就写没测到**，不要写成「正常」。

**要求**：只写你**验过或读到过**的事实。凡是推断，前面加「（推断）」二字。
整节结尾附一个「**存疑清单**」，列出你在本次验收中没能确认的点。
