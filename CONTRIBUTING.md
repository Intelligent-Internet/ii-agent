## Contributing & Provider Integrations

Thanks for contributing! This file contains a short note about the optional provider integrations and how CI handles them.

### Provider integrations (`providers` extra)

Some integrations (Google APIs, Anthropic, e2b code interpreter, and related libraries) are heavy and pull many transitive dependencies. To keep everyday development, contributor onboarding, and CI runs fast and deterministic these are provided as an optional extra named `providers`.

When to opt into `providers`:
- If you are developing or testing code that interacts with those provider APIs (e.g., Google GenAI, Anthropic, e2b), install the `providers` extra locally.
- If you are working on core features, UI, or small tools that don't call external providers, you do not need to install `providers`.

How to install locally (recommended with constraints):

```powershell
# Install only providers (use the repo constraints for deterministic resolution)
python -m pip install -e "[.providers]" -c constraints.txt

# Or install dev and providers when running tests that require providers
python -m pip install -e ".[dev]" -c constraints.txt
python -m pip install -e ".[providers]" -c constraints.txt
```

Notes:
- `constraints.txt` is included to pin heavy dependencies and avoid pip resolver backtracking. Use it in CI and locally when installing the `providers` extra.
- Provider integrations may require credentials or API keys. Do NOT add secrets to the repo. Use repository secrets in CI or local environment variables.

### CI behavior

- The default `test` job runs lightweight unit tests and installs the `dev` extras using `constraints.txt` to keep runs fast and deterministic.
- A separate `integration` job installs the `providers` extra (also using `constraints.txt`) and performs a quick smoke check and `pip check`. This job runs after `test` and is intended to verify provider installs in CI without running long integration suites by default.

If you are adding provider-specific integration tests that require credentials, please:

1. Add tests under `tests/integration/` (or a similar directory). Keep them separate from unit tests.
2. Guard tests that rely on external credentials with markers or environment checks so they are skipped when credentials are not present.
3. Add instructions in this file for any required secrets and which GitHub Actions secrets to set.

Thanks for keeping the repo tidy — small, focused installs make the project easier for everyone to contribute to.
