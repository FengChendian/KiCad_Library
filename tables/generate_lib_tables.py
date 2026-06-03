#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KiCad Library Table Generator

Generates sym_lib_table and fp_lib_table files from custom library directories.
Compatible with Linux, macOS, and Windows.

Usage:
    python generate_lib_tables.py

Environment Variables:
    KICAD_CUSTOM_LIB_DIR - Base directory for custom libraries (default: script's parent directory)
"""

import os


import re
import json
from pathlib import Path
from enum import Enum


class InputMode(Enum):
    ASK_EACH = "ask"
    USE_JSON = "json"
    SKIP = "skip"


CONFIG_FILE_NAME = "libs_config.json"


def get_script_dir() -> Path:
    """Get the directory where this script is located."""
    return Path(__file__).parent.resolve()


def get_default_lib_dir() -> Path:
    """Get the default library base directory from environment or script location."""
    env_dir = os.environ.get('KICAD_CUSTOM_LIB_DIR')
    if env_dir:
        return Path(env_dir).resolve()
    # Default to script's parent directory
    return get_script_dir().parent.resolve()


def find_symbol_files(symbols_dir: Path) -> list[Path]:
    """Find all .kicad_sym files in the symbols directory."""
    if not symbols_dir.exists():
        print(f"Warning: Symbols directory not found: {symbols_dir}")
        return []
    return sorted(symbols_dir.glob('*.kicad_sym'))


def find_footprint_files(footprints_dir: Path) -> list[Path]:
    """Find all .kicad_mod files in footprints directory (including .pretty subdirectories)."""
    if not footprints_dir.exists():
        print(f"Warning: Footprints directory not found: {footprints_dir}")
        return []

    footprint_files = []
    # Search in .pretty subdirectories
    for pretty_dir in footprints_dir.glob('*.pretty'):
        footprint_files.extend(sorted(pretty_dir.glob('*.kicad_mod')))

    return sorted(footprint_files)


def get_pretty_dir_name(footprint_path: Path) -> str:
    """Get the .pretty directory name for a footprint file."""
    parent = footprint_path.parent
    if parent.suffix == '.pretty':
        return parent.stem
    return parent.name


def extract_symbol_name(sym_file: Path) -> str:
    """Extract symbol name from .kicad_sym file."""
    try:
        with open(sym_file, 'r', encoding='utf-8') as f:
            content = f.read(4096)  # Read first 4KB

        # Look for (symbol "name" pattern
        match = re.search(r'\(symbol\s+"([^"]+)"', content)
        if match:
            return match.group(1)

        # Fallback: use filename without extension
        return sym_file.stem
    except Exception as e:
        print(f"Warning: Could not parse symbol name from {sym_file}: {e}")
        return sym_file.stem


def extract_footprint_name(fp_file: Path) -> str:
    """Extract footprint name from .kicad_mod file."""
    try:
        with open(fp_file, 'r', encoding='utf-8') as f:
            content = f.read(4096)  # Read first 4KB

        # Look for (footprint "name" pattern
        match = re.search(r'\(footprint\s+"([^"]+)"', content)
        if match:
            return match.group(1)

        # Fallback: use filename without extension
        return fp_file.stem
    except Exception as e:
        print(f"Warning: Could not parse footprint name from {fp_file}: {e}")
        return fp_file.stem


def get_symbol_description(sym_file: Path) -> str:
    """Extract description from symbol file (单个元件的描述)."""
    try:
        with open(sym_file, 'r', encoding='utf-8') as f:
            content = f.read(8192)

        # Look for Description property
        match = re.search(r'\(property\s+"Description"\s+"([^"]*)"', content)
        if match:
            return match.group(1)

        return ""
    except Exception:
        return ""


def get_footprint_description(fp_file: Path) -> str:
    """Extract description from footprint file (单个封装的描述)."""
    try:
        with open(fp_file, 'r', encoding='utf-8') as f:
            content = f.read(8192)

        # Look for (descr pattern
        match = re.search(r'\(descr\s+"([^"]*)"', content)
        if match:
            return match.group(1)

        return ""
    except Exception:
        return ""


def escape_uri(path: Path) -> str:
    """Convert path to URI format, escaping backslashes for Windows."""
    return str(path).replace('\\', '/')


# ============================================================================
# JSON Configuration Functions
# ============================================================================

def get_config_path() -> Path:
    """Get the path to the config file."""
    # Put config file in the same directory as this script (tables/)
    return get_script_dir() / CONFIG_FILE_NAME


def load_lib_config(config_path: Path) -> dict[str, str]:
    """Load library descriptions from JSON config file."""
    if not config_path.exists():
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('libraries', {})
    except Exception as e:
        print(f"Warning: Could not load config file: {e}")
        return {}


def save_lib_config(config_path: Path, descriptions: dict[str, str]) -> bool:
    """Save library descriptions to JSON config file."""
    try:
        # Load existing config if it exists
        existing = {}
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                pass

        # Update libraries section
        if 'libraries' not in existing:
            existing['libraries'] = {}
        existing['libraries'].update(descriptions)
        existing['libraries'] = dict(sorted(existing['libraries'].items()))

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=4, ensure_ascii=False)

        return True
    except Exception as e:
        print(f"Error: Could not save config file: {e}")
        return False


def get_lib_key(lib_name: str, lib_type: str) -> str:
    """Generate a unique key for a library."""
    return f"{lib_type}:{lib_name}"


# ============================================================================
# Interactive Input Functions
# ============================================================================

def prompt_for_description(lib_name: str, lib_type: str, preview: str = "") -> str:
    """Interactively prompt the user to enter a description for a library."""
    print("\n" + "=" * 60)
    print(f"库名称：{lib_name}")
    print(f"类型：{lib_type}")
    if preview:
        print(f"预览：{preview[:80]}..." if len(preview) > 80 else f"预览：{preview}")
    print("-" * 60)

    while True:
        desc = input("请输入该库的描述 (或按 Enter 留空): ").strip()
        return desc


def show_mode_prompt() -> str:
    """Show the mode selection prompt and return user's choice."""
    print("\n" + "=" * 60)
    print("选择描述输入模式:")
    print("  [A] 逐个输入 - 为每个库立即输入描述")
    print("  [B] JSON 模式 - 编辑配置文件后重新读取")
    print("  [S] 跳过 - 不使用描述继续")
    print("-" * 60)

    while True:
        choice = input("请选择 (A/B/S): ").strip().lower()
        if choice in ['a', 'b', 's', '']:
            return choice


def handle_json_mode(lib_keys: list[str], config_path: Path,
                     existing_config: dict[str, str]) -> tuple[dict[str, str], bool]:
    """
    Handle JSON configuration mode.
    Returns: (updated_config, success)
    """
    # Create or update config file with missing entries
    new_config = existing_config.copy()

    for key in lib_keys:
        if key not in new_config:
            new_config[key] = ""

    # Save the config file
    save_lib_config(config_path, new_config)

    print(f"\n已创建/更新配置文件：{config_path}")
    print("请在文件中编辑各库的描述字段 (libraries 部分)")
    print("\n编辑完成后，按 Enter 继续读取配置文件...")
    print("或者输入 'r' 重新扫描并跳过编辑步骤")

    while True:
        user_input = input("> ").strip().lower()
        if user_input == 'r':
            # Re-scan and return existing config without editing
            return existing_config, True
        else:
            # Try to load the updated config
            updated = load_lib_config(config_path)
            print(f"\n已读取配置文件，共 {len(updated)} 个库配置")
            return updated, True


# ============================================================================
# Library Discovery
# ============================================================================

def discover_symbol_libraries(symbols_dir: Path) -> list[tuple[str, Path, str]]:
    """
    Discover all symbol libraries.
    Returns: list of (lib_name, file_path, preview_description)
    """
    libraries = []
    symbol_files = find_symbol_files(symbols_dir)

    for sym_file in symbol_files:
        lib_name = sym_file.stem
        # Try to get a preview from first symbol in file
        preview = ""
        try:
            with open(sym_file, 'r', encoding='utf-8') as f:
                content = f.read(2048)
                # Try to find first symbol's description as preview
                match = re.search(r'\(property\s+"Description"\s+"([^"]*)"', content)
                if match:
                    preview = match.group(1)
        except:
            pass
        libraries.append((lib_name, sym_file, preview))

    return libraries


def discover_footprint_libraries(footprints_dir: Path) -> list[tuple[str, Path, str]]:
    """
    Discover all footprint libraries (.pretty directories).
    Returns: list of (lib_name, dir_path, preview_description)
    """
    libraries = []

    if not footprints_dir.exists():
        return libraries

    # Find all .pretty directories
    pretty_dirs = sorted(footprints_dir.glob('*.pretty'))

    for pretty_dir in pretty_dirs:
        lib_name = pretty_dir.stem
        # Try to get preview from first footprint
        preview = ""
        kicad_mod_files = list(pretty_dir.glob('*.kicad_mod'))
        if kicad_mod_files:
            try:
                with open(kicad_mod_files[0], 'r', encoding='utf-8') as f:
                    content = f.read(2048)
                    match = re.search(r'\(descr\s+"([^"]*)"', content)
                    if match:
                        preview = match.group(1)
            except:
                pass
        libraries.append((lib_name, pretty_dir, preview))

    return libraries


# ============================================================================
# Table Generation
# ============================================================================

def generate_sym_lib_table(
    symbols_dir: Path,
    output_dir: Path,
    config: dict[str, str] | None = None,
    mode: InputMode = InputMode.USE_JSON,
    config_path: Path | None = None,
) -> Path:
    """Generate sym_lib_table file."""
    output_file = output_dir / 'sym_lib_table'

    libraries = discover_symbol_libraries(symbols_dir)

    if not libraries:
        # Create empty table if no libraries found
        lines = ['(sym_lib_table', '\t(version 7)', ')']
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"Generated (empty): {output_file}")
        return output_file

    # Collect descriptions based on mode
    lib_descriptions: dict[str, str] = {}
    if config:
        lib_descriptions = config.copy()

    if mode == InputMode.ASK_EACH:
        updated = False
        for lib_name, lib_path, preview in libraries:
            key = get_lib_key(lib_name, 'sym')
            if key not in lib_descriptions or not lib_descriptions[key]:
                desc = prompt_for_description(lib_name, 'Symbol', preview)
                lib_descriptions[key] = desc
                updated = True
        if updated and config_path:
            save_lib_config(config_path, lib_descriptions)
    # USE_JSON: use config as-is; SKIP: all descriptions remain empty

    lines = [
        '(sym_lib_table',
        '\t(version 7)',
    ]

    for lib_name, lib_path, preview in libraries:
        key = get_lib_key(lib_name, 'sym')
        description = lib_descriptions.get(key, "")

        # Use environment variable in URI
        uri = f'${{KICAD_CUSTOM_LIB_DIR}}/symbols/{lib_path.name}'

        line = f'\t(lib (name "{lib_name}") (type "KiCad") (uri "{uri}") (options "") (descr "{description}"))'
        lines.append(line)

    lines.append('')
    lines.append(')')

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"Generated: {output_file}")
    print(f"  Found {len(libraries)} symbol library(ies)")

    return output_file


def generate_fp_lib_table(
    footprints_dir: Path,
    output_dir: Path,
    config: dict[str, str] | None = None,
    mode: InputMode = InputMode.USE_JSON,
    config_path: Path | None = None,
) -> Path:
    """Generate fp_lib_table file."""
    output_file = output_dir / 'fp_lib_table'

    libraries = discover_footprint_libraries(footprints_dir)

    if not libraries:
        # Create empty table if no libraries found
        lines = ['(fp_lib_table', '\t(version 7)', ')']
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"Generated (empty): {output_file}")
        return output_file

    # Collect descriptions based on mode
    lib_descriptions: dict[str, str] = {}
    if config:
        lib_descriptions = config.copy()

    if mode == InputMode.ASK_EACH:
        updated = False
        for lib_name, lib_path, preview in libraries:
            key = get_lib_key(lib_name, 'fp')
            if key not in lib_descriptions or not lib_descriptions[key]:
                desc = prompt_for_description(lib_name, 'Footprint', preview)
                lib_descriptions[key] = desc
                updated = True
        if updated and config_path:
            save_lib_config(config_path, lib_descriptions)
    # USE_JSON: use config as-is; SKIP: all descriptions remain empty

    lines = [
        '(fp_lib_table',
        '\t(version 7)',
    ]

    for lib_name, lib_path, preview in libraries:
        key = get_lib_key(lib_name, 'fp')
        description = lib_descriptions.get(key, "")

        # Use environment variable in URI
        uri = f'${{KICAD_CUSTOM_LIB_DIR}}/footprints/{lib_name}.pretty'

        line = f'\t(lib (name "{lib_name}") (type "KiCad") (uri "{uri}") (options "") (descr "{description}"))'
        lines.append(line)

    lines.append('')
    lines.append(')')

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"Generated: {output_file}")
    print(f"  Found {len(libraries)} footprint library(ies)")

    return output_file


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    # Determine base directory
    base_dir = get_default_lib_dir()
    print(f"Base directory: {base_dir}")

    # Set paths
    symbols_dir = base_dir / 'Symbols'
    footprints_dir = base_dir / 'Footprints'
    output_dir = get_script_dir()

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Symbols directory: {symbols_dir}")
    print(f"Footprints directory: {footprints_dir}")
    print(f"Output directory: {output_dir}")
    print()

    # Discover all libraries
    sym_libs = discover_symbol_libraries(symbols_dir)
    fp_libs = discover_footprint_libraries(footprints_dir)

    total_libs = len(sym_libs) + len(fp_libs)
    print(f"发现 {len(sym_libs)} 个符号库，{len(fp_libs)} 个封装库，共 {total_libs} 个库")

    if total_libs == 0:
        print("没有找到任何库，生成空表格文件。")
        generate_sym_lib_table(symbols_dir, output_dir, None, InputMode.SKIP)
        generate_fp_lib_table(footprints_dir, output_dir, None, InputMode.SKIP)
        return

    # Determine mode
    mode = InputMode.USE_JSON

    # Load or prepare config
    config_path = get_config_path()
    existing_config = load_lib_config(config_path)

    lib_descriptions = None

    if mode == InputMode.USE_JSON:
        print(f"\n使用 JSON 配置模式")
        print(f"配置文件：{config_path}")

        # Check if we have configs for all libraries
        missing_configs = []
        for lib_name, _, _ in sym_libs:
            key = get_lib_key(lib_name, 'sym')
            if key not in existing_config or not existing_config[key]:
                missing_configs.append((key, lib_name, 'sym'))
        for lib_name, _, _ in fp_libs:
            key = get_lib_key(lib_name, 'fp')
            if key not in existing_config or not existing_config[key]:
                missing_configs.append((key, lib_name, 'fp'))

        if missing_configs:
            print(f"\n发现 {len(missing_configs)} 个库缺少描述配置:")
            for key, name, lib_type in missing_configs:
                print(f"  - {name} ({lib_type})")
            print()

            # Let user decide how to handle missing configs
            print("如何处理缺少的配置？")
            sub_choice = show_mode_prompt()

            if sub_choice == 'a':
                mode = InputMode.ASK_EACH
            elif sub_choice == 'b':
                # Update config file and wait for user to edit
                for key, name, lib_type in missing_configs:
                    existing_config[key] = ""
                save_lib_config(config_path, existing_config)

                print(f"\n配置文件已更新：{config_path}")
                print("请编辑文件后按 Enter 继续，或输入 'r' 跳过编辑：")
                user_input = input("> ").strip().lower()
                if user_input != 'r':
                    existing_config = load_lib_config(config_path)
            else:
                mode = InputMode.SKIP

        else:
            # All libraries have descriptions - use config directly without prompting
            print(f"所有 {total_libs} 个库的描述配置已存在，直接使用配置文件。")

        lib_descriptions = existing_config

    elif mode == InputMode.ASK_EACH:
        print("\n使用交互式输入模式")
        lib_descriptions = {}

    # Generate tables
    print("\n" + "=" * 60)
    print("开始生成表格文件...")
    print("=" * 60 + "\n")

    generate_sym_lib_table(symbols_dir, output_dir, lib_descriptions, mode, config_path)
    generate_fp_lib_table(footprints_dir, output_dir, lib_descriptions, mode, config_path)

    # 最后检查并修复 JSON 配置文件的排序
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                current_config = json.load(f)
            libs = current_config.get('libraries', {})
            if libs:
                sorted_libs = dict(sorted(libs.items()))
                if list(libs.keys()) != list(sorted_libs.keys()):
                    current_config['libraries'] = sorted_libs
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(current_config, f, indent=4, ensure_ascii=False)
                    print(f"\n已修复配置文件排序: {config_path}")
        except Exception as e:
            print(f"\nWarning: 配置文件排序检查失败: {e}")

    print()
    print("Done!")


if __name__ == '__main__':
    main()
