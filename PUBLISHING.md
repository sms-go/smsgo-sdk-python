# Publicando o `smsgo` (PyPI)

Guia de release do SDK Python. Registry: **PyPI** · pacote `smsgo`. Publicação por **Trusted Publishing (OIDC)** — sem token/secret.

## Pré-requisitos (uma vez)

1. Projeto `smsgo` no PyPI com um **Trusted Publisher** (ou "pending publisher" antes do 1º release) apontando para:
   - Repositório: `SMSFy/smsgo-sdk-python`
   - Workflow: `publish.yml`
   - Environment: `pypi`
   - Guia oficial: https://docs.pypi.org/trusted-publishers/
2. No GitHub do repo → _Settings → Environments_ → criar o environment **`pypi`** (o workflow usa `environment: pypi`).

O workflow [`/.github/workflows/publish.yml`](.github/workflows/publish.yml) builda (`python -m build`) e publica via `pypa/gh-action-pypi-publish` usando OIDC. **Nenhum token é necessário.**

## Passo a passo do release

1. `master` verde no CI (`python -m unittest`).
2. **Suba a versão** em **dois** lugares (devem bater):
   - [`pyproject.toml`](pyproject.toml) → `version = "0.3.0"`
   - [`src/smsgo/__init__.py`](src/smsgo/__init__.py) → `__version__ = "0.3.0"`
3. Atualize o [`CHANGELOG.md`](CHANGELOG.md).
4. (Opcional, sanity local) `python -m pip install --upgrade build && python -m build` → confira `dist/`.
5. Commit + push na `master`.
6. **Tag + Release:**
   ```bash
   git tag v0.3.0 && git push origin v0.3.0
   ```
   No GitHub → _Releases → Draft a new release_ → tag `v0.3.0` → _Publish release_ → dispara o `publish.yml`.
   - Alternativa: _Actions → Publish to PyPI → Run workflow_.
   - Fallback com token: `python -m build && twine upload dist/*` (usando um API token do PyPI).

## Verificação pós-publicação

```bash
pip index versions smsgo            # deve listar a nova versão
python -m venv /tmp/venv && /tmp/venv/bin/pip install "smsgo==0.3.0"
/tmp/venv/bin/python -c "import smsgo; print(smsgo.__version__, smsgo.verify_webhook_signature)"
```
Página: https://pypi.org/project/smsgo/

## Notas

- O PyPI é **imutável**: não dá para sobrescrever uma versão — só `yank` (esconde) e publicar uma nova.
- `version` do `pyproject.toml` **e** `__version__` precisam bater com a tag. Ver o guia central [`api/docs/sdks-publicacao.md`](../api/docs/sdks-publicacao.md).
