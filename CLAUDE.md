# CLAUDE.md

## Agent Instructions

Load all `AGENTS.md` files found anywhere in this project before proceeding. These files contain
project-specific context, conventions, and constraints that take precedence over general defaults.
Check the following locations and load every file that exists:

- `./AGENTS.md`
- `./openspec/AGENTS.md`
- Any `AGENTS.md` found in subdirectories

---

## Code Discovery with codebase-memory-mcp (optional)

This repo declares the `codebase-memory-mcp` server in `.mcp.json`. It provides a code
knowledge graph (call graphs, architecture overview, semantic search) that makes structural
exploration of this large workspace much faster.

**If the `codebase-memory-mcp` tools are available in this session**, prefer them over raw
`Read`/`Grep`/`Glob` for _understanding structure_ (raw file tools remain the right choice
for editing and line-level work). Follow the tool guide below.

**If they are not available**, use the built-in search tools normally. Do NOT ask the user
to install anything, and ignore the rest of this section.

> Maintainers who want it: install the `codebase-memory-mcp` binary somewhere on your
> `PATH` (e.g. `~/.local/bin`), then approve the server when Claude Code prompts for
> `.mcp.json`. Declining the prompt is fine — everything works without it.

### Step 0 — Ensure the project is indexed

Before any code exploration, confirm the project is indexed:

```
index_status   →  check if current repo is indexed
index_repository  →  index it if not (use absolute path)
list_projects  →  confirm it appears in the registry
```

Run `index_repository` once per project. After that, the background watcher keeps it current.

### Tool Reference

#### Indexing

| Tool               | When to use                                                  |
| ------------------ | ------------------------------------------------------------ |
| `index_repository` | First time opening a project, or after a major branch switch |
| `list_projects`    | Verify which repos are indexed and their node/edge counts    |
| `index_status`     | Quick check if the current project is up to date             |
| `delete_project`   | Clean up a repo that's no longer needed in the graph         |

#### Understanding Structure (use before writing any code)

| Tool               | When to use                                                                                                                                                                       |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `get_architecture` | **Start here.** Get languages, entry points, packages, routes, hotspots, module clusters, and ADRs in one call. Run this at the start of every `opsx:explore` and `opsx:propose`. |
| `get_graph_schema` | When you need to know what node/edge types exist before writing a `query_graph` query.                                                                                            |

#### Finding Things

| Tool               | When to use                                                                                                                                                    |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `search_graph`     | Find functions, classes, interfaces, routes by name pattern, label, or file. Use instead of Grep when you need structural results. Supports regex.             |
| `search_code`      | Grep-like text search scoped to indexed files only. Use when you need to find a string that isn't a symbol (e.g. a config value, a comment, a string literal). |
| `semantic_query`   | When you know _what_ you're looking for conceptually but not the exact name. Uses vector embeddings — no API key required.                                     |
| `get_code_snippet` | Fetch source code for a specific function by its qualified name (find the name via `search_graph` first).                                                      |

#### Tracing & Impact

| Tool             | When to use                                                                                                                                                                                                                           |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `trace_path`     | Find who calls a function and what it calls (inbound, outbound, or both). Use during `opsx:explore` to understand how a feature is connected, and during `opsx:verify` to confirm the call chain is correct after changes. Depth 1–5. |
| `detect_changes` | Map current git diff to affected symbols with risk classification. Run this before `opsx:propose` to know the blast radius, and after `opsx:apply` to confirm the scope matches expectations.                                         |
| `query_graph`    | Run Cypher-like read queries for custom analysis — dead code detection, cross-package dependencies, finding all implementations of an interface, etc. Read-only.                                                                      |

#### Knowledge & Validation

| Tool            | When to use                                                                                                                             |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `manage_adr`    | Create or retrieve Architecture Decision Records. Log significant decisions made during `opsx:propose` so they persist across sessions. |
| `ingest_traces` | After running the app, ingest runtime traces to validate that HTTP call edges in the graph match actual runtime behaviour.              |

### When to use which tool — by OpenSpec phase

**`opsx:explore`**

1. `get_architecture` — get the lay of the land
2. `search_graph` — locate the specific symbols relevant to the task
3. `trace_path` — understand how they connect
4. `semantic_query` — if the exact name is unknown

**`opsx:propose`**

1. `detect_changes` — assess blast radius of the proposed approach
2. `query_graph` — verify no dead code or orphaned paths will be affected
3. `trace_path` — confirm entry points and downstream impact
4. `manage_adr` — record the architectural decision being made

**`opsx:apply`**

- Use `get_code_snippet` to read the exact current implementation before editing
- Use `search_graph` to find all related files that may need parallel updates

**`opsx:verify`**

1. `detect_changes` — confirm the diff scope matches what was proposed
2. `trace_path` — verify new call chains are correctly wired
3. `search_graph` — check no related symbols were left unupdated
4. `ingest_traces` — if HTTP routes were changed, validate with runtime traces

### Cypher quick reference

Use `query_graph` for custom structural queries:

```cypher
-- Dead code: functions with no callers
MATCH (f:Function)
WHERE NOT EXISTS { (f)<-[:CALLS]-() }
RETURN f.name, f.file

-- All callers of a function
MATCH (caller:Function)-[:CALLS]->(f:Function {name: "ProcessOrder"})
RETURN caller.name, caller.file

-- All HTTP routes in the project
MATCH (r:Route) RETURN r.name, r.file

-- Functions that call across packages
MATCH (a:Function)-[:CALLS]->(b:Function)
WHERE a.package <> b.package
RETURN a.name, a.package, b.name, b.package
LIMIT 20
```

### Notes

- Always pass **absolute paths** to `index_repository`
- Use `list_projects` to get the exact project name, then pass `project="name"` to scoped queries
- If `trace_path` returns 0 results, use `search_graph` first to confirm the exact symbol name
- The background watcher handles incremental re-indexing after file changes — no need to
  re-run `index_repository` on every save
