import argparse
import subprocess
import json
import logging
import os
import shutil

# Configuration
MANIFEST_PATH = "tools/typing/typing_manifest.json"
LOG_DIR = "tools/typing/logs"
STUB_ROOT = "typings"
SRC_ROOT = "src"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_manifest():
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)

def run_stubgen_python(module_entry):
    source_path = module_entry["source_path"] # e.g., src/sage/foo.py
    # We want to run from src/ so that sage/... is preserved
    rel_path = os.path.relpath(source_path, SRC_ROOT) # sage/foo.py

    # Ensure output directory exists (stubgen handles it, but just in case)
    os.makedirs(STUB_ROOT, exist_ok=True)

    cmd = ["stubgen", "--parse-only", rel_path, "-o", "../typings"]

    logger.info(f"Running: {' '.join(cmd)} (cwd={SRC_ROOT})")

    result = subprocess.run(cmd, cwd=SRC_ROOT, capture_output=True, text=True)

    return result

def run_stubgen_cython(module_entry):
    source_path = module_entry["source_path"] # src/sage/groups/group.pyx
    stub_path = module_entry["stub_path"] # typings/sage/groups/group.pyi
    output_dir = os.path.dirname(stub_path) # typings/sage/groups

    os.makedirs(output_dir, exist_ok=True)

    rel_to_sage = os.path.relpath(source_path, "src/sage")

    cmd = [
        "stubgen-pyx",
        "src/sage",
        "--file", rel_to_sage,
        "--output-dir", output_dir
    ]

    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result

def generate_skeleton(module_entry):
    module_name = module_entry["module"]
    module_type = module_entry["type"]
    log_file = os.path.join(LOG_DIR, f"{module_name}.log")

    logger.info(f"Generating skeleton for {module_name} ({module_type})")

    if module_type == "python":
        result = run_stubgen_python(module_entry)
    else:
        result = run_stubgen_cython(module_entry)

    # Log output
    with open(log_file, "w") as f:
        f.write(f"Command stdout:\n{result.stdout}\n")
        f.write(f"Command stderr:\n{result.stderr}\n")

    if result.returncode == 0:
        logger.info(f"Success for {module_name}")
        return True
    else:
        logger.error(f"Failure for {module_name}. See {log_file}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("module", help="Module name to generate skeleton for (or 'next')")
    args = parser.parse_args()

    manifest = load_manifest()

    target_entry = None
    if args.module == "next":
        # Find first pending
        target_entry = next((m for m in manifest if m["status"] == "pending"), None)
        if not target_entry:
            logger.info("No pending modules found.")
            return
    else:
        target_entry = next((m for m in manifest if m["module"] == args.module), None)

    if not target_entry:
        logger.error(f"Module {args.module} not found in manifest")
        return

    if generate_skeleton(target_entry):
        target_entry["status"] = "skeleton_generated"

        # Create checklist
        checklist_path = os.path.join("tools/typing/checklists", f"{target_entry['module']}.md")
        log_path = os.path.join(LOG_DIR, f"{target_entry['module']}.log")

        with open(checklist_path, "w") as f:
            f.write(f"""# Checklist for {target_entry['module']}

## A. Skeleton Provenance
- [ ] Generator: {'stubgen' if target_entry['type'] == 'python' else 'stubgen-pyx'}
- [ ] Log path: `{log_path}`
- [ ] Parsing status: Success

## B. Export Surface
- [ ] Method:
    - [ ] `__all__`
    - [ ] `__init__` imports
    - [ ] grep for usage
- [ ] Exports verified

## C. Symbol-by-Symbol Completion
(List exported symbols here and check them off)

## D. Dynamic/Conditional Behavior
- [ ] Checked for runtime attributes
- [ ] Checked for conditional imports

## E. Internal Consistency
- [ ] `python -m py_compile {target_entry['stub_path']}` passed
- [ ] Imports are valid or guarded

## F. Review Gate
- [ ] Reviewer:
- [ ] Date:
""")

        # Update manifest
        # Reload to avoid race? For now, just rewrite.
        for i, entry in enumerate(manifest):
            if entry["module"] == target_entry["module"]:
                manifest[i] = target_entry
                break

        with open(MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)

if __name__ == "__main__":
    main()
