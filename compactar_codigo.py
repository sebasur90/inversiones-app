#!/usr/bin/env python3
import os
from pathlib import Path

# Carpetas a excluir
EXCLUDE_DIRS = {
    '.claude',
    '.git',
    '.github',
    '.pytest_cache',
    '.vscode',
    '.superpowers',
    '__pycache__',
    'node_modules',
    '.env',
    'dist',
    'build',
    '.venv',
    'venv',
    'env',
    '.turbo',
    'credentials',
}

# Extensiones de archivo a incluir
INCLUDE_EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.jsx'}

def should_exclude(path):
    """Verifica si una ruta debe ser excluida"""
    path_parts = Path(path).parts
    return any(part in EXCLUDE_DIRS for part in path_parts)

def get_directory_tree(root_path, prefix="", exclude_dirs=None):
    """Genera un árbol de directorios como string"""
    if exclude_dirs is None:
        exclude_dirs = EXCLUDE_DIRS

    tree = ""
    try:
        items = sorted(os.listdir(root_path))
    except PermissionError:
        return tree

    dirs = []
    files = []

    for item in items:
        item_path = os.path.join(root_path, item)
        if should_exclude(item_path):
            continue
        if os.path.isdir(item_path):
            dirs.append(item)
        else:
            files.append(item)

    # Mostrar directorios primero
    for i, dir_name in enumerate(dirs):
        is_last = (i == len(dirs) - 1 and len(files) == 0)
        tree += f"{prefix}{'└── ' if is_last else '├── '}{dir_name}/\n"

        new_prefix = prefix + ("    " if is_last else "│   ")
        dir_path = os.path.join(root_path, dir_name)
        tree += get_directory_tree(dir_path, new_prefix, exclude_dirs)

    # Luego archivos
    for i, file_name in enumerate(files):
        is_last = (i == len(files) - 1)
        tree += f"{prefix}{'└── ' if is_last else '├── '}{file_name}\n"

    return tree

def compact_code(root_path, output_path):
    """Compacta todo el código (Python, TypeScript, JavaScript) en un archivo .txt"""

    source_files = []

    # Buscar todos los archivos de código
    for root, dirs, files in os.walk(root_path):
        # Filtrar directorios excluidos
        dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d))]

        for file in files:
            if any(file.endswith(ext) for ext in INCLUDE_EXTENSIONS):
                file_path = os.path.join(root, file)
                if not should_exclude(file_path):
                    source_files.append(file_path)

    source_files.sort()

    # Crear el archivo de salida
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as out_file:
        # Encabezado
        out_file.write("=" * 80 + "\n")
        out_file.write("CÓDIGO COMPACTADO DEL PROYECTO\n")
        out_file.write("=" * 80 + "\n\n")

        # Árbol de directorios
        out_file.write("ESTRUCTURA DE DIRECTORIOS:\n")
        out_file.write("-" * 80 + "\n")
        tree = get_directory_tree(root_path)
        out_file.write(tree)
        out_file.write("\n" + "=" * 80 + "\n\n")

        # Contenido de archivos
        out_file.write(f"ARCHIVOS INCLUIDOS: {len(source_files)}\n")
        out_file.write("=" * 80 + "\n\n")

        for i, file_path in enumerate(source_files, 1):
            rel_path = os.path.relpath(file_path, root_path)
            out_file.write(f"\n{'#' * 80}\n")
            out_file.write(f"# ARCHIVO {i}/{len(source_files)}: {rel_path}\n")
            out_file.write(f"{'#' * 80}\n\n")

            try:
                with open(file_path, 'r', encoding='utf-8') as py_file:
                    content = py_file.read()
                    out_file.write(content)
                    if not content.endswith('\n'):
                        out_file.write('\n')
            except Exception as e:
                out_file.write(f"ERROR al leer archivo: {e}\n")

            out_file.write("\n")

    print(f"✓ Código compactado en: {output_path}")
    print(f"✓ Total de archivos incluidos: {len(source_files)}")

if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    output = os.path.join(root, "codigo_compactado.txt")
    compact_code(root, output)
