# SageMath Typing Stubs

This directory contains Python type stubs (`.pyi`) for the SageMath library, generated using a combination of `stubgen` and manual completion.

## Workflow

1.  **Inventory**: `tools/typing/inventory.py` identifies modules to stub.
2.  **Skeleton**: `tools/typing/generate_skeleton.py` generates initial skeletons using `stubgen` (Python) or `stubgen-pyx` (Cython).
3.  **Manual Completion**: Each module is manually refined against the source code to ensure correct types and signatures.
4.  **Review**: Stubs are verified against the checklist in `tools/typing/checklists/`.
5.  **Completion**: Once approved, the manifest is updated and work proceeds to the next module.

## Directory Structure

- `typings/sage/`: Contains the generated stubs.
- `tools/typing/checklists/`: Checklists for each module's manual completion.
- `tools/typing/logs/`: Logs from stubgen runs.
- `tools/typing/notes/`: Additional notes and documentation.
- `tools/typing/typing_manifest.json`: Tracks the status of each module.
