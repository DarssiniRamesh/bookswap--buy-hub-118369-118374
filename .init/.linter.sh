#!/bin/bash
cd /home/kavia/workspace/code-generation/bookswap--buy-hub-118369-118374/book_swap_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

