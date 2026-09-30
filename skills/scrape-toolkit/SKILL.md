---
name: scrape-toolkit
description: 抓包分析与接口复现工具集（mitmproxy .flow 文件）。当手上有 capture/*.flow 需要摸清接口、切片喂本地模型、或复现某条请求时使用。五个脚本：flow_probe（体检）/ flow_index（请求总表）/ flow_slice（分片）/ flow_extract（单条精简）/ flow_replay（复现）。Use when you need to inspect, slice, extract, or replay requests from a mitmproxy flow capture.
---

# scrape-toolkit — 抓包分析与接口复现

mitmproxy 的 `.flow` 是原生序列化格式：**现代版本写 tnetstring 记录流**，首条记录形如
`1628:9:websocket;...`（`NNN:` 是长度前缀）；`!mitmproxy` 是**旧版**格式的魔法头（两者
`flow_probe.py` 都能读，不需要先转 HAR，也不要因为看到 `NNN:` 就当成坏文件）。

脚本位置：`tools\` 目录，与本技能同级（`<本 preset 包根>\tools\`）。已装到 profile 时
就是 `<profile>\node_modules\@emo-bird\dsh-preset-scrape\tools\`；在仓库里开发时就是
`<仓库根>\tools\`。下面统一用 `$T` 指代这个目录，取不到时先 `Get-Location` 确认再拼。

## 铁律

1. **绝不把整份抓包读进上下文**。`.flow` 动辄几 MB，先跑 `flow_index.py` 出总表，
   确认目标接口后再 `flow_extract.py` 或 `flow_slice.py` 只取需要的部分。
2. **抓包可能含隐私**（真实姓名、手机号出现在 URL query 里是常见情况）。
   分片与提取结果**只喂本地模型**（`local-llm`），绝不喂云端。
   注意两处脱敏**不对称**，别记混：
   - `flow_slice.py` / `flow_extract.py` 会截断 `Authorization`、`x-token`、`x-sign`、
     `x-signature`、`x-api-key`（且无视 `--cookie-mode`）；
   - `flow_replay.py` 的 dry-run **只**脱敏 cookie 和 `Authorization`，
     `x-sign` 这类自定义凭证会**原样打印**。
   所以 dry-run 输出同样含敏感信息，**不要随手贴进云端对话**。
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
      ├─③ flow_slice.py    ← 按 (host, 路径首段) 分组切片，每片约 24KB
      │   └→ 分片喂 local-llm（workflow 的 agent() 钩子）提炼成结构化 JSON
      │   └→ 汇总成 docs/接口清单.md
      │
      └─④ flow_replay.py   ← 按接口清单复现请求，证明清单是对的
```

（`flow_extract.py` 不在这条主线上，它是单条精查的旁路工具，见 ④ 节。）

## ① flow_probe.py — 体检

```powershell
python "$T\flow_probe.py" capture\xxx.flow
```

输出：文件头字节、legacy 魔法头判定、flow 总数与其中 http 条数、方法分布、状态码分布、
Top 域名（`--top`，默认 25）、样本 URL（`--samples`，默认 20）。
用来判断「这份抓包有没有我要的东西」。

两点实际行为：

- 没有 response 的流状态码记成 `None`，样本行显示 `NO-RESPONSE`，不是错误。
- 状态码、方法、域名统计的是 **flow 全量**，不受 `--samples` 影响。

## ② flow_index.py — 请求总表

```powershell
# 打印到屏幕
python "$T\flow_index.py" capture\xxx.flow --only-api

# 落盘成 markdown，方便贴进 docs/
python "$T\flow_index.py" capture\xxx.flow --only-api -o docs\抓包总表.md

# 只要某个域名（可重复传）
python "$T\flow_index.py" capture\xxx.flow --host www.example.com

# 机器可读
python "$T\flow_index.py" capture\xxx.flow --json capture\index.json
```

输出是一张 markdown 表，列为
`idx | method | status | resp | req | host | path | ctype`，屏幕打印上限 `--max-rows`（默认 500，
超出会打印「N more rows truncated」）；**`-o` 写文件时不受 `--max-rows` 限制，写全量**。

常用参数：`--only-api` 去静态资源（按扩展名判定，见下）、`--min-size` 只留响应体积
≥ 该字节数的条目、`--host` 反复传可多选。

**`--only-api` 是纯扩展名判定**（`flow_index.py:26-30, 43-45`），只砍以 `.js .mjs .css
.png .jpg .jpeg .gif .svg .webp .ico .woff .woff2 .ttf .eot .map .mp4 .webm .mp3 .wav
.avif .bmp` 结尾的路径。像 `/api/getData` 这种没有扩展名的接口一律保留，
所以它**不会**漏掉接口，但也**不会**过滤掉 `/track?e=png` 这类伪装路径。

`--json` 每行的字段：`idx / method / status / size / host / path / query / ctype /
req_body / url`（`req_body` 是请求体**字节数**，不是内容）。

## ③ flow_slice.py — 分片喂本地模型

```powershell
python "$T\flow_slice.py" capture\xxx.flow -o capture\slices --only-api --max-bytes 24576
```

产出 `slices/slice_01.json`、`slice_02.json`… 加一份 `manifest.json`。
每片结构：

```json
{
  "slice": 1,
  "group": { "host": "www.example.com", "segment": "api" },
  "requests": [
    {
      "idx": 12, "method": "POST", "url": "...", "host": "...", "path": "...",
      "query": "...", "status": 200,
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
（`str` / `int` / `bool` / `float` / `null` / `{"__list__": {...}, "__count__": 12}`），
既让模型看懂结构，又把体积压到极小。这就是省 token 的核心。

**`resp_schema` 与 `resp_preview` 互斥**：响应体是合法 JSON 才有 `resp_schema`，
否则 `resp_schema` 为 `null` 而 `resp_preview` 放前 1200 字符原文（HTML 报错页走这条）。
没有 response 的流两者都是 `null`。

分片规则（`flow_slice.py:194-265`）有三条，别被「按 host+路径首段分片」这句话误导：

1. **分组**按 `(host, 路径首段)`：`/v2/a` 与 `/v2/b` 同组，`/wiki/x` 是另一组。
   路径首段是 `path.strip("/").split("/")[0]`，根路径 `/` 的段是空串。
2. **同组不相邻时会被拆成多片**。代码是顺序扫描、只在「当前组 key 变了」时切分，
   并不跨组归并。所以 `A B A` 三条流会产出 `A`、`B`、`A` **三片**，不是两片。
3. 单片字节数超过 `--max-bytes`（默认 24576）时继续切，所以一个组也可能出多片。

其余参数：`--max-body` 单条正文上限字符数（默认 4000）、
`--host` 反复传可多选、`--only-api` 同 `flow_index.py` 的扩展名判定。
`manifest.json` 记录每片的 `host / segment / requests / bytes / idx` 区间 ——
**靠它可以按需求去只读某一两片，不要整目录读进来**。

`--cookie-mode` 三档：

| 档 | 效果 | 什么时候用 |
|---|---|---|
| `summary`（默认） | 只留 cookie 名字，形如 `<2 cookies: sid, uid>` | 喂本地模型 |
| `full` | 完整 cookie 值 | 要在本地复现请求时 |
| `drop` | 完全去掉 Cookie 头 | 纯粹看结构 |

**注意 `--cookie-mode full` 只影响 Cookie**。`Authorization` 与 `x-token` / `x-sign` /
`x-signature` / `x-api-key` / `api-key` 无论哪一档都会被 `redact()` 截断
（`flow_slice.py:88-95`），这是硬编码的，不要指望 `full` 能拿到它们。

请求头只保留 `content-type / accept / accept-language / referer / origin / user-agent /
authorization / x-requested-with / content-length / x-csrf-token / x-xsrf-token / x-token /
x-sign / x-signature`，外加任何 `x-` 或 `sec-` 开头的；其余丢弃。单值截到 300 字符。

给本地模型的提示词模板：

```
以下是抓包分片 JSON。请为每个 request 输出一行结构化结论，只要 JSON 数组，不要解释：
[{"idx":N,"接口用途":"一句话","是否业务接口":true/false,
  "请求参数":{...},"响应关键字段":[...],
  "可疑签名字段":[...],"是否依赖cookie":true/false}]
```

## ④ flow_extract.py — 单条精简

```powershell
# 先看前 N 条都有什么（N 是「扫到第 N 条 http 就停」，不是「显示 N 条」）
python "$T\flow_extract.py" capture\xxx.flow --list 20

# 提取第 37 条
python "$T\flow_extract.py" capture\xxx.flow --idx 37

# 按 URL 片段找（取第一条命中的）
python "$T\flow_extract.py" capture\xxx.flow --url-contains /api/conversations

# 落盘
python "$T\flow_extract.py" capture\xxx.flow --idx 37 -o capture\req37.json
```

比 `flow_slice.py` 更细：带上 `resp_body_json` 原文（默认最多 6000 字符），
用于手工分析单条接口。

实际行为：

- `--idx` / `--url-contains` / `--list` 三选一，都不给会报
  `flow_extract.py: error: give --idx, --url-contains, or --list` 并以 **exit 2** 退出。
- `--list N` 打印前 N 条 http 后**直接退出**，不会走后面的提取流程。
- 找不到时打印 `no matching request found` 并以 **exit 1** 退出。
- 响应体是 JSON 时给 `resp_schema`，并且**只有 `--max-body >= 6000`（默认满足）才同时给
  `resp_body_json` 原文**；把 `--max-body` 调小会导致 `resp_body_json` 变 `null`。
- 字段名与 slice 略有不同：请求体叫 `req_body_text`（不是 `req_body`），
  且多一个 `http_version`。
- 请求头白名单比 slice **少** `x-csrf-token / x-xsrf-token / x-token / x-sign / x-signature`
  这几个具名项，但仍然保留任何 `x-` / `sec-` 开头；单值截到 400 字符。
- 脱敏规则与 slice 相同且同样无视 `--cookie-mode`：`Authorization` 截前 14 字符，
  `x-token / x-sign / x-signature / x-api-key / api-key` 截前 8 字符。

## ⑤ flow_replay.py — 复现请求

```powershell
# 默认 dry-run，只打印将要发送什么
python "$T\flow_replay.py" capture\xxx.flow --idx 37

# 真发
python "$T\flow_replay.py" capture\xxx.flow --idx 37 --send

# 改参数重打
python "$T\flow_replay.py" capture\xxx.flow --idx 37 --send --set-query page=2 --set-query limit=20

# 换 Referer / 换 body
python "$T\flow_replay.py" capture\xxx.flow --idx 37 --send --set-header Referer:https://example.com/list --set-body '{"a":1}'

# 只要响应体原文
python "$T\flow_replay.py" capture\xxx.flow --idx 37 --send --dry-body
```

`--set-query K=V` 加或改一个 query 参数；写 `--set-query K`（不带 `=`）则删掉它。
重复传同一个 key 时**后一个覆盖前一个**（内部用的是 dict）。
`--set-header K:V` 加或改请求头，**必须带冒号**，否则报
`--set-header wants K:V`。`--set-body` 直接替换请求体。

实际行为：

- 不给 `--idx` 也不给 `--url-contains` 时报
  `flow_replay.py: error: give --idx or --url-contains` 并 **exit 2**。
- 没有 `--dry-body` 选项时，`--send` 后响应若是 JSON 会格式化打印（`--max-response`
  默认 4000 字符截断），否则打印原文。
- 发送用的是标准库 `urllib`，**不走 mitmproxy 代理**；`Host / Content-Length /
  Connection / Accept-Encoding / Transfer-Encoding / Upgrade / Proxy-Connection /
  TE / Trailer` 这些头会被丢掉，由 urllib 自己重算。
- 有 body 而没显式 Content-Type 时自动补 `application/json`。
- 请求失败（超时、DNS 等）打印 `request failed: <类型>: <信息>` 并 **exit 1**；
  HTTP 4xx/5xx 不算失败，会正常打印状态码和响应体。

**dry-run 的输出会自动脱敏 —— 但只脱 cookie 和 Authorization**（`flow_replay.py:119-126`）：
cookie 只显示名字，`Authorization` 只显示前 14 字符。
⚠️ **`x-sign` / `x-token` / `x-api-key` 之类的自定义凭证在 dry-run 里是原样打印的**
（与 `flow_slice.py` / `flow_extract.py` 的 `redact()` 不同）。所以 dry-run 输出同样
含敏感信息，**不要随手贴进云端对话**。

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