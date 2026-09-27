#!/bin/zsh
cd "${0:A:h}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
python3 scripts/stop_web.py
if [[ $? -ne 0 ]]; then
  read '?按回车关闭窗口…'
fi
