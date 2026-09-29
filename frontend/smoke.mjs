// Throwaway smoke test: render <App /> on the server to catch runtime
// errors a plain `vite build` cannot see.  Run:  node smoke.mjs
import { createServer } from 'vite'
import { renderToString } from 'react-dom/server'
import { createElement } from 'react'

const server = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'error',
})

const checks = [
  ['mic button', 'Talk'],
  ['status pill', 'Ready'],
  ['typed input', 'Or type a question'],
  ['empty state', 'Press the microphone'],
  ['brand', 'Apex Global Technologies'],
  ['transcript card', 'Conversation'],
  ['controls', 'Clear'],
  ['composer send', 'Send'],
  ['footer', 'RAG over Qdrant'],
  ['orb a11y label', 'Assistant status: idle'],
]

try {
  const { default: App } = await server.ssrLoadModule('/src/App.jsx')
  const html = renderToString(createElement(App))

  console.log('SSR render OK, length:', html.length)

  let failed = 0
  for (const [label, needle] of checks) {
    const ok = html.includes(needle)
    console.log(`${ok ? 'ok  ' : 'FAIL'}  ${label.padEnd(18)} "${needle}"`)
    if (!ok) failed += 1
  }

  if (failed > 0) {
    console.error(`\n${failed}/${checks.length} checks failed`)
    process.exitCode = 1
  } else {
    console.log(`\nall ${checks.length} checks passed`)
  }
} finally {
  await server.close()
}
