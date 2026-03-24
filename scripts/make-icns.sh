#!/bin/bash
# scripts/make-icns.sh
# 将 resources/icon.png 转换为 macOS 所需的 icon.icns
# 要求：resources/icon.png 尺寸至少 512×512（推荐 1024×1024）
set -e

SRC="resources/icon.png"
ICONSET="resources/icon.iconset"
DEST="resources/icon.icns"

if [ ! -f "$SRC" ]; then
  echo "⚠️  未找到 $SRC，跳过 icns 转换"
  echo "   请在 resources/ 目录下放一张 1024×1024 的 icon.png"
  exit 0
fi

echo "🖼️  Converting $SRC → $DEST ..."

mkdir -p "$ICONSET"

sips -z 16   16   "$SRC" --out "$ICONSET/icon_16x16.png"    > /dev/null
sips -z 32   32   "$SRC" --out "$ICONSET/icon_16x16@2x.png" > /dev/null
sips -z 32   32   "$SRC" --out "$ICONSET/icon_32x32.png"    > /dev/null
sips -z 64   64   "$SRC" --out "$ICONSET/icon_32x32@2x.png" > /dev/null
sips -z 128  128  "$SRC" --out "$ICONSET/icon_128x128.png"  > /dev/null
sips -z 256  256  "$SRC" --out "$ICONSET/icon_128x128@2x.png" > /dev/null
sips -z 256  256  "$SRC" --out "$ICONSET/icon_256x256.png"  > /dev/null
sips -z 512  512  "$SRC" --out "$ICONSET/icon_256x256@2x.png" > /dev/null
sips -z 512  512  "$SRC" --out "$ICONSET/icon_512x512.png"  > /dev/null
cp "$SRC"                     "$ICONSET/icon_512x512@2x.png"

iconutil -c icns "$ICONSET" -o "$DEST"
rm -rf "$ICONSET"

echo "✅ icon.icns created at $DEST"