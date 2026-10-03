---
name: clip-picker
description: Encontra os melhores trechos de um video longo para virar cortes (shorts, reels, tiktoks) - gera candidatos pela transcricao e pelo audio, pontua, escolhe limites perfeitos de inicio e fim e grava os clipes no edit_plan. Use SEMPRE que o usuario pedir "cortes", "melhores momentos", "highlights", "clips", "transforma esse podcast/live/gameplay em shorts" ou quando houver video com mais de 3 minutos para encurtar.
---

# clip-picker

Pre-requisito: `work/transcript.words.json` (skill `transcribe-and-cut`) e `edit_plan.json` (skill `video-router`).

## Regra de ouro dos tempos
**Nunca peca ao LLM timestamps de cabeca** (eles escorregam alguns segundos). O fluxo correto:
1. O LLM escolhe o trecho citando **a frase inicial exata e a frase final exata** da transcricao.
2. O codigo localiza essas frases em `transcript.words.json` e le `start`/`end` reais das palavras.
3. Refine o inicio e o fim para fronteiras naturais: comece no inicio de uma frase (ou pouco antes, ~0.15 s) e termine no fim de uma ideia + ~0.3 s de respiro.

## Como gerar candidatos

**Passo A - blocos de assunto.** Divida a transcricao em blocos por mudanca de tema (pausas longas, perguntas novas, mudanca de falante). Cada bloco e uma area de busca.

**Passo B - sinais.** Procure, por bloco:
- Historia completa (situacao -> conflito -> desfecho).
- Opiniao forte, polemica saudavel, "a verdade e que...".
- Dado/numero surpreendente e explicacao curta.
- Emocao: risada, raiva, surpresa (picos de energia do audio: use `ffmpeg ... ebur128` ou calcule RMS por janela de 1 s).
- Conselho acionavel ("faca X em vez de Y").
- Gameplay/live: pico de volume da voz + evento de jogo + reacao.

**Passo C - descartes.** Rejeite trechos que: dependem de contexto anterior, terminam no meio do raciocinio, tem muito silencio/enrolacao, repetem outro clipe, ou tratam de assunto que o proprio falante pede para nao divulgar.

## Pontuacao (0-100)
| Criterio | Peso |
|---|---|
| Gancho natural nos primeiros segundos (`hook-engine` refina) | 25 |
| Autocontido (entende sem o resto) | 20 |
| Payoff/desfecho claro | 20 |
| Emocao ou novidade | 15 |
| Ritmo (pouca enrolacao) | 10 |
| Potencial de comentario/compartilhamento | 10 |

Descarte tudo abaixo de 60. Seja honesto: se so existirem 2 bons cortes, entregue 2.

## Duracao
- Padrao 20-60 s; ideal entre 25 e 45 s para a maioria dos temas. Respeite `target.max_duration` do plano (e confira os limites atuais das plataformas).
- Prefira cortar por baixo: um clipe de 30 s forte vale mais que 55 s com meio vazio.
- Se uma historia boa precisa de 90 s, avise o usuario e proponha parte 1/parte 2 em vez de espremer.

## Diversidade
- Sem sobreposicao entre clipes (ou, se houver, avise).
- Espalhe pelo video; nao pegue 6 clipes do mesmo bloco de 5 minutos.

## Saida
Para cada clipe escolhido preencha em `edit_plan.json`: `id`, `start`, `end`, `title_internal`, `score`, `why`. Mostre ao usuario uma tabela curta (id, tempo, score, motivo) e siga para as proximas skills, a menos que ele queira aprovar antes.
