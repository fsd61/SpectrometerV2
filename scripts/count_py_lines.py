import pathlib

def count_lines():
    total_lines = 0
    # Search recursively from the current working directory
    for path in pathlib.Path('.').rglob('*.py'):
        # Skip common virtual environment and cache folders
        if any(part in path.parts for part in ['.venv', 'venv', 'env', '__pycache__', '.git']):
            continue
            
        try:
            lines = len(path.read_text(encoding='utf-8').splitlines())
            print(f"{lines:<8} {path}")
            total_lines += lines
        except Exception:
            print(f"Skipped  {path} (Could not read)")

    print("-" * 40)
    print(f"{total_lines:<8} TOTAL PYTHON LINES")

if __name__ == "__main__":
    count_lines()
