# Sprint Checklist

## Pre-Merge Checks

- [ ] All unit tests pass: `pytest tests/unit/ -v`
- [ ] All integration tests pass: `pytest tests/integration/ -v`
- [ ] No regressions in existing tests: `pytest tests/ -v`
- [ ] Test coverage acceptable: `pytest tests/ --cov=binance-bot/src --cov=shared --tb=short`
- [ ] Code passes linting: `ruff check binance-bot/src/ shared/`
- [ ] No hardcoded secrets or credentials in code
- [ ] New dependencies added to requirements.txt

## Post-Merge Checks

- [ ] GitHub Actions CI passes on main
- [ ] No breaking changes to existing functionality
- [ ] Database migrations applied (if any)
- [ ] Documentation updated for new features

## Release Checklist

- [ ] Version bumped in pyproject.toml
- [ ] CHANGELOG updated
- [ ] Tag created: `git tag -a vX.Y.Z -m "Release X.Y.Z"`
- [ ] Docker images rebuilt (if applicable)
