import os
import ast
import importlib.metadata
import subprocess

def find_python_files(root_dir):
    """
    Finds all Python files in the given directory.
    """
    python_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.py'):
                python_files.append(os.path.join(dirpath, filename))
    return python_files

def extract_imports(file_path):
    """
    Extracts top-level imported module names from a Python file.
    E.g., `import requests` -> `requests`
    `from django.shortcuts import render` -> `django`
    `import google.generativeai as genai` -> `google`
    """
    imports = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module: # node.module can be None for relative imports like 'from . import views'
                        imports.add(node.module.split('.')[0])
    except SyntaxError as e:
        print(f"Warning: Could not parse {file_path} due to SyntaxError: {e}")
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    return imports

def get_package_info_from_import(import_name):
    """
    Attempts to find the installed version and the *actual PyPI distribution name*
    for a given top-level import name.
    This function tries to be 'generic' by leveraging `importlib.metadata`
    and `pip show`. It does NOT use any manual import->PyPI name mapping.

    Returns:
        tuple: (version_string, pypi_package_name_string) or (None, None)
    """
    # Try to find via importlib.metadata directly
    try:
        dist = importlib.metadata.distribution(import_name)
        return dist.version, dist.name # dist.name is the actual PyPI package name
    except importlib.metadata.PackageNotFoundError:
        pass # Continue to pip fallback

    # Fallback to pip show if importlib.metadata doesn't find it
    # This might find the package if pip's internal mapping works,
    # or if the import_name directly matches the PyPI name.
    try:
        result = subprocess.run(['pip', 'show', import_name], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            version_line = next((line for line in result.stdout.splitlines() if line.startswith('Version:')), None)
            name_line = next((line for line in result.stdout.splitlines() if line.startswith('Name:')), None)
            if version_line and name_line:
                return version_line.split(': ')[1].strip(), name_line.split(': ')[1].strip()
            elif version_line: # If only version found, assume import_name is PyPI name
                return version_line.split(': ')[1].strip(), import_name
        return None, None
    except FileNotFoundError:
        print("Error: pip command not found. Please ensure pip is installed and in your PATH.")
        return None, None
    except Exception as e:
        print(f"Error getting version/name for {import_name}: {e}")
        return None, None


def generate_requirements(root_dir, output_file='requirements.txt'):
    """
    Generates a requirements.txt file based on imports found in Python files.
    """
    python_files = find_python_files(root_dir)
    all_top_level_imports = set()

    for file_path in python_files:
        all_top_level_imports.update(extract_imports(file_path))

    # Manually curated list of top-level standard library modules.
    # This list is *necessary* because standard library modules are not PyPI packages
    # and should NEVER be in requirements.txt.
    standard_library_modules = {
        'os', 'sys', 'math', 'datetime', 'time', 'json', 'random', 'urllib',
        'unittest', 'logging', 're', 'collections', 'io', 'argparse', 'socket',
        'threading', 'multiprocessing', 'asyncio', 'enum', 'typing', 'copy',
        'functools', 'itertools', 'contextlib', 'abc', 'pathlib', 'subprocess',
        'ast', 'importlib', '__future__', 'site', 'warnings', 'traceback', 'locale',
        'binascii', 'zlib', 'bz2', 'lzma', 'array', 'struct', 'decimal', 'fractions',
        'statistics', 'uuid', 'secrets', 'inspect', 'pdb', 'profile', 'cProfile',
        'trace', 'venv', 'ensurepip', 'distutils', 'setuptools', 'pip', # Add pip
        'email', 'http', 'ftplib', 'smtplib', 'imaplib', 'poplib', 'nntplib',
        'xml', 'html', 'csv', 'zipfile', 'tarfile', 'gzip', 'shutil', 'glob',
        'tempfile', 'mimetypes', 'webbrowser', 'pydoc', 'configparser', 'getopt',
        'cmd', 'shlex', 'sndhdr', 'wave', 'base64', 'hashlib', 'hmac', 'ssl',
        'crypt', 'tkinter', 'doctest', 'test', 'lib2to3',
        'django' # Catch all django.* imports at top level. Django is still considered a single package.
    }

    # Modules that are part of your local project's apps.
    # These should not be installed via pip.
    local_app_modules = {
        'weather', # Your 'weather' Django app
        # 'weather_ai_app' # The top-level project folder if it imports itself (less common)
    }

    final_requirements_packages = {} # {PyPI_name: version}

    for imported_top_level_module in all_top_level_imports:
        # 1. Skip if it's a standard library module
        if imported_top_level_module in standard_library_modules:
            continue

        # 2. Skip if it's a local application module
        if imported_top_level_module in local_app_modules:
            continue

        # Attempt to find the package version and its actual PyPI name
        # No manual mapping is done here.
        version, pypi_name = get_package_info_from_import(imported_top_level_module)

        if pypi_name:
            final_requirements_packages[pypi_name] = version
        else:
            # If we couldn't determine a PyPI name (or confirm it exists)
            # based on the import name, we skip it based on "add only those who are packages exist"
            print(f"Skipping import '{imported_top_level_module}' as its corresponding PyPI package could not be confidently identified or confirmed to be installable.")

    with open(output_file, 'w') as f:
        for package_name in sorted(final_requirements_packages.keys()):
            version = final_requirements_packages[package_name]
            if version:
                f.write(f"{package_name}=={version}\n")
            else:
                # If a package name was identified but version not found, list without version
                f.write(f"{package_name}\n")
                print(f"Warning: Could not determine version for '{package_name}'. Added without version.")

    print(f"\nGenerated requirements.txt in {output_file}")
    print("-" * 60)
    print("IMPORTANT NOTE ON ACCURACY:")
    print("This script operates on a 'generic' principle, meaning it does NOT use any hardcoded")
    print("manual mapping between Python import names (e.g., 'google') and their actual PyPI")
    print("package names (e.g., 'google-generativeai').")
    print("This means that:")
    print("  - If an import's top-level name does not directly match its PyPI package name,")
    print("    and `importlib.metadata` or `pip show` cannot resolve this discrepancy automatically,")
    print("    the package might be SKIPPED from requirements.txt.")
    print("  - For your specific project, this implies 'google.generativeai' might NOT be included")
    print("    because its top-level import 'google' does not directly map to a 'google' package on PyPI.")
    print("  - Similarly, `django` might be less robustly handled, though pip often resolves it.")
    print("ALWAYS review the generated `requirements.txt` file and manually add any missing packages")
    print("or correct package names/versions if necessary. This generic approach inherently has limitations.")
    print("-" * 60)


if __name__ == "__main__":
    # Set this to the root directory of your project
    project_directory = '.' # Current directory where manage.py is located
    generate_requirements(project_directory)