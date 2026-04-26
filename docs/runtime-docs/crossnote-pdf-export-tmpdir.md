# Crossnote / Markdown Preview Enhanced PDF Export — `ERR_FILE_NOT_FOUND`

## Symptom

Exporting a PDF (Puppeteer/Chrome) from VS Code's *Markdown Preview Enhanced*
(crossnote) extension fails with:

```
Error: net::ERR_FILE_NOT_FOUND at file:////tmp/crossnote2026325-2049-cpy2lw.y98io.html
```

The temp HTML file genuinely exists at `/tmp/crossnote*.html` and is readable
by the user, but Chromium reports it missing.

## Root cause

When Chromium is installed via **snap** (the default on Ubuntu 22.04+, including
under WSL2), snap confinement remaps `/tmp` to a per-snap private tmp directory
(`/tmp/snap-private-tmp/snap.chromium/tmp/`). Files written to the host's real
`/tmp` are invisible to the confined Chromium process, so the `file:///tmp/...`
URL handed to it by crossnote resolves to nothing → `ERR_FILE_NOT_FOUND`.

This is **not WSL2-specific** — it reproduces on any Ubuntu (or other distro)
where Chromium ships as a snap. WSL2 just makes it more common because Ubuntu
22.04 is the typical default distro and its `chromium` apt package is a
transitional shim to the snap.

Confirm with:

```bash
snap list | grep -i chromium                       # snap present?
ls -la /tmp/crossnote*                             # file exists for your user
snap run --shell chromium -c 'ls /tmp/crossnote*'  # snap can't see it
```

## Fix (verified working)

The `TMPDIR`-only approach is **not sufficient on its own** — even with
`TMPDIR` redirected, snap-confined Chromium remained the blocker (and in
practice MPE/crossnote sometimes still emits paths under `/tmp` depending on
which code path runs). The reliable fix is to point MPE at a **non-snap**
Chrome binary in `$HOME`, where snap confinement does not apply.

If Puppeteer is already installed (e.g. via another Node project that
depends on it), Chrome-for-Testing is already cached under
`~/.cache/puppeteer/chrome/linux-*/chrome-linux64/chrome`. Use it directly.

### Steps

1. Belt-and-braces: also set `TMPDIR` inside `$HOME` so any temp file MPE
   creates lands in a snap-readable location:

   ```bash
   mkdir -p "$HOME/.cache/crossnote-tmp"
   echo 'export TMPDIR="$HOME/.cache/crossnote-tmp"' >> ~/.bashrc
   ```

2. Find your bundled Chrome:

   ```bash
   find ~/.cache/puppeteer -maxdepth 4 -name chrome -type f
   ```

   If nothing prints, install Puppeteer to populate the cache:

   ```bash
   npm i -g puppeteer
   ```

3. In VS Code, open `settings.json` and add (substitute the actual path
   from step 2):

   ```jsonc
   "markdown-preview-enhanced.chromePath": "/home/<you>/.cache/puppeteer/chrome/linux-146.0.7680.80/chrome-linux64/chrome"
   ```

4. Fully restart so VS Code's extension host inherits both the new env and
   the new setting:

   - Close all VS Code windows.
   - From Windows PowerShell (WSL only): `wsl --shutdown`
   - Reopen VS Code → Remote-WSL.

5. Retry the PDF export.

### Why this works

- Puppeteer's bundled Chrome lives in `$HOME`; snap confinement does not
  apply (only the **snap-installed** Chromium is confined).
- No `sudo`, no system package changes, no browser swap.
- Survives Ubuntu/snap updates.

## Alternatives

1. **Replace snap Chromium with the deb/Google Chrome.** Cleanest long-term
   fix but requires `sudo snap remove chromium` + `sudo apt install` (or
   the official Chrome `.deb`).
2. **Skip the chromePath setting and try `TMPDIR` alone.** Worked in some
   reports; did **not** work in this environment (April 2026, Ubuntu 22.04,
   WSL2, MPE 0.x, snap chromium 147). Listed for completeness, not
   recommended as the first move.

## References

- snap confinement & private tmp: <https://snapcraft.io/docs/snap-confinement>
- Upstream issue (one of many): <https://github.com/shd101wyy/markdown-preview-enhanced/issues/1827>
- Related: same root cause hits `mermaid-cli`, `puppeteer-pdf`, anything that
  spawns snap-Chromium against a `file:///tmp/...` URL.
