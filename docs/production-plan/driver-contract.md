# Driver Contract

Every platform driver (`LinuxDriver`, `MacOSDriver`, `WindowsDriver`) exposes the
same sub-drivers: `services`, `packages`, `web`, `dns`, `mail`, `php_fpm`
(Linux also `database`, `ssl`, `firewall`). Each method returns an `ApplyResult`
(`ok`, `action`, `changed`, `message`, `files`, `commands`).

## Rules

1. **Dry-run by default.** With `dry_run=True` a method performs no I/O and
   returns the files and commands it *would* touch.
2. **Never raise on a missing binary.** `run_command` returns
   `ok=False, message="command not found: <bin>"`.
3. **Validate before reload.** Writers (`web.apply_site`, `dns.apply_zone`)
   must run a config test after writing.
4. **Roll back on failed validation.** `web.apply_site` restores the previous
   file (or deletes a newly created one) and returns `ok=False` when the
   config test fails. A missing test binary is not treated as a failure.
5. **Idempotent.** Applying identical input twice yields the same files.

## Web server test commands

| Platform | Server | Test command |
|----------|--------|--------------|
| Linux | nginx | `nginx -t` |
| macOS / Windows | Caddy | `caddy validate` |
