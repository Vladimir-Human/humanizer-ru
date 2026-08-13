# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
#!/bin/sh
# setup_synthid.sh — выкачать ВНЕШНИЙ скоринг reverse-SynthID (опционально).
# Не входит в проект: сторонний код под некоммерческой Research License,
# не является официальным детектором Google. Только оценка, не снятие.
set -e
DIR="${1:-$HOME/opt/reverse-SynthID}"
if [ -d "$DIR" ]; then
  echo "уже есть: $DIR (повторный клон пропущен)"
else
  git clone --depth 1 https://github.com/aloshdenny/reverse-SynthID "$DIR"
fi
echo "дальше: export REVERSE_SYNTHID_DIR=$DIR"
echo "зависимости внешнего скоринга ставьте в отдельное окружение (numpy/opencv/pywavelets/scikit-learn)"
