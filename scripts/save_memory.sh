#!/bin/bash
# data/memory/ 以下に日次のメモファイルを保存する
#
# 使い方: save_memory.sh YYYY-MM-DD "タイトル" "本文" "追記セクション（任意）"

DATE=$1
TITLE=$2
BODY=$3
EXTRA=$4
MEMORY_DIR="${MEMORY_DIR:-$HOME/secretary/data/memory}"
OUTPUT="$MEMORY_DIR/${DATE}.md"

mkdir -p "$MEMORY_DIR"

cat > "$OUTPUT" << MDEOF
# ${DATE} ${TITLE}

## メモ
${BODY}
MDEOF

if [ -n "$EXTRA" ]; then
cat >> "$OUTPUT" << MDEOF

## 追記
${EXTRA}
MDEOF
fi

echo "保存: $OUTPUT"
