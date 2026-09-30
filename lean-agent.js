/**
 * lean_agent — 轻量子代理工具（本 preset 专用）。
 *
 * 为什么需要它：workflow 工具的 agent() 钩子在 PTC 引擎里只认
 * prompt / provider / model / schema 四个字段（见 dsh-workflow-ptc 的
 * childRequest()），无法为每个子代理指定 persona 与工具白名单。结果是每个
 * 子代理都整套继承父 preset：数千字的 persona + 全部工具 schema，批量跑
 * 就是成倍重复付费。
 *
 * 本插件把 subagents.start() 缺失的那两个口子补上：
 *   - persona   → 换成一句极短的话（同名 section 覆盖，不是叠加）
 *   - toolFilter → 只留调用方点名的工具
 *
 * 另外，小模型在没有「环境手册」时会反复做注定失败的事（在这台 Windows 机器上用
 * bash、用 [System.IO.File]:: 读文件、往只读沙箱里写文件、把二进制抓包喂给 read_image），
 * 而这些错误又常常不给出可读的报错。所以本插件在注册时会读取同包的
 * skills/subagent-brief/SKILL.md，把它的正文追加到每个子代理的 persona 后面 ——
 * 子代理不需要主动调用 skill 工具就能拿到这份手册。
 * 设 config.brief = false 可关闭（例如换一个与本手册无关的任务域）。
 *
 * 零依赖：不 import 任何**包**（只用 node: 内置模块），直接用 ctx.tools.register
 * 的原始对象形式（与 dsh-subagent-in-process-driver 里 attachStructuredRuntime
 * 的写法一致），因此不需要 bundle 目录能解析 @deepseek-ai/* 包。
 *
 * 代价：原始 register 不编译作者 DSL（那是 defineTool 的事）——
 *   - parameters 必须写成真正的 JSON Schema（根部 object + properties + required 数组）；
 *   - output.schema 会先过 assertSupportedJsonSchema，同样只接受真 JSON Schema
 *     （属性级 required:true 与 type:'json' 会被拒）。
 *
 * @module lean-agent
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/** 默认 persona：一句话，替换掉父 preset 的整份 persona。 */
const DEFAULT_PERSONA =
  'You are a focused worker. Do exactly the task in the prompt and reply concisely. ' +
  'You have no other responsibilities and no tools beyond the ones provided.';

/**
 * 环境手册正文（`skills/subagent-brief/SKILL.md`），以及正文里 `<TOOLS>` 要替换成的
 * 绝对路径。两个都相对 lean-agent.js 自己的位置解析 —— 仓库里开发时是 <仓库根>/，
 * 装进 profile 后是 <profile>/node_modules/@emo-bird/dsh-preset-scrape/，两种都对。
 *
 * 注意：手册正文里**故意不写出占位符的字面量**（只写 `<TOOLS>` 这种说明性写法），
 * 否则下面那行朴素替换会把「解释占位符的那句话」也一起替换掉，子代理会读到自相矛盾的说明。
 */
const BRIEF_URL = new URL('./skills/subagent-brief/SKILL.md', import.meta.url);
const TOOLS_DIR = fileURLToPath(new URL('./tools/', import.meta.url)).replace(/[\\/]+$/, '');
const TOOLS_PLACEHOLDER = '<TOOLS>';

/**
 * 读取环境手册正文。读不到就返回 undefined —— 缺一份文档不该让工具注册失败，
 * 更不该让整个 preset 起不来。
 */
function loadBrief() {
  let raw;
  try {
    raw = readFileSync(BRIEF_URL, 'utf8');
  } catch {
    return undefined;
  }
  // 去掉 YAML frontmatter：那是给技能目录扫描器看的，喂给子代理纯属浪费 token。
  const body = raw.replace(/^---\r?\n[\s\S]*?\r?\n---[ \t]*\r?\n/, '');
  // 手册正文里写 `<TOOLS>` 表示脚本目录；替换成真实绝对路径。
  const text = body.split(TOOLS_PLACEHOLDER).join(TOOLS_DIR).trim();
  return text.length > 0 ? text : undefined;
}

/** 从子代理的 output blocks 里拼出纯文本。 */
function textOf(output) {
  if (!Array.isArray(output)) return '';
  const parts = [];
  for (const block of output) {
    if (
      block !== null &&
      typeof block === 'object' &&
      block.type === 'text' &&
      typeof block.text === 'string'
    ) {
      parts.push(block.text);
    }
  }
  return parts.join('');
}

/** 把非 completed 的 stopReason 翻成错误文案；completed 返回 undefined。 */
function stopReasonError(result) {
  switch (result === undefined || result === null ? undefined : result.stopReason) {
    case 'completed':
      return undefined;
    case 'aborted':
      return 'lean_agent run was cancelled';
    case 'error':
      return 'lean_agent run failed';
    case 'max-tokens':
      return 'lean_agent run hit its token limit before finishing';
    case 'refusal':
      return 'lean_agent declined the task';
    default:
      return 'lean_agent ended abnormally (' + String(result && result.stopReason) + ')';
  }
}

/** 接受 JSON 文本或对象；其他一律报错，避免把坏 schema 传下去。 */
function parseSchema(value) {
  if (value === undefined || value === null || value === '') return undefined;
  if (typeof value === 'string') {
    let parsed;
    try {
      parsed = JSON.parse(value);
    } catch (error) {
      throw new Error('lean_agent: schema 不是合法 JSON：' + String(error && error.message));
    }
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('lean_agent: schema 必须是一个对象根（object-rooted）的 JSON Schema');
    }
    return parsed;
  }
  if (typeof value === 'object' && !Array.isArray(value)) return value;
  throw new Error('lean_agent: schema 必须是对象或 JSON 文本');
}

export const name = 'tool-lean-agent';

export const inject = ['tools', 'subagents'];

/**
 * 注册 lean_agent 工具。
 * @param ctx - 当前 preset 作用域的 Context。
 * @param config - 可选：toolName / backend / provider / model / persona。
 */
export function apply(ctx, config) {
  const cfg = config === undefined || config === null ? {} : config;
  const toolName = typeof cfg.toolName === 'string' && cfg.toolName.length > 0 ? cfg.toolName : 'lean_agent';
  // backend 是 subagent 后端名（spawn / fork），不是 LLM provider。
  const backend = typeof cfg.backend === 'string' && cfg.backend.length > 0 ? cfg.backend : 'spawn';
  const defaultProvider = typeof cfg.provider === 'string' ? cfg.provider : undefined;
  const defaultModel = typeof cfg.model === 'string' ? cfg.model : undefined;
  const defaultPersona =
    typeof cfg.persona === 'string' && cfg.persona.length > 0 ? cfg.persona : DEFAULT_PERSONA;
  // 环境手册：默认注入。cfg.brief === false 关闭；文件缺失时自动退化为不注入。
  const brief = cfg.brief === false ? undefined : loadBrief();

  /** persona = 角色（调用方给的或内置的）+ 环境手册（append，不覆盖角色）。 */
  const personaFor = (args) => {
    const base =
      typeof args.persona === 'string' && args.persona.length > 0 ? args.persona : defaultPersona;
    return brief === undefined ? base : base + '\n\n' + brief;
  };

  ctx.tools.register({
    name: toolName,
    description:
      'Run one delegated subagent with a minimal system prompt and only the tools you name. ' +
      'Unlike the workflow tool, this call sets the child persona and the child tool allow-list per ' +
      'invocation, so the child does NOT inherit this preset\'s full persona or its whole tool schema. ' +
      'Use it for high-token, low-difficulty offload: HTML/DOM structure analysis, selector and endpoint ' +
      'extraction, summarising or compressing long content, batch classification, translation, structured ' +
      'extraction to JSON/CSV, boilerplate/regex/SQL drafts, commit messages, document drafts, log ' +
      'clustering. Returns the child\'s text output and, when a schema is supplied, its structured result. ' +
      'The child always also receives this preset\'s environment brief (sandbox rules and how to read ' +
      'mitmproxy captures), so it does not need to be told those things in the prompt. ' +
      'Runs in the foreground. The child cannot delegate further.',
    // 原始 ctx.tools.register() 不做 DSL 编译（那是 defineTool 的事），
    // 所以 parameters 必须写成真正的 JSON Schema：根部 object + properties + required 数组。
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        prompt: {
          type: 'string',
          description:
            'The complete, self-contained task for the child. It does not share this conversation\'s context, ' +
            'so include everything it needs. State the required output shape explicitly.'
        },
        description: {
          type: 'string',
          description: 'A short (3-5 word) label for display.'
        },
        tools: {
          type: 'array',
          items: { type: 'string' },
          description:
            'Names of the tools the child may call, chosen from the tools this preset already exposes ' +
            '(an unknown name fails the run). Default: none (empty list). The child has no other tools, ' +
            'so a pure extraction or summarisation task usually needs none. When a schema is supplied, ' +
            'structured_output is registered by the driver into the child\'s own scope and stays usable ' +
            'without being named here.'
        },
        schema: {
          type: 'string',
          description:
            'Optional object-rooted JSON Schema, as JSON text. When supplied, the child must report its result ' +
            'by calling structured_output, and that validated object comes back in the structured field.'
        },
        persona: {
          type: 'string',
          description:
            'Optional replacement persona for the child (one short paragraph). Omit to use the built-in minimal ' +
            'persona. This REPLACES the preset persona inside the child, it does not add to it. The environment ' +
            'brief is appended after whatever persona is used here, so do not repeat sandbox rules in it.'
        },
        provider: {
          type: 'string',
          description:
            'Optional LLM provider for the child, e.g. local-llm. Omit to use the configured default, or to ' +
            'inherit the parent route.'
        },
        model: {
          type: 'string',
          description: 'Optional model id for the child. Supply together with provider.'
        }
      },
      required: ['prompt']
    },
    output: {
      // 同样必须是真 JSON Schema：register() 会对它跑 assertSupportedJsonSchema，
      // 属性级 required:true 与 type:'json' 都会被拒。structured 用注记式空 schema。
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          text: { type: 'string' },
          stopReason: { type: 'string' },
          structured: {}
        },
        required: ['text', 'stopReason']
      },
      // 调用方（模型）只能看见 render 的输出——return 出的对象本身它看不到。
      // 所以 structured 必须在这里摊成文本，否则带 schema 的调用（子代理走
      // structured_output、不产生 text）在调用方看来永远是「no text output」，
      // schema 参数就白传了。
      render: (_args, value) => {
        const blocks = [];
        const text =
          value !== null && typeof value === 'object' && typeof value.text === 'string' ? value.text : '';
        const structured =
          value !== null && typeof value === 'object' ? value.structured : undefined;
        if (text.length > 0) blocks.push({ type: 'text', text });
        if (structured !== undefined) {
          blocks.push({ type: 'text', text: JSON.stringify(structured) });
        }
        if (blocks.length === 0) {
          blocks.push({ type: 'text', text: '(lean_agent produced no text output)' });
        }
        return blocks;
      }
    },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const parent = exec.agent;
      if (parent === undefined || parent === null) {
        throw new Error('lean_agent requires a calling agent (exec.agent was undefined)');
      }

      const outputSchema = parseSchema(args.schema);
      const requested = Array.isArray(args.tools)
        ? args.tools.filter((entry) => typeof entry === 'string' && entry.length > 0)
        : [];
      // 不要把 structured_output 加进 allow：driver 在 applyChildComposition()（它会跑
      // restrict()）之后才把它注册进子代理自己的层，而 restrict() 只接受已知的全局工具名，
      // 白名单里出现它会让整次运行抛 unknown global tool。own-layer 注册本来就不受限制影响，
      // 所以不写它，结构化返回照样可用。
      const allow = Array.from(new Set(requested));

      const provider = typeof args.provider === 'string' && args.provider.length > 0 ? args.provider : defaultProvider;
      const model = typeof args.model === 'string' && args.model.length > 0 ? args.model : defaultModel;
      const agentOptions = {};
      if (provider !== undefined) agentOptions.provider = provider;
      if (model !== undefined) agentOptions.model = model;

      const label =
        typeof args.description === 'string' && args.description.length > 0 ? args.description : 'lean agent';

      const run = await ctx.subagents.start(backend, {
        label,
        prompt: [{ type: 'text', text: args.prompt }],
        parent,
        signal: exec.signal,
        persona: personaFor(args),
        toolFilter: { allow },
        ...(Object.keys(agentOptions).length === 0 ? {} : { agentOptions }),
        ...(outputSchema === undefined ? {} : { outputSchema })
      });

      try {
        const result = await run.result;
        const failure = stopReasonError(result);
        if (failure !== undefined) throw new Error(failure);
        const text = textOf(result.output);
        return {
          text,
          stopReason: String(result.stopReason),
          ...(result.structured === undefined ? {} : { structured: result.structured })
        };
      } finally {
        await run.dispose();
      }
    }
  });
}
