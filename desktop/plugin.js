// Show Your Work: Desktop half. Plain ESM, no build step, SDK imports only.
//
// Board of acceptance criteria with four SEPARATE statuses per requirement
// (coverage / outcome / freshness / review), run detail, and the human-only
// Accept / Reject sign-off. All data comes from this plugin's own API via ctx.rest.
import { ROUTES_AREA, SIDEBAR_NAV_AREA, Button, Input } from '@hermes/plugin-sdk'
import * as React from 'react'

const h = React.createElement
const { useState, useEffect, useCallback } = React

const TONE = {
  good: 'var(--ui-text-success, #3a9a6a)',
  bad: 'var(--ui-text-danger, #d0473a)',
  warn: 'var(--ui-text-warning, #b98a2e)',
  muted: 'var(--ui-text-tertiary)'
}

const BADGES = {
  coverage: { none: ['untested', 'bad'], linked: ['linked', 'good'] },
  outcome: {
    pass: ['pass', 'good'], fail: ['fail', 'bad'], error: ['error', 'bad'],
    skipped: ['skipped', 'warn'], 'not run': ['not run', 'muted']
  },
  freshness: { current: ['current', 'good'], stale: ['stale', 'warn'], unknown: ['unknown', 'muted'] },
  review: {
    accepted: ['accepted', 'good'], rejected: ['rejected', 'bad'],
    stale: ['review stale', 'warn'], none: ['not reviewed', 'muted']
  },
  change: {
    'new test': ['new test', 'good'], 'new test (new file)': ['new test', 'good'],
    'changed test': ['changed test', 'warn'], unchanged: ['unchanged', 'muted'],
    'unchanged test (other parts of the file changed)': ['unchanged', 'muted'],
    'new file, not committed or staged': ['not in git yet', 'warn']
  }
}

function Pill({ kind, value }) {
  const [label, tone] = (BADGES[kind] || {})[value] || [value, 'muted']
  return h('span', {
    style: {
      display: 'inline-block', padding: '1px 8px', borderRadius: 999, fontSize: 11, whiteSpace: 'nowrap',
      color: TONE[tone], border: `1px solid color-mix(in srgb, ${TONE[tone]} 45%, transparent)`,
      background: `color-mix(in srgb, ${TONE[tone]} 10%, transparent)`
    }
  }, label)
}

const cell = { padding: '8px 10px', borderBottom: '1px solid var(--ui-stroke-secondary)', verticalAlign: 'top' }
const head = { ...cell, textAlign: 'left', fontWeight: 600, fontSize: 12, color: 'var(--ui-text-secondary)' }

function Summary({ s }) {
  const item = (n, label, tone) => h('div', { style: { display: 'flex', flexDirection: 'column', minWidth: 90 } },
    h('span', { style: { fontSize: 22, fontWeight: 650, color: n && tone ? TONE[tone] : undefined } }, n),
    h('span', { style: { fontSize: 11, color: TONE.muted } }, label))
  return h('div', { style: { display: 'flex', gap: 24, margin: '12px 0 16px' } },
    item(s.requirements, 'requirements'),
    item(s.passing, 'passing', 'good'),
    item(s.untested, 'untested', 'bad'),
    item(s.failing, 'failing', 'bad'),
    item(s.stale, 'stale', 'warn'),
    item(s.accepted, 'accepted by you', 'good'))
}

function ReviewControls({ ctx, project, req, onDone }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const send = decision => {
    setBusy(true); setErr(null)
    ctx.rest('/review', { method: 'POST', body: { project, requirement: req.id, decision, note } })
      .then(() => { setNote(''); onDone() })
      .catch(e => setErr(String((e && e.message) || e)))
      .finally(() => setBusy(false))
  }
  return h('div', { style: { display: 'flex', gap: 8, alignItems: 'center', marginTop: 10 } },
    h(Input, { value: note, placeholder: 'Note (optional)', onChange: e => setNote(e.target.value), style: { maxWidth: 320 } }),
    h(Button, { size: 'sm', disabled: busy, onClick: () => send('accepted') }, 'Accept'),
    h(Button, { size: 'sm', variant: 'outline', disabled: busy, onClick: () => send('rejected') }, 'Reject'),
    err && h('span', { style: { color: TONE.bad, fontSize: 12 } }, err))
}

const mono = { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 11.5, lineHeight: 1.45 }
const codeBox = {
  ...mono, margin: '6px 0 10px', padding: '8px 10px', borderRadius: 6, overflow: 'auto', maxHeight: 360,
  background: 'var(--ui-control-background, rgba(127,127,127,0.08))', border: '1px solid var(--ui-stroke-secondary)',
  whiteSpace: 'pre'
}

// Red/green rendering of a unified diff. Plain text only, never HTML.
function Diff({ text }) {
  const lines = (text || '').split('\n').filter(l => !/^(diff --git|index |--- |\+\+\+ )/.test(l))
  return h('div', { style: codeBox }, lines.map((l, i) => {
    const c = l[0]
    const style = c === '+' ? { color: TONE.good, background: 'color-mix(in srgb, ' + TONE.good + ' 10%, transparent)' }
      : c === '-' ? { color: TONE.bad, background: 'color-mix(in srgb, ' + TONE.bad + ' 10%, transparent)' }
        : c === '@' ? { color: TONE.muted } : {}
    return h('div', { key: i, style: { ...style, minHeight: '1.45em' } }, l || ' ')
  }))
}

const label = { fontSize: 11, fontWeight: 600, color: 'var(--ui-text-secondary)', marginTop: 8 }

// Source + diff for one linked test, fetched when you open it.
function TestEvidence({ ctx, project, testId }) {
  const [ev, setEv] = useState({ loading: true })
  useEffect(() => {
    ctx.rest(`/evidence?project=${encodeURIComponent(project)}&test_id=${encodeURIComponent(testId)}`)
      .then(data => setEv({ data }))
      .catch(e => setEv({ error: String((e && e.message) || e) }))
  }, [project, testId])
  if (ev.loading) return h('div', { style: { color: TONE.muted, padding: '4px 0' } }, 'Finding the test…')
  if (ev.error) return h('div', { style: { color: TONE.bad, padding: '4px 0' } }, ev.error)
  const d = ev.data
  const where = d.file ? `${d.file}${d.lines ? `:${d.lines[0]}–${d.lines[1]}` : ''}` : 'source not found'
  const base = d.base && d.base.ok ? `${d.base.ref} (${String(d.base.commit).slice(0, 10)})` : null
  return h('div', { style: { padding: '2px 0 6px' } },
    h('div', { style: { display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'baseline', color: TONE.muted } },
      h('span', { style: mono }, where),
      d.status && h(Pill, { kind: 'change', value: d.status }),
      base && h('span', null, `compared with ${base}`)),
    d.notes && d.notes.length > 0 && h('div', { style: { color: TONE.warn, marginTop: 4 } }, d.notes.join(' · ')),
    d.diff && h('div', null, h('div', { style: label }, d.diff_scope === 'method' ? 'What changed in this test' : 'What changed in this file'),
      h(Diff, { text: d.diff })),
    d.source && h('div', null, h('div', { style: label }, d.method_found ? 'The test' : 'The whole file (method not located)'),
      h('div', { style: codeBox }, d.source)))
}

function LinkedTests({ ctx, project, req }) {
  const [open, setOpen] = useState(null)
  return h('table', { style: { borderCollapse: 'collapse', width: '100%' } },
    h('tbody', null, req.tests.flatMap(t => {
      const isOpen = open === t.test_id
      const row = h('tr', { key: t.test_id, onClick: () => setOpen(isOpen ? null : t.test_id), style: { cursor: 'pointer' },
        title: 'Show this test and its diff' },
      h('td', { style: { padding: '3px 4px', width: 14, color: TONE.muted } }, isOpen ? '▾' : '▸'),
      h('td', { style: { padding: '3px 8px', ...mono, textDecoration: 'underline dotted' } }, t.test_id),
      h('td', { style: { padding: '3px 8px' } }, h(Pill, { kind: 'outcome', value: t.outcome })),
      h('td', { style: { padding: '3px 8px', color: TONE.muted } }, t.message || ''))
      return isOpen
        ? [row, h('tr', { key: t.test_id + ':ev' }, h('td', null), h('td', { colSpan: 3, style: { padding: '0 8px' } },
          h(TestEvidence, { ctx, project, testId: t.test_id })))]
        : [row]
    })))
}

// The change under review: file list + production diff, collapsed by default.
function ChangePanel({ ctx, project }) {
  const [open, setOpen] = useState(false)
  const [st, setSt] = useState(null)
  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next) { // refetch on every open: the diff changes as the work does
      setSt({ loading: true })
      ctx.rest(`/change?project=${encodeURIComponent(project)}`)
        .then(data => setSt({ data }))
        .catch(e => setSt({ error: String((e && e.message) || e) }))
    }
  }
  const d = st && st.data
  return h('div', { style: { margin: '4px 0 14px', fontSize: 12 } },
    h('div', { onClick: toggle, style: { cursor: 'pointer', fontWeight: 600, color: 'var(--ui-text-secondary)' } },
      (open ? '▾ ' : '▸ ') + 'The change under review (code the tests are checking)'),
    open && st && st.loading && h('div', { style: { color: TONE.muted } }, 'Loading diff…'),
    open && st && st.error && h('div', { style: { color: TONE.bad } }, st.error),
    open && d && h('div', { style: { paddingLeft: 14 } },
      d.base && d.base.ok
        ? h('div', { style: { color: TONE.muted, marginTop: 4 } }, `Compared with ${d.base.ref} (${String(d.base.commit).slice(0, 10)}), `,
          `including uncommitted changes. ${d.files.length} file(s) changed.`)
        : null,
      d.notes && d.notes.length > 0 && h('div', { style: { color: TONE.warn, marginTop: 4 } }, d.notes.join(' · ')),
      d.files.length > 0 && h('div', { style: { ...mono, marginTop: 6 } }, d.files.map(f => h('div', { key: f.path },
        f.untracked ? `  new (untracked)  ${f.path}` : `+${f.added} -${f.removed}  ${f.path}`))),
      d.diff ? h(Diff, { text: d.diff }) : (d.base && d.base.ok ? h('div', { style: { color: TONE.muted, marginTop: 6 } },
        'No non-test files changed.') : null)))
}

function RequirementDetail({ ctx, project, req, onDone }) {
  const d = req.review_detail
  return h('div', { style: { padding: '8px 10px 14px 34px', fontSize: 12 } },
    req.tests.length === 0
      ? h('div', { style: { color: TONE.bad } }, 'No test is linked to this requirement. Nothing has checked it.')
      : h('div', null,
        h('div', { style: { color: TONE.muted, marginBottom: 4 } },
          'Click a test to see its code and what changed. Ask: does it really check this requirement?'),
        h(LinkedTests, { ctx, project, req })),
    d && h('div', { style: { marginTop: 8, color: TONE.muted } },
      `Last review: ${d.decision} by ${d.by} at ${d.at}${d.note ? ` ("${d.note}")` : ''}`,
      req.review === 'stale' ? '. The requirement wording or the tracked code changed since, so review it again.' : ''),
    h(ReviewControls, { ctx, project, req, onDone }))
}

function Board({ ctx, project }) {
  const [state, setState] = useState({ loading: true })
  const [open, setOpen] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  const load = useCallback(() => {
    ctx.rest(`/board?project=${encodeURIComponent(project)}`)
      .then(data => setState({ data }))
      .catch(e => setState({ error: String((e && e.message) || e) }))
  }, [ctx, project])

  useEffect(() => {
    load()
    const stop = ctx.setInterval(load, 5000) // freshness is computed live, so poll
    return stop
  }, [load])

  if (state.loading) return h('div', { style: { color: TONE.muted } }, 'Loading board…')
  if (state.error) return h('div', { style: { color: TONE.bad } }, state.error)
  const b = state.data
  const run = b.latest_run

  const exportReport = () => {
    setBusy(true)
    ctx.rest('/export', { method: 'POST', body: { project } })
      .then(r => setMsg(`Wrote ${r.path}`))
      .catch(e => setMsg(String((e && e.message) || e)))
      .finally(() => setBusy(false))
  }

  return h('div', null,
    h('div', { style: { fontSize: 12, color: TONE.muted } },
      run ? `Latest run ${run.run_id} · ${run.imported_at} · ${run.report_path} · ${run.provenance} · ${run.tests} tests`
        : 'No test report imported yet.',
      run && run.older_report ? h('span', { style: { color: TONE.warn } },
        ' · report was older than the code when imported, so freshness is unknown') : null),
    h(Summary, { s: b.summary }),
    h(ChangePanel, { key: project + ':' + (run ? run.run_id : ''), ctx, project }),
    h('table', { style: { borderCollapse: 'collapse', width: '100%', fontSize: 13 } },
      h('thead', null, h('tr', null,
        ['', 'Requirement', 'Coverage', 'Outcome', 'Freshness', 'Review'].map((t, i) => h('th', { key: i, style: head }, t)))),
      h('tbody', null, b.requirements.flatMap(r => {
        const isOpen = open === r.id
        const row = h('tr', {
          key: r.id, onClick: () => setOpen(isOpen ? null : r.id),
          style: { cursor: 'pointer', background: isOpen ? 'var(--ui-control-hover-background)' : undefined }
        },
        h('td', { style: { ...cell, width: 24, color: TONE.muted } }, isOpen ? '▾' : '▸'),
        h('td', { style: cell }, h('strong', null, r.id), ' ', r.text),
        h('td', { style: cell }, h(Pill, { kind: 'coverage', value: r.coverage })),
        h('td', { style: cell }, h(Pill, { kind: 'outcome', value: r.outcome })),
        h('td', { style: cell }, h(Pill, { kind: 'freshness', value: r.freshness })),
        h('td', { style: cell }, h(Pill, { kind: 'review', value: r.review })))
        return isOpen
          ? [row, h('tr', { key: r.id + ':d' }, h('td', { colSpan: 6, style: { borderBottom: '1px solid var(--ui-stroke-secondary)' } },
            h(RequirementDetail, { ctx, project, req: r, onDone: load })))]
          : [row]
      }))),
    b.orphan_links.length > 0 && h('div', { style: { marginTop: 10, fontSize: 12, color: TONE.warn } },
      `${b.orphan_links.length} link(s) point at requirements no longer in ${b.criteria_file}.`),
    h('div', { style: { display: 'flex', gap: 8, alignItems: 'center', marginTop: 16 } },
      h(Button, { size: 'sm', variant: 'outline', disabled: busy, onClick: exportReport }, 'Export review report'),
      msg && h('span', { style: { fontSize: 12, color: TONE.muted } }, msg)),
    h('div', { style: { marginTop: 18, fontSize: 11, color: TONE.muted, maxWidth: 720 } },
      'A linked test is a coverage claim, not proof it checks the requirement well. Results are imported from reports; ',
      'this plugin runs no tests. Only you can accept or reject; the agent has no tool for it.'))
}

function makeApp(ctx) {
  return function App() {
    const [projects, setProjects] = useState(null)
    // ctx.storage is synchronous (get(key, fallback) / set(key, value)).
    const [project, setProject] = useState(() => ctx.storage.get('lastProject', null))
    const [typed, setTyped] = useState('')
    const [err, setErr] = useState(null)

    useEffect(() => {
      ctx.rest('/projects').then(r => setProjects(r.projects)).catch(e => setErr(String((e && e.message) || e)))
    }, [])

    const choose = p => { setProject(p); ctx.storage.set('lastProject', p) }

    return h('div', { style: { height: '100%', overflow: 'auto', padding: '28px 32px', boxSizing: 'border-box' } },
      h('div', { style: { display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' } },
        h('h1', { style: { fontSize: 22, fontWeight: 650, margin: 0 } }, 'Show Your Work'),
        h('span', { style: { color: TONE.muted, fontSize: 13 } }, 'Which requirements did your agent actually test, and have you signed off?')),
      h('div', { style: { display: 'flex', gap: 8, alignItems: 'center', margin: '16px 0 8px', flexWrap: 'wrap' } },
        (projects || []).map(p => h(Button, {
          key: p.path, size: 'sm', variant: p.path === project ? 'default' : 'outline',
          disabled: !p.exists, onClick: () => choose(p.path), title: p.path
        }, p.path.split('/').filter(Boolean).pop())),
        h(Input, { value: typed, placeholder: '/path/to/project (folder with syw.toml)',
          onChange: e => setTyped(e.target.value), style: { maxWidth: 360 },
          onKeyDown: e => { if (e.key === 'Enter' && typed.trim()) choose(typed.trim()) } }),
        h(Button, { size: 'sm', variant: 'outline', disabled: !typed.trim(), onClick: () => choose(typed.trim()) }, 'Open')),
      err && h('div', { style: { color: TONE.bad } }, err),
      project
        ? h('div', null, h('div', { style: { fontFamily: 'ui-monospace, monospace', fontSize: 12, color: TONE.muted } }, project),
          h(Board, { key: project, ctx, project }))
        : h('div', { style: { color: TONE.muted, marginTop: 24 } },
          'Pick a project above, or ask your agent to run syw_board on a folder that has a syw.toml.'))
  }
}

export default {
  id: 'show-your-work',
  name: 'Show Your Work',
  register(ctx) {
    const App = makeApp(ctx)
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/show-your-work' }, render: () => h(App) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/show-your-work', label: 'Show Your Work', codicon: 'checklist' } }
    ])
  }
}
