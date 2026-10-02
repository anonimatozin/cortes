# divulgacao — hashtags, grupos do Facebook e registro de resultados

Módulo **novo e autocontido** que roda **depois** que um corte é exportado.
Não modifica, apaga nem renomeia nada do projeto principal — só cria arquivos
dentro de `divulgacao/`.

| Módulo | Arquivo | O que faz |
|---|---|---|
| 1. Pesquisa de hashtags e tags | `hashtags.py` | IA + YouTube Data API v3 + lista manual do TikTok → `saida/<corte>/metadata.json` |
| 2. Divulgação em grupos | `grupos.py` | buscas para achar grupos, 1 texto por grupo, plano de 2/dia → `plano_divulgacao.md` |
| 3. Registro de resultados | `registro.py` | `resultados.csv`, relatório e pesos que voltam para o Módulo 1 → `relatorio_resultados.md` |

---

## O que este módulo NÃO faz (de propósito)

- **Não posta no Facebook.** A Meta aposentou a Groups API em 22/04/2024.
  Nenhuma ferramenta de terceiros publica em grupos automaticamente. Robô de
  navegador (Selenium e cia.) finge ser você, viola os termos e costuma terminar
  em bloqueio de postagem ou ban na conta. Aqui não existe nem login automatizado.
  O plano sai com o texto pronto para **você copiar e colar** (2 minutos por dia).
- **Não raspa o TikTok.** `tiktok_trending.txt` é uma lista que você cola ou
  exporta do Creative Center. Scraping quebra e viola os termos.
- Não usa scraping do Google Trends: o suporte a Trends é opcional (`pytrends`),
  desligado por padrão e pode quebrar sem aviso.

> **Ideia melhor:** crie uma **Página** no Facebook para o canal. Páginas ainda
> aceitam agendamento, inclusive de Reels — aí sim dá para publicar sem tocar em
> nada, e o bot pode escrever os posts da Página.

---

## Instalação (Windows)

```bat
cd /d C:\Users\Administrator\Documents\cortes

:: dependências novas (o restante já está no requirements.txt da raiz)
pip install -r divulgacao\requirements.txt

:: checagem geral: chaves, pastas, transcrições, arquivos
python -m divulgacao doctor
```

O módulo usa as mesmas chaves do projeto:

- `GROQ_API_KEY` — já existe no `.env` da raiz (serve para a IA).
- `YOUTUBE_API_KEY` — **opcional**. Sem ela, o módulo usa o OAuth que o projeto
  já tem em `tokens/youtube.json` (é o que acontece hoje). Com chave, é só criar
  em *Google Cloud Console → APIs & Services → Credentials → API key* e colar
  `YOUTUBE_API_KEY=` no `.env` (modelo em `divulgacao\.env.example`).

---

## Passo a passo

### Módulo 1 — hashtags e tags

```bat
:: um corte específico (id = nome do arquivo em clips\, sem .mp4)
python -m divulgacao hashtags --corte 01_2tlZdonG59o_SO_UM_EVANGELICO_INVENTOU_O_COMPUTADOR

:: todos os cortes que ainda não têm metadata (o normal)
python -m divulgacao hashtags --todos

:: sem gastar cota do YouTube (só IA + listas locais)
python -m divulgacao hashtags --todos --sem-youtube
```

O que acontece por dentro:

1. lê a transcrição do trecho (`source\<id>.transcript.json`) usando o `start/end`
   gravado no sidecar do corte;
2. a IA gera **30 candidatas** (tema, jogo, personagem, emoção, público) — sem IA,
   cai num fallback a partir do nicho e das tags do autor;
3. `search.list` + `videos.list` buscam os vídeos do nicho, leem `snippet.tags`
   e contam quais tags aparecem **acima da média do próprio canal**;
4. o autocomplete do YouTube traz variações de busca;
5. `tiktok_trending.txt` entra como bônus (lista local, zero scraping);
6. **nota = frequência nos fortes × relevância ao corte × (1 − concorrência)**,
   somada aos pesos do Módulo 3 quando existirem;
7. grava `divulgacao\saida\<corte>\metadata.json` com:
   `titulo`, `descricao`, **3 a 5 hashtags** (1 ampla, 2 de nicho, 1 específica),
   `tags_youtube` (até 500 caracteres) e `hashtags_tiktok` em lista separada.

Proteções: cache de 7 dias em `cache\` (repetir a chamada custa **0** de cota),
teto diário de cota (`hashtags.youtube.cota_dia`) e fallback automático se a API
cair — a rodada nunca falha, só avisa.

### Módulo 2 — grupos do Facebook

```bat
:: 1) gera as buscas sugeridas e cria grupos.csv (só cabeçalho)
python -m divulgacao grupos --buscas --nicho podcast

:: 2) você pesquisa no Facebook, entra nos grupos e cola os links em
::    divulgacao\grupos.csv  (colunas: nome,link,tema,aceita_divulgacao,regras,ultima_postagem)
::    modelo em divulgacao\grupos.exemplo.csv

:: 3) escreve 1 texto por grupo que aceita divulgação e monta o plano
python -m divulgacao grupos --textos --plano 14

:: 4) publicou? registra (começa o cooldown de 7 dias do grupo)
python -m divulgacao grupos --postado "https://www.facebook.com/groups/xxxx"

:: situação da fila
python -m divulgacao grupos --status
```

Limites que o plano respeita: **2 grupos por dia**, **7 dias** entre posts no
mesmo grupo, **texto nunca repetido** (hash de todos os textos já escritos),
grupos com `aceita_divulgacao` diferente de `sim` ficam de fora e as regras
anotadas no CSV entram no prompt da IA.

Saída: `divulgacao\plano_divulgacao.md` — cada dia com o texto pronto para copiar
e o link do grupo.

### Módulo 3 — registro de resultados

```bat
python -m divulgacao registro add --corte 01_xxx --plataforma youtube --views 1200 --curtidas 90
python -m divulgacao registro add --corte 01_xxx --plataforma facebook --grupo "Minecraft BR" --views 300

:: depois de umas semanas, atualiza as views
python -m divulgacao registro views --corte 01_xxx --plataforma youtube --views 5400

:: relatório + pesos para as próximas rodadas
python -m divulgacao registro relatorio
```

Gera `resultados.csv`, `relatorio_resultados.md` e `cache\prioridades.json` —
este último é lido pelo Módulo 1, que passa a dar mais peso às hashtags e grupos
que trouxeram resultado (mínimo de `registro.min_amostras` amostras, padrão 2).

### Um comando só

```bat
python -m divulgacao tudo
```

Roda hashtags dos cortes novos → buscas e textos de grupos → plano → relatório.

---

## Como ligar e desligar

### Cada módulo

| Onde | O quê | Padrão |
|---|---|---|
| `divulgacao\config.yaml` → `modulos.hashtags / grupos / registro` | liga/desliga o módulo | `true` |
| `.env` → `DIVULGACAO_MODULO_HASHTAGS=off` | idem, por variável | ligado |
| `config.yaml` → `hashtags.youtube.ativo` / `tiktok.ativo` / `ia.modo` | desliga fontes dentro do Módulo 1 | `true/true/auto` |

Desligar o módulo não apaga nada: o CLI só avisa e sai com código 1.

### Ponto de integração com `cortes.py` (desligado por padrão)

Hoje a integração está **off**: `ativo: false` em `divulgacao\config.yaml`
(`DIVULGACAO_ATIVO=on` no `.env` liga sem editar arquivo). Para passar a rodar
sozinho depois de cada render, são 2 passos:

1. `divulgacao\config.yaml` → `ativo: true`
2. em `cortes.py`, logo **depois** da linha

   ```python
   render.write_sidecar(info["path"], clip)
   ```

   acrescente **uma linha**:

   ```python
   from divulgacao.integracao import apos_exportacao; apos_exportacao(clip)
   ```

Enquanto `ativo: false`, `apos_exportacao()` devolve `None` na hora, sem ler
arquivo e sem custo de API. A chamada é protegida por `try/except`: uma falha de
divulgação **nunca** derruba a renderização. Nenhum arquivo existente foi
modificado nesta entrega.

---

## Teste de ponta a ponta

```bat
divulgacao\rodar_teste.cmd
:: ou
python -m divulgacao.teste.teste_ponta_a_ponta
```

Cria um corte de exemplo (transcrição + sidecar) e valida os três módulos:
mix de 3 a 5 hashtags com 1 ampla/2 nicho/1 específica, tags do YouTube dentro de
500 caracteres, 1 texto por grupo sem repetição, teto de 2 por dia, cooldown de
7 dias, CSV e relatório. Roda **sem rede e sem chave** (IA e YouTube desligados)
e sai em `%TEMP%\divulgacao_teste` — nenhum arquivo real é tocado. Foram 54
checagens na última execução.

---

## Arquivos criados

```
divulgacao\
├── config.yaml              flags e limites
├── .env.example             chaves/variáveis opcionais
├── README.md                este arquivo
├── requirements.txt         pyyaml + requests (pytrends opcional)
├── grupos.csv               os seus grupos (criado com --buscas)
├── grupos.exemplo.csv       modelo pronto para copiar
├── tiktok_trending.txt      hashtags em alta (você cola)
├── buscas_grupos.md         buscas sugeridas por nicho
├── plano_divulgacao.md      plano diário com texto pronto para copiar
├── resultados.csv           histórico: corte, hashtags, plataforma, grupo, data, views, curtidas
├── relatorio_resultados.md  o que trouxe resultado
├── saida\<corte>\metadata.json   saída do Módulo 1
├── cache\                   cache do YouTube, cota e prioridades.json
├── estado\grupos_estado.json     textos, hashes e agenda dos grupos
├── logs\
├── hashtags.py  grupos.py  registro.py  integracao.py  cli.py  llm.py  config.py
└── teste\teste_ponta_a_ponta.py + rodar_teste.cmd
```

---

## Limites conhecidos

- **Cota do YouTube:** `search.list` custa 100 unidades por chamada; o padrão do
  módulo é 9000/dia (o projeto inteiro tem 10000). O cache de 7 dias evita gastar
  de novo no mesmo nicho.
- **`pytrends`** não é oficial e pode parar de funcionar; por isso vem desligado.
- **Autocomplete** usa o endpoint público de sugestões (sem cota, sem garantia):
  se falhar, o módulo segue normalmente.
- **Sem chave de IA** tudo funciona: hashtags caem no fallback pelo nicho, e os
  textos de grupo saem de templates — só ficam menos afiados.
