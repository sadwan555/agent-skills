# Windows WSL Ubuntu Migration

This guide installs the five Skills from one master repository for Codex, Claude Code, and OpenCode. It does not require or recommend separate copies for each Agent.

## 1. WSL prerequisites

Use Ubuntu inside WSL 2. Store the repository in the Linux filesystem under `$HOME`, not under `/mnt/c`, to preserve normal permissions and symlink behavior and to avoid cross-filesystem performance penalties.

Required commands:

```bash
git --version
python3 --version
```

Python must be version 3.10 or newer. If either command is absent, install it through the Ubuntu package manager before continuing. No Node.js, npm, pip packages, or uv environment is required by these Skills.

## 2. Transfer the master repository

### Option A: clone the private GitHub repository

Authenticate in WSL as a GitHub account that has access to the private
repository. With GitHub CLI installed:

```bash
gh auth login --hostname github.com --git-protocol https --web
gh repo clone sadwan555/agent-skills "$HOME/agent-skills"
```

If Git credentials are already configured in WSL, clone directly instead:

```bash
git clone https://github.com/sadwan555/agent-skills.git "$HOME/agent-skills"
```

The repository is private. A clone attempt without repository access will fail.

### Option B: copy from a transferred directory

Copy the complete repository, including `.git`, into the WSL Linux home directory. If the transferred folder is temporarily visible through a Windows mount:

```bash
MIGRATION_SOURCE="/mnt/c/<path-to-transferred-agent-skills>"
if [ -e "$HOME/agent-skills" ] || [ -L "$HOME/agent-skills" ]; then
  printf 'ERROR: destination already exists: %s\n' "$HOME/agent-skills" >&2
  exit 1
fi
cp -a "$MIGRATION_SOURCE" "$HOME/agent-skills"
```

Do not keep the working master under `/mnt/c`. After copying, verify:

```bash
git -C "$HOME/agent-skills" status --short --branch
git -C "$HOME/agent-skills" log -1 --oneline
```

The working tree should be clean.

## 3. Validate before linking

```bash
cd "$HOME/agent-skills"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

To run the optional external-template integration checks:

```bash
RESEARCH_TEMPLATE_PATH="$HOME/<path-to-research-template>" \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s tests -v
```

## 4. Create discovery links

Create the discovery directories without overwriting anything:

```bash
mkdir -p "$HOME/.agents/skills" "$HOME/.claude/skills"
```

Inspect existing names first:

```bash
for skill in \
  research-experiment-design \
  research-literature-review \
  research-paper-audit \
  research-reproducibility \
  research-result-verification
do
  for base in "$HOME/.agents/skills" "$HOME/.claude/skills"
  do
    target="$base/$skill"
    if [ -e "$target" ] || [ -L "$target" ]; then
      printf 'EXISTS\t%s\t%s\n' "$target" "$(readlink "$target" 2>/dev/null || printf 'not-a-symlink')"
    fi
  done
done
```

Resolve every reported collision before linking. Do not delete or overwrite an existing directory merely because it has the same name.

When no collisions remain:

```bash
for skill in \
  research-experiment-design \
  research-literature-review \
  research-paper-audit \
  research-reproducibility \
  research-result-verification
do
  ln -s "$HOME/agent-skills/$skill" "$HOME/.agents/skills/$skill"
  ln -s "$HOME/agent-skills/$skill" "$HOME/.claude/skills/$skill"
done
```

The resulting ownership is:

- Codex: `$HOME/.agents/skills`
- OpenCode: `$HOME/.agents/skills`
- Claude Code: `$HOME/.claude/skills`

No copy is required under `$HOME/.config/opencode/skills` or `$HOME/.opencode/skills` when OpenCode discovers `$HOME/.agents/skills`.

## 5. Verify links

```bash
bash "$HOME/agent-skills/scripts/verify-install-links.sh"
```

The verifier exits nonzero on a missing link, an ordinary directory in place of a link, a wrong target, a missing `SKILL.md`, or a missing master directory. It prints success only after all ten links resolve to the master.

Restart an Agent only if it does not refresh its Skill inventory automatically.

## 6. OpenCode duplicate discovery warning

Some OpenCode versions scan both `$HOME/.agents/skills` and `$HOME/.claude/skills`. Because both links intentionally resolve to the same master, OpenCode may log `duplicate skill name` and select one discovered path.

This is not evidence of two masters or divergent content. Confirm both paths resolve to the same directory. Do not create a third copy to suppress the warning.

## 7. Script execution rule

An Agent commonly runs from the research project's directory. A relative command such as `python3 scripts/tool.py` would therefore target the wrong directory. Each Skill now instructs the Agent to resolve the directory containing its active `SKILL.md` and run:

```bash
SKILL_ROOT="<directory-containing-the-active-SKILL.md>"
python3 "$SKILL_ROOT/scripts/<script>.py" <arguments>
```

All helpers use only the Python standard library. Explicit `python3` invocation also works when executable permission metadata is unavailable after a Windows-side transfer.

## 8. Line endings and permissions

`.gitattributes` fixes Markdown, Python, CSV, JSON, and Shell text to LF. Clone with Git inside WSL when possible. If files were copied through Windows, run the test suite before linking; CRLF in Python or shell entrypoints will be reported.

Four original scripts carry an executable bit and one does not. This does not affect supported execution because all examples use `python3` explicitly.

## 9. Agent-specific behavior

The portable core is common to all three Agents. `research-paper-audit` retains additional policy:

| Label | Meaning |
|---|---|
| Portable | Evidence vocabulary, deterministic helper, outputs, and upstream handoffs |
| OpenCode only | Optional high-throughput first-pass inventory and consistency extraction |
| Codex only | Final severity, core-claim judgment, cross-Skill escalation, and scientific audit gate |
| Claude Code policy | Do not use the paper-audit workflow without explicit user authorization |

Do not silently remove or transfer these responsibilities when changing hosts.

## 10. Updating the repository

Update the single master, validate it, commit it, and let all discovery links see the same files:

```bash
cd "$HOME/agent-skills"
git status --short --branch
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Review remote changes before pulling. Never replace a dirty working tree or overwrite local Skill changes without resolving them explicitly.

## Compatibility change record

| Change in this master | Reason |
|---|---|
| Flattened the five Skill directories at repository root | Makes each directory directly linkable from Agent discovery paths |
| Preserved complete `scripts/`, `references/`, and `assets/` trees | Prevents a `SKILL.md`-only migration from losing runtime resources |
| Replaced two unversioned `python` examples with `python3` | Ubuntu/WSL does not guarantee a `python` alias |
| Added a Portable execution section to every `SKILL.md` | Declares Python 3.10+ and standard-library-only runtime requirements |
| Resolved script/resource instructions from the active Skill directory | Agents usually execute from a project directory, not the Skill directory |
| Labeled paper-audit host roles | Preserves Codex, OpenCode, and Claude Code-specific policy without presenting it as universal |
| Added LF attributes | Prevents Windows checkout settings from introducing CRLF into scripts and text assets |
| Made the external research-template tests optional | Keeps this repository self-contained while retaining opt-in integration coverage |
| Added a fail-fast installation-link verifier | Prevents a partial or misdirected link set from being reported as successful |
| Excluded caches and Mac metadata | They are generated state, not Skill runtime resources |
