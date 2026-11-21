import ast, sys

tree = ast.parse(open(sys.argv[1]).read())
for node in ast.walk(tree):
    if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        b = node.body
        if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
            node.body = b[1:] or [ast.Pass()]
open(sys.argv[2], "w").write(ast.unparse(tree) + "\n")
