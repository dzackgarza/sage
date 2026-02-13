import os
import json
import logging

# Configuration
SRC_ROOT = "src"
SAGE_ROOT = "src/sage"
MANIFEST_PATH = "tools/typing/typing_manifest.json"
CHECKLIST_DIR = "tools/typing/checklists"
LOG_DIR = "tools/typing/logs"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_module_name(filepath: str) -> str:
    """Converts a file path to a dotted module name."""
    rel_path = os.path.relpath(filepath, SRC_ROOT)
    module_name = rel_path.replace(os.sep, ".").rsplit(".", 1)[0]
    if module_name.endswith(".__init__"):
        module_name = module_name[:-9]
    return module_name

def scan_modules():
    modules = []
    for root, _, files in os.walk(SAGE_ROOT):
        for file in files:
            if file.endswith((".py", ".pyx")):
                filepath = os.path.join(root, file)
                module_name = get_module_name(filepath)
                # Ensure we capture extensions correctly for tools to use
                ext = file.split('.')[-1]
                modules.append((module_name, filepath, ext))
    return sorted(modules)

def update_manifest():
    manifest_data = []
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, 'r') as f:
                content = f.read()
                if content:
                    manifest_data = json.loads(content)
        except json.JSONDecodeError:
            pass

    existing_entries = {item['module']: item for item in manifest_data}

    scanned_modules = scan_modules()

    new_manifest = []

    for module_name, filepath, ext in scanned_modules:
        if module_name in existing_entries:
            # Preserve existing status
            entry = existing_entries[module_name]
            # Update source path if it somehow changed (unlikely but safe)
            entry["source_path"] = filepath
            entry["type"] = "python" if ext == "py" else "cython"
            new_manifest.append(entry)
        else:
            # Determine expected stub path
            rel_stub_path = os.path.relpath(filepath, SRC_ROOT)
            # Remove extension and add .pyi
            stub_rel = os.path.splitext(rel_stub_path)[0] + ".pyi"
            stub_path = os.path.join("typings", stub_rel)

            entry = {
                "module": module_name,
                "source_path": filepath,
                "stub_path": stub_path,
                "status": "pending",
                "type": "python" if ext == "py" else "cython"
            }
            new_manifest.append(entry)

    with open(MANIFEST_PATH, 'w') as f:
        json.dump(new_manifest, f, indent=2)

    logger.info(f"Updated manifest with {len(new_manifest)} modules.")

if __name__ == "__main__":
    update_manifest()
