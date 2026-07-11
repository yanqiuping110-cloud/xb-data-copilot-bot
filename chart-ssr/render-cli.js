#!/usr/bin/env node
/** 单次 CLI 渲染：stdin JSON → stdout JSON（供 Python 无侧车时调用） */
const { renderChart } = require('./renderCore')

let raw = ''
process.stdin.setEncoding('utf8')
process.stdin.on('data', (c) => { raw += c })
process.stdin.on('end', async () => {
  try {
    const body = JSON.parse(raw || '{}')
    const out = await renderChart(body)
    if (!out) {
      process.stderr.write('cannot_render')
      process.exit(2)
    }
    process.stdout.write(JSON.stringify(out))
  } catch (e) {
    process.stderr.write(String(e.message || e))
    process.exit(1)
  }
})
