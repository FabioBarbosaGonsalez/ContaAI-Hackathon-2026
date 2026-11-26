# Lista de senhas comuns

`senhas_comuns.txt.gz` é a lista que o cadastro usa para recusar senhas comuns (NIST SP 800-63B-4, §3.1.1.2; [ADR 0015](../../../docs/adr/0015-contas.md)).

- **Origem:** `Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt` do [SecLists](https://github.com/danielmiessler/SecLists), baixada em 2026-11-26 de `raw.githubusercontent.com/danielmiessler/SecLists/master/`.
- **SHA-256 do arquivo baixado:** `c2e5696882c603b76bb67a47ee970897e5a76fc4c3f5547abe3d0ca340c576e0` (99.840 linhas).
- **Licença:** o SecLists é MIT ("MIT License", "Copyright (c) 2018 Daniel Miessler"), lida em 2026-11-26. A lista é derivada de dados do NCSC do Reino Unido, e os termos do próprio NCSC **não foram verificados**: o endereço do NCSC respondeu 404.
- **O que foi feito com ela:** cada linha passou por NFKC e por `casefold()`. Ficaram só as linhas imprimíveis com 8 caracteres ou mais (o mínimo da senha), sem repetição e em ordem: 46.483 senhas. O gzip foi gravado com `mtime=0`, para que o arquivo seja reprodutível.

Para refazer a lista, baixe o arquivo, confira o SHA-256 e repita o filtro:

```python
import gzip, unicodedata

linhas = open("100k-most-used-passwords-NCSC.txt", encoding="utf-8").read().splitlines()
s = sorted(
    {
        unicodedata.normalize("NFKC", l).casefold()
        for l in linhas
        if len(unicodedata.normalize("NFKC", l)) >= 8 and l.isprintable()
    }
)
with gzip.GzipFile("senhas_comuns.txt.gz", "wb", mtime=0) as f:
    f.write(("\n".join(s) + "\n").encode())
```
