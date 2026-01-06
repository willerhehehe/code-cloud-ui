# code-cloud-ui

A tiny Python web UI that visualizes a repository as either a word cloud (human-facing terms) or a code cloud (identifier-focused terms).

## Quick start

```bash
python app.py --port 8000
```

Then open http://localhost:8000. Use the toggle in the header to switch between word and code clouds and click **Refresh** to re-scan the working tree.

### Modes

- **Word cloud**: longer, human-readable terms from all text files.
- **Code cloud**: identifier fragments from code and configuration files.
- **Structure cloud**: class, function/method, and top-level variable names, skipping JavaScript/TypeScript files entirely.
