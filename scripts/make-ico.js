// scripts/make-ico.js
// 将 resources/icon.png 转换为 Windows 所需的 icon.ico
// 用法：node scripts/make-ico.js

const pngToIco = require('png-to-ico')
const fs = require('fs')
const path = require('path')

const src  = path.resolve(__dirname, '../resources/icon.png')
const dest = path.resolve(__dirname, '../resources/icon.ico')

if (!fs.existsSync(src)) {
  console.error('❌ 未找到 resources/icon.png，请先放置 1024×1024 的图标文件')
  process.exit(1)
}

pngToIco(src)
  .then(buf => {
    fs.writeFileSync(dest, buf)
    console.log('✅ icon.ico 已生成：resources/icon.ico')
  })
  .catch(err => {
    console.error('❌ 转换失败：', err.message)
    process.exit(1)
  })
