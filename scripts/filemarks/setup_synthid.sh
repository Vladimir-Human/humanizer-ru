#!/bin/sh
# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
# setup_synthid.sh — выкачать ВНЕШНИЙ скоринг reverse-SynthID (опционально).
# Не входит в проект: сторонний код под некоммерческой Research License,
# не является официальным детектором Google. Только оценка, не снятие.
set -e
DIR="${1:-$HOME/opt/reverse-SynthID}"
PINNED_COMMIT="f10efaa7efc75591b4744cc1d885874a79f5f7ee"
if [ -d "$DIR" ]; then
  echo "уже есть: $DIR (повторный клон пропущен)"
else
  # Fetch the exact reviewed revision; cloning the moving default branch would
  # make this optional helper execute unreviewed third-party code.
  git clone https://github.com/aloshdenny/reverse-SynthID "$DIR"
  git -C "$DIR" checkout --detach "$PINNED_COMMIT"
fi
echo "дальше: export REVERSE_SYNTHID_DIR=$DIR"
echo "зависимости внешнего скоринга ставьте в отдельное окружение (numpy/opencv/pywavelets/scikit-learn)"
