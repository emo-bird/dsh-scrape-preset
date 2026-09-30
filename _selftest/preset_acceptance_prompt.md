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
它带来的两样东西在真实会话里**尚未实测**：

1. `skills\scrape-toolkit\SKILL.md` —— 靠 preset 里 `skill-filesystem` 那一行的
   `config.customSkillDirs` 指过来，期望**只在本 preset 的会话里**可见。
2. `lean-agent.js` —— 注册 `lean_agent` 工具，补齐 `workflow` 的 `agent()` 传不了的
   `persona` 与 `toolFilter`。期望子代理换成**一句极短 persona、工具集由调用方指定**。

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
- 下面我写的「预期值」**都是从源码推的，没实测过**。任何一条不符，都当成「我的推断错了」来报，
  别当成小毛病略过。
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

### 第 1 条：preset 本身

你现在这个会话就是 scrape preset。确认你的工具表里：

- **有** `lean_agent`
- **有** `workflow`
- **没有** `subagent` / `subagent_fork` / `spawn_teammate` / `task_board_*` / `get_goal` /
  `ralph` / 任何 ssh 相关工具 / `plugin_manager`

用 `cordis_inspect_query` 的 Tool provider（`platform: host`, `method: listTools`）
取**完整清单**来对，不要凭印象。把清单里的工具名逐个列出，再逐条标 有/无。

### 第 2 条：scrape-toolkit 技能可见

用 `skill` 工具加载 `scrape-toolkit`。

- **通过**：能加载出来，且内容讲的是 `flow_probe` / `flow_index` / `flow_slice` /
  `flow_extract` / `flow_replay`。贴出加载到的开头 20 行。
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
  - (1) 回的是类似 `You are a focused worker. Do exactly the task...` 这句英文；
  - (2) 回 `none`，或只有 `structured_output`。
- **失败**：
  - (1) 开始背一段**中文的**、关于「用户不拍板不动手 / 渐进式确认 / git 分支」的长文
    —— 说明同名 section 覆盖**没生效**，子代理仍在整套继承父 preset 的长 persona；
  - (2) 列出了 `pwsh` / `read` / `write` / `workflow` / `skill` / `todo_write` 等
    —— 说明 `toolFilter` 没生效。

**如果拿不准，走硬证据路线互相印证**：调用后去 `C:\Users\一门鸽鸽\.dsh\sessions\` 下按修改时间
找最新的**子会话**文件，读出它首条请求的 system prompt 与 provider/model，和子代理自述对比。
**两条对不上，以文件为准**，并明确说明哪里对不上。

### 第 4 条：子代理确实跑在本地模型上

接第 3 条，从子会话文件 / request header 里确认 `provider` 是 `local-llm`、
`model` 是 `ornith-1.5-9b-dsh-agentic-gpt-5.6-sol-distill`。

**只看「没报错」不算通过。** 要贴出含这两个字段的原始片段。

### 第 5 条：`structured_output` 没被工具白名单挡掉

再调一次 `lean_agent`，这次带 `schema`：

```json
{"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":false}
```

`prompt` 让它返回一个简单结果（例如「回答 ok」）。

- **通过**：返回里有 `structured` 字段，且值是**符合 schema 的对象**。
- **失败就报**，不要改代码。

顺便记录这次**有没有**在 `tools` 里写 `structured_output`（预期：没写，也不该写）。

### 第 6 条：子代理无法递归

第 3 条的 (2) 已经覆盖：若子代理的工具列表里**没有** `lean_agent`、也**没有** `workflow`，
即为通过。请显式引用第 3 条 (2) 的原文作为证据，不要重新推断。

### 收尾

1. 全部跑完后给我**一张表**：`第 0~6 条 / 实际结果 / 通过与否 / 证据在哪`。
   证据要写清是「命令 + 输出片段」「工具返回值」还是「某个文件的第 N 行」。
2. 表下面另起一段「**我的推断错在哪**」：凡是实际结果与预期不符的，逐条写清楚
   我原来的预期是什么、实际是什么、最可能的原因是什么（只做归因，**不要动代码**）。
3. `<PKG>\_selftest\` 下有一个加载测试脚本，是我上一轮留下的。
   **不要自行删除**——先问我，我说删你再删。

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
   - 其他你实测确认存在的工具（`workflow` 等）。
3. **明确不提供的** —— 有意砍掉的能力（子代理类工具、goal/ralph、Agent Teams、ssh 等），
   并说明**砍掉的理由**（理由要来自你在会话/preset 里真实读到的内容，不要编）。
4. **边界与限制** —— 至少覆盖：
   - `lean_agent` 的子代理**不能再委派**；
   - 子代理**不共享上下文**，prompt 必须自包含；
   - 走本地模型的**隐私考虑**（哪些内容不该发出去）；
   - 安装方式对 `customSkillDirs` 的影响（本地绝对路径 vs 从 GitHub 装进 `node_modules`）；
   - 改了哪些文件需要重新安装、哪些立即生效。
5. **验收状态** —— 直接引用你这次测出的结果：哪些**已实测通过**、哪些**没测到**、
   哪些**测出与文档不符**。**没测到的就写没测到**，不要写成「正常」。

**要求**：只写你**验过或读到过**的事实。凡是推断，前面加「（推断）」二字。
整节结尾附一个「**存疑清单**」，列出你在本次验收中没能确认的点。
