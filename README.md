# preset: scrape —— Web 采集与逆向

油猴脚本（UserScript）/ 网站接口逆向 / 数据采集与自动化开发用的 DSH agent preset，
外加一套 mitmproxy 抓包分析工具（`scrape-toolkit`）。

## 目录结构

```
C:\Project\dsh-scrape-preset\
├─ package.json            ← DSH bundle 清单（dsh.bundle.patch 指向 cordis.patch.yml）
├─ cordis.patch.yml        ← preset 声明 + persona 全文
├─ lean-agent.js           ← 本 preset 专用的 lean_agent 工具插件（零依赖）
├─ README.md               ← 本文件
├─ skills\                 ← 只在本 preset 会话里可见的技能目录
│   └─ scrape-toolkit\
│       └─ SKILL.md        ← 脚本说明书（技能发现认的标准布局）
├─ tools\                  ← Python 抓包分析脚本
│   ├─ flow_probe.py       ① 体检：能不能读、多少条、哪些域名
│   ├─ flow_index.py       ② 请求总表（idx/method/status/体积/host/path）
│   ├─ flow_slice.py       ③ 按 host+路径首段分片，每片约 24KB，喂本地模型
│   ├─ flow_extract.py     ④ 单条请求导出成精简 JSON
│   └─ flow_replay.py      ⑤ 复现请求（默认 dry-run，加 --send 才真发）
└─ _selftest\
    └─ load_test.mjs       ← 预检：模块能否加载 + schema 是否被真校验器接受
```

**仓库根就是包根**（`package.json` 在根上），所以既能本地装、也能直接从
GitHub 当 git 依赖装。

`skills\` 只在装了本 preset 的会话里生效，靠 preset 里 `skill-filesystem` 那一行的
`config.customSkillDirs` 指过来；其他会话看不到 `scrape-toolkit`，也不用往
`$DSH_HOME\skills\` 塞指针。用户级的 `local-llm-offload` 不受影响。

## 安装

### 本地装

用 `plugin_manager` 工具，`action: install_bundle`，`target` 填**仓库根目录的绝对路径**：

```
C:\Project\dsh-scrape-preset
```

### 从 GitHub 装

`target` 填仓库地址，三种写法都认：

```
https://github.com/emo-bird/dsh-scrape-preset.git
github:emo-bird/dsh-scrape-preset
https://github.com/emo-bird/dsh-scrape-preset.git#<tag 或 commit>
```

**注意**：从 GitHub 装时包里没有 `skills\` 之外的东西可省，但
`cordis.patch.yml` 里 `customSkillDirs` 是绝对路径，指向本机仓库；走 GitHub
安装后需要把它改成 `<profile>\node_modules\@local\dsh-preset-scrape\skills`
（`cordis.patch.yml` 里已留了注释说明）。

它会自己跑包安装并写入 profile 的 bundle 列表，**不要**手动改 profile 的
`package.json` 或 `cordis.patch.yml`。

装完在 Web GUI 新建会话时选「**Web 采集与逆向**」即可。

## 这个 preset 和 standard 的差别

保留：`pwsh` / 文件工具 / `jobs` / `skill` / `ask_user_question` / `todo_write` /
`web_search`+`web_fetch` / `present` / plan mode / 上下文压缩 / `workflow`。

不挂（`disabled: true`）：

| row | 为什么 |
|---|---|
| `tool-subagent` / `tool-subagent-fork` | 委派统一走 `workflow` 的 `agent()` |
| `tool-subagent-control` / `tool-subagent-list-agents` | 同上 |
| `command-goal` / `tool-goal` | goal 是「自动续轮、无人值守」，与「每个决策点都要用户拍板」冲突 |
| `tool-plugin-manager` | preset 装好之后它自己不需要改插件 |
| `tool-ralph` | 自动迭代循环，同上 |

**注意**：`subagents` 注册表和 `spawn` provider 在**宿主平面**，preset 只挑「工具」。
所以不挂 `tool-subagent` **不影响** `workflow-ptc` 的 `provider: spawn`。

## persona 里固化了什么

见 `cordis.patch.yml` 的 `persona.config.prefix`（约 3100 字）。要点：

1. **开场协议**：检查 `docs/开发文档.md`、`docs/环境文档.md`、`docs/交接文档.md`；
   缺环境文档就自行探测（node/python/mitmproxy/端口/Edge/LM Studio），只问探测不到的。
2. **交互铁律**：用户不拍板不动手；每个决策点给 2~3 个方案；出现任何非预期情况
   （接口对不上、结构不符、依赖装不上、抓包被拦）**立即停下上报**，严禁自己绕过。
3. **git**：新功能必须开分支；任何修改都要 commit。
4. **测试**：档1 纯函数冒烟（node assert）/ 档2 接口契约冒烟 / 档3 UI 由用户手测；
   风险接口不做自动化测试。
5. **省 token**：抓网页用 `pwsh` 落盘而非 `web_fetch`；抓包绝不整份读入，先 index 再 slice；
   高 token 低难度活儿走 `workflow` + `agent(provider:'local-llm')`。
6. **隐私**：抓包可能含真实姓名/手机号，只喂本地模型，绝不喂云端。
7. **委派**：只用 `workflow`；不用 subagent 工具、不用 Agent Teams、不用 ssh、不开 computer use。

## 工具脚本用法

见 [skills/scrape-toolkit/SKILL.md](./skills/scrape-toolkit/SKILL.md)。常用：

```powershell
$T = "C:\Project\dsh-scrape-preset\tools"
python "$T\flow_probe.py"  capture\xxx.flow
python "$T\flow_index.py"  capture\xxx.flow --only-api -o docs\抓包总表.md
python "$T\flow_slice.py"  capture\xxx.flow -o capture\slices --only-api
python "$T\flow_extract.py" capture\xxx.flow --idx 13
python "$T\flow_replay.py" capture\xxx.flow --idx 13            # dry-run
```

脚本已做的安全处理：

- `flow_slice.py` / `flow_extract.py` 输出的 `Authorization` 一律截断为
  `Bearer eyJhbGc...<redacted>`，cookie 默认只留名字，**不会把可用凭证写进分片**。
- `flow_replay.py` 默认 dry-run，dry-run 输出里 cookie 只显示名字、
  `Authorization` 脱敏。
- 所有脚本只读抓包文件，不修改它。

## 已知依赖

- Python 3.14.7（`python` 在 PATH）
- mitmproxy 12.2.3（作为库使用，`python -m pip install mitmproxy`）

## 已知限制

- `scrape-toolkit` 只在装了本 preset 的会话里可见（靠 `skill-filesystem` 的
  `customSkillDirs` 指向 `skills\`）。**preset 未安装时技能未激活**——
  这一点要等实装后实测确认。
- 修改 `cordis.patch.yml` 后必须**重新 install_bundle** 才生效；
  改 `tools\*.py`、`lean-agent.js` 则直接生效，无需重装。
- `skills\` 目录里的 `SKILL.md` 改动**立即生效**（技能 watcher 监听该根目录），
  不需要重装 bundle。