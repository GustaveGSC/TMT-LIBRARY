#!/usr/bin/env node
/**
 * scripts/upload-release.js
 * 将 release/latest.yml 上传到 OSS tmt-library/releases/
 * 用法：node scripts/upload-release.js
 */

const fs   = require('fs')
const path = require('path')
const OSS  = require('ali-oss')

// ── 读取 backend/.env ──────────────────────────────
const envPath = path.join(__dirname, '../backend/.env')
const env = {}
fs.readFileSync(envPath, 'utf8').split(/\r?\n/).forEach(line => {
  const m = line.match(/^([^#=]+)=(.*)$/)
  if (m) env[m[1].trim()] = m[2].trim()
})

const client = new OSS({
  region:          'oss-cn-hangzhou',
  accessKeyId:     env.OSS_ACCESS_KEY_ID,
  accessKeySecret: env.OSS_ACCESS_KEY_SECRET,
  bucket:          env.OSS_BUCKET_NAME,
})

const LOCAL_FILE = path.join(__dirname, '../release/latest.yml')
const OSS_KEY    = 'tmt-library/releases/latest.yml'

async function upload() {
  if (!fs.existsSync(LOCAL_FILE)) {
    console.error('❌ release/latest.yml 不存在，请先打包')
    process.exit(1)
  }

  console.log(`⬆  上传 latest.yml → ${OSS_KEY}`)
  await client.put(OSS_KEY, LOCAL_FILE, {
    headers: { 'Content-Type': 'application/x-yaml', 'Cache-Control': 'no-cache' }
  })
  console.log('✅ latest.yml 上传成功')
}

upload().catch(e => {
  console.error('❌ 上传失败：', e.message)
  process.exit(1)
})
