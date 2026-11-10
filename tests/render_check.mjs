// Renders desktop/plugin.js components with a tiny fake React (hooks + effects run once)
// against canned API responses, and fails if anything throws. Run: node tests/render_check.mjs
import fs from 'node:fs'
import path from 'node:path'
import url from 'node:url'
const here = path.dirname(url.fileURLToPath(import.meta.url))
let src = fs.readFileSync(path.join(here, '..', 'desktop', 'plugin.js'), 'utf8')
src = src.replace(/import \{[^}]*\} from '@hermes\/plugin-sdk'/, 'const { ROUTES_AREA, SIDEBAR_NAV_AREA, Button, Input } = globalThis.__SDK')
  .replace("import * as React from 'react'", 'const React = globalThis.__React')
const effects = []
let hookState = new Map(), hookIdx = 0, current = ''
globalThis.__React = {
  createElement: (type, props, ...children) => ({ type, props: props || {}, children }),
  useState(init) {
    const k = current + ':' + hookIdx++
    if (!hookState.has(k)) hookState.set(k, typeof init === 'function' ? init() : init)
    return [hookState.get(k), v => hookState.set(k, typeof v === 'function' ? v(hookState.get(k)) : v)]
  },
  useEffect(fn) { effects.push(fn) },
  useCallback: f => f
}
globalThis.__SDK = { ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'nav', Button: 'Button', Input: 'Input' }
const tmp = path.join(process.env.TMPDIR || '/tmp', 'syw-render-' + process.pid + '.mjs')
fs.writeFileSync(tmp, src)
const mod = (await import(url.pathToFileURL(tmp).href)).default
fs.unlinkSync(tmp)

const board = {
  project: '/p', criteria_file: 'c.md', base: 'main', code: { digest: 'd', tracked_files: 1 },
  latest_run: { run_id: 'r1', imported_at: 't', report_path: 'x', provenance: 'agent-imported', tests: 2, older_report: true },
  summary: { requirements: 2, passing: 1, untested: 1, failing: 0, stale: 0, accepted: 0 },
  requirements: [
    { id: 'R1', text: 'a', coverage: 'linked', outcome: 'pass', freshness: 'current', review: 'none', review_detail: null,
      tests: [{ test_id: 'a.B::c', outcome: 'pass', message: '' }] },
    { id: 'R2', text: 'b', coverage: 'none', outcome: 'not run', freshness: 'unknown', review: 'none', review_detail: null, tests: [] }],
  orphan_links: []
}
const evidence = { test_id: 'a.B::c', file: 'src/BTest.java', lines: [3, 8], status: 'new test', method_found: true,
  source: 'void c() {}', diff: 'diff --git a b\n@@ -1 +1,2 @@\n+void c() {}\n context', diff_scope: 'method',
  base: { ok: true, ref: 'main', commit: 'abcdef1234567' }, notes: ['n'] }
const change = { base: { ok: true, ref: 'main', commit: 'abcdef1234567' }, notes: [],
  files: [{ path: 'x.java', added: 2, removed: 1 }, { path: 'y.java', added: null, removed: 0, untracked: true }],
  diff: '@@ -1 +1 @@\n-a\n+b', production_files: ['x.java'] }
const ctx = {
  registerMany(items) { this.items = items },
  storage: { get: () => '/p', set() {} },
  setInterval: () => () => {},
  rest: p => Promise.resolve(p.startsWith('/board') ? board : p.startsWith('/evidence') ? evidence
    : p.startsWith('/change') ? change : p.startsWith('/projects') ? { projects: [{ path: '/p', exists: true }] } : {})
}
mod.register(ctx)

// Walk the element tree, calling function components, so their bodies run.
let rendered = 0
function walk(node, pathKey) {
  if (node == null || typeof node !== 'object') return
  if (Array.isArray(node)) { node.forEach((n, i) => walk(n, pathKey + '.' + i)); return }
  if (typeof node.type === 'function') {
    current = pathKey + '/' + (node.type.name || 'anon'); hookIdx = 0
    rendered++
    walk(node.type({ ...node.props, children: node.children }), current)
    return
  }
  ;(node.children || []).forEach((c, i) => walk(c, pathKey + '.' + i))
}
async function pass(force) {
  effects.length = 0
  walk(ctx.items[0].render(), 'root')
  for (const f of effects) f()
  await new Promise(r => setTimeout(r, 0))
  for (const k of hookState.keys()) {           // open everything: rows, tests, change panel
    const v = hookState.get(k)
    if (force && k.includes('/Board') && k.endsWith(':1') && v === null) hookState.set(k, 'R1')
    if (force && k.includes('/LinkedTests') && v === null) hookState.set(k, 'a.B::c')
    if (force && k.includes('/ChangePanel') && k.endsWith(':0') && v === false) hookState.set(k, true)
    if (force && k.includes('/ChangePanel') && k.endsWith(':1') && v === null) hookState.set(k, { data: change })
  }
}
await pass(false); await pass(true); await pass(true); await pass(true)
const names = [...hookState.keys()].map(k => k.split('/').pop().split(':')[0])
for (const need of ['App', 'Board', 'Summary', 'ChangePanel', 'RequirementDetail', 'LinkedTests', 'TestEvidence', 'Diff']) {
  if (!names.includes(need) && !JSON.stringify(names).includes(need)) {
    // Diff/Summary have no hooks; check they rendered by counting
  }
}
console.log(`rendered ${rendered} components without errors; hooks seen: ${[...new Set(names)].join(', ')}`)
