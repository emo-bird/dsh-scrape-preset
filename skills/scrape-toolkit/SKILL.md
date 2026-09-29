---
name: scrape-toolkit
description: 抓包分析与接口复现工具集（mitmproxy .flow 文件）。当手上有 capture/*.flow 需要摸清接口、切片喂本地模型、或复现某条请求时使用。四个脚本：flow_probe（体检）/ flow_index（请求总表）/ flow_slice（分片）/ flow_extract（单条精简）/ flow_replay（复现）。Use when you need to inspect, slice, extract, or replay requests from a mitmproxy flow capture.
---

# scrape-toolkit — 抓包分析与接口复现

mitmproxy 的 `.flow` 是原生序列化格式：**现代版本写 tnetstring 记录流**，首条记录形如
`1628:9:websocket;...`（`NNN:` 是长度前缀）；`!mitmproxy` 是**旧版**格式的魔法头（两者
`flow_probe.py` 都能读，不需要先转 HAR，也不要因为看到 `NNN:` 就当成坏文件）。

脚本位置：`C:\Project\dsh-scrape-preset\tools\`

## 铁律

1. **绝不把整份抓包读进上下文**。`.flow` 动辄几 MB，先跑 `flow_index.py` 出总表，
   确认目标接口后再 `flow_extract.py` 或 `flow_slice.py` 只取需要的部分。
2. **抓包可能含隐私**（真实姓名、手机号出现在 URL query 里是常见情况）。
   分片与提取结果**只喂本地模型**（`local-llm`），绝不喂云端。
3. **`flow_replay.py` 默认 dry-run**。不加 `--send` 不发任何请求。
   只对你有授权测试的站点用，优先只读接口。会留痕、有风控的接口先问用户。
4. 所有脚本只读抓包文件，不修改它。

## 标准流程

```
capture/xxx.flow
      │
      ├─① flow_probe.py    ← 体检：能不能读、多少条、哪些域名
      │
      ├─② flow_index.py    ← 请求总表（idx/method/status/体积/host/path）
      │                       与用户确认「哪几条是目标接口」
      │
      ├─③ flow_slice.py    ← 按 host+路径首段分片，每片约 24KB
      │   └→ 分片喂 local-llm（workflow 的 agent() 钩子）提炼成结构化 JSON
      │   └→ 汇总成 docs/接口清单.md
      │
      └─④ flow_replay.py   ← 按接口清单复现请求，证明清单是对的
```

## ① flow_probe.py — 体检

```powershell
python C:\Project\dsh-scrape-preset\tools\flow_probe.py capture\xxx.flow
```

输出：文件头、flow 总数、方法分布、状态码分布、Top 域名、前若干条样本 URL。
用来判断「这份抓包有没有我要的东西」。

## ② flow_index.py — 请求总表

```powershell
# 打印到屏幕
python ...\flow_index.py capture\xxx.flow --only-api

# 落盘成 markdown，方便贴进 docs/
python ...\flow_index.py capture\xxx.flow --only-api -o docs\抓包总表.md

# 只要某个域名
python ...\flow_index.py capture\xxx.flow --host www.example.com

# 机器可读
python ...\flow_index.py capture\xxx.flow --json capture\index.json
```

常用参数：`--only-api` 去静态资源、`--min-size` 只留大响应、`--max-rows` 限制行数。

## ③ flow_slice.py — 分片喂本地模型

```powershell
python ...\flow_slice.py capture\xxx.flow -o capture\slices --only-api --max-bytes 24576
```

产出 `slices/slice_01.json`、`slice_02.json`… 加一份 `manifest.json`。
每片结构：

```json
{
  "slice": 1,
  "group": { "host": "www.example.com", "segment": "api" },
  "requests": [
    {
      "idx": 12, "method": "POST", "url": "...", "status": 200,
      "req_headers": { ... 只留关键项 ... },
      "req_body": "...", "req_body_json": { ... },
      "resp_headers": { ... },
      "resp_size": 1234,
      "resp_schema": { ... 结构骨架，值被替换成类型名 ... },
      "resp_preview": null
    }
  ]
}
```

**`resp_schema` 是关键**：它把响应 JSON 的值全部替换成类型名
（`str` / `int` / `{"__list__": {...}, "__count__": 12}`），
既让模型看懂结构，又把体积压到极小。这就是省 token 的核心。

`--cookie-mode` 三档：

| 档 | 效果 | 什么时候用 |
|---|---|---|
| `summary`（默认） | 只留 cookie 名字 | 喂本地模型 |
| `full` | 完整 cookie 值 | 要在本地复现请求时 |
| `drop` | 完全去掉 | 纯粹看结构 |

给本地模型的提示词模板：

```
以下是抓包分片 JSON。请为每个 request 输出一行结构化结论，只要 JSON 数组，不要解释：
[{"idx":N,"接口用途":"一句话","是否业务接口":true/false,
  "请求参数":{...},"响应关键字段":[...],
  "可疑签名字段":[...],"是否依赖cookie":true/false}]
```

## ④ flow_extract.py — 单条精简

```powershell
# 先看前 20 条都有什么
python ...\flow_extract.py capture\xxx.flow --list 20

# 提取第 37 条
python ...\flow_extract.py capture\xxx.flow --idx 37

# 按 URL 片段找
python ...\flow_extract.py capture\xxx.flow --url-contains /api/conversations

# 落盘
python ...\flow_extract.py capture\xxx.flow --idx 37 -o capture\req37.json
```

比 `flow_slice.py` 更细：带上 `resp_body_json` 原文（默认最多 6000 字符），
用于手工分析单条接口。

## ⑤ flow_replay.py — 复现请求

```powershell
# 默认 dry-run，只打印将要发送什么
python ...\flow_replay.py capture\xxx.flow --idx 37

# 真发
python ...\flow_replay.py capture\xxx.flow --idx 37 --send

# 改参数重打
python ...\flow_replay.py capture\xxx.flow --idx 37 --send --set-query page=2 --set-query limit=20

# 换 Referer / 换 body
python ...\flow_replay.py capture\xxx.flow --idx 37 --send --set-header Referer:https://example.com/list --set-body '{"a":1}'
```

`--set-query K=V` 加或改一个 query 参数；写 `--set-query K`（不带 `=`）则删掉它。
`--set-header K:V` 加或改请求头。

**dry-run 的输出会自动脱敏**：cookie 只显示名字，`Authorization` 只显示前 14 字符。

## 环境

- Python 3.14.7（`python` 在 PATH）
- mitmproxy 12.2.3 作为库使用（`pip install mitmproxy` 已装）
- 抓包时用户侧：`mitmweb --listen-port 8080 --web-port 8081`
  + Edge 用 ZeroOmega 切到 `mitm` 情景模式（只代理目标站点）
- 抓完提醒用户：ZeroOmega 切回「直接连接」并停掉 mitmweb

## 排错

| 现象 | 原因 | 处理 |
|---|---|---|
| `mitmproxy import failed` | 没装库 | `python -m pip install mitmproxy` |
| 文件头既不是 `NNN:...` 也不是 `!mitmproxy` | 是 HAR 或别的格式 | 让用户在 mitmweb 里重新 Save，或改用 HAR 解析路径 |
| `no matching request found` | idx 是全局序号，受 `--host`/`--only-api` 过滤影响 | 先跑 `flow_extract.py --list` 看真实序号 |
| 输出中文乱码 | Windows 控制台编码 | 脚本已强制 utf-8；仍乱码则 `$env:PYTHONIOENCODING='utf-8'` |
| 复现返回 403 | cookie 过期 / 站点检测 | **上报用户**，不要自己绕 |