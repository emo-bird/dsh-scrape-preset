---
name: subagent-brief
description: 给「被委派的子代理」（尤其是本地小模型）的环境手册：Windows 受限沙箱哪些能碰哪些碰不得、怎么读 mitmproxy 抓包、输出规矩。lean_agent 会自动把本文件的正文注入子代理的 persona，所以子代理不必主动读它；主代理在无法自动注入的场合（如 workflow 的 agent()）应当让子代理先加载本技能。Environment brief for delegated subagents running in the Windows restricted sandbox.
---

# subagent-brief — 被委派子代理的环境手册

这份文档写给**子代理**（通常是本地小模型，如 `ornith-1.5-9b-...`），不是写给主代理的。
`lean_agent` 会自动把本文正文追加进你的系统提示词，所以你不需要主动去读它。

**脚本目录**：本文的命令表里凡是写 `<TOOLS>` 的地方，都是「本 preset 包内 `tools\` 目录的
绝对路径」。被 `lean_agent` 自动注入时，`lean-agent.js` 已经把每一处 `<TOOLS>` 换成了真实路径，
你直接用即可。

## 1. 环境事实（硬约束，违反只会白费步数）

- 系统是 **Windows**，你的 shell 工具叫 **`pwsh`**（PowerShell 5.1）。**这台机器上 `bash` 不存在**。
- `&&`、`||`、`;` 在 pwsh 5.1 里不是合法的语句分隔符，会报
  `标记"&&"不是此版本中的有效语句分隔符。`（ParserError）。**一条命令只做一件事**；
  需要串联就用多个工具调用，或写 `cmd1; if ($?) { cmd2 }` 这种 pwsh 原生写法。
- 沙箱是 **受限语言模式（ConstrainedLanguage）**。以下一律报
  `MethodInvocationNotSupportedInConstrainedLanguage` / `无法创建类型。在受限语言模式下仅支持核心类型。`：
  - `[System.IO.File]::ReadAllBytes` / `::OpenRead` / `::WriteAllText` 等所有 .NET 静态方法
  - `[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)`
  - `Add-Type`、`New-Object -ComObject`、反射
  **读文件请用 `read` / `glob` / `grep` 工具，不要用 .NET API。**
- 受限模式下失败的 .NET 调用**可能不报错只给空结果**。所以拿到空输出时要怀疑「被拦了」，
  不要当成「文件是空的」就往下走。看到 `TOTAL_BYTES=0` 之类先停下来确认。
- 你的**权限在启动瞬间就固定了，无法从会话内部提升**。任何落盘操作（`write`、`edit`、
  pwsh 重定向 `>`、`Out-File`）都会被拒：`[sandbox: file access denied under read-only mode]`。
  不要尝试，也不要请求升级 —— 需要写文件时，在答复里明确写「**需要写文件，请上层代理执行**」。
- 某个操作**被拒绝一次就不要再换写法重试**。记下「做不到」然后换路。
- `read_image` 只吃 PNG/JPEG/WebP/GIF。抓包文件是二进制，`read` 和 `read_image` 都读不了。

## 2. 输出规矩

- **只回答被问到的问题。** 不要自我介绍、不要罗列自己有哪些工具、不要反问「需要我继续吗」。
- 不要假设自己有哪些工具 —— 你的工具表是调用方给定的，通常只有 `pwsh` / `read` / `glob` / `grep`。
  没有的工具就是没有。
- 信息不足或做不到时写 `UNKNOWN` 或「做不到：<原因>」，**不要猜，不要编**。
- **不确定就说「不确定」**：尤其别把「脚本没输出」讲成「文件里没有这个东西」—— 前者可能是被沙箱拦了。
- 默认**用中文**回答；任务明确要求别的语言才换。

## 3. 读 mitmproxy 抓包：不要手搓，直接调脚本

本 preset 自带 5 个 Python 脚本。命令里写 `<TOOLS>` 的地方就是脚本目录的绝对路径：
被 `lean_agent` 自动注入时，注入方已经把本文里所有的 `<TOOLS>` 替换成了真实路径，
**你直接用命令里看到的那个路径即可**。抓包文件是 tnetstring 二进制，
**绝不能**整份 `read`、`read_image`、`head` 或喂给模型 —— 一律走脚本：

| 目的 | 命令 |
| --- | --- |
| 总览：条数 / 方法 / 状态码 / 域名分布 | `& python "<TOOLS>\flow_probe.py" "<文件或目录>"` |
| 请求总表（只看接口加 `--only-api`） | `& python "<TOOLS>\flow_index.py" "<文件>" --only-api` |
| 按接口切片导出 JSON | `& python "<TOOLS>\flow_slice.py" "<文件>" -o "<输出目录>"` |
| 单条精查（可取响应体） | `& python "<TOOLS>\flow_extract.py" "<文件>" --idx <N>` |
| 复现某条请求（默认 dry-run） | `& python "<TOOLS>\flow_replay.py" "<文件>" --idx <N>` |

> 上面表格里若是仍然看到字面的 `<TOOLS>`，说明你没被自动注入 —— 那就先用 `glob` 找
> `flow_probe.py` 的实际位置，把 `<TOOLS>` 换成它所在的目录再用。

- `&` 是 pwsh 的调用运算符，路径含空格或中文时必须写 `& python "<路径>"`。
- 控制台编码问题会让脚本输出乱码；先跑 `$env:PYTHONIOENCODING='utf-8'`（一次即可）。
- 脚本输出**含敏感信息**（cookie、token）。只在本机处理，不要粘贴到任何外部服务。
- 更细的参数、字段含义、退出码见同一个包里的 `skills\scrape-toolkit\SKILL.md`。
