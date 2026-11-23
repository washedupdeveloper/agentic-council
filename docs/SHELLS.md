# Shells

The CLI is Python; the repository's executable shell scripts are bash. Fish is
the login shell on some NixOS and WSL images and is deliberately not
POSIX-compatible: it cannot execute a bash script body, and `$?` is a syntax
error in fish. That is not a defect in the scripts — it is a rule about how to
invoke them.

## The rule

- Run a script by naming its interpreter: `bash tools/sandbox.sh …`.
- Do not `source` a repository bash script from fish, and do not paste its body
  into a fish prompt.
- A one-liner written for fish uses fish syntax; the table below is the
  translation.

## WSL: `--exec` bypasses the login shell

This is the failure that produced `fish: $? is not the exit status`:

```sh
wsl.exe -d NixOS -- bash -lc 'false; echo $?'
```

`wsl.exe --` hands the command to the distribution's default shell. On this
machine that shell is fish, so fish parses and expands the string before bash
ever runs; the check never starts. Both forms below bypass fish:

```sh
wsl.exe -d NixOS --exec bash -lc 'false; echo $?'      # login profile, bash quoting
wsl.exe -d NixOS --exec bash /home/you/script.sh       # a script file, no quoting layer
```

Prefer the script file for anything longer than one line. `--exec` runs the
named program directly and does **not** start a login shell, so the NixOS
profile is not loaded and `nix` may be missing from PATH. When the script needs
the profile, use `--exec bash -lc 'bash /path/script.sh'`; when it does not,
`--exec bash /path/script.sh` is enough. For a single command, use
`--exec bash -lc '…'`.

## Shell translation

| task | bash | fish | PowerShell |
|---|---|---|---|
| last exit status | `$?` | `$status` | `$LASTEXITCODE` |
| export a variable | `export FOO=bar` | `set -gx FOO bar` | `$env:FOO = 'bar'` |
| variable for one command | `FOO=bar cmd` | `env FOO=bar cmd` | `$env:FOO = 'bar'; cmd` |
| run on success / failure | `cmd1 && cmd2` / `cmd1 \|\| cmd2` | `cmd1; and cmd2` / `cmd1; or cmd2` | `cmd1; if ($?) { cmd2 }` |
| command substitution | `$(cmd)` | `(cmd)` | `$(cmd)` |
| file test | `[[ -f path ]]` | `test -f path` | `Test-Path path` |
| loop | `for x in …; do …; done` | `for x in …; …; end` | `foreach ($x in …) { … }` |
| function | `f() { …; }` | `function f; …; end` | `function f { … }` |
| run a repository script | `bash s.sh` | `bash s.sh` | `bash s.sh` |
| source a file | `. s.sh` | `source s.sh` | `. ./s.ps1` |

There is no shell that executes both bash and fish source natively. What can be
portable is the **invocation**: always name `bash` (or the Python entry point)
and the caller's shell stops mattering.

## The milestone runner

`tools/milestone.py` runs each task's `verify` command with `shell=True`. That
is `/bin/sh` on POSIX (dash on NixOS), never the caller's login shell, and
`cmd.exe` on Windows. A fish user is therefore safe, but predicates must be
POSIX shell, not fish and not bash:

- good: `test -f dist/council.whl`, `python -m pytest tests/test_run.py -q`,
  `git diff --check`
- not portable: `[[ -f dist/council.whl ]]`, `set -gx PATH …`,
  `cmd1; and cmd2`

## Repository scripts

`tools/*.sh` declare `#!/usr/bin/env bash`. `tests/test_shell_scripts.py` fails
the suite when a script lacks that shebang or does not parse with `bash -n`.
CI runs bash; it never runs fish. Add new scripts the same way.

The Python entry points (`council`, `council-verify`) are shell-independent and
work unchanged from fish, zsh, bash and PowerShell.
