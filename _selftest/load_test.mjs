// Pre-flight test for bundle/lean-agent.js. Two layers:
//
//   1. LOAD   — apply() runs against a stub ctx, proving the module loads and
//               registers a well-formed tool without a live preset session.
//   2. SCHEMA — the registered `parameters` and `output.schema` are validated
//               with the REAL dsh-tools checkers. This is the layer that matters:
//               raw ctx.tools.register() does NOT compile the defineTool author
//               DSL, so a DSL-shaped literal passes a stub ctx and then throws
//               JsonSchemaError in a real session. A stub ctx alone cannot catch
//               that, which is exactly how the bug this test guards against got in.
//   3. RUN    — execute() is driven against a stub subagents.start() to assert the
//               child request is shaped correctly (notably: `structured_output`
//               must NOT be in toolFilter.allow).
import { pathToFileURL, fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

const target = process.argv[2];
if (!target) {
  console.log('usage: node load_test.mjs <path-to-lean-agent.js>');
  process.exit(2);
}

let failures = 0;
function check(label, ok, detail) {
  console.log((ok ? 'ok   ' : 'FAIL ') + label + (detail === undefined ? '' : ' — ' + detail));
  if (!ok) failures += 1;
}

const mod = await import(pathToFileURL(target).href);

console.log('=== module exports ===');
console.log('keys   :', Object.keys(mod).sort().join(', '));
console.log('name   :', mod.name);
console.log('inject :', JSON.stringify(mod.inject));
console.log('apply  :', typeof mod.apply);
if (typeof mod.apply !== 'function') {
  console.log('FAIL: no apply export');
  process.exit(1);
}

// ---------------------------------------------------------------- 1. LOAD
let registered;
const stub = {
  tools: { register(tool) { registered = tool; } },
  subagents: { start() { throw new Error('subagents.start must not be reached in a load test'); } }
};

mod.apply(stub, {
  toolName: 'lean_agent',
  backend: 'spawn',
  provider: 'local-llm',
  model: 'ornith-1.5-9b-dsh-agentic-gpt-5.6-sol-distill'
});

console.log('');
console.log('=== registered tool ===');
if (!registered) {
  console.log('FAIL: nothing registered');
  process.exit(1);
}
console.log('name              :', registered.name);
console.log('description chars :', registered.description.length);
console.log('parameters root   :', registered.parameters.type, '| props:',
  Object.keys(registered.parameters.properties ?? {}).join(', '));
console.log('required          :', JSON.stringify(registered.parameters.required));
console.log('tools param       :', registered.parameters.properties?.tools?.type, '/ items',
  registered.parameters.properties?.tools?.items?.type);
console.log('output props      :', Object.keys(registered.output.schema.properties).join(', '));
console.log('isConcurrencySafe :', registered.isConcurrencySafe());
console.log('execute is fn     :', typeof registered.execute === 'function');

// --------------------------------------------------------------- 2. SCHEMA
console.log('');
console.log('=== schema validation against real dsh-tools ===');

// Locate the running DSH checkout: derive from this file's own install location
// (…/preset/scrape/_selftest/…) or fall back to the recorded app root.
function findDshTools() {
  const candidates = [
    process.env.DSH_APP_ROOT ? join(process.env.DSH_APP_ROOT, 'node_modules/@deepseek-ai/dsh-tools/lib/index.js') : undefined,
    'C:/Program Files/DSH NEXT/resources/app/node_modules/@deepseek-ai/dsh-tools/lib/index.js',
    // a real profile install: <profile>/node_modules/... resolves via the bundle link
    join(resolve(dirname(fileURLToPath(import.meta.url)), '../../..'), 'node_modules/@deepseek-ai/dsh-tools/lib/index.js')
  ].filter(Boolean);
  return candidates.find((p) => existsSync(p));
}

const dshToolsPath = findDshTools();
if (dshToolsPath === undefined) {
  console.log('SKIP  dsh-tools not found — cannot validate schemas against the real checker.');
  console.log('      Set DSH_APP_ROOT to the DSH resources/app directory to enable this layer.');
} else {
  console.log('using:', dshToolsPath);
  // NOTE: validateArgs() is the defineTool path — it runs the spec through
  // parameterSchemaSpecToJsonSchema first, so it expects the DSL, not raw JSON
  // Schema. Raw registrations must be validated with validateJsonSchemaValue.
  const { assertSupportedJsonSchema, validateJsonSchemaValue } = await import(pathToFileURL(dshToolsPath).href);

  try {
    assertSupportedJsonSchema(registered.parameters);
    check('parameters is a supported JSON Schema', true);
  } catch (error) {
    check('parameters is a supported JSON Schema', false, String(error && error.message));
  }

  try {
    assertSupportedJsonSchema(registered.output.schema);
    check('output.schema is a supported JSON Schema', true);
  } catch (error) {
    check('output.schema is a supported JSON Schema', false, String(error && error.message));
  }

  if (typeof validateJsonSchemaValue === 'function') {
    const violationsOf = (args) => validateJsonSchemaValue(registered.parameters, args, '');
    const ok = violationsOf({ prompt: 'hello' });
    check('args {prompt} validate clean', Array.isArray(ok) && ok.length === 0, JSON.stringify(ok));
    const missing = violationsOf({});
    check('args {} are rejected (missing required prompt)', Array.isArray(missing) && missing.length > 0, JSON.stringify(missing));
    const wrong = violationsOf({ prompt: 42 });
    check('args {prompt:42} are rejected (wrong type)', Array.isArray(wrong) && wrong.length > 0, JSON.stringify(wrong));
  }
}

// ------------------------------------------------------------------ 3. RUN
console.log('');
console.log('=== render() ===');
console.log('with text :', JSON.stringify(registered.output.render(undefined, { text: 'hello', stopReason: 'completed' })));
console.log('empty text:', JSON.stringify(registered.output.render(undefined, { text: '', stopReason: 'completed' })));

console.log('');
console.log('=== execute() child request shape ===');
let captured;
const runStub = {
  tools: { register(tool) { registered = tool; } },
  subagents: {
    async start(backend, options) {
      captured = { backend, options };
      return {
        result: Promise.resolve({ output: [{ type: 'text', text: 'child output' }], stopReason: 'completed' }),
        async dispose() { captured.disposed = true; }
      };
    }
  }
};
mod.apply(runStub, { backend: 'spawn' });

const tool = registered;
const exec = { agent: {}, signal: undefined };
const value = await tool.execute(
  { prompt: 'do the thing', description: 'unit test', tools: ['read', 'glob'], schema: '{"type":"object","properties":{"a":{"type":"string"}},"required":["a"]}' },
  exec
);

console.log('backend           :', captured.backend);
console.log('label             :', captured.options.label);
console.log('prompt blocks     :', JSON.stringify(captured.options.prompt));
console.log('toolFilter.allow  :', JSON.stringify(captured.options.toolFilter.allow));
console.log('agentOptions      :', JSON.stringify(captured.options.agentOptions));
console.log('outputSchema      :', JSON.stringify(captured.options.outputSchema));
console.log('has persona       :', typeof captured.options.persona === 'string' && captured.options.persona.length > 0);
console.log('returned value    :', JSON.stringify(value));
console.log('disposed          :', captured.disposed === true);

check('backend passed through', captured.backend === 'spawn');
check('prompt forwarded as text blocks', Array.isArray(captured.options.prompt) && captured.options.prompt[0]?.text === 'do the thing');
check('persona supplied', typeof captured.options.persona === 'string' && captured.options.persona.length > 0);
check('toolFilter.allow keeps requested tools', JSON.stringify(captured.options.toolFilter.allow) === JSON.stringify(['read', 'glob']));
check(
  'toolFilter.allow does NOT name structured_output (restrict() would reject it)',
  !captured.options.toolFilter.allow.includes('structured_output')
);
check('outputSchema parsed from JSON text', captured.options.outputSchema?.properties?.a?.type === 'string');
check('run disposed', captured.disposed === true);
check('value.text from child output', value.text === 'child output');
check('value.stopReason surfaced', value.stopReason === 'completed');
check('value.structured absent when driver returns none', !('structured' in value));

console.log('');
console.log('=== apply() with no config (defaults) ===');
mod.apply({ tools: { register(t) { registered = t; } }, subagents: {} }, undefined);
console.log('default name:', registered.name);
check('default tool name is lean_agent', registered.name === 'lean_agent');

console.log('');
if (failures === 0) {
  console.log('LOAD TEST OK');
} else {
  console.log('LOAD TEST FAILED — ' + failures + ' check(s) failed');
  process.exit(1);
}
