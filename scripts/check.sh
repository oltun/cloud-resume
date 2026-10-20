set -euo pipefail

echo "1/3 Required files exist"
for f in index.html style.css favicon.png backend/lambda_function.py; do
  [ -f "$f" ] || { echo "MISSING: $f"; exit 1; }
done

echo "2/3 Lambda code parses"
python3 -c "import ast; ast.parse(open('backend/lambda_function.py').read())"

echo "3/3 No AWS access key IDs in the repo"
if grep -rIE --exclude-dir=.git 'AKIA[0-9A-Z]{16}' . ; then
  echo "Possible AWS access key found"
  exit 1
fi

echo "All checks passed"
