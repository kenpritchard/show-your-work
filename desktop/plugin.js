// Show Your Work: Desktop half (Phase 0 spike). Plain ESM, no build step.
import { ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import * as React from 'react'

const h = React.createElement

function makeApp(ctx) {
  return function App() {
    const [state, setState] = React.useState({ loading: true })
    React.useEffect(() => {
      let live = true
      ctx
        .rest('/ping')
        .then(data => live && setState({ data }))
        .catch(err => live && setState({ error: String(err && err.message ? err.message : err) }))
      return () => {
        live = false
      }
    }, [])
    return h(
      'div',
      { className: 'flex h-full flex-col gap-2 p-6 text-sm' },
      h('div', { className: 'text-lg font-medium' }, 'Show Your Work'),
      h('div', { className: 'text-(--ui-text-tertiary)' }, 'Phase 0 spike: Desktop page → plugin API round trip'),
      state.loading && h('div', null, 'Calling /ping…'),
      state.error && h('div', { style: { color: 'var(--ui-text-danger, #c33)' } }, 'API error: ' + state.error),
      state.data && h('pre', null, JSON.stringify(state.data, null, 2))
    )
  }
}

export default {
  id: 'show-your-work',
  name: 'Show Your Work',
  register(ctx) {
    const App = makeApp(ctx)
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/show-your-work' }, render: () => h(App) },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: '/show-your-work', label: 'Show Your Work', codicon: 'checklist' }
      }
    ])
  }
}
