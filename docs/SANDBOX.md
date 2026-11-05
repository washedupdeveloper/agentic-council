# Running the council without a container runtime

`docker run` needs a daemon, a setuid helper, or `newuidmap`. A machine can have none of those and
still be able to run the image this flake builds — the image is a tarball, and an unpacked tarball
plus a user namespace is a container. That is what `council sandbox` is for.

```bash
council sandbox                                        # the image's entrypoint, no arguments
council sandbox --repo . -- doctor --repo /repo        # the deterministic analyzers, in the image
council sandbox --repo . --home ~/.hermes -- /bin/council-entrypoint /repo
```

`--image auto` (the default) builds `.#container` with nix. Give `--image <tarball>` to use one you
already have — the release asset works, so this needs no nix at all on the running side.

## What it mounts, and nothing else

| Flag | Target inside | Mode | Why |
|---|---|---|---|
| `--repo` | `/repo` | rw | the project under review |
| `--home` | `/home/council/.hermes` | rw | the profiles, rubrics and credentials a review needs |
| `--hermes` | `/opt/hermes` | **ro** | the Hermes the council borrows — never written to |
| `--seed` | `/seed` | **ro** | `config.yaml` / `.env` for a first run on a fresh volume |

Nothing is mounted that was not asked for, and `plan_mounts()` is tested in both directions: four
flags give four mounts with those exact targets, and no flags give **none** — there is no implicit
`/repo`, because a default repo is a review of the wrong tree when the flag is forgotten.

## Why it can run as root inside and still be safe to use

`unshare -r` maps *container root* to **the invoking user**. Writes to the bind-mounted repository
therefore land owned by you on the host — not by an unmapped root that shows up as `nobody`. This is
the one property that makes the arrangement usable rather than a machine that eats your file
ownership.

## What the rootfs is given, because a bare chroot is not a container

- a **tmpfs `/dev`** with `null zero full random urandom tty` bound in, `devpts` mounted, and
  `/dev/shm` at mode 1777. Without these, chromium aborts on `Failed to open /dev/null` and every
  `dom` claim is `unrunnable` — measured, not assumed;
- **`/proc`**, which the browser also needs;
- the **image's own `Env`**, read from the config blob (the manifest names a *filename*, it does not
  carry the config inline — reading it as inline JSON yields an empty `FONTCONFIG_FILE` and a
  browser that renders every glyph as a box).

Nothing is torn down explicitly: every mount lives in the process's mount namespace and dies with
it. Only the unpacked rootfs survives, under `~/.cache/council-sandbox/<key>`, where `<key>` is
derived from the image's path, size and mtime so a rebuilt image never reuses a stale unpack.

## The limits

- **Not a security boundary.** It is a run environment with an explicit mount set; it is not a
  jail. A process inside runs with your privileges on the paths you mounted.
- **Needs `unshare`.** util-linux, present on any Linux; absent on Windows, where the documented
  path is docker with the release asset.
- **No networking policy.** The review needs the model provider; the namespace keeps the host's
  network rather than pretending to isolate it.
- **`sandbox` is a dev verb.** It is not in the image — the image has no privilege to create the
  namespace it would need to enter.
