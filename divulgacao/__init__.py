"""Módulo de divulgação — roda DEPOIS que um corte é exportado.

Três submódulos:
  hashtags.py  -> pesquisa de hashtags e tags (YouTube Data API v3 + TikTok manual + IA)
  grupos.py    -> plano de divulgação em grupos do Facebook (sem automação de postagem)
  registro.py  -> CSV de resultados e relatório de prioridades

Este pacote é autocontido: não importa `core.*` e não modifica nenhum arquivo
fora de `divulgacao/`. O único ponto de integração opcional está em
`divulgacao/integracao.py` (desligado por padrão).
"""

__versao__ = "1.0.0"
