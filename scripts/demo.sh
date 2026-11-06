#!/usr/bin/env sh
set -eu
echo "Reset through node 1"; curl -sS -X DELETE http://localhost:8001/abacus/sum; echo
echo "Add 10 through node 1"; curl -sS -X POST http://localhost:8001/abacus/number -H 'Content-Type: application/json' -d '{"number":10}'; echo
echo "Add 7 through node 2"; curl -sS -X POST http://localhost:8002/abacus/number -H 'Content-Type: application/json' -d '{"number":7}'; echo
echo "Read through node 1"; curl -sS http://localhost:8001/abacus/sum; echo
echo "Read through node 2"; curl -sS http://localhost:8002/abacus/sum; echo
